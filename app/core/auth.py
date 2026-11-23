"""Password hashing, opaque login sessions, and workspace authorization."""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import DateTime, ForeignKey, Integer, String, delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.config import get_settings
from app.core.database import Base, get_db, utc_now
from app.modules.users.models import User

COOKIE_NAME = "timeblind_session"
SESSION_SECONDS = 7 * 24 * 60 * 60


class AccountCredential(Base):
    __tablename__ = "account_credentials"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True)
    email_key: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))


class AdminAccess(Base):
    __tablename__ = "admin_access"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True)


class RecoveryKey(Base):
    __tablename__ = "recovery_keys"
    name: Mapped[str] = mapped_column(String(32), unique=True)
    key_hash: Mapped[str] = mapped_column(String(64))


class LoginSession(Base):
    __tablename__ = "login_sessions"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PasswordReset(Base):
    __tablename__ = "password_resets"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuthRateLimit(Base):
    __tablename__ = "auth_rate_limits"
    bucket: Mapped[str] = mapped_column(String(64), unique=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600_000).hex()
    return f"pbkdf2_sha256$600000${salt}${key}"


def verify_password(password: str, encoded: str | None) -> bool:
    # Missing accounts still perform the same expensive hash operation.
    encoded = encoded or "pbkdf2_sha256$600000$missing-account$" + "0" * 64
    try:
        algorithm, iterations, salt, expected = encoded.split("$")
        if algorithm != "pbkdf2_sha256" or int(iterations) != 600_000:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def secure_session_cookie() -> bool:
    settings = get_settings()
    return settings.environment == "production" or settings.render


def browser_request(request: Request):
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    origins = {item.strip().rstrip("/") for item in get_settings().cors_origins.split(",")}
    if request.headers.get("x-timeblind-client") != "web":
        raise HTTPException(403, "Missing request protection header")
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") not in origins:
        raise HTTPException(403, "Origin is not allowed")


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    browser_request(request)
    token = request.cookies.get(COOKIE_NAME)
    login = db.scalar(select(LoginSession).where(LoginSession.token_hash == digest(token))) if token else None
    if login is None or aware(login.expires_at) <= utc_now():
        raise HTTPException(401, "Please log in to continue")
    user = db.get(User, login.user_id)
    if user is None:
        raise HTTPException(401, "Please log in to continue")
    return user


def issue_session(db: Session, user: User, response: Response, request: Request):
    previous = request.cookies.get(COOKIE_NAME)
    if previous:
        db.execute(delete(LoginSession).where(LoginSession.token_hash == digest(previous)))
    db.execute(delete(LoginSession).where(LoginSession.expires_at < utc_now()))
    token = secrets.token_urlsafe(32)
    db.add(LoginSession(user_id=user.id, token_hash=digest(token), expires_at=utc_now() + timedelta(seconds=SESSION_SECONDS)))
    db.commit()
    response.set_cookie(COOKIE_NAME, token, max_age=SESSION_SECONDS, httponly=True,
                        secure=secure_session_cookie(),
                        samesite="lax", path="/")
    response.headers["Cache-Control"] = "no-store"


def rate_limit(db: Session, request: Request, email: str):
    now = utc_now()
    window = int(now.timestamp()) // 900
    ip = request.client.host if request.client else "unknown"
    db.execute(delete(AuthRateLimit).where(AuthRateLimit.expires_at < now))
    db.commit()
    for subject, maximum in (("ip:" + ip, 50), ("email:" + email, 10)):
        key = digest(f"{subject}:{window}")
        if db.scalar(select(AuthRateLimit.id).where(AuthRateLimit.bucket == key)) is None:
            db.add(AuthRateLimit(bucket=key, attempts=0, expires_at=now + timedelta(minutes=30)))
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
        updated = db.execute(update(AuthRateLimit).where(
            AuthRateLimit.bucket == key, AuthRateLimit.attempts < maximum
        ).values(attempts=AuthRateLimit.attempts + 1))
        db.commit()
        if not updated.rowcount:
            remaining = max(1, (window + 1) * 900 - int(now.timestamp()))
            raise HTTPException(429, "Too many attempts. Wait for the retry interval before trying again.", headers={"Retry-After": str(remaining)})


async def require_workspace_access(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Check all top-level resource references before a workspace route runs.

    List endpoints additionally filter by the authenticated user's ID. New resource
    reference fields must be registered here as well as declared in their schema.
    """
    from app.modules.events.models import Event
    from app.modules.goals.models import Goal
    from app.modules.interventions.models import Reminder
    from app.modules.schedules.models import Schedule, TimeBlock
    from app.modules.sessions.models import SessionRecord
    from app.modules.tasks.models import Task

    references = {"task_id": Task, "depends_on_task_id": Task, "goal_id": Goal, "event_id": Event,
                  "schedule_id": Schedule, "time_block_id": TimeBlock, "session_id": SessionRecord,
                  "reminder_id": Reminder}
    sources = [request.path_params, request.query_params]
    if request.method in {"POST", "PATCH", "PUT"} and await request.body():
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(422, "Invalid JSON") from None
        if not isinstance(body, dict):
            raise HTTPException(422, "Expected a JSON object")
        sources.append(body)
    for source in sources:
        if source.get("user_id") is not None and source["user_id"] != user.id:
            raise HTTPException(404, "Workspace not found")
        for field, model in references.items():
            resource_id = source.get(field)
            if resource_id is None:
                continue
            if not isinstance(resource_id, str):
                raise HTTPException(422, "Invalid resource ID")
            record = db.get(model, resource_id)
            if record is None or record.user_id != user.id:
                raise HTTPException(404, "Resource not found")
