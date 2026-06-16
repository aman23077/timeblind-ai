from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    time_zone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    preferred_nudge_style: Mapped[str] = mapped_column(String(32), default="supportive")


class UserModelProfile(Base):
    __tablename__ = "user_model_profiles"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), unique=True, index=True)
    chronotype: Mapped[str] = mapped_column(String(32), default="unknown")
    optimal_session_minutes: Mapped[int] = mapped_column(default=45)
    break_recovery_minutes: Mapped[int] = mapped_column(default=10)
    peak_focus_start: Mapped[str] = mapped_column(String(5), default="09:00")
    peak_focus_end: Mapped[str] = mapped_column(String(5), default="12:00")
    low_energy_start: Mapped[str] = mapped_column(String(5), default="14:00")
    low_energy_end: Mapped[str] = mapped_column(String(5), default="16:00")
    distraction_risk_notes: Mapped[str] = mapped_column(default="")
