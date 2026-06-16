from pydantic import BaseModel


class InsightsWindow(BaseModel):
    period: str
    anchor_date: str
    window_start: str
    window_end: str


class InsightsSummary(BaseModel):
    completed_tasks: int
    completed_sessions: int
    completed_blocks: int
    missed_blocks: int
    average_prediction_delta_minutes: int
    average_prediction_delta_percent: int
    average_delay_minutes: int
    average_overrun_minutes: int
    top_friction_reason: str | None = None


class LeakageSummary(BaseModel):
    observed_drift_minutes: int
    average_drift_minutes: int
    drift_rate_percent: int
    delayed_blocks: int
    overrun_blocks: int
    focus_drift_sessions: int
    top_observed_signal: str | None = None
    predicted_risk_level: str
    predicted_risk_score: int
    predicted_risk_reason: str


class InsightCard(BaseModel):
    title: str
    detail: str
    metric_label: str
    metric_value: str
    category: str


class TaskTypeInsight(BaseModel):
    task_type: str
    completed_tasks: int
    average_estimated_minutes: int
    average_actual_minutes: int
    average_delta_minutes: int
    average_delay_minutes: int
    average_overrun_minutes: int


class FeedbackInsight(BaseModel):
    reason: str
    count: int


class InsightsResponse(BaseModel):
    window: InsightsWindow
    summary: InsightsSummary
    leakage: LeakageSummary
    review_narrative: str
    recommended_actions: list[str]
    top_insights: list[InsightCard]
    task_type_breakdown: list[TaskTypeInsight]
    feedback_breakdown: list[FeedbackInsight]
