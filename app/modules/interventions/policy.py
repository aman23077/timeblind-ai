"""Deterministic replanning and activity policies, evaluated at most every 30 seconds."""
import hashlib
import json
import math
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db, utc_now
from app.modules.behaviour.activity import ActivityInterval, ActivityMonitor, aware
from app.modules.interventions.models import Intervention, PolicyState, Reminder
from app.modules.schedules.models import AdaptivePlan, PlanRevision, Schedule, TimeBlock
from app.modules.schedules.planner import build_schedule_blocks, priority_rank_for
from app.modules.schedules.schemas import ScheduleGenerationResponse
from app.modules.sessions.models import RemainingEstimate, SessionRecord
from app.modules.tasks.models import Task
from app.modules.users.models import User

router = APIRouter()


def activity_signal(db, session, now):
    monitor = db.scalar(select(ActivityMonitor).where(ActivityMonitor.session_id == session.id))
    result = {"switches": 0, "idle_seconds": 0, "coverage": 0, "fresh": False}
    if not monitor or not monitor.last_seen_at or not monitor.enabled:
        return result
    result["fresh"] = (now - aware(monitor.last_seen_at)).total_seconds() <= 15
    since = max(aware(session.started_at), now - timedelta(minutes=5))
    rows = db.scalars(select(ActivityInterval).where(
        ActivityInterval.monitor_id == monitor.id, ActivityInterval.ended_at > since
    ).order_by(ActivityInterval.started_at)).all()
    runs = []
    observed = 0
    for row in rows:
        start, end = max(since, aware(row.started_at)), min(now, aware(row.ended_at))
        seconds = max(0, (end - start).total_seconds())
        if seconds == 0:
            continue
        if row.state != "unknown":
            observed += seconds
        key = (row.state, row.app_name)
        if runs and runs[-1]["key"] == key and (start - runs[-1]["end"]).total_seconds() <= 3:
            runs[-1]["seconds"] += seconds
            runs[-1]["end"] = end
        else:
            runs.append({"key": key, "start": start, "end": end, "seconds": seconds})
    previous = None
    for run in runs:
        if run["key"][0] != "active":
            previous = None
            continue
        if run["seconds"] < 6:
            continue
        if previous and (run["start"] - previous["end"]).total_seconds() <= 5 and run["key"] != previous["key"]:
            result["switches"] += 1
        previous = run
    if runs and runs[-1]["key"][0] == "idle" and (now - runs[-1]["end"]).total_seconds() <= 15:
        result["idle_seconds"] = round(runs[-1]["seconds"])
    result["coverage"] = round(min(1, observed / max(1, (now - since).total_seconds())), 2)
    return result


def reserve_active_until(db, session, now):
    task = db.get(Task, session.task_id) if session.task_id else None
    block = db.get(TimeBlock, session.time_block_id) if session.time_block_id else None
    estimate = db.scalar(select(RemainingEstimate).where(RemainingEstimate.session_id == session.id))
    start = aware(estimate.reported_at if estimate else session.actual_start or session.started_at)
    minutes = estimate.remaining_minutes if estimate else (block.planned_duration_minutes if block else None) or (task.estimated_minutes if task else None) or 30
    monitor = db.scalar(select(ActivityMonitor).where(ActivityMonitor.session_id == session.id))
    idle = 0
    if monitor:
        rows = db.scalars(select(ActivityInterval).where(ActivityInterval.monitor_id == monitor.id,
                          ActivityInterval.state == "idle", ActivityInterval.ended_at > start)).all()
        idle = sum(max(0, (min(now, aware(row.ended_at)) - max(start, aware(row.started_at))).total_seconds()) for row in rows)
    # An unfinished session always reserves at least five more minutes.
    return max(now + timedelta(minutes=5), start + timedelta(minutes=minutes, seconds=idle))


def ensure_plan(db, schedule, blocks):
    runtime = db.scalar(select(AdaptivePlan).where(AdaptivePlan.schedule_id == schedule.id))
    if runtime is None and blocks:
        runtime = AdaptivePlan(schedule_id=schedule.id, user_id=schedule.user_id,
                               window_start=min(aware(block.start_at) for block in blocks),
                               window_end=max(aware(block.end_at) for block in blocks), break_minutes=10)
        db.add(runtime)
        db.flush()
    return runtime


