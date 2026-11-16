"""Reproducible synthetic data and an isolated benchmark of the actual app policies.

Run from the repository root: python -m scripts.synthetic_benchmark --seed-account
No external model calls. See docs/synthetic-evaluation.md for interpretation.
"""
import argparse
import csv
import hashlib
import json
import math
import random
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.main import app  # registers the application's model tables
from app.core.database import Base, SessionLocal, initialize_database
from app.core.auth import AccountCredential, hash_password
from app.modules.users.datasets import DatasetAccount
from app.modules.users.models import User
from app.modules.tasks.models import Task, TaskDependency
from app.modules.tasks.schemas import TaskDecompositionRequest
from app.modules.sessions.models import SessionRecord, RemainingEstimate
from app.modules.schedules.models import Schedule, AdaptivePlan, TimeBlock, PlanRevision
from app.modules.schedules.planner import build_schedule_blocks
from app.modules.events.models import Event
from app.modules.behaviour.activity import ActivityMonitor, ActivityInterval, aware
from app.modules.interventions.models import Intervention, Reminder, PolicyState
from app.modules.interventions.policy import activity_signal, tick, replan
from app.modules.reasoning.task_decomposer import decompose_task

DATASET = "btp-synthetic-v1"
TEST_EMAIL = "timeblind-btp-test@example.com"
NOW = datetime(2026, 10, 1, 10, tzinfo=timezone.utc)
FIXTURE_MODELS = (Task, TaskDependency, Schedule, TimeBlock, AdaptivePlan, SessionRecord, RemainingEstimate,
                  Event, ActivityMonitor, ActivityInterval, Reminder, Intervention, PlanRevision)


def identity(value):
    return str(uuid5(NAMESPACE_URL, DATASET + "/" + value))


def duration_rows(seed):
    rng = random.Random(seed)
    rows = []
    # Independent workload simulator. These constants are assumptions, not measured data.
    workloads = [("reading", "Read pages", 2.7), ("coding", "Implement features", 27),
                 ("assignment", "Solve questions", 18), ("writing", "Write sections", 13),
                 ("study", "Revise topics", 19)]
    for participant in range(15):
        speed = rng.uniform(.7, 1.5)
        split = "train" if participant < 9 else "validation" if participant < 12 else "test"
        for index in range(20):
            kind, title, unit = workloads[index % len(workloads)]
            difficulty = rng.choice(["easy", "medium", "hard"])
            quantity = rng.randint(5, 30) if kind == "reading" else rng.randint(1, 5)
            title = f"{title}: {quantity} ({difficulty})"
            latent_work = (8 + unit * quantity) * {"easy": .8, "medium": 1, "hard": 1.45}[difficulty] * speed
            interruptions = rng.randint(5, 30) if rng.random() < .25 else 0
            actual = max(10, round(latent_work * rng.lognormvariate(0, .18) + interruptions))
            predicted = NOW - timedelta(days=25) + timedelta(days=index, hours=participant % 5)
            rules = decompose_task(TaskDecompositionRequest(title=title, task_type=kind,
                difficulty=difficulty, quantity_value=quantity)).personalized_estimate_minutes
            rows.append(dict(task_id=identity(f"p{participant}/t{index}"), data_source="synthetic",
                dataset_id=DATASET, simulated_participant_id=f"p{participant:02d}", split=split,
                title=title, task_type=kind, difficulty=difficulty, quantity_value=quantity,
                predicted_at=predicted.isoformat(), completed_at=(predicted + timedelta(minutes=actual)).isoformat(),
                rules_minutes=rules, actual_minutes=actual, llm_status="not_run"))
    return rows


