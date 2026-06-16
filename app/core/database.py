from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.core.config import get_settings


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now)


settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(
    settings.database_url,
    echo=settings.database_echo,
    connect_args=connect_args,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def initialize_database() -> None:
    import app.modules.behaviour.models  # noqa: F401
    import app.modules.context.models  # noqa: F401
    import app.modules.events.models  # noqa: F401
    import app.modules.goals.models  # noqa: F401
    import app.modules.interventions.models  # noqa: F401
    import app.modules.schedules.models  # noqa: F401
    import app.modules.sessions.models  # noqa: F401
    import app.modules.tasks.models  # noqa: F401
    import app.modules.users.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_columns()


def save_and_refresh(db: Session, entity):
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return entity


def _ensure_sqlite_columns() -> None:
    if not settings.database_url.startswith("sqlite"):
        return

    inspector = inspect(engine)
    task_columns = {column["name"] for column in inspector.get_columns("tasks")} if inspector.has_table("tasks") else set()
    session_columns = (
        {column["name"] for column in inspector.get_columns("sessions")} if inspector.has_table("sessions") else set()
    )
    time_block_columns = (
        {column["name"] for column in inspector.get_columns("time_blocks")} if inspector.has_table("time_blocks") else set()
    )
    required_columns = {
        "difficulty": "ALTER TABLE tasks ADD COLUMN difficulty VARCHAR(16) DEFAULT 'medium'",
        "quantity_value": "ALTER TABLE tasks ADD COLUMN quantity_value INTEGER",
    }
    required_session_columns = {
        "difficulty_feedback": "ALTER TABLE sessions ADD COLUMN difficulty_feedback VARCHAR(32) DEFAULT 'as_expected'",
        "feedback_reasons": "ALTER TABLE sessions ADD COLUMN feedback_reasons TEXT DEFAULT ''",
        "feedback_notes": "ALTER TABLE sessions ADD COLUMN feedback_notes TEXT DEFAULT ''",
        "actual_start": "ALTER TABLE sessions ADD COLUMN actual_start DATETIME",
        "actual_end": "ALTER TABLE sessions ADD COLUMN actual_end DATETIME",
        "elapsed_minutes": "ALTER TABLE sessions ADD COLUMN elapsed_minutes INTEGER",
        "delay_minutes": "ALTER TABLE sessions ADD COLUMN delay_minutes INTEGER DEFAULT 0",
        "overrun_minutes": "ALTER TABLE sessions ADD COLUMN overrun_minutes INTEGER DEFAULT 0",
    }
    required_time_block_columns = {
        "planned_duration_minutes": "ALTER TABLE time_blocks ADD COLUMN planned_duration_minutes INTEGER",
        "risk_level": "ALTER TABLE time_blocks ADD COLUMN risk_level VARCHAR(16) DEFAULT 'low'",
        "risk_buffer_minutes": "ALTER TABLE time_blocks ADD COLUMN risk_buffer_minutes INTEGER DEFAULT 0",
        "risk_reason": "ALTER TABLE time_blocks ADD COLUMN risk_reason VARCHAR(240) DEFAULT ''",
        "actual_start": "ALTER TABLE time_blocks ADD COLUMN actual_start DATETIME",
        "actual_end": "ALTER TABLE time_blocks ADD COLUMN actual_end DATETIME",
        "delay_minutes": "ALTER TABLE time_blocks ADD COLUMN delay_minutes INTEGER DEFAULT 0",
        "overrun_minutes": "ALTER TABLE time_blocks ADD COLUMN overrun_minutes INTEGER DEFAULT 0",
    }

    with engine.begin() as connection:
        for column_name, statement in required_columns.items():
            if column_name not in task_columns:
                connection.execute(text(statement))
        for column_name, statement in required_session_columns.items():
            if column_name not in session_columns:
                connection.execute(text(statement))
        for column_name, statement in required_time_block_columns.items():
            if column_name not in time_block_columns:
                connection.execute(text(statement))
