from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.insights.schemas import (
    FeedbackInsight,
    InsightCard,
    InsightsResponse,
    InsightsSummary,
    InsightsWindow,
    LeakageSummary,
    TaskTypeInsight,
)
from app.modules.schedules.models import TimeBlock
from app.modules.sessions.models import SessionRecord
from app.modules.tasks.models import Task


router = APIRouter()

LEAKAGE_REASONS = {
    "Interrupted",
    "Lost focus",
    "Took a break",
    "Needed to switch context",
    "Environment distraction",
}


@router.get("", response_model=InsightsResponse)
def get_insights(
    user_id: str = Query(...),
    period: str = Query(default="week", pattern="^(day|week|month|all)$"),
    anchor_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
) -> InsightsResponse:
    anchor = anchor_date or datetime.now(timezone.utc).date()
    window_start, window_end = _build_window(period, anchor)

    tasks = db.scalars(select(Task).where(Task.user_id == user_id)).all()
    sessions = db.scalars(select(SessionRecord).where(SessionRecord.user_id == user_id)).all()
    blocks = db.scalars(select(TimeBlock).where(TimeBlock.user_id == user_id)).all()

    filtered_sessions = [session for session in sessions if _is_in_window(session.ended_at or session.updated_at, window_start, window_end)]
    filtered_blocks = [
        block for block in blocks if _is_in_window(block.actual_end or block.end_at or block.updated_at, window_start, window_end)
    ]

    completed_sessions = [session for session in filtered_sessions if session.status == "completed"]
    completed_task_ids = {session.task_id for session in completed_sessions if session.task_id}
    completed_tasks = [
        task
        for task in tasks
        if task.id in completed_task_ids
        and task.status == "completed"
        and task.estimated_minutes is not None
        and task.actual_minutes is not None
    ]
    completed_blocks = [block for block in filtered_blocks if block.status == "completed"]
    missed_blocks = [block for block in filtered_blocks if block.status == "missed"]

    average_prediction_delta_minutes = _rounded_average(
        [(task.actual_minutes or 0) - (task.estimated_minutes or 0) for task in completed_tasks]
    )
    average_prediction_delta_percent = _rounded_average(
        [
            (((task.actual_minutes or 0) - (task.estimated_minutes or 0)) / task.estimated_minutes) * 100
            for task in completed_tasks
            if task.estimated_minutes
        ]
    )
    average_delay_minutes = _rounded_average([session.delay_minutes for session in completed_sessions if session.time_block_id])
    average_overrun_minutes = _rounded_average(
        [session.overrun_minutes for session in completed_sessions if session.time_block_id]
    )

    feedback_counter = Counter()
    leakage_reason_counter = Counter()
    focus_drift_sessions = 0
    for session in completed_sessions:
        reasons = [reason.strip() for reason in session.feedback_reasons.split(",") if reason.strip()]
        feedback_counter.update(reasons)
        leakage_reasons = [reason for reason in reasons if reason in LEAKAGE_REASONS]
        leakage_reason_counter.update(leakage_reasons)
        if leakage_reasons:
            focus_drift_sessions += 1

    top_friction_reason = feedback_counter.most_common(1)[0][0] if feedback_counter else None

    summary = InsightsSummary(
        completed_tasks=len(completed_tasks),
        completed_sessions=len(completed_sessions),
        completed_blocks=len(completed_blocks),
        missed_blocks=len(missed_blocks),
        average_prediction_delta_minutes=average_prediction_delta_minutes,
        average_prediction_delta_percent=average_prediction_delta_percent,
        average_delay_minutes=average_delay_minutes,
        average_overrun_minutes=average_overrun_minutes,
        top_friction_reason=top_friction_reason,
    )

    total_delay_minutes = sum(session.delay_minutes for session in completed_sessions if session.time_block_id)
    total_overrun_minutes = sum(session.overrun_minutes for session in completed_sessions if session.time_block_id)
    total_observed_drift_minutes = total_delay_minutes + total_overrun_minutes
    actual_elapsed_minutes = sum(session.elapsed_minutes or 0 for session in completed_sessions)
    predicted_risk_level, predicted_risk_score, predicted_risk_reason = _predict_leakage_risk(
        completed_sessions=completed_sessions,
        leakage_reason_counter=leakage_reason_counter,
        average_delay_minutes=average_delay_minutes,
        average_overrun_minutes=average_overrun_minutes,
        missed_blocks_count=len(missed_blocks),
    )

    leakage = LeakageSummary(
        observed_drift_minutes=total_observed_drift_minutes,
        average_drift_minutes=_rounded_average(
            [session.delay_minutes + session.overrun_minutes for session in completed_sessions if session.time_block_id]
        ),
        drift_rate_percent=int(round((total_observed_drift_minutes / actual_elapsed_minutes) * 100))
        if actual_elapsed_minutes
        else 0,
        delayed_blocks=sum(1 for session in completed_sessions if session.time_block_id and session.delay_minutes > 0),
        overrun_blocks=sum(1 for session in completed_sessions if session.time_block_id and session.overrun_minutes > 0),
        focus_drift_sessions=focus_drift_sessions,
        top_observed_signal=leakage_reason_counter.most_common(1)[0][0] if leakage_reason_counter else None,
        predicted_risk_level=predicted_risk_level,
        predicted_risk_score=predicted_risk_score,
        predicted_risk_reason=predicted_risk_reason,
    )

    all_time_completed_sessions = [session for session in sessions if session.status == "completed"]
    all_time_completed_task_ids = {session.task_id for session in all_time_completed_sessions if session.task_id}
    all_time_completed_tasks = [
        task
        for task in tasks
        if task.id in all_time_completed_task_ids
        and task.status == "completed"
        and task.estimated_minutes is not None
        and task.actual_minutes is not None
    ]
    all_time_average_prediction_delta_percent = _rounded_average(
        [
            (((task.actual_minutes or 0) - (task.estimated_minutes or 0)) / task.estimated_minutes) * 100
            for task in all_time_completed_tasks
            if task.estimated_minutes
        ]
    )
    all_time_average_delay_minutes = _rounded_average(
        [session.delay_minutes for session in all_time_completed_sessions if session.time_block_id]
    )
    all_time_average_overrun_minutes = _rounded_average(
        [session.overrun_minutes for session in all_time_completed_sessions if session.time_block_id]
    )

    task_type_breakdown = _build_task_type_breakdown(completed_tasks, completed_sessions)
    feedback_breakdown = [
        FeedbackInsight(reason=reason, count=count) for reason, count in feedback_counter.most_common(5)
    ]
    top_insights = _build_top_insights(
        summary=summary,
        leakage=leakage,
        task_type_breakdown=task_type_breakdown,
        feedback_breakdown=feedback_breakdown,
    )
    review_narrative = _build_review_narrative(
        period=period,
        summary=summary,
        leakage=leakage,
        task_type_breakdown=task_type_breakdown,
        all_time_average_prediction_delta_percent=all_time_average_prediction_delta_percent,
        all_time_average_delay_minutes=all_time_average_delay_minutes,
        all_time_average_overrun_minutes=all_time_average_overrun_minutes,
    )
    recommended_actions = _build_recommended_actions(
        period=period,
        summary=summary,
        leakage=leakage,
        feedback_breakdown=feedback_breakdown,
        task_type_breakdown=task_type_breakdown,
        all_time_average_prediction_delta_percent=all_time_average_prediction_delta_percent,
        all_time_average_delay_minutes=all_time_average_delay_minutes,
        all_time_average_overrun_minutes=all_time_average_overrun_minutes,
    )

    return InsightsResponse(
        window=InsightsWindow(
            period=period,
            anchor_date=anchor.isoformat(),
            window_start=window_start.isoformat(),
            window_end=window_end.isoformat(),
        ),
        summary=summary,
        leakage=leakage,
        review_narrative=review_narrative,
        recommended_actions=recommended_actions,
        top_insights=top_insights,
        task_type_breakdown=task_type_breakdown,
        feedback_breakdown=feedback_breakdown,
    )


