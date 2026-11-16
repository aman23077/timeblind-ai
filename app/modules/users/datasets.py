"""Explicit data provenance and credential-free administrator dataset exports."""

import csv
import io
import json
import zipfile
from datetime import date, datetime, timezone

from sqlalchemy import ForeignKey, String, select, func
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.database import Base
from app.modules.users.models import User


class DatasetAccount(Base):
    __tablename__ = "dataset_accounts"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True)
    source: Mapped[str] = mapped_column(String(32))
    dataset_id: Mapped[str] = mapped_column(String(80))


def scalar(value):
    if isinstance(value, datetime):
        return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    # Protect spreadsheets from evaluating user-entered text as formulas.
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def record_queries(user_ids):
    """Allowlisted research tables. Authentication and pairing secrets never enter this map."""
    from app.modules.tasks.models import Task, TaskDependency, TaskStep
    from app.modules.sessions.models import SessionRecord, RemainingEstimate
    from app.modules.schedules.models import Schedule, TimeBlock, PlanRevision, AdaptivePlan
    from app.modules.events.models import Event, EventPrepItem
    from app.modules.behaviour.activity import ActivityInterval, ActivityMonitor
    from app.modules.behaviour.models import BehaviourEvent
    from app.modules.context.models import ContextEvent
    from app.modules.goals.models import Goal
    from app.modules.interventions.models import Intervention, Reminder
    from app.modules.users.models import UserModelProfile
    tasks = select(Task.id).where(Task.user_id.in_(user_ids))
    sessions = select(SessionRecord.id).where(SessionRecord.user_id.in_(user_ids))
    schedules = select(Schedule.id).where(Schedule.user_id.in_(user_ids))
    events = select(Event.id).where(Event.user_id.in_(user_ids))
    monitors = select(ActivityMonitor.id).where(ActivityMonitor.session_id.in_(sessions))
    result = {name: (model, select(model).where(model.user_id.in_(user_ids))) for name, model in (
        ("tasks", Task), ("sessions", SessionRecord), ("schedules", Schedule), ("schedule_blocks", TimeBlock),
        ("events", Event), ("policy_decisions", Intervention), ("reminders", Reminder),
        ("adaptive_plans", AdaptivePlan), ("behaviour_events", BehaviourEvent), ("context_events", ContextEvent),
        ("goals", Goal), ("model_profiles", UserModelProfile))}
    result.update({name: (model, select(model).where(field.in_(ids))) for name, model, field, ids in (
        ("task_steps", TaskStep, TaskStep.task_id, tasks), ("dependencies", TaskDependency, TaskDependency.task_id, tasks),
        ("remaining_estimates", RemainingEstimate, RemainingEstimate.session_id, sessions),
        ("plan_revisions", PlanRevision, PlanRevision.schedule_id, schedules),
        ("event_prep_items", EventPrepItem, EventPrepItem.event_id, events),
        ("activity_intervals", ActivityInterval, ActivityInterval.monitor_id, monitors))})
    return result


def browse_records(db, user_id, table, offset=0):
    queries = record_queries([user_id])
    model, query = queries[table]
    columns = [column.name for column in model.__table__.columns]
    rows = db.scalars(query.order_by(model.created_at.desc(), model.id).offset(offset).limit(50)).all()
    marker = db.scalar(select(DatasetAccount).where(DatasetAccount.user_id == user_id))
    return {"table": table, "tables": list(queries), "columns": columns,
            "total": db.scalar(select(func.count()).select_from(query.subquery())),
            "data_source": marker.source if marker else "unverified",
            "dataset_id": marker.dataset_id if marker else None,
            "rows": [{column: scalar(getattr(row, column)) for column in columns} for row in rows]}


