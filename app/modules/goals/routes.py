from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, Query

from app.core.database import get_db, save_and_refresh
from app.core.http import not_found
from app.modules.goals.models import Goal
from app.modules.goals.schemas import GoalCreate, GoalRead


router = APIRouter()


@router.post("", response_model=GoalRead)
def create_goal(payload: GoalCreate, db: Session = Depends(get_db)) -> GoalRead:
    goal = Goal(**payload.model_dump())
    goal = save_and_refresh(db, goal)
    return GoalRead.model_validate(goal)


@router.get("", response_model=list[GoalRead])
def list_goals(
    user_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[GoalRead]:
    query = select(Goal).order_by(Goal.created_at.desc())
    if user_id:
        query = query.where(Goal.user_id == user_id)
    goals = db.scalars(query).all()
    return [GoalRead.model_validate(goal) for goal in goals]


@router.get("/{goal_id}", response_model=GoalRead)
def get_goal(goal_id: str, db: Session = Depends(get_db)) -> GoalRead:
    goal = db.get(Goal, goal_id)
    if goal is None:
        raise not_found("Goal", goal_id)
    return GoalRead.model_validate(goal)
