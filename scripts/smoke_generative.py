"""Two live AI checks using the selected provider and an in-memory database only.

Run: python -m scripts.smoke_generative
No existing user records or tasks are read, changed, or sent to the provider.
"""
import json
from time import monotonic, sleep
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.main import app
from app.modules.events.models import Event
from app.modules.tasks.models import Task, TaskDependency
from app.modules.users.models import User


def main():
    settings = get_settings()
    if not settings.llm_enabled:
        raise SystemExit("Enable LLM_ENABLED for this live check.")
    if not settings.planning_api_key or not settings.planning_api_key.get_secret_value():
        raise SystemExit(f"Configure a key for {settings.llm_provider} in the backend environment first.")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    zone = ZoneInfo("Asia/Kolkata")
    tomorrow = datetime.now(zone).date() + timedelta(days=1)
    report = {"provider": settings.llm_provider, "model": settings.llm_model, "isolated_database": True}
    try:
        with Session(engine, expire_on_commit=False) as db:
            app.dependency_overrides[get_db] = lambda: db
            db.add(User(id="smoke-user", email="smoke@example.com", display_name="Test", time_zone="Asia/Kolkata"))
            db.commit()
            # Deliberately omit TestClient's lifespan to avoid initializing the real database.
            with_client = TestClient(app)
            try:
                request_started = monotonic()
                response = with_client.post("/api/v1/tasks/decompose", json={
                    "user_id": "smoke-user", "title": "Read 10 textbook pages and take brief notes",
                    "description": "A moderately familiar chapter. Take one or two bullet notes per page.",
                    "task_type": "reading", "difficulty": "medium", "quantity_value": 10,
                    "current_time": datetime.now(timezone.utc).isoformat(),
                })
                report["estimate_http_status"] = response.status_code
                if response.status_code != 200:
                    report["success"] = False
                    return save_report(report)
                estimate = response.json()
                if estimate["generation_source"] != "llm":
                    report.update(success=False, reason="Unexpected fallback instead of AI")
                    return save_report(report)
                report["estimate"] = estimate
                print("Live estimate passed.", flush=True)
                assert sum(step["suggested_minutes"] for step in estimate["steps"]) == estimate["personalized_estimate_minutes"]
                db.add_all([
                    Task(id="smoke-read", user_id="smoke-user", title="Read chapter", task_type="reading",
                         difficulty="easy", estimated_minutes=30, status="pending"),
                    Task(id="smoke-summary", user_id="smoke-user", title="Write summary of chapter", task_type="writing",
                         difficulty="easy", estimated_minutes=30, status="pending"),
                ])
                db.flush()
                db.add(TaskDependency(task_id="smoke-summary", depends_on_task_id="smoke-read"))
                event_start = datetime.combine(tomorrow, time(10), zone).astimezone(timezone.utc)
                event_end = event_start + timedelta(hours=1)
                db.add(Event(user_id="smoke-user", title="Fixed appointment", start_at=event_start, end_at=event_end,
                             commute_minutes=0, get_ready_minutes=0, departure_buffer_minutes=0))
                db.commit()
                if settings.llm_provider == "groq":
                    print("Spacing the schedule request for Groq free-tier token limits.", flush=True)
                    sleep(max(0, 60 - (monotonic() - request_started)))
                response = with_client.post("/api/v1/schedules/generate", json={
                    "user_id": "smoke-user", "plan_date": tomorrow.isoformat(),
                    "window_start": "09:00", "window_end": "13:00", "break_minutes": 10,
                })
                report["schedule_http_status"] = response.status_code
                if response.status_code != 200:
                    report["success"] = False
                    return save_report(report)
                schedule = response.json()
                assert schedule["generation_source"] == "llm"
                blocks = schedule["time_blocks"]
                assert [block["task_id"] for block in blocks if block["kind"] == "task"] == ["smoke-read", "smoke-summary"]
                for block in blocks:
                    start = datetime.fromisoformat(block["start_at"].replace("Z", "+00:00"))
                    end = datetime.fromisoformat(block["end_at"].replace("Z", "+00:00"))
                    if start.tzinfo is None:
                        start, end = start.replace(tzinfo=timezone.utc), end.replace(tzinfo=timezone.utc)
                    assert end <= event_start or start >= event_end
                report["schedule"] = {
                    "generation_source": schedule["generation_source"],
                    "planning_explanation": schedule["planning_explanation"],
                    "blocks": [{key: block[key] for key in ("title", "kind", "start_at", "end_at")} for block in blocks],
                    "deferred_count": len(schedule["unscheduled_tasks"]),
                }
                report["success"] = True
                save_report(report)
            finally:
                with_client.close()
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def save_report(report):
    path = Path(f"data/evaluation/{report['provider']}_live_smoke_report.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"success": report.get("success"), "estimate_http_status": report.get("estimate_http_status"),
                      "schedule_http_status": report.get("schedule_http_status"), "report": str(path)}, indent=2))
    if not report.get("success"):
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Avoid dumping requests or environment settings through a traceback.
        print(json.dumps({"success": False, "error_type": type(exc).__name__}))
        raise SystemExit(1) from None
