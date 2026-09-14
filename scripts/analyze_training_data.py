"""Create a small baseline report from exported TimeBlindAI training data.

Run after export_training_data.py:
    python scripts/analyze_training_data.py
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import mean, median


DEFAULT_CSV = Path("data/training/timeblind_training_data.csv")
DEFAULT_REPORT = Path("data/training/model_baseline_report.md")


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze TimeBlindAI training data with simple duration baselines.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="Training CSV path.")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="Markdown report path.")
    args = parser.parse_args()

    if not args.csv.exists():
        raise SystemExit(f"Training CSV not found: {args.csv}. Run scripts/export_training_data.py first.")

    rows = _load_rows(args.csv)
    supervised = [
        row
        for row in rows
        if row["estimated_minutes"] is not None
        and row["actual_minutes"] is not None
        and row["estimated_minutes"] > 0
        and row["actual_minutes"] > 0
    ]
    if not supervised:
        raise SystemExit("No supervised rows found. Add tasks with both estimated_minutes and actual_minutes first.")

    train, test = _split_rows(supervised)
    global_ratio = median(_bounded_ratio(row) for row in train)
    group_ratios = _group_ratios(train)

    raw_predictions = [row["estimated_minutes"] for row in test]
    global_predictions = [round(row["estimated_minutes"] * global_ratio) for row in test]
    grouped_predictions = [_predict_grouped(row, group_ratios, global_ratio) for row in test]
    actuals = [row["actual_minutes"] for row in test]

    report = _render_report(
        rows=rows,
        supervised=supervised,
        train=train,
        test=test,
        actuals=actuals,
        raw_predictions=raw_predictions,
        global_predictions=global_predictions,
        grouped_predictions=grouped_predictions,
        global_ratio=global_ratio,
        group_ratios=group_ratios,
    )

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8")
    print(f"Wrote baseline report to {args.report}")


def _load_rows(path: Path) -> list[dict[str, object]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for raw in reader:
            rows.append(
                {
                    **raw,
                    "estimated_minutes": _to_int(raw.get("estimated_minutes")),
                    "actual_minutes": _to_int(raw.get("actual_minutes")),
                    "quantity_value": _to_int(raw.get("quantity_value")),
                    "estimate_error_minutes": _to_int(raw.get("estimate_error_minutes")),
                    "actual_to_estimate_ratio": _to_float(raw.get("actual_to_estimate_ratio")),
                    "completed_session_count": _to_int(raw.get("completed_session_count")) or 0,
                }
            )
        return rows


def _split_rows(rows: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    if len(rows) < 10:
        return rows, rows
    train = [row for index, row in enumerate(rows) if index % 5 != 0]
    test = [row for index, row in enumerate(rows) if index % 5 == 0]
    return train, test


def _group_ratios(rows: list[dict[str, object]]) -> dict[tuple[str, str], float]:
    buckets: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        key = (str(row["task_type"]), str(row["difficulty"]))
        buckets[key].append(_bounded_ratio(row))
    return {key: median(values) for key, values in buckets.items() if len(values) >= 2}


def _predict_grouped(row: dict[str, object], group_ratios: dict[tuple[str, str], float], global_ratio: float) -> int:
    key = (str(row["task_type"]), str(row["difficulty"]))
    ratio = group_ratios.get(key, global_ratio)
    return round(float(row["estimated_minutes"]) * ratio)


def _bounded_ratio(row: dict[str, object]) -> float:
    ratio = float(row["actual_minutes"]) / float(row["estimated_minutes"])
    return max(0.25, min(3.0, ratio))


def _render_report(
    *,
    rows: list[dict[str, object]],
    supervised: list[dict[str, object]],
    train: list[dict[str, object]],
    test: list[dict[str, object]],
    actuals: list[int],
    raw_predictions: list[int],
    global_predictions: list[int],
    grouped_predictions: list[int],
    global_ratio: float,
    group_ratios: dict[tuple[str, str], float],
) -> str:
    errors = [int(row["actual_minutes"]) - int(row["estimated_minutes"]) for row in supervised]
    overrun_count = sum(1 for error in errors if error > 0)
    underrun_count = sum(1 for error in errors if error < 0)

    lines = [
        "# TimeBlindAI Baseline Model Report",
        "",
        "## Dataset",
        f"- Exported task rows: {len(rows)}",
        f"- Supervised rows with estimate and actual time: {len(supervised)}",
        f"- Train rows: {len(train)}",
        f"- Test rows: {len(test)}",
        "",
        "## Estimation Behavior",
        f"- Average estimate error: {mean(errors):.2f} minutes",
        f"- Median estimate error: {median(errors):.2f} minutes",
        f"- Overruns: {overrun_count}",
        f"- Underruns: {underrun_count}",
        f"- Robust actual/estimated ratio used by baseline: {global_ratio:.3f}",
        "",
        "## Baseline Prediction Results",
        f"- Raw user estimate MAE: {_mae(actuals, raw_predictions):.2f} minutes",
        f"- Global ratio predictor MAE: {_mae(actuals, global_predictions):.2f} minutes",
        f"- Task type + difficulty predictor MAE: {_mae(actuals, grouped_predictions):.2f} minutes",
        "",
        "## Learned Group Ratios",
    ]

    if group_ratios:
        for (task_type, difficulty), ratio in sorted(group_ratios.items()):
            lines.append(f"- {task_type} / {difficulty}: {ratio:.3f}x")
    else:
        lines.append("- Not enough repeated task type + difficulty groups yet.")

    lines.extend(
        [
            "",
            "## What This Proves",
            "This is not the final model. It proves that TimeBlindAI can collect supervised planning data and evaluate whether personalization improves duration prediction over a raw user estimate.",
            "",
        ]
    )
    return "\n".join(lines)


def _mae(actuals: list[int], predictions: list[int]) -> float:
    return mean(abs(actual - prediction) for actual, prediction in zip(actuals, predictions))


def _to_int(value: object) -> int | None:
    if value in ("", None):
        return None
    return int(float(str(value)))


def _to_float(value: object) -> float | None:
    if value in ("", None):
        return None
    return float(str(value))


if __name__ == "__main__":
    main()
