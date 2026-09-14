"""Export TimeBlindAI task/session history into a model-ready CSV.

Usage:
    python scripts/export_training_data.py
    python scripts/export_training_data.py --db timeblind_ai.db --out data/training/timeblind_training_data.csv
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path


DEFAULT_DB = Path("timeblind_ai.db")
DEFAULT_OUT = Path("data/training/timeblind_training_data.csv")


FIELDS = [
    "task_id",
    "user_id",
    "title",
    "task_type",
    "difficulty",
    "priority",
    "quantity_value",
    "status",
    "deadline_at",
    "created_at",
    "estimated_minutes",
    "actual_minutes",
    "estimate_error_minutes",
    "actual_to_estimate_ratio",
    "completed_session_count",
    "total_elapsed_minutes",
    "avg_delay_minutes",
    "avg_overrun_minutes",
    "latest_difficulty_feedback",
    "latest_feedback_reasons",
    "latest_feedback_notes",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Export model training rows from the TimeBlindAI SQLite database.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to SQLite database.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output CSV path.")
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(f"Database not found: {args.db}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    rows = export_rows(args.db)

    with args.out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    usable_rows = [
        row
        for row in rows
        if row["estimated_minutes"] not in ("", None)
        and row["actual_minutes"] not in ("", None)
        and int(row["estimated_minutes"]) > 0
        and int(row["actual_minutes"]) > 0
    ]
    print(f"Exported {len(rows)} task rows to {args.out}")
    print(f"Usable supervised rows with estimate + actual: {len(usable_rows)}")


def export_rows(db_path: Path) -> list[dict[str, str | int | float]]:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        tasks = connection.execute(
            """
            SELECT
                id,
                user_id,
                title,
                task_type,
                difficulty,
                priority,
                quantity_value,
                status,
                deadline_at,
                created_at,
                estimated_minutes,
                actual_minutes
            FROM tasks
            ORDER BY created_at DESC
            """
        ).fetchall()

        session_stats = _session_stats_by_task(connection)
        latest_feedback = _latest_feedback_by_task(connection)

        rows: list[dict[str, str | int | float]] = []
        for task in tasks:
            stats = session_stats.get(task["id"], {})
            feedback = latest_feedback.get(task["id"], {})
            estimated = _to_int(task["estimated_minutes"])
            actual = _to_int(task["actual_minutes"])
            estimate_error = ""
            ratio = ""
            if estimated and actual:
                estimate_error = actual - estimated
                ratio = round(actual / estimated, 4)

            rows.append(
                {
                    "task_id": task["id"],
                    "user_id": task["user_id"],
                    "title": task["title"],
                    "task_type": task["task_type"],
                    "difficulty": task["difficulty"],
                    "priority": task["priority"],
                    "quantity_value": task["quantity_value"] or "",
                    "status": task["status"],
                    "deadline_at": task["deadline_at"] or "",
                    "created_at": task["created_at"] or "",
                    "estimated_minutes": estimated or "",
                    "actual_minutes": actual or "",
                    "estimate_error_minutes": estimate_error,
                    "actual_to_estimate_ratio": ratio,
                    "completed_session_count": stats.get("completed_session_count", 0),
                    "total_elapsed_minutes": stats.get("total_elapsed_minutes", ""),
                    "avg_delay_minutes": stats.get("avg_delay_minutes", ""),
                    "avg_overrun_minutes": stats.get("avg_overrun_minutes", ""),
                    "latest_difficulty_feedback": feedback.get("difficulty_feedback", ""),
                    "latest_feedback_reasons": feedback.get("feedback_reasons", ""),
                    "latest_feedback_notes": feedback.get("feedback_notes", ""),
                }
            )
        return rows
    finally:
        connection.close()


def _session_stats_by_task(connection: sqlite3.Connection) -> dict[str, dict[str, int | float]]:
    rows = connection.execute(
        """
        SELECT
            task_id,
            COUNT(*) AS completed_session_count,
            SUM(COALESCE(elapsed_minutes, 0)) AS total_elapsed_minutes,
            AVG(COALESCE(delay_minutes, 0)) AS avg_delay_minutes,
            AVG(COALESCE(overrun_minutes, 0)) AS avg_overrun_minutes
        FROM sessions
        WHERE task_id IS NOT NULL
          AND status = 'completed'
        GROUP BY task_id
        """
    ).fetchall()
    return {
        row["task_id"]: {
            "completed_session_count": row["completed_session_count"] or 0,
            "total_elapsed_minutes": row["total_elapsed_minutes"] or 0,
            "avg_delay_minutes": round(row["avg_delay_minutes"] or 0, 2),
            "avg_overrun_minutes": round(row["avg_overrun_minutes"] or 0, 2),
        }
        for row in rows
    }


def _latest_feedback_by_task(connection: sqlite3.Connection) -> dict[str, dict[str, str]]:
    rows = connection.execute(
        """
        SELECT task_id, difficulty_feedback, feedback_reasons, feedback_notes
        FROM sessions
        WHERE task_id IS NOT NULL
          AND status = 'completed'
        ORDER BY ended_at DESC, updated_at DESC
        """
    ).fetchall()
    latest: dict[str, dict[str, str]] = {}
    for row in rows:
        if row["task_id"] in latest:
            continue
        latest[row["task_id"]] = {
            "difficulty_feedback": row["difficulty_feedback"] or "",
            "feedback_reasons": row["feedback_reasons"] or "",
            "feedback_notes": row["feedback_notes"] or "",
        }
    return latest


def _to_int(value: object) -> int | None:
    if value in ("", None):
        return None
    return int(value)


if __name__ == "__main__":
    main()
