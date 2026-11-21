from fastapi import APIRouter, Depends, HTTPException, Query, Response
from typing import Literal
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import AdminAccess, get_current_user
from app.core.database import get_db
from app.modules.users.models import User
from app.modules.users.schemas import UserRead
from app.modules.tasks.models import Task
from app.modules.tasks.schemas import TaskRead
from app.modules.sessions.models import SessionRecord
from app.modules.sessions.schemas import SessionRead
from app.modules.users.datasets import export_dataset, browse_records, record_queries


class AdminUserRead(UserRead):
    # Preserve imported addresses in admin output; registration stays validated.
    email: str


def require_admin(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if db.scalar(select(AdminAccess.id).where(AdminAccess.user_id == user.id)) is None:
        raise HTTPException(403, "Administrator access required")
    return user


router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("/export")
def export(user_id: str | None = None, source: Literal["all", "synthetic", "unverified"] = "all", db: Session = Depends(get_db)):
    if user_id and db.get(User, user_id) is None:
        raise HTTPException(404, "User not found")
    return Response(export_dataset(db, user_id, source), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="timeblind-dataset.zip"', "Cache-Control": "no-store"})


@router.get("/users")
def users(offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    rows = db.scalars(select(User).order_by(User.created_at.desc(), User.id).offset(offset).limit(50)).all()
    return {"total": db.scalar(select(func.count()).select_from(User)), "users": [AdminUserRead.model_validate(row) for row in rows]}


@router.get("/users/{user_id}")
def entries(user_id: str, offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    tasks = select(Task).where(Task.user_id == user_id)
    sessions = select(SessionRecord).where(SessionRecord.user_id == user_id)
    return {"user": AdminUserRead.model_validate(user),
            "task_count": db.scalar(select(func.count()).select_from(tasks.subquery())),
            "session_count": db.scalar(select(func.count()).select_from(sessions.subquery())),
            "tasks": [TaskRead.model_validate(row) for row in db.scalars(tasks.order_by(Task.created_at.desc(), Task.id).offset(offset).limit(50))],
            "sessions": [SessionRead.model_validate(row) for row in db.scalars(sessions.order_by(SessionRecord.started_at.desc(), SessionRecord.id).offset(offset).limit(50))]}


@router.get("/users/{user_id}/records")
def records(user_id: str, table: str = "tasks", offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    if db.get(User, user_id) is None:
        raise HTTPException(404, "User not found")
    if table not in record_queries([user_id]):
        raise HTTPException(422, "Unknown dataset table")
    return browse_records(db, user_id, table, offset)