def _build_task_type_breakdown(tasks: list[Task], sessions: list[SessionRecord]) -> list[TaskTypeInsight]:
    sessions_by_task = defaultdict(list)
    for session in sessions:
        if session.task_id and session.status == "completed":
            sessions_by_task[session.task_id].append(session)

    grouped_tasks = defaultdict(list)
    for task in tasks:
        grouped_tasks[task.task_type].append(task)

    breakdown: list[TaskTypeInsight] = []
    for task_type, grouped in grouped_tasks.items():
        relevant_sessions = [session for task in grouped for session in sessions_by_task.get(task.id, [])]
        breakdown.append(
            TaskTypeInsight(
                task_type=task_type,
                completed_tasks=len(grouped),
                average_estimated_minutes=_rounded_average([task.estimated_minutes or 0 for task in grouped]),
                average_actual_minutes=_rounded_average([task.actual_minutes or 0 for task in grouped]),
                average_delta_minutes=_rounded_average(
                    [(task.actual_minutes or 0) - (task.estimated_minutes or 0) for task in grouped]
                ),
                average_delay_minutes=_rounded_average(
                    [session.delay_minutes for session in relevant_sessions if session.time_block_id]
                ),
                average_overrun_minutes=_rounded_average(
                    [session.overrun_minutes for session in relevant_sessions if session.time_block_id]
                ),
            )
        )

    return sorted(breakdown, key=lambda item: (-item.completed_tasks, item.task_type))


