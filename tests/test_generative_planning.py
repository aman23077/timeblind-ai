import json
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.main import app
from app.modules.events.models import Event
from app.modules.reasoning import generative, llm
from app.modules.schedules.models import Schedule, TimeBlock
from app.modules.schedules.planner import build_schedule_blocks
from app.modules.schedules.schemas import ScheduleGenerateRequest
from app.modules.tasks.models import Task, TaskDependency
from app.modules.tasks.schemas import TaskDecompositionRequest
from app.modules.users.models import User

NOW = datetime(2026, 10, 8, 9, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def configure(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4.1-mini-2025-04-14")
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-only")
    monkeypatch.setenv("LLM_FAILURE_MODE", "fallback")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        session.add_all([User(id="u", email="u@example.com", display_name="U", time_zone="Asia/Kolkata"),
                         User(id="other", email="other@example.com", display_name="Other")])
        session.commit()
        yield session
    engine.dispose()


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    # Do not run the application lifespan, which initializes the real local database.
    test_client = TestClient(app)
    yield test_client
    test_client.close()
    app.dependency_overrides.clear()


def estimate(**updates):
    data = {"estimated_minutes": 40, "lower_minutes": 30, "upper_minutes": 60,
            "explanation": "Includes checking the result.", "assumptions": ["Scope is one short chapter."],
            "steps": [{"title": "Read and annotate", "minutes": 30, "rationale": "Capture the key ideas."},
                      {"title": "Review", "minutes": 10, "rationale": "Check understanding."}]}
    data.update(updates)
    return generative.GeneratedEstimate.model_validate(data)


def task(db, id="t", **updates):
    data = dict(id=id, user_id="u", title=id, task_type="reading", difficulty="easy",
                estimated_minutes=30, status="pending", created_at=NOW)
    data.update(updates)
    value = Task(**data)
    db.add(value)
    db.commit()
    return value


def test_estimate_preserves_full_scope_when_deadline_impossible(db, monkeypatch):
    monkeypatch.setattr(generative, "generate_structured", lambda *args: estimate())
    result = generative.estimate_task(db, TaskDecompositionRequest(
        user_id="u", title="Read chapter", current_time=NOW, deadline_at=NOW + timedelta(minutes=20)))
    assert result.generation_source == "llm"
    assert result.personalized_estimate_minutes == 40
    assert result.fit_status == "overflow" and result.overflow_minutes == 20
    assert sum(step.suggested_minutes for step in result.steps) == 40


@pytest.mark.parametrize("updates", [
    {"upper_minutes": 20}, {"estimated_minutes": 50}, {"estimated_minutes": -5},
    {"estimated_minutes": "40"}, {"steps": []},
])
def test_rejects_invalid_generated_estimates(updates):
    with pytest.raises(ValidationError):
        estimate(**updates)


def test_history_is_completed_scoped_and_bounded(db):
    for i in range(8):
        task(db, f"old{i}", status="completed", actual_minutes=20)
    task(db, "private", user_id="other", status="completed", actual_minutes=100)
    task(db, "unfinished", actual_minutes=50)
    examples = generative.history_examples(db, "u", "reading")
    assert len(examples) == 6
    assert all(item["title"] not in {"private", "unfinished"} for item in examples)
    assert all("user_id" not in item and "feedback_notes" not in item for item in examples)


def test_disabled_makes_no_provider_request(db, monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "false")
    get_settings.cache_clear()
    monkeypatch.setattr(generative, "generate_structured", lambda *args: pytest.fail("Unexpected API call"))
    assert generative.estimate_task(db, TaskDecompositionRequest(title="Read")).generation_source == "rules"


def test_missing_key_falls_back_or_returns_safe_503(db, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    assert generative.estimate_task(db, TaskDecompositionRequest(title="Read")).generation_source == "rules_fallback"
    monkeypatch.setenv("LLM_FAILURE_MODE", "error")
    get_settings.cache_clear()
    with pytest.raises(HTTPException) as failure:
        generative.estimate_task(db, TaskDecompositionRequest(title="Read"))
    assert failure.value.status_code == 503


@pytest.mark.parametrize("ids", [["unknown"], ["t", "t"], []])
def test_invalid_schedule_ids_trigger_fallback(db, monkeypatch, ids):
    items = [task(db)]
    monkeypatch.setattr(generative, "generate_structured", lambda *args: generative.GeneratedOrder(
        ordered_task_ids=ids, explanation="Order"))
    order, metadata = generative.order_tasks(items, NOW, NOW + timedelta(hours=2), [])
    assert order is None and metadata["generation_source"] == "rules_fallback"


def test_scheduler_honors_dependencies_deadlines_and_events(db):
    first = task(db, "first", estimated_minutes=20)
    second = task(db, "second", estimated_minutes=20)
    late = task(db, "expired", deadline_at=NOW - timedelta(minutes=1))
    db.add(TaskDependency(task_id=second.id, depends_on_task_id=first.id))
    db.add(Event(user_id="u", title="Appointment", start_at=NOW + timedelta(minutes=40),
                 end_at=NOW + timedelta(minutes=90), commute_minutes=0,
                 get_ready_minutes=0, departure_buffer_minutes=0))
    db.commit()
    blocks, deferred = build_schedule_blocks(db, "s", "u", [first, second, late], NOW,
        NOW + timedelta(hours=3), 10, ordered_task_ids=["second", "expired", "first"])
    assert [block.task_id for block in blocks if block.kind == "task"] == ["first", "second"]
    assert [item["task_id"] for item in deferred] == ["expired"]
    assert all(block.end_at <= NOW + timedelta(minutes=40) or block.start_at >= NOW + timedelta(minutes=90) for block in blocks)
    assert all(left.end_at <= right.start_at for left, right in zip(blocks, blocks[1:]))


def test_dependency_cycle_is_deferred(db):
    first, second = task(db, "a"), task(db, "b")
    db.add_all([TaskDependency(task_id="a", depends_on_task_id="b"), TaskDependency(task_id="b", depends_on_task_id="a")])
    db.commit()
    blocks, deferred = build_schedule_blocks(db, "s", "u", [first, second], NOW, NOW + timedelta(hours=2), 0)
    assert not blocks and len(deferred) == 2


def test_old_event_without_end_does_not_block_today(db):
    item = task(db)
    db.add(Event(user_id="u", title="Old", start_at=NOW - timedelta(days=5)))
    db.commit()
    blocks, _ = build_schedule_blocks(db, "s", "u", [item], NOW, NOW + timedelta(hours=2), 0)
    assert len(blocks) == 1


def test_schedule_route_converts_local_time_and_uses_generated_order(client, db, monkeypatch):
    task(db, "a")
    task(db, "b")
    monkeypatch.setattr(generative, "generate_structured", lambda *args: generative.GeneratedOrder(
        ordered_task_ids=["b", "a"], explanation="Start with b."))
    response = client.post("/api/v1/schedules/generate", json={
        "user_id": "u", "plan_date": "2026-10-08", "window_start": "09:00", "window_end": "12:00"})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["generation_source"] == "llm"
    assert [block["task_id"] for block in result["time_blocks"] if block["kind"] == "task"] == ["b", "a"]
    assert datetime.fromisoformat(result["time_blocks"][0]["start_at"].replace("Z", "+00:00")).hour == 3


def test_failed_regeneration_preserves_draft(client, db, monkeypatch):
    task(db)
    schedule = Schedule(id="s", user_id="u", plan_date=date(2026, 10, 8))
    db.add(schedule)
    db.add(TimeBlock(id="old", user_id="u", schedule_id="s", task_id="t", title="Old",
                     start_at=NOW, end_at=NOW + timedelta(minutes=30), status="planned"))
    db.commit()
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("LLM_FAILURE_MODE", "error")
    get_settings.cache_clear()
    response = client.post("/api/v1/schedules/generate", json={
        "user_id": "u", "plan_date": "2026-10-08", "window_start": "09:00", "window_end": "12:00"})
    assert response.status_code == 503
    assert db.get(TimeBlock, "old") is not None


def test_reversed_window_rejected():
    with pytest.raises(ValidationError):
        ScheduleGenerateRequest(user_id="u", plan_date=date.today(), window_start="12:00", window_end="09:00")


def mock_provider(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr(llm.httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))


def test_responses_api_contract_and_no_storage(monkeypatch):
    def handler(request):
        body = json.loads(request.content)
        assert body["store"] is False
        assert body["text"]["format"]["strict"] is True
        assert body["text"]["format"]["schema"]["additionalProperties"] is False
        assert request.url == "https://api.openai.com/v1/responses"
        return httpx.Response(200, json={"status": "completed", "output": [{"type": "message", "content": [
            {"type": "output_text", "text": estimate().model_dump_json()}]}]})
    mock_provider(monkeypatch, handler)
    assert llm.generate_structured("Plan", {}, generative.GeneratedEstimate).estimated_minutes == 40


@pytest.mark.parametrize("payload", [
    {"status": "incomplete", "output": []},
    {"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal"}]}]},
    {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "not json"}]}]},
])
def test_bad_provider_output_fails_safely(monkeypatch, payload):
    mock_provider(monkeypatch, lambda request: httpx.Response(200, json=payload))
    with pytest.raises(llm.PlanningUnavailable):
        llm.generate_structured("Plan", {}, generative.GeneratedEstimate)


