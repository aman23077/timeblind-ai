from fastapi import APIRouter, Depends
from app.core.auth import require_workspace_access
from app.modules.users.auth_routes import router as auth_router
from app.modules.users.admin_routes import router as admin_router
from app.modules.behaviour.activity import router as activity_router

from app.modules.behaviour.routes import router as behaviour_router
from app.modules.context.routes import router as context_router
from app.modules.events.routes import router as events_router
from app.modules.goals.routes import router as goals_router
from app.modules.health.routes import router as health_router
from app.modules.insights.routes import router as insights_router
from app.modules.interventions.routes import router as interventions_router
from app.modules.schedules.routes import router as schedules_router
from app.modules.sessions.routes import router as sessions_router
from app.modules.tasks.routes import router as tasks_router
from app.modules.users.routes import router as users_router
from app.modules.study.routes import router as study_router


from app.modules.interventions.policy import router as policy_router

api_router = APIRouter()
api_router.include_router(study_router, prefix="/api/v1/study", tags=["study"])
api_router.include_router(policy_router, prefix="/api/v1/policy", tags=["policy"])
api_router.include_router(admin_router, prefix="/api/v1/admin", tags=["admin"])
api_router.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
api_router.include_router(activity_router, prefix="/api/v1/activity", tags=["activity"])
api_router.include_router(health_router)
api_router.include_router(users_router, prefix="/api/v1/users", tags=["users"])
api_router.include_router(goals_router, prefix="/api/v1/goals", tags=["goals"], dependencies=[Depends(require_workspace_access)])
api_router.include_router(events_router, prefix="/api/v1/events", tags=["events"], dependencies=[Depends(require_workspace_access)])
api_router.include_router(tasks_router, prefix="/api/v1/tasks", tags=["tasks"], dependencies=[Depends(require_workspace_access)])
api_router.include_router(schedules_router, prefix="/api/v1/schedules", tags=["schedules"], dependencies=[Depends(require_workspace_access)])
api_router.include_router(insights_router, prefix="/api/v1/insights", tags=["insights"], dependencies=[Depends(require_workspace_access)])
api_router.include_router(interventions_router, prefix="/api/v1/interventions", tags=["interventions"], dependencies=[Depends(require_workspace_access)])
api_router.include_router(sessions_router, prefix="/api/v1/sessions", tags=["sessions"], dependencies=[Depends(require_workspace_access)])
api_router.include_router(context_router, prefix="/api/v1/context", tags=["context"], dependencies=[Depends(require_workspace_access)])
api_router.include_router(behaviour_router, prefix="/api/v1/behaviour", tags=["behaviour"], dependencies=[Depends(require_workspace_access)])