def policy_cases():
    # Expected labels are specified before executing policies, including boundary cases.
    cases = [
        ("steady_focus", "steady", "none", {}),
        ("two_legitimate_switches", "three_runs", "none", {"switches": 2}),
        ("three_switches_below_threshold", "four_runs", "none", {"switches": 3}),
        ("four_switches_at_threshold", "five_runs", "context_switches", {"switches": 4}),
        ("nine_sustained_switches", "burst", "context_switches", {"switches": 9}),
        ("brief_alt_tab", "brief", "none", {"switches": 0}),
        ("idle_118_seconds", "idle", "none", {"idle": 118}),
        ("idle_120_seconds", "idle", "idle", {"idle": 120}),
        ("idle_180_seconds", "idle", "idle", {"idle": 180}),
        ("unknown_observation_gap", "unknown", "none", {}),
        ("low_coverage_switches", "sparse", "none", {}),
        ("stale_monitor", "burst", "none", {"stale": True}),
        ("disabled_monitor", "burst", "none", {"disabled": True}),
        ("slippage_4_minutes", "steady", "none", {"overrun": 4, "duration": 20}),
        ("slippage_5_minutes", "steady", "slippage", {"overrun": 5, "duration": 25}),
        ("slippage_below_fraction", "steady", "none", {"overrun": 5, "duration": 30}),
        ("slippage_priority_over_switches", "burst", "slippage", {"overrun": 10, "duration": 30}),
        ("upcoming_5_minutes", "reminder", "upcoming", {"start_offset": 5}),
        ("upcoming_6_minutes", "reminder", "none", {"start_offset": 6}),
        ("late_4_minutes", "reminder", "none", {"start_offset": -4}),
        ("late_5_minutes", "reminder", "late_start", {"start_offset": -5}),
        ("cooldown_suppresses_repeat", "burst", "none", {"cooldown": 10}),
        ("minimal_cooldown_suppresses_repeat", "burst", "none", {"cooldown": 20}),
    ]
    return [dict(id=name, pattern=pattern, expected=expected, **options) for name, pattern, expected, options in cases]


