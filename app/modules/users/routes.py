from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db, save_and_refresh
from app.modules.users.auth_routes import user_detail
from app.modules.users.models import User
from app.modules.users.schemas import UserDetail, UserRead, UserUpdate

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[UserRead])
def list_users(user: User = Depends(get_current_user)):
    return [UserRead.model_validate(user)]


@router.get("/by-email/{email}", response_model=UserDetail)
def get_user_by_email(email: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.email.lower() != email.strip().lower():
        raise HTTPException(404, "User not found")
    return user_detail(db, user)


@router.get("/{user_id}", response_model=UserDetail)
def get_user(user_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.id != user_id:
        raise HTTPException(404, "User not found")
    return user_detail(db, user)


@router.patch("/{user_id}", response_model=UserRead)
def update_user(user_id: str, payload: UserUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.id != user_id:
        raise HTTPException(404, "User not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    return UserRead.model_validate(save_and_refresh(db, user))
