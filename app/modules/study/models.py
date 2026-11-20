"""Prospective pilot records, kept separate from synthetic and ordinary usage."""
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

PROTOCOL = "nov2026-pilot-v1"


class StudyEnrollment(Base):
    __tablename__ = "study_enrollments"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True)
    protocol: Mapped[str] = mapped_column(String(40), default=PROTOCOL)
    baseline_frequency: Mapped[str] = mapped_column(String(32))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StudyTask(Base):
    __tablename__ = "study_tasks"
    __table_args__ = (Index("study_one_active_task_per_member", "enrollment_id", unique=True,
                           sqlite_where=text("outcome = 'active'"), postgresql_where=text("outcome = 'active'")),)
    enrollment_id: Mapped[str] = mapped_column(ForeignKey("study_enrollments.id"), index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), unique=True)
    session_id: Mapped[str | None] = mapped_column(ForeignKey("sessions.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(180))
    task_type: Mapped[str] = mapped_column(String(32))
    difficulty: Mapped[str] = mapped_column(String(16))
    user_estimate_minutes: Mapped[int] = mapped_column(Integer)
    rules_estimate_minutes: Mapped[int] = mapped_column(Integer)
    prediction_method: Mapped[str] = mapped_column(String(64), default="rules-unpersonalized-v1")
    predicted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    elapsed_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    break_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    scope_changed: Mapped[bool | None] = mapped_column(nullable=True)
    outcome: Mapped[str] = mapped_column(String(16), default="planned")
    friction: Mapped[str] = mapped_column(String(40), default="none")


class StudyFeedback(Base):
    __tablename__ = "study_feedback"
    enrollment_id: Mapped[str] = mapped_column(ForeignKey("study_enrollments.id"), unique=True)
    ease: Mapped[int] = mapped_column(Integer)
    clarity: Mapped[int] = mapped_column(Integer)
    usefulness: Mapped[int] = mapped_column(Integer)
    trust: Mapped[int] = mapped_column(Integer)
    use_again: Mapped[int] = mapped_column(Integer)
    best_part: Mapped[str] = mapped_column(Text, default="")
    biggest_problem: Mapped[str] = mapped_column(Text, default="")
    suggestion: Mapped[str] = mapped_column(Text, default="")
