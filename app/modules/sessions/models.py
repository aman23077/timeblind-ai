from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SessionRecord(Base):
    __tablename__ = "sessions"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    task_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tasks.id"), nullable=True, index=True)
    time_block_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("time_blocks.id"), nullable=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    elapsed_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delay_minutes: Mapped[int] = mapped_column(Integer, default=0)
    overrun_minutes: Mapped[int] = mapped_column(Integer, default=0)
    attention_state: Mapped[str] = mapped_column(String(32), default="unknown")
    energy_level: Mapped[str] = mapped_column(String(32), default="unknown")
    difficulty_feedback: Mapped[str] = mapped_column(String(32), default="as_expected")
    feedback_reasons: Mapped[str] = mapped_column(Text, default="")
    feedback_notes: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="active")
