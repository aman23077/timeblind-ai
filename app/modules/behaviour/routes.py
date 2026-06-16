from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db, save_and_refresh
from app.modules.behaviour.models import BehaviourEvent
from app.modules.behaviour.schemas import BehaviourEventCreate, BehaviourEventRead


router = APIRouter()


@router.post("/events", response_model=BehaviourEventRead)
def create_behaviour_event(
    payload: BehaviourEventCreate,
    db: Session = Depends(get_db),
) -> BehaviourEventRead:
    behaviour_event = BehaviourEvent(**payload.model_dump())
    behaviour_event = save_and_refresh(db, behaviour_event)
    return BehaviourEventRead.model_validate(behaviour_event)


@router.get("/events", response_model=list[BehaviourEventRead])
def list_behaviour_events(
    user_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[BehaviourEventRead]:
    query = select(BehaviourEvent).order_by(BehaviourEvent.occurred_at.desc())
    if user_id:
        query = query.where(BehaviourEvent.user_id == user_id)
    events = db.scalars(query).all()
    return [BehaviourEventRead.model_validate(event) for event in events]
