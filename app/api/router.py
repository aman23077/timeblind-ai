from fastapi import APIRouter

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


api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(users_router, prefix="/api/v1/users", tags=["users"])
api_router.include_router(goals_router, prefix="/api/v1/goals", tags=["goals"])
api_router.include_router(events_router, prefix="/api/v1/events", tags=["events"])
api_router.include_router(tasks_router, prefix="/api/v1/tasks", tags=["tasks"])
api_router.include_router(schedules_router, prefix="/api/v1/schedules", tags=["schedules"])
api_router.include_router(insights_router, prefix="/api/v1/insights", tags=["insights"])
api_router.include_router(interventions_router, prefix="/api/v1/interventions", tags=["interventions"])
api_router.include_router(sessions_router, prefix="/api/v1/sessions", tags=["sessions"])
api_router.include_router(context_router, prefix="/api/v1/context", tags=["context"])
api_router.include_router(behaviour_router, prefix="/api/v1/behaviour", tags=["behaviour"])