@pytest.mark.parametrize("status", [401, 429, 500])
def test_provider_errors_do_not_expose_body(monkeypatch, status):
    mock_provider(monkeypatch, lambda request: httpx.Response(status, text="private provider details"))
    with pytest.raises(llm.PlanningUnavailable) as failure:
        llm.generate_structured("Plan", {}, generative.GeneratedEstimate)
    assert "private" not in str(failure.value)


def test_timeout_fails_safely(monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout("private details", request=request)
    mock_provider(monkeypatch, handler)
    with pytest.raises(llm.PlanningUnavailable) as failure:
        llm.generate_structured("Plan", {}, generative.GeneratedEstimate)
    assert "private" not in str(failure.value)


@pytest.mark.parametrize("code", ["insufficient_quota", "credit_balance_exhausted", "project_spend_limit_exceeded"])
def test_quota_error_is_distinguished_from_rate_limit(monkeypatch, code):
    mock_provider(monkeypatch, lambda request: httpx.Response(429, json={
        "error": {"code": code, "message": "private provider details"}}))
    with pytest.raises(llm.PlanningUnavailable) as failure:
        llm.generate_structured("Plan", {}, generative.GeneratedEstimate)
    assert str(failure.value) == code


def test_decompose_route_passes_description_and_history(client, db, monkeypatch):
    task(db, "previous", status="completed", actual_minutes=35)
    def generate(instructions, context, schema):
        assert context["task"]["description"] == "Take notes for the exam"
        assert "user_id" not in context["task"]
        assert len(context["history"]) == 1
        return estimate()
    monkeypatch.setattr(generative, "generate_structured", generate)
    response = client.post("/api/v1/tasks/decompose", json={
        "title": "Read", "user_id": "u", "description": "Take notes for the exam"})
    assert response.status_code == 200
    assert response.json()["generation_source"] == "llm"


def test_active_schedule_is_not_replaced(client, db):
    db.add(Schedule(id="s", user_id="u", plan_date=date(2026, 10, 8)))
    db.add(TimeBlock(id="active", user_id="u", schedule_id="s", title="Active",
                     start_at=NOW, end_at=NOW + timedelta(minutes=30), status="active"))
    db.commit()
    response = client.post("/api/v1/schedules/generate", json={
        "user_id": "u", "plan_date": "2026-10-08", "window_start": "09:00", "window_end": "12:00"})
    assert response.status_code == 409
    assert db.get(TimeBlock, "active") is not None


def use_groq(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("LLM_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-only")
    get_settings.cache_clear()


def test_groq_request_uses_groq_key_endpoint_and_strict_schema(monkeypatch):
    use_groq(monkeypatch)
    def handler(request):
        body = json.loads(request.content)
        assert request.url == "https://api.groq.com/openai/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer groq-test-only"
        assert body["model"] == "openai/gpt-oss-120b"
        assert body["messages"][0] == {"role": "system", "content": "Plan"}
        assert json.loads(body["messages"][1]["content"]) == {"task": "Read"}
        assert body["response_format"]["json_schema"]["strict"] is True
        assert body["response_format"]["json_schema"]["schema"]["additionalProperties"] is False
        assert body["max_completion_tokens"] == get_settings().llm_max_output_tokens
        assert body["reasoning_effort"] == "low"
        assert body["include_reasoning"] is False
        assert "store" not in body and "text" not in body and "tools" not in body
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {
            "content": estimate().model_dump_json(), "reasoning": "not used as output"}}]})
    mock_provider(monkeypatch, handler)
    result = llm.generate_structured("Plan", {"task": "Read"}, generative.GeneratedEstimate)
    assert result.estimated_minutes == 40


