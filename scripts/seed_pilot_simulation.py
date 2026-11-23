"""Repeatable synthetic demo using real app models, planner and activity summaries.

No real participant identities, login credentials, consent or subjective reviews.
Default writes only the local SQLite application database, with a backup first.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import sqlite3
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5
from getpass import getpass

from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from app.main import app  # registers model tables without starting the server
from app.core.database import Base
from app.modules.users.models import User, UserModelProfile
from app.modules.users.datasets import DatasetAccount
from app.modules.users.simulation import DATASET, simulation_summary
from app.modules.tasks.models import Task, TaskStep
from app.modules.tasks.schemas import TaskDecompositionRequest
from app.modules.reasoning.task_decomposer import decompose_task
from app.modules.schedules.models import Schedule
from app.modules.schedules.planner import build_schedule_blocks
from app.modules.sessions.models import SessionRecord
from app.modules.behaviour.activity import ActivityMonitor, ActivityInterval

def identity(label):
    return str(uuid5(NAMESPACE_URL, DATASET+"/"+label))


def seed(engine):
    Base.metadata.create_all(engine)
    with Session(engine) as db, db.begin():
        rng=random.Random(23077)
        choices=[("coding","Debug a Python data parser",35), ("reading","Read five pages of course notes",18),
                 ("study","Revise DBMS indexing and write a summary",40), ("assignment","Solve three mathematics problems",45),
                 ("writing","Draft an internship cover letter",30), ("exercise","Complete a gym routine",50),
                 ("admin","Compare two internship applications",25), ("chore","Organize desk and course files",20)]
        for i in range(19):
            uid=identity(f"P{i+1:03}")
            existing=db.get(User,uid)
            marker=db.scalar(select(DatasetAccount).where(DatasetAccount.user_id==uid))
            if existing:
                if not marker or marker.dataset_id!=DATASET or marker.source!="synthetic":
                    raise ValueError("Refusing to reuse a non-simulation account")
                continue
            db.add(User(id=uid,email=f"pilot-sim-p{i+1:03}@example.com",display_name=f"SYNTHETIC P{i+1:03}",participant_type="simulation",consent_to_research="false"))
            db.flush()
            db.add(DatasetAccount(user_id=uid,source="synthetic",dataset_id=DATASET))
            db.add(UserModelProfile(user_id=uid))
            speed=.8+i*.035
            start=datetime(2026,11,1,tzinfo=timezone.utc)+timedelta(days=i)
            schedule=Schedule(id=identity(f"{i}/schedule"),user_id=uid,plan_date=start.date(),generated_by="synthetic_rules_test",status="archived")
            db.add(schedule)
            tasks=[]
            rng.shuffle(choices)
            plans=[]
            durations=[]
            for j,(kind,title,base) in enumerate(choices):
                difficulty=rng.choice(["easy","medium","hard"])
                actual=round(base*speed*{"easy":.85,"medium":1,"hard":1.3}[difficulty]*rng.lognormvariate(0,.15)+rng.randint(0,12))
                plan=decompose_task(TaskDecompositionRequest(title=title,task_type=kind,difficulty=difficulty))
                task=Task(id=identity(f"{i}/{j}/task"),user_id=uid,title="SYNTHETIC: "+title,task_type=kind,difficulty=difficulty,priority=rng.choice(["low","medium","high"]),estimated_minutes=plan.personalized_estimate_minutes,status="pending",created_at=start,
                          description=json.dumps({"data_source":"synthetic","dataset_id":DATASET,"seed":23077,"personal_guess_minutes":max(5,round(actual*rng.uniform(.6,1.25))),"outcome_generator":"base workload times profile speed, difficulty and lognormal noise plus interruptions"}))
                db.add(task);tasks.append(task);plans.append(plan);durations.append(actual)
            db.flush()
            blocks,deferred=build_schedule_blocks(db,schedule.id,uid,tasks,start,start+timedelta(minutes=rng.choice([180,240,300])),5)
            for k,block in enumerate(blocks):
                block.id=identity(f"{i}/block/{k}")
                db.add(block)
            by_task={b.task_id:b for b in blocks if b.task_id}
            db.flush()
            for j,task in enumerate(tasks):
                complete=j<5
                task.status="completed" if complete else ["unfinished","missed","pending"][j-5]
                if j>=6:continue
                minutes=durations[j] if complete else max(5,durations[j]//2)
                task.actual_minutes=minutes if complete else None
                block=by_task.get(task.id)
                began=(block.start_at if block else start+timedelta(hours=8+j*2))+timedelta(minutes=rng.randint(0,18))
                ended=began+timedelta(minutes=minutes)
                session=SessionRecord(id=identity(f"{i}/{j}/session"),user_id=uid,task_id=task.id,time_block_id=block.id if block else None,started_at=began,actual_start=began,ended_at=ended,actual_end=ended,elapsed_minutes=minutes,status="completed" if complete else "cancelled",energy_level=rng.choice(["low","medium","high"]),feedback_notes="SYNTHETIC generated fixture; no participant feedback",notes="SYNTHETIC, not measured human work")
                db.add(session)
                db.flush()
                if block:
                    block.actual_start=began;block.actual_end=ended;block.status=session.status
                for n,step in enumerate(plans[j].steps):
                    db.add(TaskStep(id=identity(f"{i}/{j}/step/{n}"),task_id=task.id,title=step.title,order_index=step.order,suggested_minutes=step.suggested_minutes,rationale=step.rationale))
                monitor=ActivityMonitor(id=identity(f"{i}/{j}/monitor"),session_id=session.id,enabled=False,enabled_at=began,last_seen_at=began+timedelta(seconds=180),last_sequence=36,
                                        token_hash=hashlib.sha256((DATASET+session.id).encode()).hexdigest())
                db.add(monitor)
                db.flush()
                for n in range(36):
                    idle=rng.random()<.18
                    a=began+timedelta(seconds=n*5)
                    db.add(ActivityInterval(id=identity(f"{i}/{j}/interval/{n}"),monitor_id=monitor.id,sequence=n+1,started_at=a,ended_at=a+timedelta(seconds=5),state="idle" if idle else "active",app_name=None if idle else rng.choice(["Code.exe","chrome.exe","WindowsTerminal.exe"])))
            db.flush()
    with Session(engine) as db:
        return simulation_summary(db)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database",type=Path,default=Path("timeblind_ai.db"))
    parser.add_argument("--output",type=Path,default=Path("output/simulation"))
    parser.add_argument("--postgres",action="store_true",help="Seed only simulation accounts on a chosen PostgreSQL database; URL input is hidden")
    args=parser.parse_args()
    path=args.database.resolve()
    if not args.postgres and path.exists():
        backup=Path("backups")/f"before-simulation-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.db"
        backup.parent.mkdir(exist_ok=True)
        with sqlite3.connect(path.as_uri()+"?mode=ro",uri=True) as src, sqlite3.connect(backup) as dst:
            src.backup(dst)
        print("Backup:",backup)
    if args.postgres:
        try:
            url=make_url(getpass("External PostgreSQL URL (hidden): ").strip())
            if url.drivername not in {"postgres","postgresql","postgresql+psycopg"}:raise ValueError()
            url=url.set(drivername="postgresql+psycopg").update_query_dict({"sslmode":"require"})
        except Exception:
            raise SystemExit("Invalid PostgreSQL URL. No credentials are printed.") from None
        if input("Type SEED SYNTHETIC to add the labelled demo cohort: ").strip()!="SEED SYNTHETIC":
            raise SystemExit("Cancelled.")
        engine=create_engine(url,connect_args={"connect_timeout":15})
    else:
        engine=create_engine("sqlite:///"+path.as_posix())
    try:
        result=seed(engine)
    except Exception as error:
        print(f"Seeding failed ({type(error).__name__}); no record details or credentials printed.")
        raise SystemExit(1) from None
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/"simulation-results.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    result.pop("people")
    print(json.dumps(result,indent=2))
    engine.dispose()


if __name__=="__main__":main()
