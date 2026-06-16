from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db, save_and_refresh
from app.core.http import not_found
from app.modules.reasoning.task_decomposer import decompose_task
from app.modules.sessions.models import SessionRecord
from app.modules.tasks.models import Task, TaskDependency, TaskStep
from app.modules.tasks.schemas import (
    TaskCreate,
    TaskDecompositionRequest,
    TaskDecompositionResponse,
    TaskDependencyCreate,
    TaskDependencyRead,
    TaskDetail,
    TaskRead,
    TaskStepCreate,
    TaskStepRead,
    TaskUpdate,
)


router = APIRouter()


@router.post("", response_model=TaskRead)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)) -> TaskRead:
    task = Task(**payload.model_dump())
    task = save_and_refresh(db, task)
    return TaskRead.model_validate(task)


@router.get("", response_model=list[TaskRead])
def list_tasks(
    user_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[TaskRead]:
    query = select(Task).order_by(Task.created_at.desc())
    if user_id:
        query = query.where(Task.user_id == user_id)
    tasks = db.scalars(query).all()
    return [TaskRead.model_validate(task) for task in tasks]


@router.get("/{task_id}", response_model=TaskDetail)
def get_task(task_id: str, db: Session = Depends(get_db)) -> TaskDetail:
    task = db.get(Task, task_id)
    if task is None:
        raise not_found("Task", task_id)
    return _task_detail(db, task)


@router.patch("/{task_id}", response_model=TaskRead)
def update_task(task_id: str, payload: TaskUpdate, db: Session = Depends(get_db)) -> TaskRead:
    task = db.get(Task, task_id)
    if task is None:
        raise not_found("Task", task_id)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, field, value)

    task = save_and_refresh(db, task)
    return TaskRead.model_validate(task)


@router.post("/{task_id}/steps", response_model=TaskStepRead)
def create_task_step(task_id: str, payload: TaskStepCreate, db: Session = Depends(get_db)) -> TaskStepRead:
    task = db.get(Task, task_id)
    if task is None:
        raise not_found("Task", task_id)
    step = TaskStep(task_id=task_id, **payload.model_dump())
    step = save_and_refresh(db, step)
    return TaskStepRead.model_validate(step)


@router.post("/{task_id}/dependencies", response_model=TaskDependencyRead)
def create_task_dependency(
    task_id: str,
    payload: TaskDependencyCreate,
    db: Session = Depends(get_db),
) -> TaskDependencyRead:
    task = db.get(Task, task_id)
    depends_on = db.get(Task, payload.depends_on_task_id)
    if task is None:
        raise not_found("Task", task_id)
    if depends_on is None:
        raise not_found("Task", payload.depends_on_task_id)
    dependency = TaskDependency(task_id=task_id, **payload.model_dump())
    dependency = save_and_refresh(db, dependency)
    return TaskDependencyRead.model_validate(dependency)


@router.post("/decompose", response_model=TaskDecompositionResponse)
def decompose_task_route(payload: TaskDecompositionRequest, db: Session = Depends(get_db)) -> TaskDecompositionResponse:
    multiplier, confidence = _prediction_profile(db, payload.user_id, payload.task_type)
    return decompose_task(payload, personalization_multiplier=multiplier, prediction_confidence=confidence)


def _task_detail(db: Session, task: Task) -> TaskDetail:
    steps = db.scalars(
        select(TaskStep).where(TaskStep.task_id == task.id).order_by(TaskStep.order_index.asc())
    ).all()
    dependencies = db.scalars(
        select(TaskDependency).where(TaskDependency.task_id == task.id).order_by(TaskDependency.created_at.asc())
    ).all()
    return TaskDetail.model_validate(
        {
            **task.__dict__,
            "steps": steps,
            "dependencies": dependencies,
        }
    )


