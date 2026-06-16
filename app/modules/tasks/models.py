from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Task(Base):
    __tablename__ = "tasks"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    goal_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("goals.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default="")
    task_type: Mapped[str] = mapped_column(String(32), default="generic")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    priority: Mapped[str] = mapped_column(String(32), default="medium")
    difficulty: Mapped[str] = mapped_column(String(16), default="medium")
    quantity_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TaskStep(Base):
    __tablename__ = "task_steps"

    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id"), index=True)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default="")
    order_index: Mapped[int] = mapped_column(default=1)
    suggested_minutes: Mapped[int] = mapped_column(default=15)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    rationale: Mapped[str] = mapped_column(Text, default="")


class TaskDependency(Base):
    __tablename__ = "task_dependencies"

    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id"), index=True)
    depends_on_task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id"), index=True)
    dependency_kind: Mapped[str] = mapped_column(String(32), default="requires")
