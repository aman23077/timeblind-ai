from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.database import get_db, save_and_refresh
from app.core.http import not_found
from app.modules.schedules.models import Schedule, TimeBlock
from app.modules.schedules.planner import build_schedule_blocks
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


router = APIRouter()


@router.post("", response_model=ScheduleRead)
def create_schedule(payload: ScheduleCreate, db: Session = Depends(get_db)) -> ScheduleRead:
    schedule = Schedule(**payload.model_dump())
    schedule = save_and_refresh(db, schedule)
    return ScheduleRead.model_validate(schedule)


@router.get("", response_model=list[ScheduleRead])
def list_schedules(
    user_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[ScheduleRead]:
    query = select(Schedule).order_by(Schedule.plan_date.asc())
    if user_id:
        query = query.where(Schedule.user_id == user_id)
    schedules = db.scalars(query).all()
    return [ScheduleRead.model_validate(schedule) for schedule in schedules]


@router.post("/generate", response_model=ScheduleGenerationResponse)
def generate_schedule(payload: ScheduleGenerateRequest, db: Session = Depends(get_db)) -> ScheduleGenerationResponse:
    schedule = db.scalar(
        select(Schedule).where(Schedule.user_id == payload.user_id, Schedule.plan_date == payload.plan_date)
    )
    if schedule is None:
        schedule = Schedule(
            user_id=payload.user_id,
            plan_date=payload.plan_date,
            status="draft",
            generated_by="timeblind_scheduler",
        )
        schedule = save_and_refresh(db, schedule)
    else:
        schedule.generated_by = "timeblind_scheduler"
        schedule.status = "draft"
        schedule = save_and_refresh(db, schedule)

    db.execute(delete(TimeBlock).where(TimeBlock.schedule_id == schedule.id))
    db.commit()

    tasks = db.scalars(
        select(Task).where(Task.user_id == payload.user_id, Task.status != "completed").order_by(Task.created_at.asc())
    ).all()
    window_end = _combine_local(payload.plan_date, payload.window_end)
    blocks, unscheduled_raw = build_schedule_blocks(
        db=db,
        schedule_id=schedule.id,
        user_id=payload.user_id,
        tasks=tasks,
        start_at=_combine_local(payload.plan_date, payload.window_start),
        window_end=window_end,
        break_minutes=payload.break_minutes,
    )

    persisted_blocks = [save_and_refresh(db, block) for block in blocks]
    unscheduled = [UnscheduledTask(**item) for item in unscheduled_raw]

    return ScheduleGenerationResponse.model_validate(
        {
            **schedule.__dict__,
            "time_blocks": persisted_blocks,
            "unscheduled_tasks": unscheduled,
        }
    )


@router.get("/{schedule_id}", response_model=ScheduleDetail)
def get_schedule(schedule_id: str, db: Session = Depends(get_db)) -> ScheduleDetail:
    schedule = db.get(Schedule, schedule_id)
    if schedule is None:
        raise not_found("Schedule", schedule_id)
    _mark_missed_blocks(db, schedule.user_id)
    blocks = db.scalars(
        select(TimeBlock).where(TimeBlock.schedule_id == schedule_id).order_by(TimeBlock.start_at.asc())
    ).all()
    return ScheduleDetail.model_validate({**schedule.__dict__, "time_blocks": blocks})


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
    _mark_missed_blocks(db, payload.user_id)
    block = db.get(TimeBlock, time_block_id)
    if block is None:
        raise not_found("TimeBlock", time_block_id)

    started_at = payload.started_at or datetime.now(timezone.utc)
    normalized_start = _normalize_datetime(started_at)
    scheduled_start = _normalize_datetime(block.start_at)
    delay_minutes = max(0, round((normalized_start - scheduled_start).total_seconds() / 60))

    block.status = "active"
    block.actual_start = normalized_start
    block.delay_minutes = delay_minutes
    block.planned_duration_minutes = block.planned_duration_minutes or _duration_minutes(block.start_at, block.end_at)
    block = save_and_refresh(db, block)

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

    resumed_from = _normalize_datetime(payload.resumed_from or datetime.now(timezone.utc))
    all_blocks = db.scalars(
        select(TimeBlock).where(TimeBlock.schedule_id == schedule.id).order_by(TimeBlock.start_at.asc())
    ).all()
    planned_future_blocks = [
        block
        for block in all_blocks
        if block.status == "planned" and _normalize_datetime(block.start_at) >= _normalize_datetime(current_block.end_at)
    ]
    latest_window_end = max(_normalize_datetime(block.end_at) for block in all_blocks)

    for block in planned_future_blocks:
        db.delete(block)
    db.commit()

    occupied_task_ids = {
        block.task_id
        for block in all_blocks
        if block.kind == "task"
        and block.task_id
        and (block.id == current_block.id or block.status in {"active", "completed", "missed"})
    }
    task_query = select(Task).where(Task.user_id == payload.user_id, Task.status != "completed")
    if occupied_task_ids:
        task_query = task_query.where(Task.id.not_in(occupied_task_ids))
    tasks = db.scalars(task_query.order_by(Task.created_at.asc())).all()

    if not tasks:
        refreshed_blocks = db.scalars(
            select(TimeBlock).where(TimeBlock.schedule_id == schedule.id).order_by(TimeBlock.start_at.asc())
        ).all()
        return ScheduleRecoveryResponse(
            schedule=ScheduleDetail.model_validate({**schedule.__dict__, "time_blocks": refreshed_blocks}),
            next_time_block=None,
            suggested_break_minutes=0,
            message="Nice work. That wraps this window, and there are no other pending tasks ready to pull in right now.",
            rescheduled=False,
            deferred_tasks=[],
        )

    start_after_break = resumed_from
    suggested_break_minutes = payload.suggested_break_minutes if tasks else 0
    if tasks and suggested_break_minutes > 0:
        break_block = TimeBlock(
            schedule_id=schedule.id,
            user_id=payload.user_id,
            title="Catch your breath",
            kind="break",
            start_at=resumed_from,
            end_at=resumed_from + _minutes_delta(suggested_break_minutes),
            planned_duration_minutes=suggested_break_minutes,
            risk_level="low",
            risk_buffer_minutes=0,
            risk_reason="Short recovery space after the schedule shifted.",
            status="planned",
        )
        save_and_refresh(db, break_block)
        start_after_break = break_block.end_at

    rebuilt_blocks, deferred_raw = build_schedule_blocks(
        db=db,
        schedule_id=schedule.id,
        user_id=payload.user_id,
        tasks=tasks,
        start_at=start_after_break,
        window_end=latest_window_end,
        break_minutes=payload.suggested_break_minutes,
    )
    persisted_blocks = [save_and_refresh(db, block) for block in rebuilt_blocks]
    refreshed_blocks = db.scalars(
        select(TimeBlock).where(TimeBlock.schedule_id == schedule.id).order_by(TimeBlock.start_at.asc())
    ).all()
    next_time_block = next((block for block in persisted_blocks if block.kind == "task" and block.task_id), None)
    deferred_tasks = [UnscheduledTask(**item) for item in deferred_raw]

    return ScheduleRecoveryResponse(
        schedule=ScheduleDetail.model_validate({**schedule.__dict__, "time_blocks": refreshed_blocks}),
        next_time_block=TimeBlockRead.model_validate(next_time_block) if next_time_block else None,
        suggested_break_minutes=suggested_break_minutes,
        message="No worries. The rest of the plan was adjusted so you can keep moving without having to recalculate it yourself.",
        rescheduled=True,
        deferred_tasks=deferred_tasks,
    )


def _combine_local(plan_date, plan_time):
    return datetime.combine(plan_date, plan_time).replace(tzinfo=timezone.utc)


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
