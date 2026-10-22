from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.api.errors import ApiError, api_error_handler, validation_error_handler
from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.modules.auth.passwords import PasswordManager


def create_app(settings: Settings | None = None) -> FastAPI:
    application_settings = settings or get_settings()
    application = FastAPI(
        title=application_settings.app_name,
        debug=application_settings.debug,
        version="0.1.0",
    )
    application.state.settings = application_settings
    application.state.password_manager = PasswordManager(
        time_cost=application_settings.auth_argon2_time_cost,
        memory_cost=application_settings.auth_argon2_memory_cost,
        parallelism=application_settings.auth_argon2_parallelism,
        minimum_length=application_settings.auth_password_min_length,
    )
    application.add_exception_handler(ApiError, api_error_handler)
    application.add_exception_handler(RequestValidationError, validation_error_handler)
    application.include_router(api_router)
    return application


app = create_app()
