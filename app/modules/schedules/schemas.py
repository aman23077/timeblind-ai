from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, Field


class ScheduleCreate(BaseModel):
    user_id: str
    plan_date: date
    status: str = "draft"
    generated_by: str = "manual"


class ScheduleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    plan_date: date
    status: str
    generated_by: str
    created_at: datetime
    updated_at: datetime


class TimeBlockCreate(BaseModel):
    user_id: str
    task_id: str | None = None
    event_id: str | None = None
    title: str
    kind: str = "task"
    start_at: datetime
    end_at: datetime
    planned_duration_minutes: int | None = Field(default=None, ge=0, le=1440)
    risk_level: str = "low"
    risk_buffer_minutes: int = Field(0, ge=0, le=240)
    risk_reason: str = ""
    actual_start: datetime | None = None
    actual_end: datetime | None = None
    delay_minutes: int = Field(0, ge=0, le=1440)
    overrun_minutes: int = Field(0, ge=0, le=1440)
    buffer_before_minutes: int = Field(0, ge=0, le=240)
    buffer_after_minutes: int = Field(0, ge=0, le=240)
    status: str = "planned"


class TimeBlockRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    schedule_id: str
    user_id: str
    task_id: str | None
    event_id: str | None
    title: str
    kind: str
    start_at: datetime
    end_at: datetime
    planned_duration_minutes: int | None
    risk_level: str | None
    risk_buffer_minutes: int | None
    risk_reason: str | None
    actual_start: datetime | None
    actual_end: datetime | None
    delay_minutes: int
    overrun_minutes: int
    buffer_before_minutes: int
    buffer_after_minutes: int
    status: str
    created_at: datetime
    updated_at: datetime


class ScheduleDetail(ScheduleRead):
    time_blocks: list[TimeBlockRead]


class ScheduleGenerateRequest(BaseModel):
    user_id: str
    plan_date: date
    window_start: time
    window_end: time
    break_minutes: int = Field(10, ge=0, le=120)


class UnscheduledTask(BaseModel):
    task_id: str
    title: str
    estimated_minutes: int
    reason: str


class ScheduleGenerationResponse(ScheduleDetail):
    unscheduled_tasks: list[UnscheduledTask]


class TimeBlockStartRequest(BaseModel):
    user_id: str
    started_at: datetime | None = None


class TimeBlockStartResponse(BaseModel):
    time_block: TimeBlockRead
    session: "SessionRead"


class ScheduleRecoveryRequest(BaseModel):
    user_id: str
    resumed_from: datetime | None = None
    suggested_break_minutes: int = Field(10, ge=0, le=60)


class ScheduleRecoveryResponse(BaseModel):
    schedule: ScheduleDetail
    next_time_block: TimeBlockRead | None
    suggested_break_minutes: int
    message: str
    rescheduled: bool
    deferred_tasks: list[UnscheduledTask]


from app.modules.sessions.schemas import SessionRead

TimeBlockStartResponse.model_rebuild()