def replan(db, runtime, now, switch_burst=False, force=False):
    # Lock the plan before reading blocks, on both SQLite and PostgreSQL.
    db.execute(update(AdaptivePlan).where(AdaptivePlan.id == runtime.id).values(updated_at=now))
    db.refresh(runtime)
    schedule = db.get(Schedule, runtime.schedule_id)
    blocks = db.scalars(select(TimeBlock).where(TimeBlock.schedule_id == schedule.id)).all()
    tasks = db.scalars(select(Task).where(Task.user_id == runtime.user_id,
                                        Task.status.in_(["pending", "in_progress"]))).all()
    sessions = db.scalars(select(SessionRecord).where(SessionRecord.user_id == runtime.user_id,
                            SessionRecord.status == "active", SessionRecord.ended_at.is_(None))).all()
    # Only sessions overlapping this day's window can reserve its future time.
    sessions = [session for session in sessions if aware(session.started_at) < aware(runtime.window_end)
                and aware(session.started_at) >= aware(runtime.window_start) - timedelta(hours=12)]
    active_ids = {session.task_id for session in sessions if session.task_id}
    forecasts = [reserve_active_until(db, session, now) for session in sessions]
    start = max([now, aware(runtime.window_start)] + forecasts)
    pending = [task for task in tasks if task.id not in active_ids]
    current_type = next((task.task_type for task in tasks if task.id in active_ids), None)
    def rank(task):
        deadline = aware(task.deadline_at) if task.deadline_at else aware(runtime.window_end) + timedelta(days=1)
        urgent = (deadline - now).total_seconds() <= 7200
        return (not urgent, priority_rank_for(task.priority),
                switch_burst and task.task_type != current_type, deadline,
                task.estimated_minutes or 30, task.id)
    pending.sort(key=rank)
    from app.modules.events.models import Event, EventPrepItem
    events = db.scalars(select(Event).where(Event.user_id == runtime.user_id)).all()
    event_ids = [event.id for event in events]
    prep = db.scalars(select(EventPrepItem).where(EventPrepItem.event_id.in_(event_ids))).all() if event_ids else []
    fingerprint = hashlib.sha256(json.dumps({
        "clock": int(now.timestamp()) // 300,
        "tasks": [(task.id, str(task.updated_at), task.status) for task in tasks],
        "sessions": [(session.id, math.ceil(forecast.timestamp() / 300)) for session, forecast in zip(sessions, forecasts)],
        "events": [(event.id, str(event.updated_at)) for event in events],
        "prep": [(item.id, str(item.updated_at)) for item in prep],
        "window": str(runtime.window_end), "burst": switch_burst,
    }, sort_keys=True).encode()).hexdigest()
    if not force and fingerprint == runtime.fingerprint:
        return False
    fixed = [block for block in blocks if block.kind not in ("task", "break") and block.status != "superseded"]
    rebuilt, deferred = build_schedule_blocks(
        db, schedule.id, runtime.user_id, pending, start, aware(runtime.window_end), runtime.break_minutes,
        ordered_task_ids=[task.id for task in pending],
        reserved_windows=[(aware(block.start_at), aware(block.end_at)) for block in fixed],
        assumed_completed_ids=active_ids)
    referenced = set(db.scalars(select(SessionRecord.time_block_id).where(
        SessionRecord.user_id == runtime.user_id, SessionRecord.time_block_id.is_not(None))).all())
    reusable = {block.task_id: block for block in blocks if block.kind == "task"
                and block.status in ("planned", "missed") and block.id not in referenced}
    changes = []
    for block in blocks:
        if block.kind in ("task", "break") and block.status in ("planned", "missed") and block.id not in referenced:
            changes.append({"id": block.id, "old_start": str(block.start_at), "old_end": str(block.end_at)})
            block.status = "superseded"
    for block in rebuilt:
        old = reusable.pop(block.task_id, None) if block.task_id else None
        if old:
            for field in ("start_at", "end_at", "planned_duration_minutes", "risk_level", "risk_buffer_minutes", "risk_reason", "status"):
                setattr(old, field, getattr(block, field))
            old.title = block.title
        else:
            db.add(block)
    runtime.revision += 1
    runtime.fingerprint = fingerprint
    runtime.last_replanned_at = now
    runtime.deferred_tasks = deferred
    runtime.reason = "Updated unfinished tasks for the remaining work window, deadlines and current-session forecast."
    if switch_burst:
        runtime.reason += " Similar work is grouped within urgency and priority."
    schedule.generated_by = "adaptive_rules"
    db.add(PlanRevision(schedule_id=schedule.id, revision=runtime.revision, reason=runtime.reason, changes=changes))
    db.flush()
    return True


