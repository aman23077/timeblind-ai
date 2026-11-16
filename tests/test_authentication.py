from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.auth import AccountCredential, COOKIE_NAME, LoginSession, PasswordReset, digest, verify_password
from app.core.config import get_settings
from app.core.database import Base, get_db, utc_now
from app.main import app
from app.modules.tasks.models import Task
from app.modules.users.auth_routes import new_reset_token
from app.modules.users.models import User

PASSWORD = "A long test passphrase 123"


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    get_settings.cache_clear()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app, headers={"X-TimeBlind-Client": "web"})
        yield client, db
        client.close()
    app.dependency_overrides.clear()
    get_settings.cache_clear()
    engine.dispose()


def register(client, email="alice@example.com"):
    response = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD, "display_name": "Test"})
    assert response.status_code == 201, response.text
    return response.json()


def test_register_normalization_password_storage_and_duplicate(setup):
    client, db = setup
    user = register(client, " Alice@Example.com ")
    assert user["email"] == "alice@example.com"
    assert "password" not in str(user)
    assert client.cookies.get(COOKIE_NAME)
    credential = db.scalar(select(AccountCredential))
    assert credential.password_hash != PASSWORD
    assert verify_password(PASSWORD, credential.password_hash)
    assert client.get("/api/v1/auth/me").json()["id"] == user["id"]
    duplicate = client.post("/api/v1/auth/register", json={"email": "ALICE@example.com", "password": PASSWORD, "display_name": "Changed"})
    assert duplicate.status_code == 409
    assert db.get(User, user["id"]).display_name == "Test"


@pytest.mark.parametrize("email,password", [("invalid", PASSWORD), ("a@example.com", "short"), ("a@example.com", "a" * 129)])
def test_invalid_registration(setup, email, password):
    client, _ = setup
    assert client.post("/api/v1/auth/register", json={"email": email, "password": password, "display_name": "Test"}).status_code == 422


def test_login_logout_expiry_and_old_demo_routes(setup):
    client, db = setup
    user = register(client)
    token = client.cookies.get(COOKIE_NAME)
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401
    client.cookies.set(COOKIE_NAME, token)
    assert client.get("/api/v1/tasks").status_code == 401
    client.cookies.clear()
    assert client.get("/api/v1/users/by-email/alice@example.com").status_code == 401
    assert client.post("/api/v1/users/ensure", json={"email": user["email"], "display_name": "Other"}).status_code in (401, 404, 405)
    assert client.post("/api/v1/auth/login", json={"email": user["email"], "password": "wrong"}).status_code == 401
    response = client.post("/api/v1/auth/login", json={"email": "ALICE@example.com", "password": PASSWORD})
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    session = db.scalar(select(LoginSession).where(LoginSession.token_hash == digest(client.cookies.get(COOKIE_NAME))))
    session.expires_at = utc_now() - timedelta(seconds=1)
    db.commit()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_account_isolation_and_foreign_references(setup):
    client, _ = setup
    alice = register(client)
    task = client.post("/api/v1/tasks", json={"user_id": alice["id"], "title": "Private task"}).json()
    session = client.post("/api/v1/sessions", json={"user_id": alice["id"], "task_id": task["id"], "started_at": utc_now().isoformat()}).json()
    bob = register(client, "bob@example.com")
    assert client.get("/api/v1/tasks").json() == []
    assert client.get("/api/v1/tasks?user_id=" + alice["id"]).status_code == 404
    assert client.get("/api/v1/tasks/" + task["id"]).status_code == 404
    assert client.patch("/api/v1/tasks/" + task["id"], json={"title": "Changed"}).status_code == 404
    assert client.post("/api/v1/tasks", json={"user_id": alice["id"], "title": "Forged"}).status_code == 404
    assert client.post("/api/v1/sessions", json={"user_id": bob["id"], "task_id": task["id"], "started_at": utc_now().isoformat()}).status_code == 404
    own = client.post("/api/v1/tasks", json={"user_id": bob["id"], "title": "My task"}).json()
    assert client.post(f'/api/v1/tasks/{own["id"]}/dependencies', json={"depends_on_task_id": task["id"]}).status_code == 404
    assert client.post(f'/api/v1/activity/sessions/{session["id"]}/enable?user_id={bob["id"]}').status_code == 404
    assert client.get(f'/api/v1/activity/sessions/{session["id"]}?user_id={alice["id"]}').status_code == 404
    assert client.get("/api/v1/users/" + alice["id"]).status_code == 404
    assert [item["id"] for item in client.get("/api/v1/users").json()] == [bob["id"]]


@pytest.mark.parametrize("path", ["tasks", "events", "goals", "sessions", "schedules", "insights?user_id=u",
                                  "context/events", "behaviour/events", "interventions", "interventions/reminders"])
def test_workspace_requires_login(setup, path):
    client, _ = setup
    assert client.get("/api/v1/" + path).status_code == 401


