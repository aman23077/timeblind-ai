from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ContextEventCreate(BaseModel):
    user_id: str
    source: str = "manual"
    event_type: str = Field(..., min_length=1, max_length=64)
    occurred_at: datetime
    energy_score: int | None = Field(default=None, ge=0, le=10)
    mood: str | None = None
    payload: dict = Field(default_factory=dict)


class ContextEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    source: str
    event_type: str
    occurred_at: datetime
    energy_score: int | None
    mood: str | None
    payload: dict
    created_at: datetime
    updated_at: datetime
