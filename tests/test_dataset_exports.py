import csv
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.auth import AdminAccess, AccountCredential, get_current_user
from app.core.database import Base, get_db
from app.modules.users.datasets import DatasetAccount
from app.modules.users.models import User
from app.modules.tasks.models import Task
from scripts import synthetic_benchmark as benchmark


@pytest.fixture
def setup():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        db.add_all([User(id="admin", email="admin@example.com", display_name="Admin"),
                    User(id="test", email="test@example.com", display_name="Test"),
                    User(id="real", email="real@example.com", display_name="Real")])
        db.add_all([DatasetAccount(user_id="test", source="synthetic", dataset_id="fixture"),
                    Task(id="synthetic", user_id="test", title="=1+1", estimated_minutes=20),
                    Task(id="private", user_id="real", title="Private task"),
                    AccountCredential(user_id="admin", email_key="admin@example.com", password_hash="SECRET_HASH")])
        db.commit()
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        try:
            yield client, db
        finally:
            client.close()
            app.dependency_overrides.clear()
    engine.dispose()


def test_export_access_filter_provenance_and_secrets(setup):
    client, db = setup
    assert client.get("/api/v1/admin/export").status_code == 401
    app.dependency_overrides[get_current_user] = lambda: db.get(User, "test")
    assert client.get("/api/v1/admin/export").status_code == 403
    db.add(AdminAccess(user_id="admin"))
    db.commit()
    app.dependency_overrides[get_current_user] = lambda: db.get(User, "admin")
    assert client.get("/api/v1/auth/me").json()["is_admin"] is True
    response = client.get("/api/v1/admin/export?source=synthetic")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        rows = list(csv.DictReader(io.StringIO(archive.read("tasks.csv").decode())))
        assert len(rows) == 1
        assert rows[0]["title"] == "'=1+1"
        assert rows[0]["data_source"] == "synthetic"
        assert rows[0]["consent_to_research"] == "false"
        assert json.loads(archive.read("manifest.json"))["account_count"] == 1
        text = "".join(archive.read(name).decode() for name in archive.namelist())
        assert "SECRET_HASH" not in text and "admin@example.com" not in text and "Private task" not in text
        assert "token_hash" not in text and "password_hash" not in text
    assert client.get("/api/v1/admin/export?source=real").status_code == 422
    assert client.get("/api/v1/admin/export?user_id=missing").status_code == 404
    db.delete(db.scalar(select(AdminAccess)))
    db.commit()
    assert client.get("/api/v1/admin/export").status_code == 403


def test_record_browser_is_allowlisted_and_scoped(setup):
    client, db = setup
    db.add(AdminAccess(user_id="admin"))
    db.commit()
    app.dependency_overrides[get_current_user] = lambda: db.get(User, "admin")
    result = client.get("/api/v1/admin/users/test/records?table=tasks").json()
    assert result["total"] == 1 and result["rows"][0]["id"] == "synthetic"
    assert result["data_source"] == "synthetic"
    assert client.get("/api/v1/admin/users/test/records?table=account_credentials").status_code == 422
    assert client.get("/api/v1/admin/users/test/records?table=tasks&offset=50").json()["rows"] == []
    app.dependency_overrides[get_current_user] = lambda: db.get(User, "test")
    assert client.get("/api/v1/auth/me").json()["is_admin"] is False
    assert client.get("/api/v1/admin/users/real/records").status_code == 403


def test_synthetic_generation_repeatability_and_grouped_splits():
    rows = benchmark.duration_rows(23077)
    assert rows == benchmark.duration_rows(23077)
    assert len(rows) == len({r["task_id"] for r in rows}) == 300
    sets = {split: {r["simulated_participant_id"] for r in rows if r["split"] == split} for split in ("train", "validation", "test")}
    assert not sets["train"] & sets["test"] and not sets["validation"] & sets["test"]
    assert all(r["actual_minutes"] > 0 and r["llm_status"] == "not_run" for r in rows)


def test_seed_is_idempotent_and_never_promotes_or_overwrites(monkeypatch, setup):
    _, db = setup
    from contextlib import nullcontext
    monkeypatch.setattr(benchmark, "initialize_database", lambda: None)
    monkeypatch.setattr(benchmark, "SessionLocal", lambda: nullcontext(db))
    rows = benchmark.duration_rows(23077)[:2]
    first = benchmark.seed_account(rows)
    assert first["new_password"] and first["admin"] is False
    second = benchmark.seed_account(rows)
    assert second["new_password"] is None
    assert len(db.scalars(select(Task).where(Task.user_id == first["user_id"])).all()) == 2
    assert not db.scalar(select(AdminAccess).where(AdminAccess.user_id == first["user_id"]))
    assert db.get(Task, "private").title == "Private task"
