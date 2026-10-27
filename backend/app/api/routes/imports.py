from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.api.errors import ApiError
from app.api.routes._shared import Database, MutationContext, QueryContext, SameOrigin
from app.modules.auth.dependencies import request_now
from app.modules.legacy_io.models import ImportRun
from app.modules.legacy_io.schemas import ImportResult, LegacyImportRequest, ValidationReport
from app.modules.legacy_io.service import export_backup, import_legacy, validate_legacy
from app.modules.users.service import ensure_owner

router = APIRouter(prefix="/api/v1", tags=["imports-exports"])
MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_JSON_DEPTH = 32


def _within_depth(value: object, depth: int = 0) -> bool:
    if depth > MAX_JSON_DEPTH:
        return False
    if isinstance(value, dict):
        return all(_within_depth(item, depth + 1) for item in value.values())
    if isinstance(value, list):
        return all(_within_depth(item, depth + 1) for item in value)
    return True


async def _payload(request: Request) -> LegacyImportRequest:
    length = request.headers.get("content-length")
    if length and (not length.isdigit() or int(length) > MAX_IMPORT_BYTES):
        raise ApiError(
            status.HTTP_413_CONTENT_TOO_LARGE,
            "payload_too_large",
            "Import payload is too large",
        )
    body = await request.body()
    if len(body) > MAX_IMPORT_BYTES:
        raise ApiError(
            status.HTTP_413_CONTENT_TOO_LARGE,
            "payload_too_large",
            "Import payload is too large",
        )
    try:
        raw = json.loads(body)
        if not _within_depth(raw):
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "validation_error",
                "Request validation failed",
            )
        return LegacyImportRequest.model_validate(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError, TypeError, RecursionError):
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "validation_error", "Request validation failed"
        ) from None


LegacyPayload = Annotated[LegacyImportRequest, Depends(_payload)]
LEGACY_REQUEST_OPENAPI = {
    "requestBody": {
        "required": True,
        "content": {"application/json": {"schema": LegacyImportRequest.model_json_schema()}},
    }
}


@router.post(
    "/imports/legacy/validate",
    response_model=ValidationReport,
    openapi_extra=LEGACY_REQUEST_OPENAPI,
)
def validate_legacy_endpoint(
    database: Database,
    context: MutationContext,
    _: SameOrigin,
    payload: LegacyPayload,
):
    ensure_owner(context.user)
    report = validate_legacy(database, context.user, payload)
    database.rollback()
    return report


@router.post(
    "/imports/legacy",
    response_model=ImportResult,
    status_code=status.HTTP_201_CREATED,
    openapi_extra=LEGACY_REQUEST_OPENAPI,
)
def import_legacy_endpoint(
    response: Response,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
    payload: LegacyPayload,
):
    ensure_owner(context.user)
    try:
        result = import_legacy(database, context.user, payload)
        database.commit()
    except IntegrityError as error:
        database.rollback()
        existing = (
            database.query(ImportRun)
            .filter(ImportRun.checksum == payload.confirmation_checksum)
            .one_or_none()
        )
        if existing is None:
            raise ApiError(
                status.HTTP_409_CONFLICT, "import_conflict", "Import conflicts with current data"
            ) from error
        result = import_legacy(database, context.user, payload)
        database.rollback()
    if result.idempotent_replay:
        response.status_code = status.HTTP_200_OK
    return result


@router.get("/exports/backup")
def export_backup_endpoint(database: Database, context: QueryContext, request: Request):
    ensure_owner(context.user)
    database.commit()
    if database.get_bind().dialect.name == "postgresql":
        database.connection(execution_options={"isolation_level": "REPEATABLE READ"})
    result = export_backup(database, context.user, request_now(request))
    database.commit()
    return result
