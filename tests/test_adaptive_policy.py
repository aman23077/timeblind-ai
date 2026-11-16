from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.auth import AdminAccess, get_current_user
from app.core.database import Base, get_db
from app.main import app
from app.modules.behaviour.activity import ActivityInterval, ActivityMonitor
from app.modules.interventions.models import Intervention
from app.modules.interventions.policy import activity_signal, replan, tick
from app.modules.schedules.models import AdaptivePlan, Schedule, TimeBlock
from app.modules.sessions.models import SessionRecord
from app.modules.tasks.models import Task
from app.modules.users.models import User

NOW = datetime(2026, 11, 13, 10, tzinfo=timezone.utc)


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        db.add(User(id="u", email="u@example.com", display_name="U"))
        db.add(User(id="other", email="other@example.com", display_name="Other"))
        db.commit()
        yield db
    engine.dispose()


def plan(db):
    schedule = Schedule(id="s", user_id="u", plan_date=NOW.date())
    runtime = AdaptivePlan(schedule_id="s", user_id="u", window_start=NOW - timedelta(hours=1),
                           window_end=NOW + timedelta(minutes=60), break_minutes=0)
    db.add_all([schedule, runtime])
    db.commit()
    return runtime


def test_replan_preserves_active_and_fits_remaining_window(db):
    runtime = plan(db)
    db.add_all([Task(id="active", user_id="u", title="Active", estimated_minutes=30, difficulty="easy"),
                Task(id="next", user_id="u", title="Next", estimated_minutes=20, difficulty="easy"),
                Task(id="large", user_id="u", title="Large", estimated_minutes=90)])
    active = TimeBlock(id="active-block", schedule_id="s", user_id="u", task_id="active", title="Active",
                       start_at=NOW - timedelta(minutes=15), end_at=NOW + timedelta(minutes=15),
                       planned_duration_minutes=30, status="active")
    db.add(active)
    db.add(SessionRecord(id="run", user_id="u", task_id="active", time_block_id="active-block", started_at=NOW - timedelta(minutes=15)))
    db.commit()
    assert replan(db, runtime, NOW)
    db.commit()
    blocks = db.scalars(select(TimeBlock).where(TimeBlock.status == "planned")).all()
    assert len(blocks) == 1 and blocks[0].task_id == "next"
    assert blocks[0].start_at.replace(tzinfo=timezone.utc) >= NOW + timedelta(minutes=15)
    assert blocks[0].end_at.replace(tzinfo=timezone.utc) <= runtime.window_end.replace(tzinfo=timezone.utc)
    assert active.status == "active"
    assert runtime.deferred_tasks[0]["task_id"] == "large"
    revision = runtime.revision
    assert not replan(db, runtime, NOW)
    assert runtime.revision == revision


def test_completed_tasks_removed_and_expired_window_defers(db):
    runtime = plan(db)
    task = Task(id="t", user_id="u", title="T", estimated_minutes=20, difficulty="easy")
    db.add(task)
    db.commit()
    replan(db, runtime, NOW)
    db.commit()
    original = db.scalar(select(TimeBlock).where(TimeBlock.task_id == "t"))
    task.status = "completed"
    db.commit()
    replan(db, runtime, NOW + timedelta(seconds=30), force=True)
    db.commit()
    assert original.status == "superseded"
    task.status = "pending"
    db.commit()
    replan(db, runtime, NOW + timedelta(hours=2), force=True)
    db.commit()
    assert len(runtime.deferred_tasks) == 1
    assert not db.scalars(select(TimeBlock).where(TimeBlock.status == "planned")).all()


def test_stable_switches_and_policy_cooldown(db):
    session = SessionRecord(id="run", user_id="u", started_at=NOW - timedelta(minutes=5))
    monitor = ActivityMonitor(id="m", session_id="run", token_hash="hash", enabled=True,
                              enabled_at=NOW - timedelta(minutes=5), last_seen_at=NOW)
    db.add_all([session, monitor])
    for index in range(150):
        start = NOW - timedelta(seconds=300 - index * 2)
        db.add(ActivityInterval(monitor_id="m", sequence=index + 1, started_at=start,
                               ended_at=start + timedelta(seconds=2), state="active",
                               app_name="a.exe" if (index // 15) % 2 else "b.exe"))
    db.commit()
    signal = activity_signal(db, session, NOW)
    assert signal["switches"] == 9 and signal["coverage"] == 1
    tick(db, "u", NOW)
    db.commit()
    assert len(db.scalars(select(Intervention)).all()) == 1
    tick(db, "u", NOW + timedelta(seconds=1))
    db.commit()
    assert len(db.scalars(select(Intervention)).all()) == 1
    assert not activity_signal(db, session, NOW + timedelta(seconds=20))["fresh"]


def test_admin_access_is_explicit(db):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: db.get(User, "u")
    client = TestClient(app)
    try:
        assert client.get("/api/v1/admin/users").status_code == 403
        db.add(AdminAccess(user_id="u"))
        db.commit()
        result = client.get("/api/v1/admin/users")
        assert result.status_code == 200
        assert result.json()["total"] == 2
        assert client.get("/api/v1/admin/users/other").status_code == 200
        assert "password" not in result.text
        grant = db.scalar(select(AdminAccess).where(AdminAccess.user_id == "u"))
        db.delete(grant)
        db.commit()
        assert client.get("/api/v1/admin/users").status_code == 403
    finally:
        client.close()
        app.dependency_overrides.clear()


def test_snooze_is_removed_and_dismiss_works(db):
    item = Intervention(user_id="u", kind="policy_idle", message="Check in", trigger_at=NOW)
    db.add(item)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: db.get(User, "u")
    client = TestClient(app)
    try:
        path = f"/api/v1/policy/nudges/{item.id}"
        assert client.post(path, json={"action": "snooze"}).status_code == 422
        assert client.post(path, json={"action": "dismiss"}).status_code == 200
        assert item.status == "dismissed"
    finally:
        client.close()
        app.dependency_overrides.clear()
