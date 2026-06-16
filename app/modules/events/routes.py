from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db, save_and_refresh
from app.core.http import not_found
from app.modules.events.models import Event, EventPrepItem
from app.modules.events.schemas import (
    EventCreate,
    EventDetail,
    EventPlanRequest,
    EventPlanResponse,
    EventPrepItemCreate,
    EventPrepItemRead,
    EventPreparationTask,
    EventRead,
)
from app.modules.reasoning.event_planner import build_event_plan


router = APIRouter()


@router.post("", response_model=EventRead)
def create_event(payload: EventCreate, db: Session = Depends(get_db)) -> EventRead:
    event = Event(**payload.model_dump())
    event = save_and_refresh(db, event)
    return EventRead.model_validate(event)


@router.get("", response_model=list[EventRead])
def list_events(
    user_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[EventRead]:
    query = select(Event).order_by(Event.start_at.asc())
    if user_id:
        query = query.where(Event.user_id == user_id)
    events = db.scalars(query).all()
    return [EventRead.model_validate(event) for event in events]


@router.get("/{event_id}", response_model=EventDetail)
def get_event(event_id: str, db: Session = Depends(get_db)) -> EventDetail:
    event = db.get(Event, event_id)
    if event is None:
        raise not_found("Event", event_id)
    return _event_detail(db, event)


@router.post("/{event_id}/prep-items", response_model=EventPrepItemRead)
def create_event_prep_item(
    event_id: str,
    payload: EventPrepItemCreate,
    db: Session = Depends(get_db),
) -> EventPrepItemRead:
    event = db.get(Event, event_id)
    if event is None:
        raise not_found("Event", event_id)
    prep_item = EventPrepItem(event_id=event_id, **payload.model_dump())
    prep_item = save_and_refresh(db, prep_item)
    return EventPrepItemRead.model_validate(prep_item)


@router.post("/prepare-plan", response_model=EventPlanResponse)
def prepare_event_plan(payload: EventPlanRequest) -> EventPlanResponse:
    return build_event_plan(payload)


@router.post("/{event_id}/prepare-plan", response_model=EventPlanResponse)
def prepare_stored_event_plan(event_id: str, db: Session = Depends(get_db)) -> EventPlanResponse:
    event = db.get(Event, event_id)
    if event is None:
        raise not_found("Event", event_id)
    prep_items = db.scalars(
        select(EventPrepItem).where(EventPrepItem.event_id == event_id).order_by(EventPrepItem.order_index.asc())
    ).all()
    payload = EventPlanRequest(
        title=event.title,
        start_at=event.start_at,
        commute_minutes=event.commute_minutes,
        get_ready_minutes=event.get_ready_minutes,
        departure_buffer_minutes=event.departure_buffer_minutes,
        prep_tasks=[
            EventPreparationTask(title=item.title, minutes=item.minutes, required=item.required)
            for item in prep_items
        ],
    )
    return build_event_plan(payload)


def _event_detail(db: Session, event: Event) -> EventDetail:
    prep_items = db.scalars(
        select(EventPrepItem).where(EventPrepItem.event_id == event.id).order_by(EventPrepItem.order_index.asc())
    ).all()
    return EventDetail.model_validate({**event.__dict__, "prep_items": prep_items})
