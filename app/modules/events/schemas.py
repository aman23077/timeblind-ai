from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class EventPreparationTask(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    minutes: int = Field(..., ge=1, le=480)
    required: bool = True


class EventPlanRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=160)
    start_at: datetime
    commute_minutes: int = Field(20, ge=0, le=240)
    get_ready_minutes: int = Field(20, ge=0, le=180)
    departure_buffer_minutes: int = Field(10, ge=0, le=120)
    prep_tasks: list[EventPreparationTask] = Field(default_factory=list)
    current_time: datetime | None = None
    user_time_zone: str = "Asia/Kolkata"


class PlannedStep(BaseModel):
    kind: Literal["prep", "get_ready", "depart", "event"]
    title: str
    start_at: datetime
    end_at: datetime
    minutes: int = Field(..., ge=0)


class EventNudge(BaseModel):
    trigger_at: datetime
    message: str
    severity: Literal["gentle", "firm", "urgent"]


class EventRiskState(BaseModel):
    level: Literal["low", "medium", "high"]
    reason: str


class EventPlanResponse(BaseModel):
    event_title: str
    ready_by: datetime
    leave_by: datetime
    prep_start_at: datetime
    total_prep_minutes: int
    steps: list[PlannedStep]
    nudges: list[EventNudge]
    risk: EventRiskState


class EventCreate(BaseModel):
    user_id: str
    title: str = Field(..., min_length=1, max_length=160)
    description: str = ""
    start_at: datetime
    end_at: datetime | None = None
    location: str = ""
    commute_minutes: int = Field(20, ge=0, le=240)
    get_ready_minutes: int = Field(20, ge=0, le=180)
    departure_buffer_minutes: int = Field(10, ge=0, le=120)


class EventPrepItemCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    minutes: int = Field(..., ge=1, le=480)
    required: bool = True
    order_index: int = Field(1, ge=1)


class EventPrepItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: str
    title: str
    minutes: int
    required: bool
    order_index: int
    created_at: datetime
    updated_at: datetime


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    title: str
    description: str
    start_at: datetime
    end_at: datetime | None
    location: str
    commute_minutes: int
    get_ready_minutes: int
    departure_buffer_minutes: int
    created_at: datetime
    updated_at: datetime


class EventDetail(EventRead):
    prep_items: list[EventPrepItemRead]
