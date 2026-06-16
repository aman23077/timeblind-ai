from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BehaviourEventCreate(BaseModel):
    user_id: str
    session_id: str | None = None
    task_id: str | None = None
    event_type: str = Field(..., min_length=1, max_length=64)
    occurred_at: datetime
    app_name: str | None = None
    url: str | None = None
    focus_state: str | None = None
    distraction_level: int | None = Field(default=None, ge=0, le=10)
    notes: str = ""
    payload: dict = Field(default_factory=dict)


class BehaviourEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    session_id: str | None
    task_id: str | None
    event_type: str
    occurred_at: datetime
    app_name: str | None
    url: str | None
    focus_state: str | None
    distraction_level: int | None
    notes: str
    payload: dict
    created_at: datetime
    updated_at: datetime
