"""Study validity, consent, access controls and outcome accounting."""
import csv
import io
import json
import zipfile
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.auth import AdminAccess, get_current_user
from app.core.database import Base, get_db, utc_now
from app.modules.study.models import StudyTask
from app.modules.users.models import User


@pytest.fixture
def setup():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        db.add_all([User(id="a", email="a@example.com", display_name="A"), User(id="b", email="b@example.com", display_name="B")])
        db.commit()
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)
        try:
            yield client, db
        finally:
            client.close()
            app.dependency_overrides.clear()
    engine.dispose()


def login(db, user="a"):
    app.dependency_overrides[get_current_user] = lambda: db.get(User, user)


def join(client):
    return client.post("/api/v1/study/enroll", json={"adult": True, "consent": True, "baseline_frequency": "often"})


def task(client, estimate=30):
    response = client.post("/api/v1/study/tasks", json={"title": "Read five pages", "task_type": "reading", "difficulty": "medium", "user_estimate_minutes": estimate})
    assert response.status_code == 200, response.text
    return response.json()


def test_consent_access_and_snapshot_independence(setup):
    client, db = setup
    assert client.get("/api/v1/study/me").status_code == 401
    login(db)
    assert client.post("/api/v1/study/tasks", json={"title": "Read pages", "user_estimate_minutes": 20}).status_code == 403
    assert client.post("/api/v1/study/enroll", json={"adult": False, "consent": True, "baseline_frequency": "often"}).status_code == 422
    assert join(client).status_code == 200
    assert join(client).status_code == 200
    first, second = task(client, 10), task(client, 120)
    assert first["rules_estimate_minutes"] == second["rules_estimate_minutes"]
    assert first["user_estimate_minutes"] == 10
    assert first["predicted_at"].endswith("+00:00")
    saved = client.get("/api/v1/study/me").json()
    assert saved["tasks"][0]["steps"]
    assert saved["feedback"] is None
    assert client.patch(f'/api/v1/study/tasks/{first["id"]}', json={"user_estimate_minutes": 2}).status_code == 404
    login(db, "b")
    join(client)
    assert client.post(f'/api/v1/study/tasks/{first["id"]}/start', json={}).status_code == 404
    assert client.get("/api/v1/study/me").json()["tasks"] == []
    assert client.get("/api/v1/study/admin/summary").status_code == 403


