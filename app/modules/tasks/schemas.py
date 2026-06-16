from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TaskType = Literal[
    "assignment",
    "reading",
    "study",
    "writing",
    "coding",
    "meeting_prep",
    "admin",
    "errand",
    "chore",
    "exercise",
    "creative",
    "generic",
]

TaskDifficulty = Literal["easy", "medium", "hard"]


class TaskDecompositionRequest(BaseModel):
    user_id: str | None = None
    title: str = Field(..., min_length=1, max_length=180)
    deadline_at: datetime | None = None
    estimated_minutes: int | None = Field(default=None, ge=5, le=1440)
    task_type: TaskType = "generic"
    difficulty: TaskDifficulty = "medium"
    quantity_value: int | None = Field(default=None, ge=1, le=500)
    current_time: datetime | None = None


class DecomposedTaskStep(BaseModel):
    title: str
    suggested_minutes: int = Field(..., ge=5)
    order: int = Field(..., ge=1)
    rationale: str


class TaskDecompositionResponse(BaseModel):
    task_title: str
    urgency: Literal["low", "medium", "high"] | None
    base_estimate_minutes: int
    personalized_estimate_minutes: int
    prediction_confidence: Literal["low", "medium", "high"]
    personalization_multiplier: float
    available_minutes: int | None
    fit_status: Literal["fits", "tight", "overflow"] | None
    overflow_minutes: int | None
    guidance: str
    total_suggested_minutes: int
    steps: list[DecomposedTaskStep]


class TaskCreate(BaseModel):
    user_id: str
    goal_id: str | None = None
    title: str = Field(..., min_length=1, max_length=180)
    description: str = ""
    task_type: TaskType = "generic"
    status: str = "pending"
    priority: str = "medium"
    difficulty: TaskDifficulty = "medium"
    quantity_value: int | None = Field(default=None, ge=1, le=500)
    estimated_minutes: int | None = Field(default=None, ge=5, le=1440)
    actual_minutes: int | None = Field(default=None, ge=0, le=1440)
    deadline_at: datetime | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    difficulty: TaskDifficulty | None = None
    quantity_value: int | None = Field(default=None, ge=1, le=500)
    estimated_minutes: int | None = Field(default=None, ge=5, le=1440)
    actual_minutes: int | None = Field(default=None, ge=0, le=1440)
    deadline_at: datetime | None = None


class TaskStepCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=180)
    description: str = ""
    order_index: int = Field(1, ge=1)
    suggested_minutes: int = Field(15, ge=5, le=480)
    status: str = "pending"
    rationale: str = ""


class TaskStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    title: str
    description: str
    order_index: int
    suggested_minutes: int
    status: str
    rationale: str
    created_at: datetime
    updated_at: datetime


class TaskDependencyCreate(BaseModel):
    depends_on_task_id: str
    dependency_kind: str = "requires"


class TaskDependencyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    depends_on_task_id: str
    dependency_kind: str
    created_at: datetime
    updated_at: datetime


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    goal_id: str | None
    title: str
    description: str
    task_type: str
    status: str
    priority: str
    difficulty: str
    quantity_value: int | None
    estimated_minutes: int | None
    actual_minutes: int | None
    deadline_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TaskDetail(TaskRead):
    steps: list[TaskStepRead]
    dependencies: list[TaskDependencyRead]