def add_policy_case(db, case, uid="u", prefix="", now=NOW):
    sid, mid = prefix + "session", prefix + "monitor"
    if case["pattern"] == "reminder":
        schedule = Schedule(id=prefix + "schedule", user_id=uid, plan_date=now.date())
        start = now + timedelta(minutes=case["start_offset"])
        task = Task(id=prefix + "task", user_id=uid, title="Synthetic reminder task", estimated_minutes=20, difficulty="easy")
        db.add_all([schedule, task, AdaptivePlan(schedule_id=schedule.id, user_id=uid,
            window_start=now - timedelta(minutes=10), window_end=now + timedelta(hours=2), break_minutes=0),
            TimeBlock(schedule_id=schedule.id, user_id=uid, task_id=task.id, title=task.title,
                      start_at=start, end_at=start + timedelta(minutes=20), planned_duration_minutes=20)])
    else:
        age = case.get("duration", 30) + case["overrun"] if "overrun" in case else 5
        task = Task(id=prefix + "task", user_id=uid, title="Synthetic observed task", estimated_minutes=case.get("duration", 30), difficulty="easy")
        session = SessionRecord(id=sid, user_id=uid, task_id=task.id, started_at=now - timedelta(minutes=age))
        monitor = ActivityMonitor(id=mid, session_id=sid, token_hash=hashlib.sha256(mid.encode()).hexdigest(),
            enabled=not case.get("disabled", False), enabled_at=session.started_at,
            last_seen_at=now - timedelta(seconds=20 if case.get("stale") else 0))
        db.add_all([task, session, monitor])
        for i in range(150):
            pattern, state, app_name = case["pattern"], "active", "editor.exe"
            if pattern in {"burst", "sparse", "three_runs", "four_runs", "five_runs"}:
                length = {"burst": 15, "sparse": 15, "three_runs": 50, "four_runs": 38, "five_runs": 30}[pattern]
                app_name = "editor.exe" if (i // length) % 2 else "browser.exe"
            if pattern == "brief" and i % 15 == 0:
                app_name = "browser.exe"
            if pattern == "idle" and i >= 150 - case["idle"] // 2:
                state, app_name = "idle", None
            if pattern == "unknown" or (pattern == "sparse" and i < 100):
                state, app_name = "unknown", None
            start = now - timedelta(seconds=300 - i * 2)
            db.add(ActivityInterval(monitor_id=mid, sequence=i + 1, started_at=start,
                ended_at=start + timedelta(seconds=2), state=state, app_name=app_name))
    if case.get("cooldown"):
        db.add(PolicyState(user_id=uid, next_evaluation_at=now, next_nudge_at=now + timedelta(minutes=case["cooldown"]), snoozed_until=now))
    db.commit()


def policy_result(db, case):
    add_policy_case(db, case)
    tick(db, "u", NOW)
    db.commit()
    emitted = db.scalars(select(Intervention)).all()
    actual = emitted[0].kind.removeprefix("policy_") if emitted else "none"
    snapshot = db.scalar(select(PolicyState)).snapshot
    checks = {"label": actual == case["expected"], "at_most_one": len(emitted) <= 1}
    if "switches" in case:
        checks["switch_count"] = snapshot["sessions"][0]["switches"] == case["switches"]
    if emitted:
        tick(db, "u", NOW + timedelta(seconds=31))
        db.commit()
        checks["no_repeat_within_cooldown"] = len(db.scalars(select(Intervention)).all()) == 1
        next_nudge = aware(db.scalar(select(PolicyState)).next_nudge_at)
        checks["cooldown_duration"] = next_nudge == NOW + timedelta(minutes=10)
    return dict(id=case["id"], expected=case["expected"], actual=actual, checks=checks, passed=all(checks.values()))


def schedule_result(db, case):
    horizon = case["window"]
    runtime = AdaptivePlan(id="runtime", schedule_id="s", user_id="u", window_start=NOW - timedelta(hours=1),
                           window_end=NOW + timedelta(minutes=horizon), break_minutes=case.get("break", 0))
    db.add_all([Schedule(id="s", user_id="u", plan_date=NOW.date()), runtime])
    tasks = []
    for i, duration in enumerate(case["durations"]):
        task = Task(id=f"t{i}", user_id="u", title=f"Synthetic task {i}", estimated_minutes=duration,
                    difficulty="easy", priority="high" if i == 0 else "medium")
        if i == 0 and case.get("deadline"):
            task.deadline_at = NOW + timedelta(minutes=case["deadline"])
        tasks.append(task)
        db.add(task)
    if case.get("dependency"):
        db.add(TaskDependency(task_id="t0", depends_on_task_id="t1"))
    if case.get("completed"):
        tasks[0].status = "completed"
    if case.get("event"):
        left, right = case["event"]
        db.add(Event(user_id="u", title="Synthetic event", start_at=NOW + timedelta(minutes=left),
                     end_at=NOW + timedelta(minutes=right), commute_minutes=0, get_ready_minutes=0, departure_buffer_minutes=0))
    active = None
    if case.get("remaining"):
        active = TimeBlock(id="active", schedule_id="s", user_id="u", task_id="t0", title="Active",
            start_at=NOW - timedelta(minutes=30), end_at=NOW - timedelta(minutes=5),
            planned_duration_minutes=25, status="active")
        db.add_all([active, SessionRecord(id="running", user_id="u", task_id="t0", time_block_id="active",
            started_at=active.start_at), RemainingEstimate(session_id="running", remaining_minutes=case["remaining"], reported_at=NOW)])
    db.commit()
    # Frozen baseline consists of an original plan beginning 20 minutes before the disruption.
    static_blocks, _ = build_schedule_blocks(db, "s", "u", tasks, NOW - timedelta(minutes=20),
                                              aware(runtime.window_end), case.get("break", 0))
    static_past_starts = sum(aware(b.start_at) < NOW for b in static_blocks)
    replan(db, runtime, NOW, force=True)
    db.commit()
    blocks = db.scalars(select(TimeBlock).where(TimeBlock.status == "planned").order_by(TimeBlock.start_at)).all()
    by_task = {b.task_id: b for b in blocks if b.task_id}
    deferred = {item["task_id"] for item in runtime.deferred_tasks}
    expected_pending = {t.id for t in tasks if t.status != "completed" and not (active and t.id == "t0")}
    checks = {
        "within_remaining_window": all(NOW <= aware(b.start_at) < aware(b.end_at) <= aware(runtime.window_end) for b in blocks),
        "no_overlap": all(aware(a.end_at) <= aware(b.start_at) for a, b in zip(blocks, blocks[1:])),
        "every_pending_scheduled_or_deferred": expected_pending == set(by_task) | deferred and not (set(by_task) & deferred),
        "deadlines": all(not t.deadline_at or t.id not in by_task or aware(by_task[t.id].end_at) <= aware(t.deadline_at) for t in tasks),
        "nonempty_when_feasible": bool(by_task) if case.get("must_schedule", True) else not by_task,
    }
    if case.get("event"):
        left, right = (NOW + timedelta(minutes=m) for m in case["event"])
        checks["event_conflicts"] = all(aware(b.end_at) <= left or aware(b.start_at) >= right for b in blocks)
    if case.get("dependency"):
        checks["dependency_order"] = "t0" not in by_task or ("t1" in by_task and aware(by_task["t1"].end_at) <= aware(by_task["t0"].start_at))
    if case.get("completed"):
        checks["completed_excluded"] = "t0" not in by_task and "t0" not in deferred
    if active:
        checks["active_preserved"] = active.status == "active" and active.end_at == NOW - timedelta(minutes=5)
        checks["remaining_forecast_reserved"] = all(aware(b.start_at) >= NOW + timedelta(minutes=case["remaining"]) for b in blocks)
    revision = runtime.revision
    checks["unchanged_input_stable"] = not replan(db, runtime, NOW) and runtime.revision == revision
    return dict(id=case["id"], checks=checks, passed=all(checks.values()), scheduled=len(by_task), deferred=len(deferred),
                planned_task_minutes=sum(b.planned_duration_minutes for b in by_task.values()),
                static_past_starts=static_past_starts, adaptive_past_starts=sum(aware(b.start_at) < NOW for b in blocks))


def schedule_cases():
    return [
        dict(id="normal", window=120, durations=[20, 30, 25]),
        dict(id="over_capacity", window=60, durations=[20, 90, 25]),
        dict(id="expired_window", window=-1, durations=[20, 30], must_schedule=False),
        dict(id="all_too_large", window=10, durations=[20, 30], must_schedule=False),
        dict(id="event_gap", window=120, durations=[20, 30, 25], event=[25, 60]),
        dict(id="dependency", window=120, durations=[20, 30, 25], dependency=True),
        dict(id="completed_task", window=120, durations=[20, 30, 25], completed=True),
        dict(id="deadline", window=120, durations=[20, 30, 25], deadline=25),
        dict(id="impossible_deadline", window=120, durations=[20, 30, 25], deadline=10),
        dict(id="active_overrun", window=90, durations=[25, 20, 25], remaining=35),
        dict(id="remaining_fills_window", window=30, durations=[25, 20], remaining=40, must_schedule=False),
        dict(id="breaks", window=180, durations=[30, 30, 30, 30], **{"break": 10}),
    ]


def snapshot_case(db, case):
    """Archive executable scenarios with stable IDs and explicit expected labels."""
    grouped = [(model, db.scalars(select(model)).all()) for model in FIXTURE_MODELS]
    mapping = {"u": identity("account")}
    for model, rows in grouped:
        for index, row in enumerate(rows):
            mapping[row.id] = identity(f"scenario/{case['id']}/{model.__tablename__}/{index}")
    def replace(value):
        if isinstance(value, str):
            return mapping.get(value, value)
        if isinstance(value, list):
            return [replace(item) for item in value]
        if isinstance(value, dict):
            return {key: replace(item) for key, item in value.items()}
        return value
    result = []
    for model, rows in grouped:
        for row in rows:
            values = {column.name: replace(getattr(row, column.name)) for column in model.__table__.columns}
            values.update(created_at=NOW, updated_at=NOW)
            if model is Intervention and values["rationale"]:
                values["rationale"] = json.dumps(replace(json.loads(values["rationale"])))
            result.append(dict(table=model.__tablename__, scenario_id=case["id"],
                               expected_policy=case.get("expected", "not_applicable"), values=values))
    return result


def isolated_case(function, case, fixtures=None):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine, expire_on_commit=False) as db:
            db.add(User(id="u", email="scenario@example.com", display_name="Synthetic scenario"))
            db.commit()
            result = function(db, case)
            if fixtures is not None:
                fixtures.extend(snapshot_case(db, case))
            return result
    finally:
        engine.dispose()