def _prediction_profile(db: Session, user_id: str | None, task_type: str) -> tuple[float, str]:
    if not user_id:
        return 1.0, "low"

    candidate_tasks = _task_history(db, user_id, task_type)
    if len(candidate_tasks) < 2:
        candidate_tasks = _task_history(db, user_id, None)

    if not candidate_tasks:
        return 1.03, "low"

    sessions_by_task = _session_feedback_by_task(db, [task.id for task in candidate_tasks])
    effective_ratios: list[float] = []
    for task in candidate_tasks:
        if not task.estimated_minutes:
            continue
        effective_ratios.append(_effective_ratio(task, sessions_by_task.get(task.id, [])))

    if not effective_ratios:
        return 1.03, "low"

    prior_weight = 6
    smoothed_ratio = (prior_weight + sum(effective_ratios)) / (prior_weight + len(effective_ratios))
    bounded_ratio = max(0.9, min(1.25, smoothed_ratio))

    if len(effective_ratios) >= 6:
        confidence = "high"
    elif len(effective_ratios) >= 3:
        confidence = "medium"
    else:
        confidence = "low"

    return bounded_ratio, confidence


def _task_history(db: Session, user_id: str, task_type: str | None) -> list[Task]:
    query = select(Task).where(
        Task.user_id == user_id,
        Task.estimated_minutes.is_not(None),
        Task.actual_minutes.is_not(None),
        Task.estimated_minutes >= 15,
        Task.actual_minutes >= 1,
    )
    if task_type is not None:
        query = query.where(Task.task_type == task_type)
    return db.scalars(query).all()


def _session_feedback_by_task(db: Session, task_ids: list[str]) -> dict[str, list[SessionRecord]]:
    if not task_ids:
        return {}

    sessions = db.scalars(
        select(SessionRecord).where(
            SessionRecord.task_id.in_(task_ids),
            SessionRecord.status == "completed",
            SessionRecord.ended_at.is_not(None),
        )
    ).all()

    sessions_by_task: dict[str, list[SessionRecord]] = {}
    for session in sessions:
        if session.task_id is None:
            continue
        sessions_by_task.setdefault(session.task_id, []).append(session)
    return sessions_by_task


def _effective_ratio(task: Task, sessions: list[SessionRecord]) -> float:
    if not task.estimated_minutes or not task.actual_minutes:
        return 1.0

    observed_ratio = max(0.6, min(1.8, task.actual_minutes / task.estimated_minutes))
    ratio_delta = observed_ratio - 1.0
    estimate_weight = 0.6
    note_adjustment = 0.0

    for session in sessions:
        estimate_weight += _outcome_weight_delta(session.difficulty_feedback)
        for reason in _split_feedback_reasons(session.feedback_reasons):
            estimate_weight += _reason_weight_delta(reason)
        note_adjustment += _notes_adjustment(session.feedback_notes)

    if sessions:
        note_adjustment /= len(sessions)

    weighted_ratio = 1.0 + ratio_delta * max(0.15, min(1.0, estimate_weight))
    return max(0.85, min(1.25, weighted_ratio + note_adjustment))


def _outcome_weight_delta(outcome: str) -> float:
    if outcome == "longer_than_expected":
        return 0.18
    if outcome == "less_than_expected":
        return 0.08
    if outcome == "as_expected":
        return 0.1
    return 0.0


def _reason_weight_delta(reason: str) -> float:
    normalized = reason.strip().lower()
    estimate_signal_weights = {
        "harder than expected": 0.34,
        "easier than expected": 0.22,
        "already familiar with it": 0.18,
        "estimate was too high": 0.2,
        "worked with strong focus": -0.05,
        "other": 0.04,
    }
    leakage_signal_weights = {
        "interrupted": -0.2,
        "lost focus": -0.14,
        "took a break": -0.2,
        "needed to switch context": -0.1,
        "environment distraction": -0.2,
    }
    if normalized in estimate_signal_weights:
        return estimate_signal_weights[normalized]
    if normalized in leakage_signal_weights:
        return leakage_signal_weights[normalized]
    return 0.0


def _notes_adjustment(notes: str) -> float:
    normalized = notes.lower()
    if not normalized.strip():
        return 0.0

    adjustment = 0.0
    if any(token in normalized for token in ("hard", "harder", "confusing", "stuck", "debug", "unexpected")):
        adjustment += 0.03
    if any(token in normalized for token in ("easy", "easier", "quick", "simple", "familiar", "revision")):
        adjustment -= 0.025
    if any(token in normalized for token in ("interrupt", "call", "noise", "phone", "family", "door")):
        adjustment += 0.005
    if any(token in normalized for token in ("break", "lunch", "rest", "pause")):
        adjustment += 0.003
    return max(-0.03, min(0.04, adjustment))


def _split_feedback_reasons(reasons: str) -> list[str]:
    return [reason.strip() for reason in reasons.split(",") if reason.strip()]