def _build_top_insights(
    summary: InsightsSummary,
    leakage: LeakageSummary,
    task_type_breakdown: list[TaskTypeInsight],
    feedback_breakdown: list[FeedbackInsight],
) -> list[InsightCard]:
    insights: list[InsightCard] = []

    if summary.completed_tasks:
        if summary.average_prediction_delta_percent >= 15:
            insights.append(
                InsightCard(
                    title="Tasks usually take longer than planned",
                    detail="Across finished work, your tasks are running longer than the first estimate.",
                    metric_label="Usually longer by",
                    metric_value=f"{summary.average_prediction_delta_percent}%",
                    category="prediction",
                )
            )
        elif summary.average_prediction_delta_percent <= -15:
            insights.append(
                InsightCard(
                    title="Tasks are often finishing sooner",
                    detail="Across finished work, your tasks are wrapping up faster than the estimate expected.",
                    metric_label="Usually shorter by",
                    metric_value=f"{abs(summary.average_prediction_delta_percent)}%",
                    category="prediction",
                )
            )

    if leakage.observed_drift_minutes >= 30:
        insights.append(
            InsightCard(
                title="Scheduled work is leaking extra time",
                detail="Starts are slipping or tasks are stretching long enough to add visible extra time to the day.",
                metric_label="Extra time seen",
                metric_value=_format_minutes(leakage.observed_drift_minutes),
                category="leakage",
            )
        )

    if leakage.drift_rate_percent >= 15:
        insights.append(
            InsightCard(
                title="A noticeable share of time is drifting away",
                detail="A meaningful chunk of logged time is moving away from the plan, so future blocks need more protection.",
                metric_label="Share of time drifting",
                metric_value=f"{leakage.drift_rate_percent}%",
                category="leakage",
            )
        )

    if summary.average_delay_minutes >= 10:
        insights.append(
            InsightCard(
                title="Scheduled blocks usually start late",
                detail="The first place the plan slips is usually at the start of the block.",
                metric_label="Usually late by",
                metric_value=f"{summary.average_delay_minutes}m",
                category="schedule",
            )
        )

    if summary.average_overrun_minutes >= 10:
        insights.append(
            InsightCard(
                title="Tasks often spill past their block",
                detail="Once work starts, it is still carrying beyond the planned finish.",
                metric_label="Usually over by",
                metric_value=f"{summary.average_overrun_minutes}m",
                category="schedule",
            )
        )

    if leakage.top_observed_signal:
        top_reason = next((item for item in feedback_breakdown if item.reason == leakage.top_observed_signal), None)
        if top_reason and top_reason.count >= 2:
            insights.append(
                InsightCard(
                    title=f"{leakage.top_observed_signal} keeps showing up",
                    detail="This is the friction signal that appears most often when execution drifts.",
                    metric_label="Seen",
                    metric_value=str(top_reason.count),
                    category="feedback",
                )
            )

    strongest_task_type = next(
        (item for item in task_type_breakdown if item.completed_tasks >= 2 and abs(item.average_delta_minutes) >= 20),
        None,
    )
    if strongest_task_type:
        drift_direction = "longer" if strongest_task_type.average_delta_minutes > 0 else "shorter"
        insights.append(
            InsightCard(
                title=f"{_format_task_type(strongest_task_type.task_type)} tasks need the most attention",
                detail=f"{_format_task_type(strongest_task_type.task_type)} tasks are usually taking {drift_direction} than planned.",
                metric_label="Typical difference",
                metric_value=_format_minutes(strongest_task_type.average_delta_minutes),
                category="task_type",
            )
        )

    if not insights:
        insights.append(
            InsightCard(
                title="The review is still learning your pattern",
                detail="A few more completed tasks and schedule blocks will make these insights much sharper.",
                metric_label="Completed tasks",
                metric_value=str(summary.completed_tasks),
                category="baseline",
            )
        )

    return insights[:6]