def error_metrics(pairs):
    errors = [abs(float(predicted) - float(actual)) for predicted, actual in pairs]
    return dict(n=len(errors), mae_minutes=round(mean(errors), 2) if errors else None,
                median_absolute_error_minutes=round(median(errors), 2) if errors else None,
                within_15_minutes_pct=round(100 * mean(e <= 15 for e in errors), 2) if errors else None)


def evaluate(rows, cases, predictions=None, fixtures=None):
    train = [r for r in rows if r["split"] == "train"]
    test = [r for r in rows if r["split"] == "test"]
    # Train-only calibration. No validation/test targets are used to fit these ratios.
    ratios = {}
    for row in train:
        ratios.setdefault((row["task_type"], row["difficulty"]), []).append(float(row["actual_minutes"]) / float(row["rules_minutes"]))
    ratio = {key: median(values) for key, values in ratios.items()}
    duration = {"rules": error_metrics([(r["rules_minutes"], r["actual_minutes"]) for r in test]),
                "train_calibrated_rules": error_metrics([(float(r["rules_minutes"]) * ratio[(r["task_type"], r["difficulty"])], r["actual_minutes"]) for r in test])}
    model_reports = {}
    if predictions:
        valid_ids = {r["task_id"] for r in rows}
        seen = set()
        for p in predictions:
            key = (p["model"], p["task_id"])
            if not p["model"].strip() or p["task_id"] not in valid_ids or key in seen:
                raise ValueError("Unknown task, empty model or duplicate model/task prediction")
            seen.add(key)
            if p["status"] not in {"ok", "failed", "not_run"}:
                raise ValueError("Prediction status must be ok, failed, or not_run")
            if p["status"] == "ok" and (not math.isfinite(float(p["predicted_minutes"])) or float(p["predicted_minutes"]) <= 0):
                raise ValueError("Predicted minutes must be finite and positive")
        for model in sorted({p["model"] for p in predictions}):
            lookup = {p["task_id"]: p for p in predictions if p["model"] == model}
            matched = [r for r in test if r["task_id"] in lookup and lookup[r["task_id"]]["status"] == "ok"]
            model_reports[model] = dict(test_total=len(test), successful=len(matched),
                coverage_pct=round(100 * len(matched) / len(test), 2),
                model=error_metrics([(lookup[r["task_id"]]["predicted_minutes"], r["actual_minutes"]) for r in matched]),
                matched_rules=error_metrics([(r["rules_minutes"], r["actual_minutes"]) for r in matched]))
    policies = [isolated_case(policy_result, case, fixtures) for case in cases["policies"]]
    schedules = [isolated_case(schedule_result, case, fixtures) for case in cases["schedules"]]
    tp = sum(p["expected"] != "none" and p["actual"] == p["expected"] for p in policies)
    fp = sum(p["actual"] != "none" and p["actual"] != p["expected"] for p in policies)
    fn = sum(p["expected"] != "none" and p["actual"] != p["expected"] for p in policies)
    return dict(dataset_id=DATASET, evidence="Synthetic simulation only. No human outcomes measured.",
        split_counts={s: sum(r["split"] == s for r in rows) for s in ("train", "validation", "test")},
        duration_test=duration, external_models=model_reports, external_models_note="No external model calls made. Missing predictions are not scored as model successes.",
        policy_metrics=dict(cases=len(policies), exact_label_accuracy=round(mean(p["actual"] == p["expected"] for p in policies), 4),
            precision=tp / (tp + fp) if tp + fp else None, recall=tp / (tp + fn) if tp + fn else None,
            false_positive_cases=fp, false_negative_cases=fn),
        policy_cases=policies, scheduler_cases=schedules,
        checks_passed=sum(sum(p["checks"].values()) for p in policies + schedules),
        checks_total=sum(len(p["checks"]) for p in policies + schedules),
        all_cases_passed=all(p["passed"] for p in policies + schedules))


