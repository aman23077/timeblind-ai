from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends

from app.core.database import get_db, save_and_refresh
from app.core.http import not_found
from app.modules.users.models import User, UserModelProfile
from app.modules.users.schemas import UserCreate, UserDetail, UserEnsure, UserRead, UserUpdate


router = APIRouter()


@router.post("", response_model=UserDetail)
def create_user(payload: UserCreate, db: Session = Depends(get_db)) -> UserDetail:
    user = User(
        email=payload.email,
        display_name=payload.display_name,
        time_zone=payload.time_zone,
        preferred_nudge_style=payload.preferred_nudge_style,
    )
    user = save_and_refresh(db, user)
    model_profile = UserModelProfile(user_id=user.id)
    model_profile = save_and_refresh(db, model_profile)
    return UserDetail.model_validate({**user.__dict__, "model_profile": model_profile})


@router.post("/ensure", response_model=UserDetail)
def ensure_user(payload: UserEnsure, db: Session = Depends(get_db)) -> UserDetail:
    existing_user = db.scalars(select(User).where(User.email == payload.email)).first()
    if existing_user is not None:
        model_profile = db.scalars(
            select(UserModelProfile).where(UserModelProfile.user_id == existing_user.id)
        ).first()
        if model_profile is None:
            model_profile = save_and_refresh(db, UserModelProfile(user_id=existing_user.id))
        return UserDetail.model_validate({**existing_user.__dict__, "model_profile": model_profile})

    return create_user(UserCreate(**payload.model_dump()), db)


@router.get("", response_model=list[UserRead])
def list_users(db: Session = Depends(get_db)) -> list[UserRead]:
    users = db.scalars(select(User).order_by(User.created_at.desc())).all()
    return [UserRead.model_validate(user) for user in users]


@router.get("/{user_id}", response_model=UserDetail)
def get_user(user_id: str, db: Session = Depends(get_db)) -> UserDetail:
    user = db.get(User, user_id)
    if user is None:
        raise not_found("User", user_id)
    model_profile = db.scalars(select(UserModelProfile).where(UserModelProfile.user_id == user_id)).first()
    if model_profile is None:
        model_profile = save_and_refresh(db, UserModelProfile(user_id=user_id))
    return UserDetail.model_validate({**user.__dict__, "model_profile": model_profile})


@router.patch("/{user_id}", response_model=UserRead)
def update_user(user_id: str, payload: UserUpdate, db: Session = Depends(get_db)) -> UserRead:
    user = db.get(User, user_id)
    if user is None:
        raise not_found("User", user_id)

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(user, field, value)

    user = save_and_refresh(db, user)
    return UserRead.model_validate(user)
