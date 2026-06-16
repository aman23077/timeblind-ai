from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Event(Base):
    __tablename__ = "events"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    location: Mapped[str] = mapped_column(String(255), default="")
    commute_minutes: Mapped[int] = mapped_column(Integer, default=20)
    get_ready_minutes: Mapped[int] = mapped_column(Integer, default=20)
    departure_buffer_minutes: Mapped[int] = mapped_column(Integer, default=10)


class EventPrepItem(Base):
    __tablename__ = "event_prep_items"

    event_id: Mapped[str] = mapped_column(String(36), ForeignKey("events.id"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    minutes: Mapped[int] = mapped_column(Integer)
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    order_index: Mapped[int] = mapped_column(Integer, default=1)