def seed_account(rows, fixtures=None):
    initialize_database()
    uid = identity("account")
    password = None
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == TEST_EMAIL))
        if user and (user.id != uid or not db.scalar(select(DatasetAccount).where(DatasetAccount.user_id == uid))):
            raise ValueError("Test email already belongs to an account without this dataset marker. No changes made.")
        if not user:
            password = secrets.token_urlsafe(18)
            db.add(User(id=uid, email=TEST_EMAIL, display_name="BTP synthetic test account", consent_to_research="false"))
            db.flush()
            db.add_all([DatasetAccount(user_id=uid, source="synthetic", dataset_id=DATASET),
                        AccountCredential(user_id=uid, email_key=TEST_EMAIL, password_hash=hash_password(password))])
        for row in rows:
            if db.get(Task, row["task_id"]):
                continue
            start = datetime.fromisoformat(row["predicted_at"])
            end = datetime.fromisoformat(row["completed_at"])
            db.add(Task(id=row["task_id"], user_id=uid, title=row["title"], task_type=row["task_type"],
                description=json.dumps({k: row[k] for k in ("data_source", "dataset_id", "simulated_participant_id", "split")}),
                status="completed", difficulty=row["difficulty"], quantity_value=int(row["quantity_value"]),
                estimated_minutes=int(row["rules_minutes"]), actual_minutes=int(row["actual_minutes"]), created_at=start, updated_at=end))
            db.add(SessionRecord(id=identity(row["task_id"] + "/session"), user_id=uid, task_id=row["task_id"],
                started_at=start, ended_at=end, actual_start=start, actual_end=end, elapsed_minutes=int(row["actual_minutes"]),
                status="completed", notes="SYNTHETIC simulation. Not a measured user session.", created_at=start, updated_at=end))
        models = {model.__tablename__: model for model in FIXTURE_MODELS}
        for fixture in fixtures or []:
            model = models[fixture["table"]]
            values = dict(fixture["values"])
            if db.get(model, values["id"]):
                continue
            # Archive scenarios so opening the test account cannot start monitoring or deliver old nudges.
            if model in (ActivityMonitor, AdaptivePlan):
                values["enabled"] = False
            if model is ActivityMonitor:
                values["token_hash"] = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
            if model is SessionRecord:
                values.update(status="completed", ended_at=NOW, notes=f"SYNTHETIC archived scenario: {fixture['scenario_id']}")
            if model is Task:
                values.update(status="completed", description=json.dumps({"data_source": "synthetic", "scenario_id": fixture["scenario_id"]}))
            if model is Intervention:
                values["status"] = "resolved"
            if model is Reminder:
                values["status"] = "delivered"
            if model is TimeBlock:
                values["status"] = "completed" if values["status"] == "active" else "superseded"
            db.add(model(**values))
        db.commit()
    return dict(email=TEST_EMAIL, user_id=uid, new_password=password, admin=False)


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/evaluation/synthetic"))
    parser.add_argument("--seed", type=int, default=23077)
    parser.add_argument("--seed-account", action="store_true")
    parser.add_argument("--predictions", type=Path, help="CSV columns: model,task_id,status,predicted_minutes")
    args = parser.parse_args()
    if args.seed_account and args.seed != 23077:
        parser.error("Use seed 23077 for this version's database fixtures. Other seeds can be evaluated without --seed-account.")
    rows = duration_rows(args.seed)
    cases = {"policies": policy_cases(), "schedules": schedule_cases()}
    predictions = None
    if args.predictions:
        with args.predictions.open(encoding="utf-8-sig", newline="") as file:
            predictions = list(csv.DictReader(file))
    fixtures = []
    report = evaluate(rows, cases, predictions, fixtures)
    args.output.mkdir(parents=True, exist_ok=True)
    write_csv(args.output / "tasks.csv", rows)
    # Creation-time input view can be sent to a model without the answer or baseline estimate.
    write_csv(args.output / "model_inputs.csv", [{k: r[k] for k in ("task_id", "split", "title", "task_type", "difficulty", "quantity_value")} for r in rows])
    scenario_dir = args.output / "scenario_records"
    scenario_dir.mkdir(exist_ok=True)
    from app.modules.users.datasets import scalar
    for model in FIXTURE_MODELS:
        records = [{**{k: scalar(v) for k, v in item["values"].items() if k != "token_hash"},
                    "scenario_id": item["scenario_id"], "expected_policy": item["expected_policy"], "data_source": "synthetic"}
                   for item in fixtures if item["table"] == model.__tablename__]
        if records:
            write_csv(scenario_dir / (model.__tablename__ + ".csv"), records)
    template = args.output / "model_predictions_template.csv"
    if not template.exists():
        write_csv(template, [dict(model="your-model", task_id=r["task_id"], status="not_run", predicted_minutes="") for r in rows if r["split"] == "test"])
    for name, value in (("scenarios.json", cases), ("report.json", report)):
        (args.output / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    checks = f"{report['checks_passed']}/{report['checks_total']}"
    summary = ["# Synthetic benchmark", "", report["evidence"], "",
        f"Seed: {args.seed}. Duration records: {len(rows)}. Profiles: 15 (9 train, 3 validation, 3 test).",
        f"Policy scenarios: {len(cases['policies'])}. Scheduler scenarios: {len(cases['schedules'])}. Checks: {checks}.", "",
        "| Duration baseline (held-out profiles) | N | MAE (minutes) | Within 15 minutes |", "|---|---:|---:|---:|"]
    for name, result in report["duration_test"].items():
        summary.append(f"| {name} | {result['n']} | {result['mae_minutes']} | {result['within_15_minutes_pct']}% |")
    summary += ["", f"Policy metrics: {json.dumps(report['policy_metrics'])}", "",
        "These cases test conformance to specified rules and constraints. They do not establish real-world distraction detection, productivity gains, or optimal scheduling.",
        "No LLM was called by this script. External prediction results, when supplied, are in report.json.", "",
        "See docs/synthetic-evaluation.md for generator assumptions, label definitions and evaluation protocol."]
    (args.output / "report.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    hashes = {name: hashlib.sha256((args.output / name).read_bytes()).hexdigest() for name in ("tasks.csv", "model_inputs.csv", "scenarios.json")}
    (args.output / "manifest.json").write_text(json.dumps(dict(dataset_id=DATASET, seed=args.seed, source="synthetic",
        account_email=TEST_EMAIL, account_id=identity("account"), files_sha256=hashes,
        simulator="Independent workload, participant speed, lognormal noise and interruptions. Constants are assumptions.",
        split="Grouped by simulated participant, 180 train / 60 validation / 60 test. No real participants."), indent=2) + "\n", encoding="utf-8")
    if args.seed_account:
        print(json.dumps(seed_account(rows, fixtures), indent=2))
    print(json.dumps(dict(output=str(args.output), checks=checks, passed=report["all_cases_passed"], duration_test=report["duration_test"]), indent=2))
    if not report["all_cases_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
