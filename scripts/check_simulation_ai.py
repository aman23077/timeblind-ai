"""Small live provider check using only labelled synthetic task inputs.

Calls consume provider quota. Predictions are compared to simulator outcomes,
never reported as human prediction accuracy. Run separately from the seeder.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic, sleep
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.main import app  # noqa: F401
from app.core.config import get_settings
from app.modules.users.datasets import DatasetAccount
from app.modules.users.simulation import DATASET
from app.modules.tasks.models import Task
from app.modules.tasks.schemas import TaskDecompositionRequest
from app.modules.reasoning.generative import estimate_task


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database",type=Path,default=Path("timeblind_ai.db"))
    parser.add_argument("--samples",type=int,choices=[1,2,3],default=2)
    parser.add_argument("--output",type=Path,default=Path("output/simulation/live-ai-check.json"))
    args=parser.parse_args()
    if not args.database.is_file():parser.error("Simulation database not found")
    settings=get_settings()
    if not settings.llm_enabled or not settings.planning_api_key:
        raise SystemExit("Configure LLM_ENABLED and a provider key locally before this live check.")
    engine=create_engine("sqlite:///"+args.database.resolve().as_posix())
    results=[]
    with Session(engine) as db:
        rows=db.scalars(select(Task).join(DatasetAccount,DatasetAccount.user_id==Task.user_id).where(DatasetAccount.source=="synthetic",DatasetAccount.dataset_id==DATASET,Task.status=="completed").order_by(Task.id).limit(args.samples)).all()
        if not rows:raise SystemExit("Seed the simulation first.")
        for i,task in enumerate(rows):
            if i:sleep(60)
            began=monotonic()
            result={"data_source":"synthetic", "task_id":task.id,"simulated_actual_minutes":task.actual_minutes,"rules_minutes":task.estimated_minutes}
            try:
                plan=estimate_task(db,TaskDecompositionRequest(title=task.title,task_type=task.task_type,difficulty=task.difficulty,user_id=None,estimated_minutes=None))
                result.update(status="ok" if plan.generation_source=="llm" else "not_ai",source=plan.generation_source,model=plan.model_name,prompt_version=plan.prompt_version,ai_minutes=plan.personalized_estimate_minutes)
            except HTTPException as error:
                result.update(status="failed",http_status=error.status_code)
            result["latency_seconds"]=round(monotonic()-began,3)
            results.append(result)
            print(f"Live synthetic-input request {i+1}/{len(rows)}: {result['status']}",flush=True)
    report={"source":"live provider check on synthetic tasks", "human_observations":0,"created_at":datetime.now(timezone.utc).isoformat(),"provider":settings.llm_provider,"model":settings.llm_model,"attempts":len(results),"successes":sum(r["status"]=="ok" for r in results),"results":results,"limitations":"Tiny integration check. Simulated outcome comparisons are not human accuracy; no participant ratings collected."}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k!="results"},indent=2))
    engine.dispose()


if __name__=="__main__":main()
