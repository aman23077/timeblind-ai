from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SessionCreate(BaseModel):
    user_id: str
    task_id: str | None = None
    time_block_id: str | None = None
    started_at: datetime
    actual_start: datetime | None = None
    delay_minutes: int = 0
    overrun_minutes: int = 0
    attention_state: str = "unknown"
    energy_level: str = "unknown"
    notes: str = ""
    status: str = "active"


class SessionEndRequest(BaseModel):
    ended_at: datetime
    status: str = "completed"
    actual_end: datetime | None = None
    difficulty_feedback: str = "as_expected"
    feedback_reasons: list[str] = Field(default_factory=list)
    feedback_notes: str = ""


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    task_id: str | None
    time_block_id: str | None
    started_at: datetime
    ended_at: datetime | None
    actual_start: datetime | None
    actual_end: datetime | None
    elapsed_minutes: int | None
    delay_minutes: int
    overrun_minutes: int
    attention_state: str
    energy_level: str
    difficulty_feedback: str
    feedback_reasons: str
    feedback_notes: str
    notes: str
    status: str
    created_at: datetime
    updated_at: datetime