def test_legacy_account_setup_preserves_data_and_token_is_single_use(setup):
    client, db = setup
    legacy = User(id="legacy", email="Old@Example.com", display_name="Original")
    db.add(legacy)
    db.add(Task(id="old-task", user_id="legacy", title="Saved work"))
    db.commit()
    response = client.post("/api/v1/auth/register", json={"email": "old@example.com", "password": PASSWORD, "display_name": "Attacker"})
    assert response.status_code == 409
    token = new_reset_token(db, legacy)
    assert client.post("/api/v1/auth/reset-password", json={"token": token, "password": PASSWORD}).status_code == 200
    assert client.post("/api/v1/auth/reset-password", json={"token": token, "password": PASSWORD}).status_code == 400
    assert client.post("/api/v1/auth/login", json={"email": "old@example.com", "password": PASSWORD}).status_code == 200
    assert client.get("/api/v1/tasks").json()[0]["title"] == "Saved work"


def test_password_reset_revokes_login_and_companion(setup):
    client, db = setup
    user = register(client)
    login_token = client.cookies.get(COOKIE_NAME)
    session = client.post("/api/v1/sessions", json={"user_id": user["id"], "started_at": utc_now().isoformat()}).json()
    companion = client.post(f'/api/v1/activity/sessions/{session["id"]}/enable?user_id={user["id"]}').json()["token"]
    assert client.get("/api/v1/activity/companion", headers={"Authorization": "Bearer " + companion}).status_code == 200
    token = new_reset_token(db, db.get(User, user["id"]))
    assert client.post("/api/v1/auth/reset-password", json={"token": token, "password": PASSWORD + "new"}).status_code == 200
    client.cookies.set(COOKIE_NAME, login_token)
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/activity/companion", headers={"Authorization": "Bearer " + companion}).status_code == 403


def test_csrf_and_rate_limit(setup):
    client, _ = setup
    data = {"email": "none@example.com", "password": PASSWORD}
    assert client.post("/api/v1/auth/login", json=data, headers={"Origin": "https://untrusted.example"}).status_code == 403
    assert client.post("/api/v1/auth/login", json=data, headers={"X-TimeBlind-Client": ""}).status_code == 403
    for _ in range(10):
        assert client.post("/api/v1/auth/login", json=data).status_code == 401
    assert client.post("/api/v1/auth/login", json=data).status_code == 429


def test_expired_reset_and_email_delivery(setup, monkeypatch):
    from app.modules.users import auth_routes
    client, db = setup
    user = register(client)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "no-reply@example.com")
    get_settings.cache_clear()
    sent = []
    monkeypatch.setattr(auth_routes, "send_reset_email", lambda email, token: sent.append((email, token)))
    response = client.post("/api/v1/auth/forgot-password", json={"email": user["email"]})
    assert response.status_code == 200
    assert len(sent) == 1 and sent[0][0] == user["email"]
    code = db.scalar(select(PasswordReset))
    assert code.token_hash == digest(sent[0][1])
    code.expires_at = utc_now() - timedelta(seconds=1)
    db.commit()
    assert client.post("/api/v1/auth/reset-password", json={"token": sent[0][1], "password": PASSWORD}).status_code == 400
    assert client.post("/api/v1/auth/forgot-password", json={"email": "absent@example.com"}).json() == response.json()
    assert len(sent) == 1


def test_production_cookie_is_secure(setup, monkeypatch):
    client, _ = setup
    monkeypatch.setenv("ENVIRONMENT", "production")
    get_settings.cache_clear()
    response = client.post("/api/v1/auth/register", json={"email": "alice@example.com", "password": PASSWORD, "display_name": "Test"})
    assert response.status_code == 201
    assert "Secure" in response.headers["set-cookie"]


def test_persistent_recovery_key_reuse_targeting_and_rotation(setup):
    from app.core.auth import RecoveryKey
    client, db = setup
    first = register(client)
    second = register(client, "bob@example.com")
    key = "persistent-test-key-" + "a" * 32
    record = RecoveryKey(name="universal", key_hash=digest(key))
    db.add(record)
    db.commit()
    for email in (first["email"], second["email"], first["email"].upper()):
        response = client.post("/api/v1/auth/reset-password", json={
            "email": email, "token": key, "password": PASSWORD + "updated"})
        assert response.status_code == 200, response.text
        assert db.scalar(select(RecoveryKey)).key_hash == digest(key)
    assert client.post("/api/v1/auth/login", json={"email": first["email"], "password": PASSWORD + "updated"}).status_code == 200
    assert client.post("/api/v1/auth/reset-password", json={"token": key, "password": PASSWORD}).status_code == 422
    assert client.post("/api/v1/auth/reset-password", json={"email": "missing@example.com", "token": key, "password": PASSWORD}).status_code == 404
    record.key_hash = digest("replacement-key")
    db.commit()
    assert client.post("/api/v1/auth/reset-password", json={"email": second["email"], "token": key, "password": PASSWORD}).status_code == 400
