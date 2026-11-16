import secrets
import hmac
import smtplib
import ssl
from datetime import timedelta
from email.message import EmailMessage

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import (AccountCredential, AdminAccess, COOKIE_NAME, LoginSession, PasswordReset, RecoveryKey, aware,
                           browser_request, digest, get_current_user, hash_password, issue_session,
                           rate_limit, secure_session_cookie, verify_password)
from app.core.config import get_settings
from app.core.database import get_db, utc_now
from app.modules.users.models import User, UserModelProfile
from app.modules.users.schemas import UserCreate, UserDetail

router = APIRouter(dependencies=[Depends(browser_request)])


class EmailInput(BaseModel):
    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class LoginInput(EmailInput):
    password: str = Field(min_length=1, max_length=128)


class RegisterInput(UserCreate, EmailInput):
    password: str = Field(min_length=12, max_length=128)


class ResetInput(BaseModel):
    token: str = Field(min_length=32, max_length=128)
    password: str = Field(min_length=12, max_length=128)
    email: EmailStr | None = None


def user_detail(db: Session, user: User) -> UserDetail:
    profile = db.scalar(select(UserModelProfile).where(UserModelProfile.user_id == user.id))
    if profile is None:
        profile = UserModelProfile(user_id=user.id)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    is_admin = db.scalar(select(AdminAccess.id).where(AdminAccess.user_id == user.id)) is not None
    return UserDetail.model_validate({**user.__dict__, "model_profile": profile, "is_admin": is_admin})


@router.post("/register", response_model=UserDetail, status_code=201)
def register(payload: RegisterInput, request: Request, response: Response, db: Session = Depends(get_db)):
    rate_limit(db, request, payload.email)
    if db.scalar(select(User.id).where(func.lower(User.email) == payload.email)):
        raise HTTPException(409, "An account already uses this email. Log in or use password setup/reset.")
    user = User(**payload.model_dump(exclude={"password"}))
    db.add(user)
    try:
        db.flush()
        db.add(UserModelProfile(user_id=user.id))
        db.add(AccountCredential(user_id=user.id, email_key=payload.email, password_hash=hash_password(payload.password)))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An account already uses this email. Log in or use password setup/reset.") from None
    issue_session(db, user, response, request)
    return user_detail(db, user)


@router.post("/login", response_model=UserDetail)
def login(payload: LoginInput, request: Request, response: Response, db: Session = Depends(get_db)):
    rate_limit(db, request, payload.email)
    credential = db.scalar(select(AccountCredential).where(AccountCredential.email_key == payload.email))
    if not verify_password(payload.password, credential.password_hash if credential else None):
        raise HTTPException(401, "Email or password is incorrect. Existing demo accounts need password setup.")
    user = db.get(User, credential.user_id)
    issue_session(db, user, response, request)
    return user_detail(db, user)


@router.get("/me", response_model=UserDetail)
def me(response: Response, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return user_detail(db, user)


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        db.execute(delete(LoginSession).where(LoginSession.token_hash == digest(token)))
        db.commit()
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="lax",
                           secure=secure_session_cookie())
    return {"message": "Signed out"}


def new_reset_token(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    db.execute(delete(PasswordReset).where(PasswordReset.user_id == user.id))
    db.add(PasswordReset(user_id=user.id, token_hash=digest(token), expires_at=utc_now() + timedelta(minutes=15)))
    db.commit()
    return token


def send_reset_email(email: str, token: str):
    settings = get_settings()
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = email
    message["Subject"] = "Set your TimeBlindAI password"
    message.set_content(
        "A password setup or reset was requested for your TimeBlindAI account.\n\n"
        "Paste this code into the Password setup/reset form in TimeBlindAI, then choose your password.\n\n"
        + token + "\n\nThis code expires in 15 minutes and can be used once.\n"
    )
    context = ssl.create_default_context()
    smtp_type = smtplib.SMTP_SSL if settings.smtp_ssl else smtplib.SMTP
    options = {"context": context} if settings.smtp_ssl else {}
    with smtp_type(settings.smtp_host, settings.smtp_port, timeout=10, **options) as server:
        if not settings.smtp_ssl:
            server.starttls(context=context)
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password.get_secret_value() if settings.smtp_password else "")
        server.send_message(message)


@router.post("/forgot-password")
def forgot_password(payload: EmailInput, request: Request, db: Session = Depends(get_db)):
    rate_limit(db, request, payload.email)
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_from:
        raise HTTPException(503, "Email delivery is not configured. The local project owner can generate a setup code using the account recovery command.")
    users = db.scalars(select(User).where(func.lower(User.email) == payload.email)).all()
    if len(users) == 1:
        token = new_reset_token(db, users[0])
        try:
            send_reset_email(payload.email, token)
        except (OSError, smtplib.SMTPException):
            db.execute(delete(PasswordReset).where(PasswordReset.token_hash == digest(token)))
            db.commit()
            raise HTTPException(503, "Email delivery failed. Try again later.") from None
    return {"message": "If an account exists for this email, a password setup code has been sent."}


@router.post("/reset-password")
def reset_password(payload: ResetInput, request: Request, response: Response, db: Session = Depends(get_db)):
    email = str(payload.email).strip().lower() if payload.email else None
    rate_limit(db, request, email or "reset:" + digest(payload.token))
    shared_key = db.scalar(select(RecoveryKey).where(RecoveryKey.name == "universal"))
    universal = shared_key is not None and hmac.compare_digest(shared_key.key_hash, digest(payload.token))
    if universal:
        if not email:
            raise HTTPException(422, "Enter the email of the account to recover.")
        users = db.scalars(select(User).where(func.lower(User.email) == email)).all()
        if len(users) != 1:
            raise HTTPException(404, "No unique account found for this email.")
        user = users[0]
    else:
        reset = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == digest(payload.token)))
        if reset is None or aware(reset.expires_at) <= utc_now():
            raise HTTPException(400, "Recovery key or setup code is invalid.")
        user = db.get(User, reset.user_id)
        if email and user.email.lower() != email:
            raise HTTPException(400, "The setup code belongs to a different account.")
        consumed = db.execute(delete(PasswordReset).where(PasswordReset.id == reset.id))
        if consumed.rowcount != 1:
            db.rollback()
            raise HTTPException(400, "The setup code was already used.")
    password_hash = hash_password(payload.password)
    credential = db.scalar(select(AccountCredential).where(AccountCredential.user_id == user.id))
    if credential is None:
        db.add(AccountCredential(user_id=user.id, email_key=user.email.strip().lower(), password_hash=password_hash))
    else:
        credential.password_hash = password_hash
    db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
    db.execute(delete(PasswordReset).where(PasswordReset.user_id == user.id))
    # Resetting credentials also revokes any companion upload credentials.
    from app.modules.behaviour.activity import ActivityMonitor
    from app.modules.sessions.models import SessionRecord
    from sqlalchemy import update
    session_ids = select(SessionRecord.id).where(SessionRecord.user_id == user.id)
    db.execute(update(ActivityMonitor).where(ActivityMonitor.session_id.in_(session_ids)).values(enabled=False))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Account email conflict. Contact the project owner.") from None
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="lax", secure=secure_session_cookie())
    return {"message": "Password saved. Log in with your email and new password."}