def _build_window(period: str, anchor: date) -> tuple[datetime, datetime]:
    if period == "all":
        return datetime(2020, 1, 1, tzinfo=timezone.utc), datetime.combine(anchor + timedelta(days=1), time.min).replace(
            tzinfo=timezone.utc
        )
    if period == "day":
        start_date = anchor
    elif period == "week":
        start_date = anchor - timedelta(days=6)
    else:
        start_date = anchor - timedelta(days=29)

    start = datetime.combine(start_date, time.min).replace(tzinfo=timezone.utc)
    end = datetime.combine(anchor + timedelta(days=1), time.min).replace(tzinfo=timezone.utc)
    return start, end


def _is_in_window(value: datetime | None, start: datetime, end: datetime) -> bool:
    if value is None:
        return False
    normalized = _normalize_datetime(value)
    return start <= normalized < end


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _rounded_average(values: list[float]) -> int:
    if not values:
        return 0
    return int(round(sum(values) / len(values)))


def _format_task_type(task_type: str) -> str:
    return task_type.replace("_", " ").title()


def _format_minutes(value: int) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value}m"


def _predict_leakage_risk(
    completed_sessions: list[SessionRecord],
    leakage_reason_counter: Counter,
    average_delay_minutes: int,
    average_overrun_minutes: int,
    missed_blocks_count: int,
) -> tuple[str, int, str]:
    risk_score = 0
    if average_delay_minutes >= 10:
        risk_score += 2
    if average_overrun_minutes >= 10:
        risk_score += 2
    if missed_blocks_count >= 2:
        risk_score += 2

    focus_drift_count = sum(
        1
        for session in completed_sessions
        if any(reason.strip() in LEAKAGE_REASONS for reason in session.feedback_reasons.split(",") if reason.strip())
    )
    if focus_drift_count >= 2:
        risk_score += 2

    most_common_signal = leakage_reason_counter.most_common(1)[0][0] if leakage_reason_counter else None
    if most_common_signal:
        risk_score += 1

    if risk_score >= 6:
        level = "high"
    elif risk_score >= 3:
        level = "medium"
    else:
        level = "low"

    if most_common_signal:
        reason = f"Past sessions often include '{most_common_signal}', so similar blocks may drift again."
    elif average_delay_minutes >= 10 or average_overrun_minutes >= 10:
        reason = "Recent scheduled blocks have drifted enough that similar blocks carry some execution risk."
    else:
        reason = "There is not enough repeated drift yet to flag a strong leakage pattern."

    return level, risk_score, reason


def _build_review_narrative(
    period: str,
    summary: InsightsSummary,
    leakage: LeakageSummary,
    task_type_breakdown: list[TaskTypeInsight],
    all_time_average_prediction_delta_percent: int,
    all_time_average_delay_minutes: int,
    all_time_average_overrun_minutes: int,
) -> str:
    if summary.completed_tasks == 0:
        return f"There is not enough finished work in { _format_period_label(period) } yet for a meaningful read. A few completed tasks and scheduled sessions will make this section much sharper."

    strongest_task_type = next(
        (item for item in task_type_breakdown if item.completed_tasks >= 2 and abs(item.average_delta_minutes) >= 15),
        None,
    )
    prediction_shift = summary.average_prediction_delta_percent - all_time_average_prediction_delta_percent
    delay_shift = summary.average_delay_minutes - all_time_average_delay_minutes
    overrun_shift = summary.average_overrun_minutes - all_time_average_overrun_minutes

    if leakage.predicted_risk_level == "high":
        return (
            f"{_format_period_starter(period)} shows a real execution-risk pattern. The biggest issue is not just estimation, but work drifting during execution through delay, overrun, or repeated friction signals."
        )
    if abs(prediction_shift) >= 10:
        direction = "more optimistic" if prediction_shift > 0 else "more realistic"
        return (
            f"{_format_period_starter(period)} you were {direction} than your broader pattern. Prediction drift moved by {abs(prediction_shift)}% compared with your all-time baseline."
        )
    if delay_shift >= 8 or overrun_shift >= 8:
        return (
            f"{_format_period_starter(period)} the main change was schedule execution, not task type. Starts and finishes drifted more than your usual pattern, which is why this window feels heavier."
        )
    if summary.average_prediction_delta_percent >= 15:
        return (
            f"The clearest pattern in {_format_period_label(period)} is underestimation. Tasks are generally taking longer than planned, so tighter estimates and gentler buffers will help more than adding more tasks."
        )
    if strongest_task_type:
        return (
            f"{_format_task_type(strongest_task_type.task_type)} work stands out most in {_format_period_label(period)}. That makes it the best place to tune predictions and schedule protection right now."
        )
    return (
        f"Your plan and execution in {_format_period_label(period)} are starting to line up more closely. The best next step is to keep collecting feedback so the app can separate true task effort from execution drift."
    )


