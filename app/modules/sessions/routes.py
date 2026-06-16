from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db, save_and_refresh
from app.core.http import not_found
from app.modules.schedules.models import TimeBlock
from app.modules.sessions.models import SessionRecord
from app.modules.sessions.schemas import SessionCreate, SessionEndRequest, SessionRead
from app.modules.tasks.models import Task


router = APIRouter()


@router.post("", response_model=SessionRead)
def create_session(payload: SessionCreate, db: Session = Depends(get_db)) -> SessionRead:
    data = payload.model_dump()
    data["actual_start"] = data["actual_start"] or data["started_at"]
    session_record = SessionRecord(**data)
    if session_record.time_block_id:
        block = db.get(TimeBlock, session_record.time_block_id)
        if block is not None:
            block.status = "active"
            block.actual_start = session_record.actual_start
            block.delay_minutes = max(
                0,
                round((_normalize_datetime(session_record.actual_start) - _normalize_datetime(block.start_at)).total_seconds() / 60),
            )
            session_record.delay_minutes = block.delay_minutes
            save_and_refresh(db, block)
    session_record = save_and_refresh(db, session_record)
    return SessionRead.model_validate(session_record)


@router.get("", response_model=list[SessionRead])
def list_sessions(
    user_id: str | None = Query(default=None),
    task_id: str | None = Query(default=None),
    time_block_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[SessionRead]:
    query = select(SessionRecord).order_by(SessionRecord.started_at.desc())
    if user_id:
        query = query.where(SessionRecord.user_id == user_id)
    if task_id:
        query = query.where(SessionRecord.task_id == task_id)
    if time_block_id:
        query = query.where(SessionRecord.time_block_id == time_block_id)
    sessions = db.scalars(query).all()
    return [SessionRead.model_validate(session_record) for session_record in sessions]


@router.patch("/{session_id}/end", response_model=SessionRead)
def end_session(
    session_id: str,
    payload: SessionEndRequest,
    db: Session = Depends(get_db),
) -> SessionRead:
    session_record = db.get(SessionRecord, session_id)
    if session_record is None:
        raise not_found("Session", session_id)
    session_record.ended_at = payload.ended_at
    session_record.actual_end = payload.actual_end or payload.ended_at
    session_record.elapsed_minutes = max(
        0,
        int(round((_normalize_datetime(session_record.actual_end) - _normalize_datetime(session_record.started_at)).total_seconds() / 60)),
    )
    session_record.status = payload.status
    session_record.difficulty_feedback = payload.difficulty_feedback
    session_record.feedback_reasons = ",".join(payload.feedback_reasons)
    session_record.feedback_notes = payload.feedback_notes
    session_record = save_and_refresh(db, session_record)

    if session_record.time_block_id:
        block = db.get(TimeBlock, session_record.time_block_id)
        if block is not None:
            block.actual_end = session_record.actual_end
            if session_record.status == "completed":
                block.status = "completed"
            elif session_record.status == "cancelled":
                block.status = "planned"
            scheduled_end = block.end_at
            block.overrun_minutes = max(
                0,
                round((_normalize_datetime(session_record.actual_end) - _normalize_datetime(scheduled_end)).total_seconds() / 60),
            )
            session_record.overrun_minutes = block.overrun_minutes
            session_record.delay_minutes = block.delay_minutes
            session_record = save_and_refresh(db, session_record)
            save_and_refresh(db, block)

    if session_record.task_id and session_record.status == "completed":
        task = db.get(Task, session_record.task_id)
        if task is not None:
            completed_sessions = db.scalars(
                select(SessionRecord).where(
                    SessionRecord.task_id == session_record.task_id,
                    SessionRecord.status == "completed",
                    SessionRecord.ended_at.is_not(None),
                )
            ).all()
            task.actual_minutes = sum(
                int(round((record.ended_at - record.started_at).total_seconds() / 60))
                for record in completed_sessions
                if record.ended_at is not None
            )
            task.status = "completed"
            save_and_refresh(db, task)

    return SessionRead.model_validate(session_record)


def _normalize_datetime(value):
    if value.tzinfo is None:
        from datetime import timezone

        return value.replace(tzinfo=timezone.utc)
    from datetime import timezone

    return value.astimezone(timezone.utc)
