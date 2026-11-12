"""Audit and evaluate without training. Run: python -m scripts.evaluate_generative

--live sends held-out tasks to the configured provider and uses its quota. Default is offline.
Evaluation is zero-shot: the CSV has no task completion timestamps, so using other
rows as history could expose future information. Production uses completed DB history.
"""
import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from time import monotonic, sleep

from app.core.config import get_settings
from app.modules.reasoning.generative import COMMON, PROMPT_VERSION, GeneratedEstimate
from app.modules.reasoning.llm import PlanningUnavailable, generate_structured
from app.modules.reasoning.task_decomposer import decompose_task
from app.modules.tasks.schemas import TaskDecompositionRequest


def prepare_rows(path: Path) -> tuple[list[dict], dict]:
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig", newline="")))
    usable = []
    seen = set()
    duplicates = 0
    for row in sorted(rows, key=lambda item: item["created_at"]):
        try:
            actual = int(row["actual_minutes"])
            estimated = int(row["estimated_minutes"])
        except (ValueError, TypeError):
            continue
        if row["status"] != "completed" or not 1 <= actual <= 1440 or not 5 <= estimated <= 1440:
            continue
        # Repeated titles on the same user/day are conservatively treated as duplicates.
        key = (row["user_id"], row["title"].strip().lower(), row["created_at"][:10])
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        usable.append(row)
    return usable, {"total_rows": len(rows), "usable_unique_completed_rows": len(usable),
                    "duplicate_rows_excluded": duplicates,
                    "users": len({row["user_id"] for row in rows})}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=Path("data/training/timeblind_training_data.csv"))
    parser.add_argument("--out", type=Path, default=Path("data/evaluation/generative_report.json"))
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--estimate-input", choices=("none", "stored"), default="none",
                        help="Default matches the task form: no starting estimate. 'stored' reproduces the seeded comparison.")
    parser.add_argument("--request-spacing", type=float, default=None,
                        help="Minimum seconds between live request starts; defaults to 60 on Groq.")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    settings = get_settings()
    key = settings.planning_api_key
    if args.live and (not key or not key.get_secret_value()):
        parser.error(f"--live requires a key for the selected provider ({settings.llm_provider})")
    spacing = args.request_spacing if args.request_spacing is not None else (60 if settings.llm_provider == "groq" else 0)
    if not 0 <= spacing <= 60:
        parser.error("--request-spacing must be between 0 and 60 seconds")
    rows, audit = prepare_rows(args.csv)
    # Hold out the latest 20%; reserve earlier data for prompt development only.
    split = max(1, int(len(rows) * 0.8))
    held_out = rows[split:][:args.limit]
    if not held_out:
        parser.error("Not enough usable rows for a holdout")
    results = []
    last_request_start = None
    for row in held_out:
        payload = TaskDecompositionRequest(
            title=row["title"], task_type=row["task_type"], difficulty=row["difficulty"],
            quantity_value=int(row["quantity_value"]) if row["quantity_value"] else None,
            estimated_minutes=int(row["estimated_minutes"]) if args.estimate_input == "stored" else None,
            deadline_at=datetime.fromisoformat(row["deadline_at"]) if row["deadline_at"] else None,
            current_time=datetime.fromisoformat(row["created_at"]).replace(tzinfo=timezone.utc),
        )
        actual = int(row["actual_minutes"])
        baseline = decompose_task(payload).personalized_estimate_minutes
        result = {"actual_minutes": actual, "raw_estimate_minutes": int(row["estimated_minutes"]),
                  "rules_estimate_minutes": baseline}
        if args.live:
            if last_request_start is not None:
                sleep(max(0, spacing - (monotonic() - last_request_start)))
            started = monotonic()
            last_request_start = started
            try:
                prediction = generate_structured(
                    COMMON + "Estimate the full task, with a plausible range, assumptions, and actionable steps. "
                    "Do not shrink to the deadline. Step minutes must sum exactly to estimated_minutes.",
                    {"task": payload.model_dump(mode="json", exclude={"user_id"}), "history": []},
                    GeneratedEstimate,
                )
                result.update(llm_estimate_minutes=prediction.estimated_minutes,
                              range_covered=prediction.lower_minutes <= actual <= prediction.upper_minutes)
            except PlanningUnavailable as exc:
                result["llm_failure"] = str(exc)
            result["latency_seconds"] = round(monotonic() - started, 3)
            print(f"Evaluated {len(results) + 1}/{len(held_out)}: "
                  f"{'failed: ' + result['llm_failure'] if 'llm_failure' in result else 'ok'}", flush=True)
        results.append(result)
    metrics = {}
    for label in ("raw", "rules", "llm"):
        errors = [abs(row[f"{label}_estimate_minutes"] - row["actual_minutes"])
                  for row in results if f"{label}_estimate_minutes" in row]
        if errors:
            metrics[label] = {"n": len(errors), "mae_minutes": round(mean(errors), 2),
                              "median_absolute_error_minutes": median(errors)}
    live_successes = [row for row in results if "llm_estimate_minutes" in row]
    if args.live:
        metrics["llm_failure_rate"] = 1 - len(live_successes) / len(results)
        metrics["llm_mean_latency_seconds"] = round(mean(row["latency_seconds"] for row in results), 3)
        metrics["planning_range_coverage"] = mean(row["range_covered"] for row in live_successes) if live_successes else None
    report = {"audit": audit, "mode": "live" if args.live else "offline",
              "provider": settings.llm_provider if args.live else None,
              "model": settings.llm_model if args.live else None, "prompt_version": PROMPT_VERSION,
              "evaluation_prompt": "zero-shot-v1", "estimate_input": args.estimate_input,
              "holdout_rows": len(results), "metrics": metrics,
              "limitations": ["Small pilot; no generalization claim.", "Conservative deduplication by user/title/day.",
                              "No historical examples: completion times unavailable in CSV.",
                              "Raw estimates may already be generated by older rules.",
                              "No post-task session counts, error ratios, or feedback used as input."],
              "results": results}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"audit": audit, "metrics": metrics, "report": str(args.out)}, indent=2))


if __name__ == "__main__":
    main()
