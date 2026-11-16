from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserModelProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    chronotype: str
    optimal_session_minutes: int
    break_recovery_minutes: int
    peak_focus_start: str
    peak_focus_end: str
    low_energy_start: str
    low_energy_end: str
    distraction_risk_notes: str


class UserCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(..., min_length=1, max_length=120)
    time_zone: str = "Asia/Kolkata"
    preferred_nudge_style: str = "supportive"
    participant_type: str = "student"
    primary_task_focus: str = "study"
    consent_to_research: str = "false"


class UserEnsure(BaseModel):
    email: EmailStr
    display_name: str = Field(..., min_length=1, max_length=120)
    time_zone: str = "Asia/Kolkata"
    preferred_nudge_style: str = "supportive"
    participant_type: str = "student"
    primary_task_focus: str = "study"
    consent_to_research: str = "false"


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    time_zone: str | None = None
    preferred_nudge_style: str | None = None
    participant_type: str | None = None
    primary_task_focus: str | None = None
    consent_to_research: str | None = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    display_name: str
    time_zone: str
    preferred_nudge_style: str
    participant_type: str
    primary_task_focus: str
    consent_to_research: str
    created_at: datetime
    updated_at: datetime


class UserDetail(UserRead):
    model_profile: UserModelProfileRead
    is_admin: bool = False
