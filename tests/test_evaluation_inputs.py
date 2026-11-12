import csv
import json
import sys
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from scripts import evaluate_generative as evaluation


@pytest.mark.parametrize("estimate_input", ["none", "stored"])
def test_evaluation_separates_reference_estimate_from_model_input(tmp_path, monkeypatch, estimate_input):
    source = tmp_path / "tasks.csv"
    output = tmp_path / "report.json"
    fields = ["user_id", "title", "status", "actual_minutes", "estimated_minutes",
              "created_at", "deadline_at", "task_type", "difficulty", "quantity_value"]
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for day in range(1, 6):
            writer.writerow(dict(user_id="synthetic-user", title=f"Read chapter {day}",
                                 status="completed", actual_minutes=60, estimated_minutes=80,
                                 created_at=f"2026-01-{day:02d}T09:00:00", deadline_at="",
                                 task_type="reading", difficulty="medium", quantity_value=10))
    monkeypatch.setattr(evaluation, "get_settings", lambda: SimpleNamespace(
        planning_api_key=SecretStr("mock-only"), llm_provider="groq", llm_model="mock"))
    captured = {}

    def rules(payload):
        captured["rules_input"] = payload.estimated_minutes
        return SimpleNamespace(personalized_estimate_minutes=40)

    def generate(instructions, context, schema):
        captured["llm_input"] = context["task"]["estimated_minutes"]
        assert "user_id" not in context["task"]
        assert context["history"] == []
        return SimpleNamespace(estimated_minutes=30, lower_minutes=25, upper_minutes=35)

    monkeypatch.setattr(evaluation, "decompose_task", rules)
    monkeypatch.setattr(evaluation, "generate_structured", generate)
    argv = ["evaluate_generative", "--csv", str(source), "--out", str(output),
            "--live", "--limit", "1", "--request-spacing", "0"]
    if estimate_input == "stored":
        argv += ["--estimate-input", "stored"]
    monkeypatch.setattr(sys, "argv", argv)
    evaluation.main()
    report = json.loads(output.read_text(encoding="utf-8"))
    expected = 80 if estimate_input == "stored" else None
    assert captured == {"rules_input": expected, "llm_input": expected}
    assert report["estimate_input"] == estimate_input
    assert report["results"][0]["raw_estimate_minutes"] == 80
    assert report["metrics"]["raw"]["mae_minutes"] == 20
    assert report["metrics"]["llm"]["mae_minutes"] == 30
