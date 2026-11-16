"""Evaluate predictions recorded before task work begins. See docs/prediction-study.md."""

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from statistics import mean, median

FIELDS = (
    "task_id", "user_id", "scope", "task_type", "difficulty", "predicted_at",
    "completed_at", "user_minutes", "rules_minutes", "llm_status",
    "llm_minutes", "llm_lower", "llm_upper", "actual_minutes",
)


def minutes(row, field):
    value = float(row[field])
    if not 0 < value < float("inf"):
        raise ValueError(f"{field} must be positive and finite")
    return value


def timestamp(value):
    result = datetime.fromisoformat(value)
    if result.utcoffset() is None:
        raise ValueError("timestamps must include a UTC offset")
    return result


def load(path):
    completed = []
    pending = 0
    seen = set()
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if not set(FIELDS).issubset(reader.fieldnames or []):
            raise ValueError("CSV is missing required columns. Generate a template with --init.")
        for line, row in enumerate(reader, 2):
            try:
                row = {key: row[key].strip() for key in FIELDS}
                if not row["task_id"] or row["task_id"] in seen:
                    raise ValueError("task_id must be present and unique")
                seen.add(row["task_id"])
                if not all(row[key] for key in ("user_id", "scope", "task_type", "difficulty")):
                    raise ValueError("user_id, scope, task_type and difficulty are required")
                predicted = timestamp(row["predicted_at"])
                for field in ("user_minutes", "rules_minutes"):
                    row[field] = minutes(row, field)
                status = row["llm_status"]
                if status not in ("ok", "failed", "not_run"):
                    raise ValueError("llm_status must be ok, failed or not_run")
                ai_fields = ("llm_minutes", "llm_lower", "llm_upper")
                if status == "ok":
                    for field in ai_fields:
                        row[field] = minutes(row, field)
                    if not row["llm_lower"] <= row["llm_minutes"] <= row["llm_upper"]:
                        raise ValueError("LLM range must contain the point estimate")
                elif any(row[field] for field in ai_fields):
                    raise ValueError("leave LLM prediction fields blank for failed or not_run")
                if not row["completed_at"] and not row["actual_minutes"]:
                    pending += 1
                    continue
                finished = timestamp(row["completed_at"])
                if finished <= predicted:
                    raise ValueError("completion must be after prediction")
                row["actual_minutes"] = minutes(row, "actual_minutes")
                completed.append((predicted, finished, row))
            except (ValueError, AttributeError) as exc:
                raise ValueError(f"CSV line {line}: {exc}") from exc
    return sorted(completed, key=lambda item: item[0]), pending


def score(rows, field):
    errors = [abs(row[field] - row["actual_minutes"]) for row in rows]
    return {
        "n": len(errors),
        "mae_minutes": round(mean(errors), 2) if errors else None,
        "median_absolute_error_minutes": round(median(errors), 2) if errors else None,
        "within_15_minutes_pct": round(100 * mean(error <= 15 for error in errors), 2) if errors else None,
    }


def evaluate(completed, pending):
    rows = []
    for predicted, _, row in completed:
        ratios = [
            other["actual_minutes"] / other["rules_minutes"]
            for _, finished, other in completed
            if finished < predicted
            and all(other[key] == row[key] for key in ("user_id", "task_type", "difficulty"))
        ]
        row["calibration_history_n"] = len(ratios)
        row["calibrated_minutes"] = row["rules_minutes"] * (median(ratios) if len(ratios) >= 3 else 1)
        row["ai_fallback_minutes"] = row["llm_minutes"] if row["llm_status"] == "ok" else row["rules_minutes"]
        rows.append(row)

    attempted = [row for row in rows if row["llm_status"] != "not_run"]
    successes = [row for row in attempted if row["llm_status"] == "ok"]
    baselines = ("user_minutes", "rules_minutes", "calibrated_minutes")
    return {
        "completed": len(rows),
        "pending_excluded": pending,
        "calibration_applied_n": sum(row["calibration_history_n"] >= 3 for row in rows),
        "all_completed": {field: score(rows, field) for field in (*baselines, "ai_fallback_minutes")},
        "matched_llm_successes": {field: score(successes, field) for field in (*baselines, "llm_minutes")},
        "llm": {
            "attempted": len(attempted),
            "not_run": len(rows) - len(attempted),
            "failed": len(attempted) - len(successes),
            "success_pct": round(100 * len(successes) / len(attempted), 2) if attempted else None,
            "range_coverage_pct": round(100 * mean(
                row["llm_lower"] <= row["actual_minutes"] <= row["llm_upper"] for row in successes
            ), 2) if successes else None,
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--init", action="store_true", help="Create a blank prediction log")
    parser.add_argument("--out", type=Path, help="Save summary JSON")
    args = parser.parse_args()
    try:
        if args.init:
            with args.csv.open("x", encoding="utf-8", newline="") as file:
                csv.writer(file).writerow(FIELDS)
            return
        completed, pending = load(args.csv)
        if not completed:
            parser.error("No completed tasks with measured durations yet")
        report = json.dumps(evaluate(completed, pending), indent=2)
        if args.out:
            if args.out.resolve() == args.csv.resolve():
                parser.error("--out must differ from the input CSV")
            args.out.write_text(report + "\n", encoding="utf-8")
        print(report)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
