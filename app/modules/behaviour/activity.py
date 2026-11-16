"""Session-scoped Windows activity ingestion and summaries."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.auth import require_workspace_access
from app.core.database import Base, get_db, utc_now
from app.modules.sessions.models import SessionRecord

router = APIRouter()


class ActivityMonitor(Base):
    __tablename__ = "activity_monitors"
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), unique=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sequence: Mapped[int] = mapped_column(Integer, default=0)


class ActivityInterval(Base):
    __tablename__ = "activity_intervals"
    __table_args__ = (UniqueConstraint("monitor_id", "sequence"),)
    monitor_id: Mapped[str] = mapped_column(ForeignKey("activity_monitors.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    state: Mapped[str] = mapped_column(String(16))
    app_name: Mapped[str | None] = mapped_column(String(120), nullable=True)


class IntervalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sequence: int = Field(ge=1)
    started_at: AwareDatetime
    ended_at: AwareDatetime
    state: Literal["active", "idle", "unknown"]
    app_name: str | None = Field(default=None, min_length=1, max_length=120, pattern=r"^[^\\/:\x00-\x1f]+$")

    @model_validator(mode="after")
    def valid_interval(self):
        if not 0 < (self.ended_at - self.started_at).total_seconds() <= 5:
            raise ValueError("Intervals must be between 0 and 5 seconds")
        if (self.state == "active") != (self.app_name is not None):
            raise ValueError("Only active intervals require an executable name")
        return self


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def get_session(db, session_id, user_id):
    record = db.get(SessionRecord, session_id)
    if record is None or record.user_id != user_id:
        raise HTTPException(404, "Session not found")
    return record


def running(record):
    return record.status == "active" and record.ended_at is None


def authorize(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Companion token required")
    digest = hashlib.sha256(authorization[7:].encode()).hexdigest()
    monitor = db.scalar(select(ActivityMonitor).where(ActivityMonitor.token_hash == digest))
    if monitor is None or not monitor.enabled or not running(db.get(SessionRecord, monitor.session_id)):
        raise HTTPException(403, "Monitoring stopped or pairing token expired")
    return monitor


@router.post("/sessions/{session_id}/enable", dependencies=[Depends(require_workspace_access)])
def enable(session_id: str, user_id: str, db: Session = Depends(get_db)):
    record = get_session(db, session_id, user_id)
    if not running(record):
        raise HTTPException(409, "Start a focus session first")
    monitor = db.scalar(select(ActivityMonitor).where(ActivityMonitor.session_id == session_id))
    token = secrets.token_urlsafe(32)
    if monitor is None:
        monitor = ActivityMonitor(session_id=session_id)
        db.add(monitor)
    monitor.token_hash = hashlib.sha256(token.encode()).hexdigest()
    monitor.enabled = True
    monitor.enabled_at = utc_now()
    monitor.last_seen_at = None
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Monitoring changed. Refresh and try again.")
    return {"token": token}


@router.post("/sessions/{session_id}/disable", dependencies=[Depends(require_workspace_access)])
def disable(session_id: str, user_id: str, db: Session = Depends(get_db)):
    get_session(db, session_id, user_id)
    db.execute(update(ActivityMonitor).where(ActivityMonitor.session_id == session_id).values(enabled=False))
    db.commit()
    return {"enabled": False}


@router.get("/companion")
def companion_status(monitor: ActivityMonitor = Depends(authorize)):
    return {"next_sequence": monitor.last_sequence + 1, "idle_seconds": 60}


@router.post("/companion/intervals")
def ingest(payload: IntervalInput, monitor: ActivityMonitor = Depends(authorize), db: Session = Depends(get_db)):
    previous = db.scalar(select(ActivityInterval).where(
        ActivityInterval.monitor_id == monitor.id, ActivityInterval.sequence == payload.sequence))
    if previous:
        same = (aware(previous.started_at) == payload.started_at and aware(previous.ended_at) == payload.ended_at
                and previous.state == payload.state and previous.app_name == payload.app_name)
        if not same:
            raise HTTPException(409, "Sequence already has different data")
        return {"accepted": True}
    last = db.scalar(select(ActivityInterval).where(ActivityInterval.monitor_id == monitor.id)
                     .order_by(ActivityInterval.sequence.desc()).limit(1))
    record = db.get(SessionRecord, monitor.session_id)
    earliest = max(aware(record.started_at), aware(monitor.enabled_at))
    if payload.started_at < earliest or payload.ended_at > utc_now() + timedelta(seconds=5):
        raise HTTPException(422, "Interval is outside the monitoring window")
    if last and payload.started_at < aware(last.ended_at):
        raise HTTPException(409, "Intervals must not overlap")
    if payload.sequence != monitor.last_sequence + 1:
        raise HTTPException(409, "Unexpected sequence. Restart the companion.")
    # Compare-and-swap serializes writers on SQLite as well as PostgreSQL.
    changed = db.execute(update(ActivityMonitor).where(
        ActivityMonitor.id == monitor.id, ActivityMonitor.last_sequence == monitor.last_sequence,
        ActivityMonitor.enabled.is_(True), ActivityMonitor.token_hash == monitor.token_hash,
    ).values(last_sequence=payload.sequence, last_seen_at=utc_now()))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Monitoring changed. Retry the interval.")
    db.add(ActivityInterval(monitor_id=monitor.id, **payload.model_dump()))
    db.commit()
    from app.modules.interventions.policy import tick, policy_view
    try:
        tick(db, record.user_id)
        db.commit()
        nudges = policy_view(db, record.user_id)["nudges"]
    except Exception:
        db.rollback()
        import logging
        logging.getLogger(__name__).exception("Activity saved; policy evaluation will retry")
        nudges = []
    return {"accepted": True, "nudges": nudges}


@router.get("/sessions/{session_id}", dependencies=[Depends(require_workspace_access)])
def summary(session_id: str, user_id: str, db: Session = Depends(get_db)):
    record = get_session(db, session_id, user_id)
    now = utc_now()
    stop = min(aware(record.actual_end or record.ended_at or now), now)
    start = aware(record.started_at)
    monitor = db.scalar(select(ActivityMonitor).where(ActivityMonitor.session_id == session_id))
    intervals = [] if monitor is None else db.scalars(select(ActivityInterval).where(
        ActivityInterval.monitor_id == monitor.id).order_by(ActivityInterval.sequence)).all()
    active, idle, switches = 0.0, 0.0, 0
    apps = {}
    previous = None
    for interval in intervals:
        seconds = max(0, (min(aware(interval.ended_at), stop) - max(aware(interval.started_at), start)).total_seconds())
        if seconds == 0:
            continue
        if interval.state == "active":
            active += seconds
            apps[interval.app_name] = apps.get(interval.app_name, 0) + seconds
            if (previous and previous.state == "active" and previous.app_name != interval.app_name
                    and (aware(interval.started_at) - aware(previous.ended_at)).total_seconds() <= 1):
                switches += 1
        elif interval.state == "idle":
            idle += seconds
        previous = interval
    enabled = bool(monitor and monitor.enabled and running(record))
    connected = bool(enabled and monitor.last_seen_at and (now - aware(monitor.last_seen_at)).total_seconds() < 10)
    return {"enabled": enabled, "connected": connected, "idle_threshold_seconds": 60,
            "active_seconds": round(active, 1), "idle_seconds": round(idle, 1),
            "unobserved_seconds": round(max(0, (stop - start).total_seconds() - active - idle), 1),
            "context_switches": switches,
            "apps": [{"name": name, "seconds": round(seconds, 1)}
                     for name, seconds in sorted(apps.items(), key=lambda item: item[1], reverse=True)]}
