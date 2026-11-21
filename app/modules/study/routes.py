"""Authenticated, consent-scoped pilot collection and pseudonymous analysis."""
import csv
import io
import json
import statistics
import zipfile
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import aware, get_current_user
from app.core.database import get_db, utc_now
from app.modules.reasoning.task_decomposer import decompose_task
from app.modules.sessions.models import SessionRecord
from app.modules.study.models import PROTOCOL, StudyEnrollment, StudyFeedback, StudyTask, StudyTiming, StudyScheduleTrial
from app.modules.tasks.models import Task, TaskStep
from app.modules.tasks.schemas import TaskDecompositionRequest, TaskDifficulty, TaskType
from app.modules.users.admin_routes import require_admin
from app.modules.users.models import User

router = APIRouter()


class TrialReview(BaseModel):
    feasible: int = Field(ge=1, le=5)
    ordering: int = Field(ge=1, le=5)
    feedback_useful: int = Field(ge=1, le=5)
    explanation_clear: int = Field(ge=1, le=5)
    comments: str = Field(default="", max_length=1000)


class EnrollmentInput(BaseModel):
    adult: Literal[True]
    consent: Literal[True]
    baseline_frequency: Literal["never", "rarely", "sometimes", "often", "very_often"]


class TaskInput(BaseModel):
    title: str = Field(min_length=5, max_length=180)
    task_type: TaskType = "study"
    difficulty: TaskDifficulty = "medium"
    user_estimate_minutes: int = Field(ge=5, le=180)


class TrialInput(BaseModel):
    tasks: list[TaskInput] = Field(min_length=3, max_length=3)
    window_minutes: int = Field(ge=15, le=480)


