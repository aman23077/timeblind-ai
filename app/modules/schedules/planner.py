from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.schedules.models import TimeBlock
from app.modules.tasks.models import Task, TaskDependency
from app.modules.events.models import Event, EventPrepItem
from app.modules.sessions.models import SessionRecord
from app.modules.users.models import User


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
    ordered_task_ids: list[str] | None = None,
) -> tuple[list[TimeBlock], list[dict[str, str | int]]]:
    current_start = _normalize_datetime(start_at)
    planning_start = current_start
    normalized_end = _normalize_datetime(window_end)
    remaining_tasks = sorted(tasks, key=task_sort_key)
    if ordered_task_ids is not None:
        rank = {task_id: i for i, task_id in enumerate(ordered_task_ids)}
        remaining_tasks.sort(key=lambda task: rank.get(task.id, len(rank)))
    requirements = dependency_requirements(db, user_id, tasks)
    completed_ids = set(db.scalars(select(Task.id).where(
        Task.user_id == user_id, Task.status == "completed"
    )).all())
    busy = event_windows(db, user_id, current_start, normalized_end)
    blocks: list[TimeBlock] = []
    unscheduled: list[dict[str, str | int]] = []
    focused_since_break = 0

    while remaining_tasks and current_start < normalized_end:
        overlapping = next((end for start, end in busy if start <= current_start < end), None)
        if overlapping:
            current_start = overlapping
            continue
        free_end = min([start for start, _ in busy if start > current_start] + [normalized_end])
        available_minutes = duration_minutes(current_start, free_end)
        fitting_tasks = []
        risk_profiles: dict[str, tuple[str, int, str]] = {}
        for task in remaining_tasks:
            if not requirements.get(task.id, set()).issubset(completed_ids):
                continue
            risk_level, risk_buffer_minutes, risk_reason = task_risk_profile(db, user_id, task)
            effective_minutes = max(15, task.estimated_minutes or 30) + risk_buffer_minutes
            deadline = _normalize_datetime(task.deadline_at) if task.deadline_at else normalized_end
            if effective_minutes <= available_minutes and current_start + timedelta(minutes=effective_minutes) <= deadline:
                fitting_tasks.append(task)
                risk_profiles[task.id] = (risk_level, risk_buffer_minutes, risk_reason)

        if not fitting_tasks:
            if free_end < normalized_end:
                current_start = free_end
                continue
            break

        task = fitting_tasks[0]
        remaining_tasks.remove(task)
        estimated_minutes = max(15, task.estimated_minutes or 30)
        risk_level, risk_buffer_minutes, risk_reason = risk_profiles[task.id]
        effective_minutes = estimated_minutes + risk_buffer_minutes

        should_insert_break = (
            break_minutes > 0
            and focused_since_break >= 50
            and duration_minutes(current_start + timedelta(minutes=break_minutes), free_end) >= effective_minutes
            and (task.deadline_at is None or current_start + timedelta(minutes=break_minutes + effective_minutes) <= _normalize_datetime(task.deadline_at))
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
        completed_ids.add(task.id)
        focused_since_break += effective_minutes

    for task in remaining_tasks:
        unscheduled.append(
            {
                "task_id": task.id,
                "title": task.title,
                "estimated_minutes": max(15, task.estimated_minutes or 30),
                "reason": deferral_reason(db, user_id, task, planning_start, normalized_end,
                                          busy, blocks, requirements, completed_ids),
            }
        )

    return blocks, unscheduled


def deferral_reason(db: Session, user_id: str, task: Task, start_at: datetime, end_at: datetime,
                    busy: list[tuple[datetime, datetime]], blocks: list[TimeBlock],
                    requirements: dict[str, set[str]], completed_ids: set[str]) -> str:
    """Explain the final plan using its actual free time and hard constraints."""
    deadline = _normalize_datetime(task.deadline_at) if task.deadline_at else end_at
    if deadline <= start_at:
        return ("The deadline is before this planning window. Update or remove the deadline "
                "if you still want to do this task, then generate again.")
    prerequisites = requirements.get(task.id, set())
    if not prerequisites.issubset(completed_ids):
        return ("A prerequisite task is unfinished or could not be scheduled. "
                "Complete or schedule the prerequisite first.")
    earliest_start = max([start_at] + [block.end_at for block in blocks if block.task_id in prerequisites])
    cutoff = min(end_at, deadline)
    _, buffer, _ = task_risk_profile(db, user_id, task)
    required = max(15, task.estimated_minutes or 30) + buffer
    reservations = sorted(busy + [(block.start_at, block.end_at) for block in blocks])
    cursor = earliest_start
    gaps = []
    for left, right in reservations:
        if right <= cursor or left >= cutoff:
            continue
        if left > cursor:
            gaps.append(duration_minutes(cursor, min(left, cutoff)))
        cursor = max(cursor, right)
    if cursor < cutoff:
        gaps.append(duration_minutes(cursor, cutoff))
    total, largest = sum(gaps), max(gaps, default=0)
    need = f"Needs {required} uninterrupted minutes, including a {buffer}-minute protective buffer."
    if largest < required and total >= required:
        return (f"{need} There are {total} free minutes, but the longest gap is {largest} minutes. "
                "This planner does not split tasks across gaps. Split it into smaller tasks or choose a longer uninterrupted window.")
    if total < required:
        limit = "before its deadline" if deadline < end_at else "in this planning window"
        return (f"{need} Only {total} minutes remain free {limit}. "
                "Choose more available hours, revise the deadline if appropriate, or split it into smaller tasks.")
    return (f"{need} The current task order did not place it in the remaining gaps. "
            "Try another planning window or break the task into smaller tasks.")


def dependency_requirements(db: Session, user_id: str, tasks: list[Task]) -> dict[str, set[str]]:
    ids = [task.id for task in tasks]
    if not ids:
        return {}
    result: dict[str, set[str]] = {}
    for dependency in db.scalars(select(TaskDependency).where(TaskDependency.task_id.in_(ids))).all():
        # A foreign or missing prerequisite cannot authorize scheduling the dependent task.
        result.setdefault(dependency.task_id, set()).add(dependency.depends_on_task_id)
    return result


def event_windows(db: Session, user_id: str, start_at: datetime, end_at: datetime) -> list[tuple[datetime, datetime]]:
    events = db.scalars(select(Event).where(Event.user_id == user_id, Event.start_at < end_at)).all()
    user = db.get(User, user_id)
    zone = ZoneInfo(user.time_zone) if user else timezone.utc
    windows = []
    for event in events:
        if event.end_at is None and _normalize_datetime(event.start_at).astimezone(zone).date() < start_at.astimezone(zone).date():
            continue
        prep = db.scalars(select(EventPrepItem).where(EventPrepItem.event_id == event.id)).all()
        reserved_start = _normalize_datetime(event.start_at) - timedelta(minutes=(
            event.commute_minutes + event.get_ready_minutes + event.departure_buffer_minutes + sum(item.minutes for item in prep)
        ))
        # No event end supplied: reserve the rest of this planning window conservatively.
        reserved_end = _normalize_datetime(event.end_at) if event.end_at else end_at
        if reserved_end > start_at and reserved_start < end_at:
            windows.append((max(start_at, reserved_start), min(end_at, reserved_end)))
    merged: list[tuple[datetime, datetime]] = []
    for start, end in sorted(windows):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


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