def plan_response(db, schedule):
    runtime = db.scalar(select(AdaptivePlan).where(AdaptivePlan.schedule_id == schedule.id))
    blocks = db.scalars(select(TimeBlock).where(TimeBlock.schedule_id == schedule.id,
                 TimeBlock.status != "superseded").order_by(TimeBlock.start_at)).all()
    return ScheduleGenerationResponse.model_validate({**schedule.__dict__, "time_blocks": blocks,
        "unscheduled_tasks": runtime.deferred_tasks if runtime else [],
        "generation_source": "adaptive_rules" if schedule.generated_by == "adaptive_rules" else "rules",
        "planning_explanation": runtime.reason if runtime else None})


def tick(db, user_id, now=None):
    now = now or utc_now()
    state = db.scalar(select(PolicyState).where(PolicyState.user_id == user_id))
    if state is None:
        # A savepoint permits concurrent first requests without losing other work.
        from sqlalchemy.exc import IntegrityError
        try:
            with db.begin_nested():
                state = PolicyState(user_id=user_id, next_evaluation_at=now,
                                    next_nudge_at=now, snoozed_until=now)
                db.add(state)
                db.flush()
        except IntegrityError:
            state = db.scalar(select(PolicyState).where(PolicyState.user_id == user_id))
    acquired = db.execute(update(PolicyState).where(PolicyState.id == state.id,
        PolicyState.next_evaluation_at <= now).values(next_evaluation_at=now + timedelta(seconds=30))
        .execution_options(synchronize_session=False))
    db.refresh(state)
    if not acquired.rowcount:
        return state.snapshot or {}
    sessions = db.scalars(select(SessionRecord).where(SessionRecord.user_id == user_id,
                    SessionRecord.status == "active", SessionRecord.ended_at.is_(None))).all()
    metrics, candidates = [], []
    burst = False
    for session in sessions:
        signal = activity_signal(db, session, now)
        block = db.get(TimeBlock, session.time_block_id) if session.time_block_id else None
        task = db.get(Task, session.task_id) if session.task_id else None
        duration = max(1, (block.planned_duration_minutes if block else None) or (task.estimated_minutes if task else None) or 30)
        end = aware(block.end_at) if block else aware(session.started_at) + timedelta(minutes=duration)
        overrun = max(0, (now - end).total_seconds() / 60)
        factor = overrun / duration
        signal.update(session_id=session.id, slippage_factor=round(factor, 2), overrun_minutes=round(overrun, 1))
        metrics.append(signal)
        if factor >= .2 and overrun >= 5:
            candidates.append((0, "slippage", session, block, "This session is running beyond its planned time. Update the minutes remaining or finish the task so the rest of the day can adjust."))
        if signal["fresh"] and signal["coverage"] >= .6:
            if signal["switches"] >= 4:
                burst = True
                candidates.append((2, "context_switches", session, block, "Several sustained app switches were observed in five minutes. Check whether you can finish the current step before switching again."))
            elif signal["idle_seconds"] >= 120:
                candidates.append((3, "idle", session, block, "Input has been idle for a while. If you are reading or thinking, keep going. Otherwise, return to the task or revise the plan."))
    runtimes = db.scalars(select(AdaptivePlan).where(AdaptivePlan.user_id == user_id,
                     AdaptivePlan.enabled.is_(True), AdaptivePlan.window_end >= now - timedelta(hours=1))).all()
    changed = []
    for runtime in runtimes:
        if now < aware(runtime.window_start) - timedelta(minutes=5):
            continue
        # Reminders use the existing plan before a late start is rescheduled.
        planned = db.scalars(select(TimeBlock).where(TimeBlock.schedule_id == runtime.schedule_id,
                    TimeBlock.status.in_(["planned", "missed"]), TimeBlock.kind == "task").order_by(TimeBlock.start_at)).all()
        if not sessions and planned:
            block = planned[0]
            delay = (now - aware(block.start_at)).total_seconds() / 60
            if delay >= 5:
                candidates.append((1, "late_start", None, block, "The next task has not started. The remaining plan is being adjusted. Start when ready or update your tasks."))
            elif -5 <= delay <= 0:
                candidates.append((4, "upcoming", None, block, f"Your next task, {block.title}, starts within five minutes."))
        if replan(db, runtime, now, burst):
            changed.append(runtime.schedule_id)
    # Resolve stale decisions, including finished sessions and recovered signals.
    kinds = {candidate[1] for candidate in candidates}
    pending = db.scalars(select(Intervention).where(Intervention.user_id == user_id,
                     Intervention.status == "pending", Intervention.kind.like("policy_%"))).all()
    for item in pending:
        if item.kind[7:] not in kinds or aware(item.trigger_at) < now - timedelta(minutes=10):
            item.status = "resolved"
    if candidates and now >= aware(state.next_nudge_at):
        _, kind, session, block, message = min(candidates, key=lambda candidate: candidate[0])
        reminder = Reminder(user_id=user_id, task_id=session.task_id if session else block.task_id,
                            time_block_id=block.id if block else None, kind="policy_" + kind,
                            severity="firm" if kind == "slippage" else "gentle", message=message,
                            trigger_at=now, status="delivered")
        db.add(reminder)
        db.flush()
        db.add(Intervention(user_id=user_id, reminder_id=reminder.id,
                           session_id=session.id if session else None, kind="policy_" + kind,
                           message=message, rationale=json.dumps({"policy_version": "adaptive-v1", "sessions": metrics}),
                           trigger_at=now, status="pending"))
        user = db.get(User, user_id)
        state.next_nudge_at = now + timedelta(minutes=20 if user.preferred_nudge_style == "minimal" else 10)
    state.snapshot = {"sessions": metrics, "changed_schedules": changed, "evaluated_at": now.isoformat()}
    db.flush()
    return state.snapshot


