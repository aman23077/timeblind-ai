from datetime import datetime, timedelta, timezone

from app.modules.events.schemas import (
    EventNudge,
    EventPlanRequest,
    EventPlanResponse,
    EventRiskState,
    PlannedStep,
)


def build_event_plan(payload: EventPlanRequest) -> EventPlanResponse:
    prep_minutes = sum(task.minutes for task in payload.prep_tasks)
    ready_by = payload.start_at - timedelta(
        minutes=payload.commute_minutes + payload.departure_buffer_minutes
    )
    get_ready_start = ready_by - timedelta(minutes=payload.get_ready_minutes)
    prep_start_at = get_ready_start - timedelta(minutes=prep_minutes)

    steps: list[PlannedStep] = []
    cursor = prep_start_at

    for prep_task in payload.prep_tasks:
        end_at = cursor + timedelta(minutes=prep_task.minutes)
        steps.append(
            PlannedStep(
                kind="prep",
                title=prep_task.title,
                start_at=cursor,
                end_at=end_at,
                minutes=prep_task.minutes,
            )
        )
        cursor = end_at

    steps.append(
        PlannedStep(
            kind="get_ready",
            title="Get ready",
            start_at=get_ready_start,
            end_at=ready_by,
            minutes=payload.get_ready_minutes,
        )
    )
    steps.append(
        PlannedStep(
            kind="depart",
            title="Leave now",
            start_at=ready_by,
            end_at=payload.start_at,
            minutes=payload.commute_minutes + payload.departure_buffer_minutes,
        )
    )
    steps.append(
        PlannedStep(
            kind="event",
            title=payload.title,
            start_at=payload.start_at,
            end_at=payload.start_at,
            minutes=0,
        )
    )

    risk = _assess_risk(payload, prep_start_at)
    nudges = _build_nudges(payload, prep_start_at, get_ready_start, ready_by, risk.level)

    return EventPlanResponse(
        event_title=payload.title,
        ready_by=ready_by,
        leave_by=ready_by,
        prep_start_at=prep_start_at,
        total_prep_minutes=prep_minutes + payload.get_ready_minutes,
        steps=steps,
        nudges=nudges,
        risk=risk,
    )


def _assess_risk(payload: EventPlanRequest, prep_start_at) -> EventRiskState:
    now = payload.current_time or datetime.now(timezone.utc)
    if payload.start_at.tzinfo is None and now.tzinfo is not None:
        now = now.replace(tzinfo=None)
    if payload.start_at.tzinfo is not None and now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    if now >= payload.start_at:
        return EventRiskState(level="high", reason="The event start time has already arrived.")
    if now >= prep_start_at:
        return EventRiskState(
            level="high",
            reason="The preparation window should already have started.",
        )
    if now >= prep_start_at - timedelta(minutes=15):
        return EventRiskState(
            level="medium",
            reason="The preparation window is close and there is little recovery slack.",
        )
    return EventRiskState(level="low", reason="There is enough slack before preparation begins.")


def _build_nudges(
    payload: EventPlanRequest,
    prep_start_at,
    get_ready_start,
    leave_by,
    risk_level: str,
) -> list[EventNudge]:
    prep_prompt = "Start prep now so leaving on time stays easy."
    if payload.prep_tasks:
        prep_prompt = f"Start prep now: {payload.prep_tasks[0].title} first."

    severity = "gentle"
    if risk_level == "medium":
        severity = "firm"
    if risk_level == "high":
        severity = "urgent"

    return [
        EventNudge(
            trigger_at=prep_start_at,
            message=prep_prompt,
            severity=severity,
        ),
        EventNudge(
            trigger_at=get_ready_start,
            message="Time to get ready. Keep it simple and focus on leaving on time.",
            severity=severity,
        ),
        EventNudge(
            trigger_at=leave_by,
            message="Leave now. Future-you will thank you for the buffer.",
            severity="urgent" if risk_level != "low" else "firm",
        ),
    ]
