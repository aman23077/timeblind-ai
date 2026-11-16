from app.core.auth import get_current_user
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.database import get_db, save_and_refresh, new_id
from app.core.http import not_found
from app.modules.schedules.models import AdaptivePlan, Schedule, TimeBlock
from app.modules.schedules.planner import build_schedule_blocks, dependency_requirements
from app.modules.reasoning.generative import order_tasks
from app.modules.schedules.schemas import (
    ScheduleGenerateRequest,
    ScheduleGenerationResponse,
    ScheduleRecoveryRequest,
    ScheduleRecoveryResponse,
    ScheduleCreate,
    ScheduleDetail,
    ScheduleRead,
    TimeBlockCreate,
    TimeBlockRead,
    TimeBlockStartRequest,
    TimeBlockStartResponse,
    UnscheduledTask,
)
from app.modules.sessions.models import SessionRecord
from app.modules.tasks.models import Task
from app.modules.users.models import User


router = APIRouter()


@router.post("", response_model=ScheduleRead)
def create_schedule(payload: ScheduleCreate, db: Session = Depends(get_db)) -> ScheduleRead:
    schedule = Schedule(**payload.model_dump())
    schedule = save_and_refresh(db, schedule)
    return ScheduleRead.model_validate(schedule)


@router.get("", response_model=list[ScheduleRead])
def list_schedules(
    user: User = Depends(get_current_user),
    user_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[ScheduleRead]:
    query = select(Schedule).where(Schedule.user_id == user.id).order_by(Schedule.plan_date.asc())
    if user_id:
        query = query.where(Schedule.user_id == user_id)
    schedules = db.scalars(query).all()
    return [ScheduleRead.model_validate(schedule) for schedule in schedules]


@router.post("/generate", response_model=ScheduleGenerationResponse)
def generate_schedule(payload: ScheduleGenerateRequest, db: Session = Depends(get_db)) -> ScheduleGenerationResponse:
    user = db.get(User, payload.user_id)
    if user is None:
        raise not_found("User", payload.user_id)
    try:
        local_zone = ZoneInfo(user.time_zone)
    except ZoneInfoNotFoundError:
        raise HTTPException(422, "User timezone must be a valid IANA timezone") from None
    start_at = datetime.combine(payload.plan_date, payload.window_start, local_zone).astimezone(timezone.utc)
    window_end = datetime.combine(payload.plan_date, payload.window_end, local_zone).astimezone(timezone.utc)
    schedule = db.scalar(
        select(Schedule).where(Schedule.user_id == payload.user_id, Schedule.plan_date == payload.plan_date)
    )
    if schedule and db.scalar(select(TimeBlock.id).where(
        TimeBlock.schedule_id == schedule.id, TimeBlock.status.in_(["active", "completed"])
    ).limit(1)):
        raise HTTPException(409, "This schedule has started. Use recovery to adjust the remaining blocks.")
    if schedule is None:
        schedule = Schedule(
            id=new_id(),
            user_id=payload.user_id,
            plan_date=payload.plan_date,
            status="draft",
            generated_by="timeblind_scheduler",
        )

    tasks = db.scalars(
        select(Task).where(Task.user_id == payload.user_id, Task.status.in_(["pending", "in_progress"])).order_by(Task.created_at.asc())
    ).all()
    requirements = dependency_requirements(db, payload.user_id, tasks)
    order, metadata = order_tasks(tasks, start_at, window_end, [
        {"task_id": task_id, "depends_on_task_id": prerequisite}
        for task_id, prerequisites in requirements.items() for prerequisite in sorted(prerequisites)
    ])
    blocks, unscheduled_raw = build_schedule_blocks(
        db=db,
        schedule_id=schedule.id,
        user_id=payload.user_id,
        tasks=tasks,
        start_at=start_at,
        window_end=window_end,
        break_minutes=payload.break_minutes,
        ordered_task_ids=order,
    )
    runtime = db.scalar(select(AdaptivePlan).where(AdaptivePlan.schedule_id == schedule.id))
    if runtime is None:
        runtime = AdaptivePlan(schedule_id=schedule.id, user_id=payload.user_id)
        db.add(runtime)
    runtime.window_start = start_at
    runtime.window_end = window_end
    runtime.break_minutes = payload.break_minutes
    runtime.deferred_tasks = unscheduled_raw
    runtime.fingerprint = ""
    # Only replace the previous draft after generation and validation have succeeded.
    schedule.generated_by = "llm_validated" if metadata["generation_source"] == "llm" else "timeblind_scheduler"
    schedule.status = "draft"
    db.execute(delete(TimeBlock).where(TimeBlock.schedule_id == schedule.id))
    db.add(schedule)
    db.add_all(blocks)
    db.commit()
    db.refresh(schedule)
    persisted_blocks = blocks
    unscheduled = [UnscheduledTask(**item) for item in unscheduled_raw]

    return ScheduleGenerationResponse.model_validate(
        {
            **schedule.__dict__,
            "time_blocks": persisted_blocks,
            "unscheduled_tasks": unscheduled,
            **metadata,
        }
    )


@router.get("/{schedule_id}", response_model=ScheduleGenerationResponse)
def get_schedule(schedule_id: str, db: Session = Depends(get_db)) -> ScheduleDetail:
    schedule = db.get(Schedule, schedule_id)
    if schedule is None:
        raise not_found("Schedule", schedule_id)
    from app.modules.interventions.policy import plan_response
    return plan_response(db, schedule)



@router.get("/time-blocks/{time_block_id}", response_model=TimeBlockRead)
def get_time_block(time_block_id: str, db: Session = Depends(get_db)) -> TimeBlockRead:
    block = db.get(TimeBlock, time_block_id)
    if block is None:
        raise not_found("TimeBlock", time_block_id)
    _mark_missed_blocks(db, block.user_id)
    db.refresh(block)
    return TimeBlockRead.model_validate(block)


@router.post("/{schedule_id}/time-blocks", response_model=TimeBlockRead)
def create_time_block(
    schedule_id: str,
    payload: TimeBlockCreate,
    db: Session = Depends(get_db),
) -> TimeBlockRead:
    schedule = db.get(Schedule, schedule_id)
    if schedule is None:
        raise not_found("Schedule", schedule_id)
    planned_duration = payload.planned_duration_minutes or _duration_minutes(payload.start_at, payload.end_at)
    block = TimeBlock(
        schedule_id=schedule_id,
        **payload.model_dump(exclude={"planned_duration_minutes"}),
        planned_duration_minutes=planned_duration,
    )
    block = save_and_refresh(db, block)
    return TimeBlockRead.model_validate(block)


@router.post("/time-blocks/{time_block_id}/start", response_model=TimeBlockStartResponse)
def start_time_block_session(
    time_block_id: str,
    payload: TimeBlockStartRequest,
    db: Session = Depends(get_db),
) -> TimeBlockStartResponse:
    block = db.get(TimeBlock, time_block_id)
    if block is None:
        raise not_found("TimeBlock", time_block_id)

    db.execute(update(AdaptivePlan).where(AdaptivePlan.schedule_id == block.schedule_id)
               .values(updated_at=datetime.now(timezone.utc)))
    db.refresh(block)

    if block.status in {"completed", "superseded", "cancelled"}:
        raise HTTPException(409, "This block is no longer available. Refresh the schedule.")
    existing = db.scalar(select(SessionRecord).where(SessionRecord.time_block_id == block.id,
                         SessionRecord.status == "active", SessionRecord.ended_at.is_(None)))
    if existing is not None:
        db.commit()
        return TimeBlockStartResponse.model_validate({"time_block": block, "session": existing})

    started_at = payload.started_at or datetime.now(timezone.utc)
    normalized_start = _normalize_datetime(started_at)
    scheduled_start = _normalize_datetime(block.start_at)
    delay_minutes = max(0, round((normalized_start - scheduled_start).total_seconds() / 60))

    block.status = "active"
    block.actual_start = normalized_start
    block.delay_minutes = delay_minutes
    block.planned_duration_minutes = block.planned_duration_minutes or _duration_minutes(block.start_at, block.end_at)
    db.add(block)

    session_record = SessionRecord(
        user_id=payload.user_id,
        task_id=block.task_id,
        time_block_id=block.id,
        started_at=normalized_start,
        actual_start=normalized_start,
        delay_minutes=delay_minutes,
        status="active",
    )
    session_record = save_and_refresh(db, session_record)

    return TimeBlockStartResponse.model_validate({"time_block": block, "session": session_record})


@router.post("/time-blocks/{time_block_id}/recover", response_model=ScheduleRecoveryResponse)
def recover_schedule_after_block(
    time_block_id: str,
    payload: ScheduleRecoveryRequest,
    db: Session = Depends(get_db),
) -> ScheduleRecoveryResponse:
    current_block = db.get(TimeBlock, time_block_id)
    if current_block is None:
        raise not_found("TimeBlock", time_block_id)

    schedule = db.get(Schedule, current_block.schedule_id)
    if schedule is None:
        raise not_found("Schedule", current_block.schedule_id)

    from app.modules.interventions.policy import ensure_plan, replan, plan_response
    blocks = db.scalars(select(TimeBlock).where(TimeBlock.schedule_id == schedule.id)).all()
    runtime = ensure_plan(db, schedule, blocks)
    if runtime is None:
        raise HTTPException(409, "Generate a schedule before recovering it")
    now = _normalize_datetime(payload.resumed_from or datetime.now(timezone.utc))
    replan(db, runtime, now, force=True)
    db.commit()
    response = plan_response(db, schedule)
    next_block = next((block for block in response.time_blocks if block.kind == "task"
                       and block.status == "planned" and _normalize_datetime(block.start_at) >= now), None)
    return ScheduleRecoveryResponse(schedule=response, next_time_block=next_block,
        suggested_break_minutes=0, message=runtime.reason, rescheduled=True,
        deferred_tasks=response.unscheduled_tasks)



def _minutes_delta(minutes: int):
    from datetime import timedelta

    return timedelta(minutes=minutes)


def _mark_missed_blocks(db: Session, user_id: str) -> None:
    now = datetime.now(timezone.utc)
    blocks = db.scalars(
        select(TimeBlock).where(
            TimeBlock.user_id == user_id,
            TimeBlock.status == "planned",
            TimeBlock.end_at < now,
        )
    ).all()
    if not blocks:
        return
    for block in blocks:
        block.status = "missed"
        db.add(block)
    db.commit()


def _normalize_datetime(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

@router.post("/{schedule_id}/replan", response_model=ScheduleGenerationResponse)
def replan_schedule(schedule_id: str, db: Session = Depends(get_db)):
    from app.modules.interventions.policy import ensure_plan, replan, plan_response
    schedule = db.get(Schedule, schedule_id)
    blocks = db.scalars(select(TimeBlock).where(TimeBlock.schedule_id == schedule_id)).all()
    runtime = ensure_plan(db, schedule, blocks)
    if runtime is None:
        raise HTTPException(409, "Generate a schedule first")
    replan(db, runtime, datetime.now(timezone.utc), force=True)
    db.commit()
    return plan_response(db, schedule)
