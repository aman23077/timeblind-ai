from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db, save_and_refresh
from app.modules.context.models import ContextEvent
from app.modules.context.schemas import ContextEventCreate, ContextEventRead


router = APIRouter()


@router.post("/events", response_model=ContextEventRead)
def create_context_event(payload: ContextEventCreate, db: Session = Depends(get_db)) -> ContextEventRead:
    context_event = ContextEvent(**payload.model_dump())
    context_event = save_and_refresh(db, context_event)
    return ContextEventRead.model_validate(context_event)


@router.get("/events", response_model=list[ContextEventRead])
def list_context_events(
    user_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[ContextEventRead]:
    query = select(ContextEvent).order_by(ContextEvent.occurred_at.desc())
    if user_id:
        query = query.where(ContextEvent.user_id == user_id)
    events = db.scalars(query).all()
    return [ContextEventRead.model_validate(event) for event in events]
