from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db, save_and_refresh
from app.modules.interventions.models import Intervention, Reminder
from app.modules.interventions.schemas import (
    InterventionCreate,
    InterventionRead,
    ReminderCreate,
    ReminderRead,
)


router = APIRouter()


@router.post("/reminders", response_model=ReminderRead)
def create_reminder(payload: ReminderCreate, db: Session = Depends(get_db)) -> ReminderRead:
    reminder = Reminder(**payload.model_dump())
    reminder = save_and_refresh(db, reminder)
    return ReminderRead.model_validate(reminder)


@router.get("/reminders", response_model=list[ReminderRead])
def list_reminders(
    user_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[ReminderRead]:
    query = select(Reminder).order_by(Reminder.trigger_at.asc())
    if user_id:
        query = query.where(Reminder.user_id == user_id)
    reminders = db.scalars(query).all()
    return [ReminderRead.model_validate(reminder) for reminder in reminders]


@router.post("", response_model=InterventionRead)
def create_intervention(payload: InterventionCreate, db: Session = Depends(get_db)) -> InterventionRead:
    intervention = Intervention(**payload.model_dump())
    intervention = save_and_refresh(db, intervention)
    return InterventionRead.model_validate(intervention)


@router.get("", response_model=list[InterventionRead])
def list_interventions(
    user_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[InterventionRead]:
    query = select(Intervention).order_by(Intervention.trigger_at.asc())
    if user_id:
        query = query.where(Intervention.user_id == user_id)
    interventions = db.scalars(query).all()
    return [InterventionRead.model_validate(intervention) for intervention in interventions]
