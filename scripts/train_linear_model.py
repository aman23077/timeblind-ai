"""Train a tiny linear regression baseline for TimeBlindAI duration prediction.

This intentionally uses only the Python standard library so the demo works
without installing scikit-learn.

Run:
    python scripts/export_training_data.py
    python scripts/train_linear_model.py
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import mean


DEFAULT_CSV = Path("data/training/timeblind_training_data.csv")
DEFAULT_MODEL = Path("data/training/linear_duration_model.json")
DEFAULT_REPORT = Path("data/training/linear_model_report.md")

LEARNING_RATE = 0.01
EPOCHS = 5000


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a first linear regression model for task duration.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="Training CSV path.")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL, help="Output model JSON path.")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="Output Markdown report path.")
    args = parser.parse_args()

    rows = _load_supervised_rows(args.csv)
    if len(rows) < 10:
        raise SystemExit(f"Need at least 10 supervised rows. Found {len(rows)}.")

    train_rows, test_rows = _split_rows(rows)
    feature_names = _feature_names(rows)
    x_train = [_features(row, feature_names) for row in train_rows]
    y_train = [row["actual_minutes"] for row in train_rows]
    x_test = [_features(row, feature_names) for row in test_rows]
    y_test = [row["actual_minutes"] for row in test_rows]

    means, stds = _scaler(x_train)
    x_train_scaled = [_scale(values, means, stds) for values in x_train]
    x_test_scaled = [_scale(values, means, stds) for values in x_test]

    weights, bias = _fit_linear_regression(x_train_scaled, y_train)
    predictions = [_predict(values, weights, bias) for values in x_test_scaled]
    raw_estimates = [row["estimated_minutes"] for row in test_rows]

    model = {
        "model_type": "standard_library_linear_regression",
        "target": "actual_minutes",
        "feature_names": feature_names,
        "means": means,
        "stds": stds,
        "weights": weights,
        "bias": bias,
        "train_rows": len(train_rows),
        "test_rows": len(test_rows),
    }

    args.model.parent.mkdir(parents=True, exist_ok=True)
    args.model.write_text(json.dumps(model, indent=2), encoding="utf-8")
    args.report.write_text(_report(rows, train_rows, test_rows, y_test, raw_estimates, predictions, feature_names), encoding="utf-8")

    print(f"Wrote model to {args.model}")
    print(f"Wrote report to {args.report}")


def _load_supervised_rows(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        raise SystemExit(f"Training CSV not found: {path}. Run scripts/export_training_data.py first.")

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for row in reader:
            estimated = _to_int(row.get("estimated_minutes"))
            actual = _to_int(row.get("actual_minutes"))
            if estimated is None or actual is None or estimated <= 0 or actual <= 0:
                continue
            if not _is_reasonable_training_row(estimated, actual):
                continue
            rows.append(
                {
                    "estimated_minutes": estimated,
                    "actual_minutes": actual,
                    "quantity_value": _to_int(row.get("quantity_value")) or 0,
                    "completed_session_count": _to_int(row.get("completed_session_count")) or 0,
                    "task_type": row.get("task_type") or "generic",
                    "difficulty": row.get("difficulty") or "medium",
                    "has_deadline": 1 if row.get("deadline_at") else 0,
                }
            )
        return rows


def _is_reasonable_training_row(estimated_minutes: int, actual_minutes: int) -> bool:
    ratio = actual_minutes / estimated_minutes
    return estimated_minutes >= 5 and actual_minutes <= 480 and 0.2 <= ratio <= 4.0


def _feature_names(rows: list[dict[str, object]]) -> list[str]:
    task_types = sorted({str(row["task_type"]) for row in rows})
    difficulties = sorted({str(row["difficulty"]) for row in rows})
    return (
        ["estimated_minutes", "quantity_value", "completed_session_count", "has_deadline"]
        + [f"task_type={task_type}" for task_type in task_types]
        + [f"difficulty={difficulty}" for difficulty in difficulties]
    )


def _features(row: dict[str, object], feature_names: list[str]) -> list[float]:
    values = []
    for name in feature_names:
        if name in {"estimated_minutes", "quantity_value", "completed_session_count", "has_deadline"}:
            values.append(float(row[name]))
        elif name.startswith("task_type="):
            values.append(1.0 if str(row["task_type"]) == name.split("=", 1)[1] else 0.0)
        elif name.startswith("difficulty="):
            values.append(1.0 if str(row["difficulty"]) == name.split("=", 1)[1] else 0.0)
        else:
            values.append(0.0)
    return values


def _split_rows(rows: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    if len(rows) < 10:
        return rows, rows
    train = [row for index, row in enumerate(rows) if index % 5 != 0]
    test = [row for index, row in enumerate(rows) if index % 5 == 0]
    return train, test


def _scaler(rows: list[list[float]]) -> tuple[list[float], list[float]]:
    columns = list(zip(*rows))
    means = [mean(column) for column in columns]
    stds = []
    for column, column_mean in zip(columns, means):
        variance = mean((value - column_mean) ** 2 for value in column)
        stds.append(max(variance**0.5, 1.0))
    return means, stds


def _scale(values: list[float], means: list[float], stds: list[float]) -> list[float]:
    return [(value - column_mean) / column_std for value, column_mean, column_std in zip(values, means, stds)]


def _fit_linear_regression(rows: list[list[float]], targets: list[int]) -> tuple[list[float], float]:
    weights = [0.0 for _ in rows[0]]
    bias = mean(targets)
    n = len(rows)

    for _ in range(EPOCHS):
        weight_gradients = [0.0 for _ in weights]
        bias_gradient = 0.0
        for values, target in zip(rows, targets):
            prediction = _predict(values, weights, bias)
            error = prediction - target
            bias_gradient += error
            for index, value in enumerate(values):
                weight_gradients[index] += error * value
        bias -= LEARNING_RATE * (bias_gradient / n)
        for index in range(len(weights)):
            weights[index] -= LEARNING_RATE * (weight_gradients[index] / n)

    return weights, bias


def _predict(values: list[float], weights: list[float], bias: float) -> float:
    return max(1.0, bias + sum(value * weight for value, weight in zip(values, weights)))


def _report(
    rows: list[dict[str, object]],
    train_rows: list[dict[str, object]],
    test_rows: list[dict[str, object]],
    actuals: list[int],
    raw_estimates: list[int],
    predictions: list[float],
    feature_names: list[str],
) -> str:
    return "\n".join(
        [
            "# TimeBlindAI Linear Regression Report",
            "",
            "## Dataset",
            f"- Supervised rows: {len(rows)}",
            f"- Train rows: {len(train_rows)}",
            f"- Test rows: {len(test_rows)}",
            "",
            "## Result",
            f"- Raw estimate MAE: {_mae(actuals, raw_estimates):.2f} minutes",
            f"- Linear regression MAE: {_mae(actuals, predictions):.2f} minutes",
            "",
            "## Features Used",
            *[f"- {name}" for name in feature_names],
            "",
            "## What This Means",
            "This is the first trainable ML model for TimeBlindAI. It predicts actual task duration from structured task data. With the current small dataset, the result should be treated as a proof of pipeline, not a final accurate model.",
            "",
        ]
    )


def _mae(actuals: list[int], predictions: list[int] | list[float]) -> float:
    return mean(abs(actual - prediction) for actual, prediction in zip(actuals, predictions))


def _to_int(value: object) -> int | None:
    if value in ("", None):
        return None
    return int(float(str(value)))


if __name__ == "__main__":
    main()
