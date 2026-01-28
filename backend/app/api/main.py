from fastapi import APIRouter

from app.api.routes.auth import views as auth_views
from app.api.routes.items import views as items_views
from app.api.routes.private import views as private_views
from app.api.routes.users import views as users_views
from app.api.routes.utils import views as utils_views
from app.api.routes.worklog import views as worklog_views
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(auth_views.router)
api_router.include_router(users_views.router)
api_router.include_router(utils_views.router)
api_router.include_router(items_views.router)
api_router.include_router(worklog_views.router)


if settings.ENVIRONMENT == "local":
    api_router.include_router(private_views.router)
