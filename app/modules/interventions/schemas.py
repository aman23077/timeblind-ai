from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ReminderCreate(BaseModel):
    user_id: str
    task_id: str | None = None
    event_id: str | None = None
    time_block_id: str | None = None
    kind: str = "nudge"
    severity: str = "gentle"
    message: str
    trigger_at: datetime
    status: str = "scheduled"


class ReminderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    task_id: str | None
    event_id: str | None
    time_block_id: str | None
    kind: str
    severity: str
    message: str
    trigger_at: datetime
    status: str
    created_at: datetime
    updated_at: datetime


class InterventionCreate(BaseModel):
    user_id: str
    reminder_id: str | None = None
    session_id: str | None = None
    kind: str = "nudge"
    message: str
    rationale: str = ""
    trigger_at: datetime


class InterventionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    reminder_id: str | None
    session_id: str | None
    kind: str
    message: str
    rationale: str
    trigger_at: datetime
    status: str
    created_at: datetime
    updated_at: datetime
