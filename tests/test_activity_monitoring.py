from app.core.auth import get_current_user
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.modules.behaviour import activity
from app.modules.sessions.models import SessionRecord
from app.modules.users.models import User

NOW = datetime(2026, 11, 13, 10, tzinfo=timezone.utc)


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(activity, "utc_now", lambda: NOW)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        db.add(User(id="u", email="u@example.com", display_name="Test"))
        db.add(SessionRecord(id="s", user_id="u", started_at=NOW - timedelta(seconds=20)))
        db.commit()
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = lambda: db.get(User, "u")
        client = TestClient(app, raise_server_exceptions=True)
        yield client, db
        client.close()
    app.dependency_overrides.clear()
    engine.dispose()


def pair(client, db):
    response = client.post("/api/v1/activity/sessions/s/enable?user_id=u")
    assert response.status_code == 200
    monitor = db.scalar(select(activity.ActivityMonitor))
    monitor.enabled_at = NOW - timedelta(seconds=20)
    db.commit()
    return {"Authorization": "Bearer " + response.json()["token"]}


def interval(sequence, start, state="active", name="code.exe"):
    return {"sequence": sequence, "started_at": (NOW + timedelta(seconds=start)).isoformat(),
            "ended_at": (NOW + timedelta(seconds=start + 2)).isoformat(), "state": state, "app_name": name}


def test_totals_retries_and_switches(setup):
    client, db = setup
    headers = pair(client, db)
    rows = [interval(1, -16), interval(2, -14, name="chrome.exe"), interval(3, -12, "idle", None),
            interval(4, -8, "unknown", None), interval(5, -6, name="code.exe")]
    for row in rows:
        for _ in range(2):
            assert client.post("/api/v1/activity/companion/intervals", headers=headers, json=row).status_code == 200
    assert db.scalar(select(func.count()).select_from(activity.ActivityInterval)) == 5
    result = client.get("/api/v1/activity/sessions/s?user_id=u").json()
    assert result["active_seconds"] == 6
    assert result["idle_seconds"] == 2
    assert result["unobserved_seconds"] == 12
    assert result["context_switches"] == 1
    assert result["apps"] == [{"name": "code.exe", "seconds": 4}, {"name": "chrome.exe", "seconds": 2}]


def test_disable_rotate_and_end_revoke_tokens(setup):
    client, db = setup
    headers = pair(client, db)
    new_headers = pair(client, db)
    assert client.get("/api/v1/activity/companion", headers=headers).status_code == 403
    client.post("/api/v1/activity/sessions/s/disable?user_id=u")
    assert client.get("/api/v1/activity/companion", headers=new_headers).status_code == 403
    headers = pair(client, db)
    response = client.patch("/api/v1/sessions/s/end", json={"ended_at": NOW.isoformat()})
    assert response.status_code == 200
    assert client.post("/api/v1/activity/companion/intervals", headers=headers, json=interval(1, -4)).status_code == 403
    assert client.post("/api/v1/activity/sessions/s/enable?user_id=u").status_code == 409


def test_ownership_and_token_required(setup):
    client, db = setup
    assert client.get("/api/v1/activity/sessions/s?user_id=other").status_code == 404
    assert client.post("/api/v1/activity/sessions/s/enable?user_id=other").status_code == 404
    assert client.get("/api/v1/activity/companion").status_code == 401
    assert client.get("/api/v1/activity/companion", headers={"Authorization": "Bearer invalid"}).status_code == 403
    result = client.get("/api/v1/activity/sessions/s?user_id=u").json()
    assert result["unobserved_seconds"] == 20
    assert not result["enabled"]


def test_overlap_sequence_and_malformed_data(setup):
    client, db = setup
    headers = pair(client, db)
    path = "/api/v1/activity/companion/intervals"
    assert client.post(path, headers=headers, json=interval(1, -10)).status_code == 200
    assert client.post(path, headers=headers, json=interval(1, -10, name="other.exe")).status_code == 409
    assert client.post(path, headers=headers, json=interval(2, -9)).status_code == 409
    assert client.post(path, headers=headers, json=interval(3, -8)).status_code == 409
    assert client.post(path, headers=headers, json=interval(2, -8, name="C:/private/code.exe")).status_code == 422
    assert client.post(path, headers=headers, json=interval(2, -8, "idle", "code.exe")).status_code == 422
    row = interval(2, -8)
    row["ended_at"] = NOW.isoformat()
    assert client.post(path, headers=headers, json=row).status_code == 422
    assert client.post(path, headers=headers, json=interval(2, 20)).status_code == 422


def test_companion_retries_identical_payload(monkeypatch):
    from scripts import windows_companion as companion
    calls = []

    def request(server, token, path, payload):
        calls.append(payload.copy())
        if len(calls) == 1:
            raise OSError("Connection interrupted")

    monkeypatch.setattr(companion, "api", request)
    monkeypatch.setattr(companion.time, "sleep", lambda _: None)
    row = interval(1, -4)
    companion.transmit("http://localhost:8000", "test", row)
    assert calls == [row, row]


def test_collector_loop_through_api_to_summary(setup, monkeypatch):
    from types import SimpleNamespace
    from scripts import windows_companion as companion

    client, db = setup
    headers = pair(client, db)
    clock = [NOW]
    samples = iter([("active", "code.exe"), ("active", "chrome.exe"), ("idle", None)])

    class Sensor:
        def sample(self, threshold):
            assert threshold == 60
            try:
                return next(samples)
            except StopIteration:
                raise KeyboardInterrupt

    def request(server, token, path, payload=None):
        url = "/api/v1/activity/companion" + path
        response = client.get(url, headers=headers) if payload is None else client.post(url, headers=headers, json=payload)
        assert response.status_code == 200
        return response.json()

    def advance(seconds):
        clock[0] += timedelta(seconds=seconds)

    monkeypatch.setattr(companion, "WindowsSensor", Sensor)
    monkeypatch.setattr(companion, "api", request)
    monkeypatch.setattr(companion, "datetime", SimpleNamespace(now=lambda _: clock[0]))
    monkeypatch.setattr(companion, "time", SimpleNamespace(sleep=advance))
    monkeypatch.setattr(activity, "utc_now", lambda: clock[0])
    with pytest.raises(KeyboardInterrupt):
        companion.run("http://localhost:8000", "test")
    summary = client.get("/api/v1/activity/sessions/s?user_id=u").json()
    assert summary["active_seconds"] == 4
    assert summary["idle_seconds"] == 2
    assert summary["context_switches"] == 1
    assert summary["unobserved_seconds"] == 20