def export_dataset(db: Session, user_id: str | None, source: str) -> bytes:
    from app.modules.tasks.models import Task, TaskDependency, TaskStep
    from app.modules.sessions.models import SessionRecord, RemainingEstimate
    from app.modules.schedules.models import Schedule, TimeBlock, PlanRevision
    from app.modules.events.models import Event
    from app.modules.behaviour.activity import ActivityInterval, ActivityMonitor
    from app.modules.interventions.models import Intervention, Reminder

    provenance = {row.user_id: row for row in db.scalars(select(DatasetAccount)).all()}
    users = db.scalars(select(User).where(User.id == user_id) if user_id else select(User)).all()
    users = [user for user in users if source == "all" or
             (provenance[user.id].source if user.id in provenance else "unverified") == source]
    owners = {user.id for user in users}
    accounts = {user.id: user for user in users}
    tasks = db.scalars(select(Task).where(Task.user_id.in_(owners))).all()
    sessions = db.scalars(select(SessionRecord).where(SessionRecord.user_id.in_(owners))).all()
    schedules = db.scalars(select(Schedule).where(Schedule.user_id.in_(owners))).all()
    monitors = db.scalars(select(ActivityMonitor).where(ActivityMonitor.session_id.in_([row.id for row in sessions]))).all()
    task_owner = {row.id: row.user_id for row in tasks}
    session_owner = {row.id: row.user_id for row in sessions}
    schedule_owner = {row.id: row.user_id for row in schedules}
    monitor_owner = {row.id: session_owner[row.session_id] for row in monitors}
    event_owner = {row.id: row.user_id for row in db.scalars(select(Event).where(Event.user_id.in_(owners)))}
    tables = {
        "tasks": (Task, tasks, lambda row: row.user_id),
        "sessions": (SessionRecord, sessions, lambda row: row.user_id),
        "schedules": (Schedule, schedules, lambda row: row.user_id),
        "schedule_blocks": (TimeBlock, db.scalars(select(TimeBlock).where(TimeBlock.user_id.in_(owners))).all(), lambda row: row.user_id),
        "events": (Event, db.scalars(select(Event).where(Event.user_id.in_(owners))).all(), lambda row: row.user_id),
        "policy_decisions": (Intervention, db.scalars(select(Intervention).where(Intervention.user_id.in_(owners))).all(), lambda row: row.user_id),
        "reminders": (Reminder, db.scalars(select(Reminder).where(Reminder.user_id.in_(owners))).all(), lambda row: row.user_id),
        "task_steps": (TaskStep, db.scalars(select(TaskStep).where(TaskStep.task_id.in_(task_owner))).all(), lambda row: task_owner[row.task_id]),
        "dependencies": (TaskDependency, db.scalars(select(TaskDependency).where(TaskDependency.task_id.in_(task_owner))).all(), lambda row: task_owner[row.task_id]),
        "remaining_estimates": (RemainingEstimate, db.scalars(select(RemainingEstimate).where(RemainingEstimate.session_id.in_(session_owner))).all(), lambda row: session_owner[row.session_id]),
        "plan_revisions": (PlanRevision, db.scalars(select(PlanRevision).where(PlanRevision.schedule_id.in_(schedule_owner))).all(), lambda row: schedule_owner[row.schedule_id]),
        "activity_intervals": (ActivityInterval, db.scalars(select(ActivityInterval).where(ActivityInterval.monitor_id.in_(monitor_owner))).all(), lambda row: monitor_owner[row.monitor_id]),
    }
    for name, (model, query) in record_queries(owners).items():
        if name not in tables:
            owner_fn = (lambda row: event_owner[row.event_id]) if name == "event_prep_items" else (lambda row: row.user_id)
            tables[name] = (model, db.scalars(query).all(), owner_fn)
    output = io.BytesIO()
    counts = {}
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, (model, rows, owner) in tables.items():
            columns = [column.name for column in model.__table__.columns]
            buffer = io.StringIO(newline="")
            writer = csv.DictWriter(buffer, fieldnames=columns + ["data_source", "dataset_id", "account_id", "consent_to_research"])
            writer.writeheader()
            for row in rows:
                account_id = owner(row)
                marker = provenance.get(account_id)
                writer.writerow({**{column: scalar(getattr(row, column)) for column in columns},
                                 "data_source": marker.source if marker else "unverified",
                                 "dataset_id": marker.dataset_id if marker else "",
                                 "account_id": account_id, "consent_to_research": accounts[account_id].consent_to_research})
            archive.writestr(name + ".csv", buffer.getvalue())
            counts[name] = len(rows)
        # Join activity to sessions without exporting pairing credentials.
        archive.writestr("monitor_sessions.json", json.dumps([{"monitor_id": row.id, "session_id": row.session_id} for row in monitors]))
        archive.writestr("manifest.json", json.dumps({"schema_version": 1, "counts": counts,
            "source_filter": source, "account_count": len(users),
            "notes": ["Existing accounts have unverified provenance unless explicitly labeled.",
                      "Task actual_minutes and session outcomes are targets or post-task values, not creation-time features.",
                      "App activity and idle periods do not directly establish focused work.",
                      "Free-text task content may contain identifying information. Review before sharing.",
                      "Credential tables and user emails are excluded."]}, indent=2))
    return output.getvalue()
