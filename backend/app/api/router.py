from fastapi import APIRouter

from app.api.routes.admin_users import router as admin_users_router
from app.api.routes.auth import router as auth_router
from app.api.routes.groups import router as groups_router
from app.api.routes.health import router as health_router
from app.api.routes.homeworks import router as homeworks_router
from app.api.routes.meetings import router as meetings_router
from app.api.routes.strategies import router as strategies_router
from app.api.routes.students import router as students_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(admin_users_router)
api_router.include_router(groups_router)
api_router.include_router(students_router)
api_router.include_router(strategies_router)
api_router.include_router(meetings_router)
api_router.include_router(homeworks_router)