@router.post("/scheduler")
def scheduler_trial(payload: TrialInput, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    member = enrollment(db, user)
    count = db.scalar(select(func.count()).select_from(StudyTask).where(StudyTask.enrollment_id == member.id, StudyTask.outcome.in_(["completed", "unfinished"])))
    if count < 3:
        raise HTTPException(409, "Record three task attempts before the scheduler exercise")
    from app.modules.schedules.planner import build_schedule_blocks
    from app.core.database import new_id
    start = utc_now()
    end = start + timedelta(minutes=payload.window_minutes)
    tasks = [Task(id=new_id(), user_id=user.id, title=t.title, task_type=t.task_type, difficulty=t.difficulty,
                  estimated_minutes=t.user_estimate_minutes, priority="medium", status="pending", created_at=start) for t in payload.tasks]
    blocks, deferred = build_schedule_blocks(db, new_id(), user.id, tasks, start, end, 5)
    ordered = sorted(blocks, key=lambda b: b.start_at)
    checks = {"within_window": all(aware(b.start_at) >= start and aware(b.end_at) <= end for b in blocks),
              "no_overlap": all(aware(a.end_at) <= aware(b.start_at) for a, b in zip(ordered, ordered[1:])),
              "positive_duration": all(b.end_at > b.start_at for b in blocks)}
    snapshot = {"kind": "hypothetical_scheduler_exercise", "window_minutes": payload.window_minutes,
                "blocks": [{"title": b.title, "start_at": aware(b.start_at).isoformat(), "end_at": aware(b.end_at).isoformat(), "kind": b.kind} for b in blocks],
                "deferred": [{"title": r.get("title"), "reason": r.get("reason")} for r in deferred], "checks": checks,
                "task_count": len(tasks), "scheduled_tasks": sum(b.task_id is not None for b in blocks),
                "guidance": "Five-minute breaks are included where feasible. Deferred tasks did not fit the available window. This exercise tests a proposed plan, not actual execution."}
    row = StudyScheduleTrial(enrollment_id=member.id, snapshot=snapshot)
    db.add(row)
    db.commit()
    return {"id": row.id, "snapshot": snapshot, "review": None}


@router.post("/scheduler/{trial_id}/review")
def trial_review(trial_id: str, payload: TrialReview, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    member = enrollment(db, user)
    row = db.get(StudyScheduleTrial, trial_id)
    if row is None or row.enrollment_id != member.id:
        raise HTTPException(404, "Scheduler exercise not found")
    row.review = payload.model_dump()
    db.commit()
    return {"saved": True}


class OutcomeInput(BaseModel):
    timing_source: Literal["timer", "recalled_real", "rehearsal"] = "timer"
    manual_minutes: float | None = Field(default=None, ge=1, le=1440, allow_inf_nan=False)
    outcome: Literal["completed", "unfinished"]
    break_minutes: float = Field(ge=0, le=1440, allow_inf_nan=False)
    scope_changed: bool
    friction: Literal["none", "interruption", "harder_than_expected", "unclear_scope", "technical_problem", "other"]


class FeedbackInput(BaseModel):
    ease: int = Field(ge=1, le=5)
    clarity: int = Field(ge=1, le=5)
    usefulness: int = Field(ge=1, le=5)
    trust: int = Field(ge=1, le=5)
    use_again: int = Field(ge=1, le=5)
    best_part: str = Field(default="", max_length=1000)
    biggest_problem: str = Field(default="", max_length=1000)
    suggestion: str = Field(default="", max_length=1000)


def enrollment(db, user, active=True):
    row = db.scalar(select(StudyEnrollment).where(StudyEnrollment.user_id == user.id))
    if active and (row is None or row.withdrawn_at is not None):
        raise HTTPException(403, "Join the study before recording tasks. Withdrawn participation cannot be resumed.")
    return row


def owned_task(db, user, record_id):
    member = enrollment(db, user)
    record = db.get(StudyTask, record_id)
    if record is None or record.enrollment_id != member.id:
        raise HTTPException(404, "Study task not found")
    return record


def task_data(row, db=None):
    fields = ["id", "task_id", "session_id", "title", "task_type", "difficulty", "user_estimate_minutes",
              "rules_estimate_minutes", "prediction_method", "predicted_at", "started_at", "completed_at",
              "elapsed_minutes", "break_minutes", "actual_minutes", "scope_changed", "outcome", "friction"]
    result = {field: getattr(row, field) for field in fields}
    timing = db.scalar(select(StudyTiming).where(StudyTiming.record_id == row.id)) if db else None
    result["timing_source"] = timing.source if timing else "timer"
    for key in ("predicted_at", "started_at", "completed_at"):
        result[key] = aware(result[key]).isoformat() if result[key] else None
    result["steps"] = [{"title": s.title, "minutes": s.suggested_minutes} for s in db.scalars(
        select(TaskStep).where(TaskStep.task_id == row.task_id).order_by(TaskStep.order_index)).all()] if db else []
    return result


@router.get("/me")
def status(response: Response, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    response.headers["Cache-Control"] = "no-store"
    member = enrollment(db, user, active=False)
    records = db.scalars(select(StudyTask).where(StudyTask.enrollment_id == member.id).order_by(StudyTask.created_at)).all() if member else []
    feedback = db.scalar(select(StudyFeedback).where(StudyFeedback.enrollment_id == member.id)) if member else None
    return {"protocol": PROTOCOL, "enrolled": member is not None, "withdrawn": bool(member and member.withdrawn_at),
            "schedule_trials": [{"id": r.id, "snapshot": r.snapshot, "review": r.review} for r in db.scalars(select(StudyScheduleTrial).where(StudyScheduleTrial.enrollment_id == member.id).order_by(StudyScheduleTrial.created_at)).all()] if member else [],
            "participant_code": member.id if member else None, "feedback_submitted": feedback is not None,
            "feedback": {key: getattr(feedback, key) for key in FeedbackInput.model_fields} if feedback else None,
            "tasks": [task_data(row, db) for row in records]}


@router.post("/enroll")
def enroll(payload: EnrollmentInput, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    previous = enrollment(db, user, active=False)
    if previous:
        if previous.withdrawn_at:
            raise HTTPException(409, "This study participation was withdrawn")
        return {"participant_code": previous.id}
    member = StudyEnrollment(user_id=user.id, baseline_frequency=payload.baseline_frequency)
    db.add(member)
    user.consent_to_research = "true"
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Participation already exists. Refresh this page.") from None
    return {"participant_code": member.id}


@router.post("/withdraw")
def withdraw(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    member = enrollment(db, user, active=False)
    if not member:
        raise HTTPException(404, "Study participation not found")
    member.withdrawn_at = member.withdrawn_at or utc_now()
    user.consent_to_research = "false"
    # Preserve the consent audit record; all dedicated study exports exclude it.
    db.commit()
    return {"withdrawn": True}


@router.post("/tasks")
def create_task(payload: TaskInput, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    member = enrollment(db, user)
    # The user's guess is deliberately omitted from the rules input. No provider call.
    plan = decompose_task(TaskDecompositionRequest(title=payload.title, task_type=payload.task_type,
                                                 difficulty=payload.difficulty), 1.0, "low")
    task = Task(user_id=user.id, title=payload.title, task_type=payload.task_type, difficulty=payload.difficulty,
                estimated_minutes=plan.personalized_estimate_minutes)
    db.add(task)
    db.flush()
    for step in plan.steps:
        db.add(TaskStep(task_id=task.id, title=step.title, order_index=step.order,
                        suggested_minutes=step.suggested_minutes, rationale=step.rationale))
    record = StudyTask(enrollment_id=member.id, task_id=task.id, title=payload.title, task_type=payload.task_type,
                       difficulty=payload.difficulty, user_estimate_minutes=payload.user_estimate_minutes,
                       rules_estimate_minutes=plan.personalized_estimate_minutes, predicted_at=utc_now())
    db.add(record)
    db.commit()
    return task_data(record)


@router.post("/tasks/{record_id}/start")
def start(record_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    record = owned_task(db, user, record_id)
    if record.outcome != "planned":
        raise HTTPException(409, "Task has already started or finished")
    member = enrollment(db, user)
    if db.scalar(select(StudyTask.id).where(StudyTask.enrollment_id == member.id, StudyTask.outcome == "active")):
        raise HTTPException(409, "Finish your current study task before starting another")
    now = utc_now()
    try:
        claimed = db.execute(update(StudyTask).where(StudyTask.id == record.id, StudyTask.outcome == "planned").values(outcome="active", started_at=now))
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Another study task is already active") from None
    if claimed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Task has already started or finished")
    session = SessionRecord(user_id=user.id, task_id=record.task_id, started_at=now, actual_start=now)
    db.add(session)
    db.flush()
    record.session_id, record.started_at, record.outcome = session.id, now, "active"
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Another study task is already active") from None
    return task_data(record)


@router.post("/tasks/{record_id}/finish")
def finish(record_id: str, payload: OutcomeInput, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    record = owned_task(db, user, record_id)
    if record.outcome != "active" or not record.started_at:
        raise HTTPException(409, "Only an active study task can be finished")
    now = utc_now()
    elapsed = (now - aware(record.started_at)).total_seconds() / 60
    if payload.timing_source != "timer" and payload.manual_minutes is None:
        raise HTTPException(422, "Enter manually reported work minutes")
    if payload.timing_source == "timer" and payload.break_minutes >= elapsed:
        raise HTTPException(422, "Break time must be less than the recorded session time")
    claimed = db.execute(update(StudyTask).where(StudyTask.id == record.id, StudyTask.outcome == "active").values(outcome=payload.outcome))
    if claimed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "This task outcome was already saved")
    record.completed_at, record.elapsed_minutes = now, round(elapsed, 3)
    record.break_minutes, record.actual_minutes = payload.break_minutes, round(elapsed - payload.break_minutes, 3)
    if payload.timing_source != "timer":
        record.actual_minutes = payload.manual_minutes
    db.add(StudyTiming(record_id=record.id, source=payload.timing_source))
    record.scope_changed, record.outcome, record.friction = payload.scope_changed, payload.outcome, payload.friction
    session = db.get(SessionRecord, record.session_id)
    session.ended_at = session.actual_end = now
    session.elapsed_minutes = round(elapsed)  # Ordinary app measures wall time, study actual excludes reported breaks.
    session.status = "completed" if payload.outcome == "completed" else "cancelled"
    session.feedback_reasons = payload.friction
    task = db.get(Task, record.task_id)
    task.status = "completed" if payload.outcome == "completed" else "pending"
    task.actual_minutes = round(record.actual_minutes) if payload.outcome == "completed" and payload.timing_source == "timer" else None
    from app.modules.behaviour.activity import ActivityMonitor
    db.execute(update(ActivityMonitor).where(ActivityMonitor.session_id == session.id).values(enabled=False))
    db.commit()
    return task_data(record)


@router.post("/feedback")
def feedback(payload: FeedbackInput, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    member = enrollment(db, user)
    if not db.scalar(select(StudyTask.id).where(StudyTask.enrollment_id == member.id,
                                              StudyTask.outcome.in_(["completed", "unfinished"]))):
        raise HTTPException(409, "Try at least one task before submitting final feedback")
    row = db.scalar(select(StudyFeedback).where(StudyFeedback.enrollment_id == member.id))
    if row is None:
        row = StudyFeedback(enrollment_id=member.id, **payload.model_dump())
        db.add(row)
    else:
        for key, value in payload.model_dump().items():
            setattr(row, key, value)
    db.commit()
    return {"saved": True}


def study_data(db):
    members = db.scalars(select(StudyEnrollment).join(User, User.id == StudyEnrollment.user_id).where(
        StudyEnrollment.withdrawn_at.is_(None), User.consent_to_research == "true")).all()
    ids = [row.id for row in members]
    records = db.scalars(select(StudyTask).where(StudyTask.enrollment_id.in_(ids)).order_by(StudyTask.created_at)).all()
    timing = {r.record_id: r.source for r in db.scalars(select(StudyTiming)).all()}
    for r in records:
        r.timing_source = timing.get(r.id, "timer")
    responses = db.scalars(select(StudyFeedback).where(StudyFeedback.enrollment_id.in_(ids))).all()
    return members, records, responses


def eligible(row):
    return getattr(row, "timing_source", "timer") == "timer" and row.outcome == "completed" and row.scope_changed is False and row.actual_minutes is not None and row.actual_minutes >= 1


def summary_data(db):
    members, records, responses = study_data(db)
    valid = [row for row in records if eligible(row)]
    methods = {}
    for name in ("user", "rules"):
        errors = [abs(getattr(row, f"{name}_estimate_minutes") - row.actual_minutes) for row in valid]
        per_person = []
        for member in members:
            group = [abs(getattr(row, f"{name}_estimate_minutes") - row.actual_minutes) for row in valid if row.enrollment_id == member.id]
            if group:
                per_person.append(statistics.mean(group))
        methods[name] = {"tasks": len(errors), "participants": len(per_person),
                         "mae_minutes": round(statistics.mean(errors), 2) if errors else None,
                         "median_absolute_error_minutes": round(statistics.median(errors), 2) if errors else None,
                         "within_15_percent": round(100 * sum(e <= 15 for e in errors) / len(errors), 2) if errors else None,
                         "participant_mean_mae_minutes": round(statistics.mean(per_person), 2) if per_person else None}
    ratings = {}
    for field in ("ease", "clarity", "usefulness", "trust", "use_again"):
        values = [getattr(row, field) for row in responses]
        ratings[field] = {"n": len(values), "median": statistics.median(values) if values else None,
                          "counts_1_to_5": [values.count(n) for n in range(1, 6)]}
    trials = db.scalars(select(StudyScheduleTrial).where(StudyScheduleTrial.enrollment_id.in_([m.id for m in members]))).all()
    scheduler = {"exercises": len(trials), "reviewed": sum(t.review is not None for t in trials),
                 "constraint_pass_count": sum(all(t.snapshot["checks"].values()) for t in trials),
                 "ratings": {k: [sum(t.review is not None and t.review[k] == n for t in trials) for n in range(1, 6)] for k in ("feasible", "ordering", "feedback_useful", "explanation_clear")}}
    return {"scheduler": scheduler, "timing_sources": {k: sum(r.timing_source == k for r in records) for k in ("timer", "recalled_real", "rehearsal")}, "protocol": PROTOCOL, "consenting_participants": len(members), "recorded_tasks": len(records),
            "started_tasks": sum(row.started_at is not None for row in records),
            "completed_tasks": sum(row.outcome == "completed" for row in records),
            "unfinished_tasks": sum(row.outcome == "unfinished" for row in records),
            "active_tasks": sum(row.outcome == "active" for row in records), "eligible_tasks": len(valid),
            "participants_with_three_completed_tasks": sum(sum(r.enrollment_id == m.id and r.outcome == "completed" for r in records) >= 3 for m in members),
            "excluded_completed_tasks": sum(row.outcome == "completed" and not eligible(row) for row in records),
            "feedback_responses": len(responses), "methods": methods, "ratings": ratings,
            "interpretation": "Exploratory convenience-sample pilot. Repeated tasks are clustered within participants. No causal or clinical conclusions."}


@router.get("/admin/summary", dependencies=[Depends(require_admin)])
def summary(response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return summary_data(db)


@router.get("/admin/export", dependencies=[Depends(require_admin)])
def export(db: Session = Depends(get_db)):
    members, records, responses = study_data(db)
    output = io.BytesIO()
    def write_csv(archive, name, fields, rows):
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        archive.writestr(name, buffer.getvalue())
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        write_csv(archive, "participants.csv", ["participant_code", "protocol", "baseline_frequency", "enrolled_at"],
                  [{"participant_code": m.id, "protocol": m.protocol, "baseline_frequency": m.baseline_frequency, "enrolled_at": aware(m.created_at).isoformat()} for m in members])
        # Exclude task titles, app user IDs, emails and free text from the report-safe export.
        fields = ["participant_code", "record_id", "task_type", "difficulty", "user_estimate_minutes", "rules_estimate_minutes", "prediction_method", "predicted_at", "started_at", "completed_at", "elapsed_minutes", "break_minutes", "actual_minutes", "timing_source", "scope_changed", "outcome", "friction", "eligible"]
        rows = []
        for r in records:
            row = {key: getattr(r, key) for key in fields if hasattr(r, key)}
            row.update(participant_code=r.enrollment_id, record_id=r.id, eligible=eligible(r))
            for key in ("predicted_at", "started_at", "completed_at"):
                row[key] = aware(row[key]).isoformat() if row[key] else ""
            rows.append(row)
        write_csv(archive, "tasks.csv", fields, rows)
        fields = ["participant_code", "ease", "clarity", "usefulness", "trust", "use_again"]
        write_csv(archive, "feedback.csv", fields, [{**{key: getattr(r, key) for key in fields if key != "participant_code"}, "participant_code": r.enrollment_id} for r in responses])
        trials = db.scalars(select(StudyScheduleTrial).where(StudyScheduleTrial.enrollment_id.in_([m.id for m in members]))).all()
        archive.writestr("scheduler.json", json.dumps([{"participant_code": t.enrollment_id, "trial_id": t.id, "checks": t.snapshot["checks"], "review": {k: v for k, v in (t.review or {}).items() if k != "comments"}} for t in trials], indent=2))
        archive.writestr("summary.json", json.dumps(summary_data(db), indent=2))
        archive.writestr("README.txt", "Consenting, non-withdrawn pilot records only. No email, task title, user ID or free text. Timing is server elapsed minus self-reported breaks. Study tasks use frozen unpersonalized rules, not LLM inference. Pseudonymous data is not anonymous. Store privately; do not commit participant exports.\n")
    return Response(output.getvalue(), media_type="application/zip", headers={"Cache-Control": "no-store", "Content-Disposition": 'attachment; filename="timeblind-pilot.zip"'})


@router.get("/admin/comments", dependencies=[Depends(require_admin)])
def comments(response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    _, _, responses = study_data(db)
    return [{"participant_code": r.enrollment_id, "best_part": r.best_part,
             "biggest_problem": r.biggest_problem, "suggestion": r.suggestion} for r in responses]