def policy_view(db, user_id):
    state = db.scalar(select(PolicyState).where(PolicyState.user_id == user_id))
    nudges = db.scalars(select(Intervention).where(Intervention.user_id == user_id,
                Intervention.kind.like("policy_%"), Intervention.status == "pending").order_by(Intervention.trigger_at.desc())).all()
    return {**(state.snapshot if state else {}), "nudges": [
        {"id": item.id, "kind": item.kind, "message": item.message, "session_id": item.session_id}
        for item in nudges]}


@router.post("/tick")
def evaluate(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    tick(db, user.id)
    db.commit()
    return policy_view(db, user.id)


class NudgeAction(BaseModel):
    action: str = Field(pattern="^dismiss$")


@router.post("/nudges/{nudge_id}")
def act(nudge_id: str, payload: NudgeAction, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.get(Intervention, nudge_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(404, "Nudge not found")
    item.status = "dismissed"
    db.commit()
    return {"status": item.status}


class RemainingInput(BaseModel):
    remaining_minutes: int = Field(ge=1, le=1440)


@router.post("/sessions/{session_id}/remaining")
def remaining(session_id: str, payload: RemainingInput, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = db.get(SessionRecord, session_id)
    if session is None or session.user_id != user.id:
        raise HTTPException(404, "Session not found")
    if session.status != "active" or session.ended_at:
        raise HTTPException(409, "Session has ended")
    estimate = db.scalar(select(RemainingEstimate).where(RemainingEstimate.session_id == session_id))
    if estimate is None:
        estimate = RemainingEstimate(session_id=session_id)
        db.add(estimate)
    estimate.remaining_minutes = payload.remaining_minutes
    estimate.reported_at = utc_now()
    db.execute(update(AdaptivePlan).where(AdaptivePlan.user_id == user.id).values(fingerprint=""))
    db.execute(update(PolicyState).where(PolicyState.user_id == user.id).values(next_evaluation_at=utc_now()))
    db.commit()
    tick(db, user.id)
    db.commit()
    return policy_view(db, user.id)
