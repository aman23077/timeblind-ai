from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GoalCreate(BaseModel):
    user_id: str
    title: str = Field(..., min_length=1, max_length=180)
    description: str = ""
    target_date: datetime | None = None
    status: str = "active"


class GoalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    title: str
    description: str
    target_date: datetime | None
    status: str
    created_at: datetime
    updated_at: datetime