def test_timing_outcomes_summary_and_withdrawal(setup):
    client, db = setup
    login(db)
    join(client)
    first, second = task(client), task(client)
    path = f'/api/v1/study/tasks/{first["id"]}'
    assert client.post(path + "/start", json={}).status_code == 200
    assert client.post(path + "/start", json={}).status_code == 409
    assert client.post(f'/api/v1/study/tasks/{second["id"]}/start', json={}).status_code == 409
    row = db.get(StudyTask, first["id"])
    row.started_at = utc_now() - timedelta(minutes=20)
    db.commit()
    payload = {"outcome": "completed", "break_minutes": 30, "scope_changed": False, "friction": "none"}
    assert client.post(path + "/finish", json=payload).status_code == 422
    payload["break_minutes"] = 5
    response = client.post(path + "/finish", json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["actual_minutes"] == pytest.approx(15, abs=.05)
    assert client.post(path + "/finish", json=payload).status_code == 409
    db.add(AdminAccess(user_id="a"))
    db.commit()
    data = client.get("/api/v1/study/admin/summary").json()
    assert data["eligible_tasks"] == 1 and data["consenting_participants"] == 1
    assert data["methods"]["user"]["mae_minutes"] == pytest.approx(15, abs=.05)
    assert data["methods"]["rules"]["tasks"] == data["methods"]["user"]["tasks"]
    feedback = {"ease": 5, "clarity": 4, "usefulness": 3, "trust": 2, "use_again": 1, "biggest_problem": "PRIVATE_COMMENT"}
    assert client.post("/api/v1/study/feedback", json=feedback).status_code == 200
    assert client.get("/api/v1/study/me").json()["feedback"]["biggest_problem"] == "PRIVATE_COMMENT"
    assert client.get("/api/v1/study/admin/summary").json()["ratings"]["ease"]["counts_1_to_5"] == [0,0,0,0,1]
    with zipfile.ZipFile(io.BytesIO(client.get("/api/v1/study/admin/export").content)) as z:
        all_text = "".join(z.read(n).decode() for n in z.namelist())
        assert "Read five pages" not in all_text and "a@example.com" not in all_text and "PRIVATE_COMMENT" not in all_text
        rows = list(csv.DictReader(io.StringIO(z.read("tasks.csv").decode())))
        assert len(rows) == 2 and rows[0]["participant_code"]
        assert json.loads(z.read("summary.json"))["eligible_tasks"] == 1
    assert client.post("/api/v1/study/withdraw", json={}).status_code == 200
    data = client.get("/api/v1/study/admin/summary").json()
    assert data["eligible_tasks"] == data["consenting_participants"] == data["feedback_responses"] == 0
    assert client.get("/api/v1/study/admin/comments").json() == []
    assert join(client).status_code == 409
    assert client.post(f'/api/v1/study/tasks/{second["id"]}/start', json={}).status_code == 403


def test_scope_changes_and_unfinished_do_not_enter_accuracy(setup):
    client, db = setup
    login(db)
    join(client)
    assert client.post("/api/v1/study/feedback", json={k: 3 for k in ("ease", "clarity", "usefulness", "trust", "use_again")}).status_code == 409
    for outcome, scope in [("completed", True), ("unfinished", False)]:
        t = task(client)
        path = f'/api/v1/study/tasks/{t["id"]}'
        client.post(path + "/start", json={})
        db.get(StudyTask, t["id"]).started_at = utc_now() - timedelta(minutes=10)
        db.commit()
        assert client.post(path + "/finish", json={"outcome": outcome, "scope_changed": scope, "break_minutes": 0, "friction": "other"}).status_code == 200
    db.add(AdminAccess(user_id="a"))
    db.commit()
    data = client.get("/api/v1/study/admin/summary").json()
    assert data["eligible_tasks"] == 0 and data["excluded_completed_tasks"] == data["unfinished_tasks"] == 1
    assert data["methods"]["rules"]["mae_minutes"] is None


def test_manual_rehearsal_and_scheduler_review(setup):
    client, db = setup
    login(db)
    join(client)
    payload = {"window_minutes": 90, "tasks": [{"title": "Review course notes", "user_estimate_minutes": 20} for _ in range(3)]}
    assert client.post("/api/v1/study/scheduler", json=payload).status_code == 409
    for _ in range(3):
        row = task(client)
        path = f'/api/v1/study/tasks/{row["id"]}'
        client.post(path + "/start", json={})
        result = client.post(path + "/finish", json={"outcome":"completed", "break_minutes":0, "scope_changed":False, "friction":"none", "timing_source":"rehearsal", "manual_minutes":35})
        assert result.status_code == 200, result.text
    response = client.post("/api/v1/study/scheduler", json=payload)
    assert response.status_code == 200, response.text
    trial = response.json()
    assert all(trial["snapshot"]["checks"].values())
    review = {"feasible":4,"ordering":3,"feedback_useful":5,"explanation_clear":4,"comments":"Private comment"}
    assert client.post(f'/api/v1/study/scheduler/{trial["id"]}/review', json=review).status_code == 200
    db.add(AdminAccess(user_id="a")); db.commit()
    data=client.get("/api/v1/study/admin/summary").json()
    assert data["eligible_tasks"] == 0
    assert data["timing_sources"]["rehearsal"] == 3
    assert data["scheduler"]["reviewed"] == 1
    login(db,"b"); join(client)
    assert client.post(f'/api/v1/study/scheduler/{trial["id"]}/review',json=review).status_code == 404
