"""Import a private SQLite backup into an empty PostgreSQL database.

Run from the project root. The external URL is requested with hidden input.
No source database or environment configuration is modified.
"""
import argparse
from datetime import datetime, timezone
from getpass import getpass
from pathlib import Path
import sqlite3
from uuid import uuid4

from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.pool import StaticPool
from sqlalchemy.exc import IntegrityError, DataError

# Import route registrations to register all domain tables without starting servers.
from app.main import app  # noqa: F401
from app.core.database import Base

EXCLUDED = {"login_sessions", "password_resets", "auth_rate_limits"}


def repaired_snapshot(path):
    """Repair legacy orphan links in an in-memory copy, preserving all records."""
    memory = sqlite3.connect(":memory:", check_same_thread=False)
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as original:
        original.backup(memory)
    snapshot = create_engine("sqlite://", creator=lambda: memory, poolclass=StaticPool)
    from app.modules.users.models import User
    from app.modules.tasks.models import Task
    from app.modules.sessions.models import SessionRecord
    with snapshot.begin() as connection:
        missing = connection.execute(select(Task.user_id).where(
            Task.user_id.not_in(select(User.id)))).scalars().all()
        for user_id in set(missing):
            # A disabled placeholder preserves task ownership without fabricating
            # a participant or granting login credentials/admin access.
            connection.execute(User.__table__.insert().values(
                id=user_id, email=f"legacy-{uuid4().hex}@migration.invalid",
                display_name="Recovered legacy owner", consent_to_research="false"))
        tasks = connection.execute(Task.__table__.update().where(
            Task.goal_id.is_not(None), Task.goal_id.not_in(select(Base.metadata.tables["goals"].c.id))
        ).values(goal_id=None)).rowcount
        sessions = connection.execute(SessionRecord.__table__.update().where(
            SessionRecord.time_block_id.is_not(None),
            SessionRecord.time_block_id.not_in(select(Base.metadata.tables["time_blocks"].c.id))
        ).values(time_block_id=None)).rowcount
    print(f"Snapshot repairs: {len(set(missing))} disabled legacy owner(s), {tasks} missing goal link(s), {sessions} missing block link(s).")
    print("Task/session records are retained. Original backup is unchanged. Legacy owners are not study participants.")
    return snapshot


def normalized(value):
    if isinstance(value, datetime):
        return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)).isoformat()
    return value


def copy_database(source, target):
    """Transactional copy; shared helper also permits isolated SQLite testing."""
    source_schema = inspect(source)
    names = set(source_schema.get_table_names())
    tables = [t for t in Base.metadata.sorted_tables if t.name in names and t.name not in EXCLUDED]
    with source.connect() as src, target.begin() as dst:
        # Schema creation and all writes share a PostgreSQL transaction.
        Base.metadata.create_all(dst)
        for table in Base.metadata.sorted_tables:
            if dst.scalar(select(func.count()).select_from(table)):
                raise ValueError("Destination is not empty; import cancelled without overwriting records.")
        # Older deployments may already have created the narrower empty table.
        # Widening preserves complete legacy values; never truncate study data.
        if target.dialect.name == "postgresql":
            columns = inspect(dst).get_columns("time_blocks")
            kind = next(c for c in columns if c["name"] == "kind")
            if getattr(kind["type"], "length", None) is not None and kind["type"].length < 64:
                dst.execute(text("ALTER TABLE time_blocks ALTER COLUMN kind TYPE VARCHAR(64)"))
        counts = {}
        for table in tables:
            available = {c["name"] for c in source_schema.get_columns(table.name)}
            columns = [c for c in table.columns if c.name in available]
            rows = [dict(r) for r in src.execute(select(*columns)).mappings()]
            for start in range(0, len(rows), 250):
                dst.execute(table.insert(), rows[start:start + 250])
            saved = {r["id"]: dict(r) for r in dst.execute(select(table)).mappings()}
            if len(saved) != len(rows):
                raise ValueError("Count verification failed for " + table.name)
            for row in rows:
                if any(normalized(value) != normalized(saved[row["id"]][key]) for key, value in row.items()):
                    raise ValueError("Content verification failed for " + table.name)
            counts[table.name] = len(rows)
        return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--repair-orphans", action="store_true", help="Repair known legacy orphan references in a temporary copy; retain all tasks and sessions")
    args = parser.parse_args()
    path = args.source.resolve()
    if not path.is_file():
        parser.error("Source backup file does not exist")
    # Read-only connection protects the original backup.
    source = repaired_snapshot(path) if args.repair_orphans else create_engine("sqlite://", creator=lambda: sqlite3.connect(path.as_uri() + "?mode=ro", uri=True))
    target = None
    try:
        raw = getpass("Paste the NEW database's External Database URL (hidden): ").strip()
        url = make_url(raw)
        if url.drivername not in {"postgres", "postgresql", "postgresql+psycopg"}:
            raise ValueError("Expected a PostgreSQL URL")
        url = url.set(drivername="postgresql+psycopg").update_query_dict({"sslmode": "require"})
        print("This imports into the new PostgreSQL database. Existing destination data is never overwritten.")
        if input("Type IMPORT to proceed: ").strip() != "IMPORT":
            print("Cancelled.")
            return
        target = create_engine(url, connect_args={"connect_timeout": 15})
        counts = copy_database(source, target)
        for name, count in counts.items():
            print(f"{name}: {count} verified records")
        print("Import committed. Password hashes, admin grants and recovery key hashes were preserved.")
        print("Old login sessions and temporary reset codes were excluded. Log in again after switching Render.")
    except ValueError as error:
        # URL parse errors can echo credentials, so only emit our known messages.
        safe = str(error)
        if safe.startswith(("Destination", "Count verification", "Content verification", "Expected a PostgreSQL")):
            print("Import failed: " + safe)
        else:
            print("Import failed: invalid connection settings. No credentials are printed.")
        raise SystemExit(1) from None
    except (IntegrityError, DataError) as error:
        diagnostic = getattr(error.orig, "diag", None)
        print("Import rejected by a database constraint. Transaction rolled back.")
        if diagnostic:
            print("Table:", diagnostic.table_name, "Constraint:", diagnostic.constraint_name,
                  "SQLSTATE:", getattr(error.orig, "sqlstate", None))
        print("No record contents or credentials are printed. Source backup unchanged.")
        raise SystemExit(1) from None
    except Exception as error:
        print(f"Import failed ({type(error).__name__}). Transaction rolled back; source backup unchanged.")
        print("Check the external URL, network access and PostgreSQL driver. Do not share connection credentials.")
        raise SystemExit(1) from None
    finally:
        source.dispose()
        if target is not None:
            target.dispose()


if __name__ == "__main__":
    main()
