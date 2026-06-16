from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Reminder(Base):
    __tablename__ = "reminders"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    task_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tasks.id"), nullable=True, index=True)
    event_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("events.id"), nullable=True, index=True)
    time_block_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("time_blocks.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(32), default="nudge")
    severity: Mapped[str] = mapped_column(String(32), default="gentle")
    message: Mapped[str] = mapped_column(Text)
    trigger_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(32), default="scheduled")


class Intervention(Base):
    __tablename__ = "interventions"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    reminder_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("reminders.id"), nullable=True, index=True)
    session_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("sessions.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(32), default="nudge")
    message: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text, default="")
    trigger_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
