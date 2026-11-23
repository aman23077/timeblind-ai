"""Live database analytics for the explicitly synthetic demonstration cohort."""
import json
import statistics
from collections import Counter
from sqlalchemy import select
from app.modules.users.datasets import DatasetAccount
from app.modules.users.models import User
from app.modules.tasks.models import Task
from app.modules.sessions.models import SessionRecord
from app.modules.schedules.models import TimeBlock, Schedule
from app.modules.behaviour.activity import ActivityInterval, ActivityMonitor, summary as activity_summary

DATASET = "btp-demo-2026-11-v1"


def metrics(tasks):
    valid = [t for t in tasks if t.status == "completed" and t.actual_minutes and t.estimated_minutes]
    errors = [t.actual_minutes-t.estimated_minutes for t in valid]
    return {"n":len(valid), "mae_minutes":round(statistics.mean(abs(e) for e in errors),2) if errors else None,
            "bias_actual_minus_estimate_minutes":round(statistics.mean(errors),2) if errors else None,
            "mape_actual_denominator_percent":round(statistics.mean(abs(t.actual_minutes-t.estimated_minutes)/t.actual_minutes*100 for t in valid),2) if valid else None,
            "within_15_minutes_percent":round(100*sum(abs(e)<=15 for e in errors)/len(errors),2) if errors else None,
            "underestimates":sum(e>0 for e in errors), "overestimates":sum(e<0 for e in errors)}


def simulation_summary(db):
    users = db.scalars(select(User).join(DatasetAccount, DatasetAccount.user_id == User.id).where(
        DatasetAccount.source == "synthetic", DatasetAccount.dataset_id == DATASET).order_by(User.display_name)).all()
    ids = [u.id for u in users]
    tasks = db.scalars(select(Task).where(Task.user_id.in_(ids))).all()
    sessions = db.scalars(select(SessionRecord).where(SessionRecord.user_id.in_(ids))).all()
    schedules = db.scalars(select(Schedule).where(Schedule.user_id.in_(ids))).all()
    blocks = db.scalars(select(TimeBlock).where(TimeBlock.user_id.in_(ids))).all()
    monitors = db.scalars(select(ActivityMonitor).join(SessionRecord, ActivityMonitor.session_id==SessionRecord.id).where(SessionRecord.user_id.in_(ids))).all()
    intervals = db.scalars(select(ActivityInterval).where(ActivityInterval.monitor_id.in_([m.id for m in monitors]))).all()
    summaries = [activity_summary(s.id,s.user_id,db) for s in sessions if s.id in {m.session_id for m in monitors}]
    people=[]
    for user in users:
        subset=[t for t in tasks if t.user_id==user.id]
        error=metrics(subset)
        people.append({"label":user.display_name, "id":user.id, "tasks":len(subset), "statuses":dict(Counter(t.status for t in subset)),
                       "estimation":error, "computed_review":f"SYNTHETIC history: {error['n']} completed examples; rules MAE {error['mae_minutes']} minutes. Inspect task scope before changing estimates. This is a deterministic computed summary, not participant feedback or an LLM review."})
    checks=[]
    for schedule in schedules:
        own=sorted([b for b in blocks if b.schedule_id==schedule.id],key=lambda b:b.start_at)
        checks.append(all(a.end_at<=b.start_at for a,b in zip(own,own[1:])) and all(b.end_at>b.start_at for b in own))
    return {"data_source":"synthetic", "dataset_id":DATASET, "human_participants":0, "simulation_profiles":len(users),
            "tasks":len(tasks), "statuses":dict(Counter(t.status for t in tasks)), "sessions":len(sessions),
            "estimation":metrics(tasks), "categories":{k:metrics([t for t in tasks if t.task_type==k]) for k in sorted({t.task_type for t in tasks})},
            "schedules":len(schedules), "nonoverlap_positive_duration_passes":sum(checks),
            "simulated_activity_intervals":len(intervals), "simulated_app_switches":sum(s["context_switches"] for s in summaries),
            "simulated_active_seconds":sum(s["active_seconds"] for s in summaries), "simulated_idle_seconds":sum(s["idle_seconds"] for s in summaries),
            "computed_reviews":len(people), "participant_reviews":0, "llm_reviews":0, "people":people,
            "limitations":["All profiles, durations, task outcomes and desktop intervals are generated, not human observations.",
                            "Metrics describe this simulation and generator assumptions, not productivity gains or real-world accuracy.",
                            "No real email addresses, diagnoses, demographics, consent or subjective ratings are invented.",
                            "No LLM was called by the seeder; summaries are computed from synthetic records."]}