@pytest.mark.parametrize("payload", [
    {"choices": []},
    {"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]},
    {"choices": [{"finish_reason": "stop", "message": {"content": None, "refusal": "Refused"}}]},
    {"choices": [{"finish_reason": "stop", "message": {"content": "not json"}}]},
    {"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]},
])
def test_groq_rejects_truncated_refused_and_invalid_output(monkeypatch, payload):
    use_groq(monkeypatch)
    mock_provider(monkeypatch, lambda request: httpx.Response(200, json=payload))
    with pytest.raises(llm.PlanningUnavailable):
        llm.generate_structured("Plan", {}, generative.GeneratedEstimate)


def test_missing_groq_key_never_uses_openai_key(monkeypatch):
    use_groq(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "")
    get_settings.cache_clear()
    mock_provider(monkeypatch, lambda request: pytest.fail("Must not send any request without Groq key"))
    with pytest.raises(llm.PlanningUnavailable, match="missing_key"):
        llm.generate_structured("Plan", {}, generative.GeneratedEstimate)


def test_groq_generated_estimate_uses_existing_api_contract(client, monkeypatch):
    use_groq(monkeypatch)
    mock_provider(monkeypatch, lambda request: httpx.Response(200, json={"choices": [{
        "finish_reason": "stop", "message": {"content": estimate().model_dump_json()}}]}))
    response = client.post("/api/v1/tasks/decompose", json={"title": "Read"})
    assert response.status_code == 200
    assert response.json()["generation_source"] == "llm"
    assert response.json()["model_name"] == "openai/gpt-oss-120b"


@pytest.mark.parametrize("status", [401, 429, 500])
def test_groq_http_errors_do_not_trigger_paid_provider_fallback(monkeypatch, status):
    use_groq(monkeypatch)
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(status, text="private details")
    mock_provider(monkeypatch, handler)
    with pytest.raises(llm.PlanningUnavailable):
        llm.generate_structured("Plan", {}, generative.GeneratedEstimate)
    assert calls == ["https://api.groq.com/openai/v1/chat/completions"]


@pytest.mark.parametrize("status,category", [
    (401, "invalid_api_key"), (403, "access_denied"), (404, "model_not_found"),
    (429, "rate_limit_exceeded"), (503, "provider_unavailable"),
])
def test_http_status_produces_safe_specific_failure(monkeypatch, status, category):
    use_groq(monkeypatch)
    mock_provider(monkeypatch, lambda request: httpx.Response(status, text="private provider text"))
    with pytest.raises(llm.PlanningUnavailable) as failure:
        llm.generate_structured("Plan", {}, generative.GeneratedOrder)
    assert str(failure.value) == category


@pytest.mark.parametrize("exception,category", [
    (httpx.ReadTimeout, "timeout"), (httpx.ConnectError, "connection_error"),
])
def test_network_failures_are_distinguished(monkeypatch, exception, category):
    def handler(request):
        raise exception("private connection details", request=request)
    mock_provider(monkeypatch, handler)
    with pytest.raises(llm.PlanningUnavailable) as failure:
        llm.generate_structured("Plan", {}, generative.GeneratedOrder)
    assert str(failure.value) == category


@pytest.mark.parametrize("content", ["not json", "{}"])
def test_invalid_model_output_has_validation_category(monkeypatch, content):
    use_groq(monkeypatch)
    mock_provider(monkeypatch, lambda request: httpx.Response(200, json={"choices": [{
        "finish_reason": "stop", "message": {"content": content}}]}))
    with pytest.raises(llm.PlanningUnavailable) as failure:
        llm.generate_structured("Plan", {}, generative.GeneratedOrder)
    assert str(failure.value) == "invalid_output"


@pytest.mark.parametrize("category,expected", [
    ("missing_key", "no API key"), ("rate_limit_exceeded", "request limit"),
    ("invalid_api_key", "rejected"), ("timeout", "timed out"),
    ("invalid_task_ids", "every task exactly once"),
    ("credit_balance_exhausted", "quota is exhausted"),
    ("private arbitrary provider message", "currently unavailable"),
])
def test_schedule_fallback_explains_reason_without_exposing_provider_text(client, db, monkeypatch, category, expected):
    task(db)
    def unavailable(*args):
        raise llm.PlanningUnavailable(category)
    monkeypatch.setattr(generative, "generate_structured", unavailable)
    response = client.post("/api/v1/schedules/generate", json={
        "user_id": "u", "plan_date": "2026-10-08", "window_start": "09:00", "window_end": "12:00"})
    assert response.status_code == 200
    result = response.json()
    assert result["generation_source"] == "rules_fallback"
    assert expected in result["generation_warning"]
    assert "standard rules" in result["generation_warning"]
    assert "private" not in result["generation_warning"]
    assert len(result["time_blocks"]) == 1


def test_overdue_task_explains_deadline_without_changing_task(db):
    item = task(db, deadline_at=NOW - timedelta(days=1))
    blocks, deferred = build_schedule_blocks(db, "s", "u", [item], NOW, NOW + timedelta(hours=3), 0)
    assert not blocks
    assert "deadline is before this planning window" in deferred[0]["reason"]
    assert "Update or remove" in deferred[0]["reason"]
    assert item.status == "pending"


def test_long_task_explains_buffer_and_available_time(db):
    item = task(db, estimated_minutes=300, difficulty="medium")
    _, deferred = build_schedule_blocks(db, "s", "u", [item], NOW, NOW + timedelta(hours=3), 0)
    assert "305 uninterrupted minutes" in deferred[0]["reason"]
    assert "5-minute protective buffer" in deferred[0]["reason"]
    assert "Only 180 minutes" in deferred[0]["reason"]


def test_fragmented_time_explains_why_total_hours_are_insufficient(db):
    item = task(db, estimated_minutes=90)
    db.add(Event(user_id="u", title="Fixed", start_at=NOW + timedelta(hours=1),
                 end_at=NOW + timedelta(hours=2), commute_minutes=0,
                 get_ready_minutes=0, departure_buffer_minutes=0))
    db.commit()
    _, deferred = build_schedule_blocks(db, "s", "u", [item], NOW, NOW + timedelta(hours=3), 0)
    assert "120 free minutes" in deferred[0]["reason"]
    assert "longest gap is 60 minutes" in deferred[0]["reason"]
    assert "does not split" in deferred[0]["reason"]


def test_blocked_dependency_explains_prerequisite(db):
    prerequisite = task(db, "large", estimated_minutes=300)
    dependent = task(db, "small", estimated_minutes=20)
    db.add(TaskDependency(task_id=dependent.id, depends_on_task_id=prerequisite.id))
    db.commit()
    _, deferred = build_schedule_blocks(db, "s", "u", [prerequisite, dependent], NOW, NOW + timedelta(hours=2), 0)
    reasons = {item["task_id"]: item["reason"] for item in deferred}
    assert "prerequisite task" in reasons[dependent.id]