def _build_recommended_actions(
    period: str,
    summary: InsightsSummary,
    leakage: LeakageSummary,
    feedback_breakdown: list[FeedbackInsight],
    task_type_breakdown: list[TaskTypeInsight],
    all_time_average_prediction_delta_percent: int,
    all_time_average_delay_minutes: int,
    all_time_average_overrun_minutes: int,
) -> list[str]:
    actions: list[str] = []
    prediction_shift = summary.average_prediction_delta_percent - all_time_average_prediction_delta_percent
    delay_shift = summary.average_delay_minutes - all_time_average_delay_minutes
    overrun_shift = summary.average_overrun_minutes - all_time_average_overrun_minutes

    if period != "all" and prediction_shift >= 10:
        actions.append(
            f"This {period} is running more optimistically than your usual baseline. Trim the load slightly before adding more blocks."
        )
    elif period != "all" and prediction_shift <= -10:
        actions.append(
            f"This {period} is landing more smoothly than your broader pattern. Keep the current task load and note what made the window easier."
        )

    if summary.average_prediction_delta_percent >= 15:
        actions.append("Trim the number of tasks in each day and allow more room for the tasks you usually underestimate.")
    elif summary.average_prediction_delta_percent <= -15:
        actions.append("Your estimates may be too padded. Try slightly tighter time predictions for familiar task types.")

    if summary.average_delay_minutes >= 10:
        actions.append("Protect your first block more aggressively. The current pattern suggests the schedule often slips at the start.")
    elif period != "all" and delay_shift >= 8:
        actions.append("This window slipped later than usual at the start. Open with one easier block or give yourself a softer runway.")

    if summary.average_overrun_minutes >= 10:
        actions.append("Leave more buffer after heavier tasks instead of packing blocks tightly back to back.")
    elif period != "all" and overrun_shift >= 8:
        actions.append("This window ran longer than your usual block endings. Use a smaller task mix or add one protective gap.")

    top_feedback = feedback_breakdown[0] if feedback_breakdown else None
    if top_feedback:
        if top_feedback.reason == "Interrupted":
            actions.append("Plan important work in a lower-interruption window or add explicit interruption buffer to those blocks.")
        elif top_feedback.reason == "Lost focus":
            actions.append("Shorten long blocks for attention-heavy work and use more natural reset points between tasks.")
        elif top_feedback.reason == "Needed to switch context":
            actions.append("Group similar tasks together so context switching stops eating into the block.")
        elif top_feedback.reason == "Took a break":
            actions.append("Breaks are stretching the real elapsed time, so schedule recovery time explicitly instead of hiding it.")
        elif top_feedback.reason == "Harder than expected":
            actions.append("The task model may be too optimistic. Increase the baseline estimate for similar tasks before scheduling them.")

    drifting_type = next(
        (item for item in task_type_breakdown if item.completed_tasks >= 2 and abs(item.average_delta_minutes) >= 20),
        None,
    )
    if drifting_type:
        actions.append(
            f"Watch {_format_task_type(drifting_type.task_type)} tasks closely. They are drifting the most from plan and deserve the next prediction adjustment."
        )

    if leakage.predicted_risk_level == "high":
        actions.append("Treat high-risk blocks as fragile: start them earlier, reduce surrounding load, and keep a protective buffer.")

    if not actions:
        actions.append(
            f"Keep using the schedule runner and feedback prompt in {_format_period_label(period)}. The review will get much more specific once a few more sessions land."
        )
    if len(actions) == 1:
        if leakage.predicted_risk_level in {"medium", "high"}:
            actions.append("Watch where time starts slipping first. A late start or a stretched finish is often the first visible sign of leakage.")
        else:
            actions.append("Keep logging quick feedback after each block so the app can tell true task effort apart from execution drift.")

    return actions[:5]


def _format_period_label(period: str) -> str:
    if period == "day":
        return "today"
    if period == "week":
        return "this week"
    if period == "month":
        return "this month"
    return "your full history"


def _format_period_starter(period: str) -> str:
    if period == "day":
        return "Today"
    if period == "week":
        return "This week"
    if period == "month":
        return "This month"
    return "Across your full history"
