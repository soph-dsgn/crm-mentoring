from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    application_settings = settings or get_settings()
    application = FastAPI(
        title=application_settings.app_name,
        debug=application_settings.debug,
        version="0.1.0",
    )
    application.state.settings = application_settings
    application.include_router(api_router)
    return application


app = create_app()
