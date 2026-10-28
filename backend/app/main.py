from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import Engine
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.errors import ApiError, api_error_handler, validation_error_handler
from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.db.session import build_engine, engine
from app.modules.auth.passwords import PasswordManager


def create_app(
    settings: Settings | None = None,
    *,
    database_engine: Engine | None = None,
) -> FastAPI:
    application_settings = settings or get_settings()
    application_engine = database_engine or (
        build_engine(
            application_settings.database_url,
            pool_size=application_settings.database_pool_size,
            max_overflow=application_settings.database_max_overflow,
            pool_timeout=application_settings.database_pool_timeout_seconds,
            connect_timeout=application_settings.database_connect_timeout_seconds,
        )
        if settings is not None
        else engine
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        application_engine.dispose()

    production = application_settings.environment == "production"
    application = FastAPI(
        title=application_settings.app_name,
        debug=application_settings.debug,
        version="0.1.0",
        docs_url=None if production else "/docs",
        redoc_url=None if production else "/redoc",
        openapi_url=None if production else "/openapi.json",
        lifespan=lifespan,
    )
    application.state.settings = application_settings
    application.state.database_engine = application_engine
    application.state.password_manager = PasswordManager(
        time_cost=application_settings.auth_argon2_time_cost,
        memory_cost=application_settings.auth_argon2_memory_cost,
        parallelism=application_settings.auth_argon2_parallelism,
        minimum_length=application_settings.auth_password_min_length,
    )
    application.add_exception_handler(ApiError, api_error_handler)
    application.add_exception_handler(RequestValidationError, validation_error_handler)
    if production:
        application.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=application_settings.permitted_hosts,
        )
        application.add_middleware(
            CORSMiddleware,
            allow_origins=application_settings.frontend_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
            allow_headers=["Content-Type", "X-CSRF-Token"],
        )

        @application.middleware("http")
        async def reject_untrusted_forwarded_headers(request, call_next):
            forwarded = any(
                name in request.headers
                for name in (
                    "forwarded",
                    "x-forwarded-for",
                    "x-forwarded-host",
                    "x-forwarded-proto",
                )
            )
            client = request.client.host if request.client else ""
            if forwarded and client not in application_settings.trusted_proxy_ips:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": {
                            "code": "untrusted_proxy_headers",
                            "message": "Forwarded headers are not trusted",
                            "details": {},
                        }
                    },
                )
            return await call_next(request)

    application.include_router(api_router)
    return application


app = create_app()
