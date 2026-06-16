from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.schedules.models import TimeBlock
from app.modules.tasks.models import Task
from app.modules.sessions.models import SessionRecord


LEAKAGE_SIGNALS = {
    "Interrupted",
    "Lost focus",
    "Took a break",
    "Needed to switch context",
    "Environment distraction",
}


def build_schedule_blocks(
    db: Session,
    schedule_id: str,
    user_id: str,
    tasks: list[Task],
    start_at: datetime,
    window_end: datetime,
    break_minutes: int,
) -> tuple[list[TimeBlock], list[dict[str, str | int]]]:
    current_start = _normalize_datetime(start_at)
    normalized_end = _normalize_datetime(window_end)
    remaining_tasks = sorted(tasks, key=task_sort_key)
    blocks: list[TimeBlock] = []
    unscheduled: list[dict[str, str | int]] = []
    focused_since_break = 0
    breaks_used = 0

    while remaining_tasks and current_start < normalized_end:
        available_minutes = duration_minutes(current_start, normalized_end)
        fitting_tasks = []
        risk_profiles: dict[str, tuple[str, int, str]] = {}
        for task in remaining_tasks:
            risk_level, risk_buffer_minutes, risk_reason = task_risk_profile(db, user_id, task)
            effective_minutes = max(15, task.estimated_minutes or 30) + risk_buffer_minutes
            if effective_minutes <= available_minutes:
                fitting_tasks.append(task)
                risk_profiles[task.id] = (risk_level, risk_buffer_minutes, risk_reason)

        if not fitting_tasks:
            break

        task = min(fitting_tasks, key=task_sort_key)
        remaining_tasks.remove(task)
        estimated_minutes = max(15, task.estimated_minutes or 30)
        risk_level, risk_buffer_minutes, risk_reason = risk_profiles[task.id]
        effective_minutes = estimated_minutes + risk_buffer_minutes

        should_insert_break = (
            break_minutes > 0
            and breaks_used < 2
            and focused_since_break >= 170
            and duration_minutes(current_start + timedelta(minutes=break_minutes), normalized_end) >= effective_minutes
        )
        if should_insert_break:
            break_end = current_start + timedelta(minutes=break_minutes)
            blocks.append(
                TimeBlock(
                    schedule_id=schedule_id,
                    user_id=user_id,
                    title="Reset break",
                    kind="break",
                    start_at=current_start,
                    end_at=break_end,
                    planned_duration_minutes=break_minutes,
                    risk_level="low",
                    risk_buffer_minutes=0,
                    risk_reason="Short recovery space before the next block.",
                    buffer_before_minutes=0,
                    buffer_after_minutes=0,
                    status="planned",
                )
            )
            current_start = break_end
            focused_since_break = 0
            breaks_used += 1

        task_end = current_start + timedelta(minutes=effective_minutes)
        if task_end > normalized_end:
            unscheduled.append(
                {
                    "task_id": task.id,
                    "title": task.title,
                    "estimated_minutes": estimated_minutes,
                    "reason": "Not enough room in the selected time window after prioritizing urgent, shorter, and lower-risk tasks.",
                }
            )
            continue

        blocks.append(
            TimeBlock(
                schedule_id=schedule_id,
                user_id=user_id,
                task_id=task.id,
                title=task.title,
                kind="task",
                start_at=current_start,
                end_at=task_end,
                planned_duration_minutes=estimated_minutes,
                risk_level=risk_level,
                risk_buffer_minutes=risk_buffer_minutes,
                risk_reason=risk_reason,
                buffer_before_minutes=0,
                buffer_after_minutes=0,
                status="planned",
            )
        )
        current_start = task_end
        focused_since_break += effective_minutes

    for task in remaining_tasks:
        unscheduled.append(
            {
                "task_id": task.id,
                "title": task.title,
                "estimated_minutes": max(15, task.estimated_minutes or 30),
                "reason": "Not enough room in the selected time window after prioritizing urgent, shorter, and lower-risk tasks.",
            }
        )

    return blocks, unscheduled


def task_sort_key(task: Task):
    deadline_rank = deadline_rank_for(task.deadline_at)
    deadline_value = deadline_timestamp(task.deadline_at)
    priority_rank = priority_rank_for(task.priority)
    estimated_value = task.estimated_minutes or 30
    created_value = _normalize_datetime(task.created_at).timestamp()
    return (deadline_rank, priority_rank, estimated_value, deadline_value, created_value)


def task_risk_profile(db: Session, user_id: str, task: Task) -> tuple[str, int, str]:
    historical_tasks = db.scalars(
        select(Task).where(
            Task.user_id == user_id,
            Task.id != task.id,
            Task.task_type == task.task_type,
            Task.status == "completed",
            Task.estimated_minutes.is_not(None),
            Task.actual_minutes.is_not(None),
        )
    ).all()

    task_ids = [item.id for item in historical_tasks]
    sessions = (
        db.scalars(
            select(SessionRecord).where(
                SessionRecord.task_id.in_(task_ids),
                SessionRecord.status == "completed",
            )
        ).all()
        if task_ids
        else []
    )

    avg_delay = rounded_average([session.delay_minutes for session in sessions if session.time_block_id])
    avg_overrun = rounded_average([session.overrun_minutes for session in sessions if session.time_block_id])
    leakage_reasons = [
        reason.strip()
        for session in sessions
        for reason in session.feedback_reasons.split(",")
        if reason.strip() in LEAKAGE_SIGNALS
    ]
    drift_count = len(leakage_reasons)

    buffer = 0
    if task.difficulty == "hard":
        buffer += 10
    elif task.difficulty == "medium":
        buffer += 5

    if avg_delay >= 10:
        buffer += 10
    elif avg_delay >= 5:
        buffer += 5

    if avg_overrun >= 10:
        buffer += 15
    elif avg_overrun >= 5:
        buffer += 8

    if drift_count >= 4:
        buffer += 10
    elif drift_count >= 2:
        buffer += 5

    buffer = min(30, buffer)

    if buffer >= 20:
        level = "high"
    elif buffer >= 10:
        level = "medium"
    else:
        level = "low"

    if leakage_reasons:
        top_reason = max(set(leakage_reasons), key=leakage_reasons.count)
        reason = f"Based on past {task.task_type} work, '{top_reason}' often shows up and this task may need extra room."
    elif avg_overrun >= 5 or avg_delay >= 5:
        reason = f"Past {task.task_type} blocks tend to drift, so this task gets a protective buffer."
    elif task.difficulty == "hard":
        reason = "Hard tasks get a protective buffer even with limited history."
    else:
        reason = "This task looks relatively stable, so only a light buffer is applied."

    return level, buffer, reason


def duration_minutes(start_at: datetime, end_at: datetime) -> int:
    return max(0, round((_normalize_datetime(end_at) - _normalize_datetime(start_at)).total_seconds() / 60))


def deadline_rank_for(deadline_at):
    if deadline_at is None:
        return 2

    normalized_deadline = _normalize_datetime(deadline_at)
    remaining_minutes = (normalized_deadline - datetime.now(timezone.utc)).total_seconds() / 60
    if remaining_minutes <= 180:
        return 0
    if remaining_minutes <= 24 * 60:
        return 1
    return 2


def deadline_timestamp(deadline_at):
    if deadline_at is None:
        return float("inf")
    return _normalize_datetime(deadline_at).timestamp()


def priority_rank_for(priority: str | None):
    if priority == "high":
        return 0
    if priority == "medium":
        return 1
    return 2


def rounded_average(values: list[int]) -> int:
    if not values:
        return 0
    return int(round(sum(values) / len(values)))


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
