from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.api.errors import ApiError
from app.api.routes._shared import Database, MutationContext, QueryContext, SameOrigin
from app.modules.auth.dependencies import request_now
from app.modules.knowledge.import_service import import_knowledge, logical_export, validate_import
from app.modules.knowledge.library import get_library_state
from app.modules.knowledge.schemas import (
    KnowledgeImportRequest,
    KnowledgeImportResult,
    KnowledgeImportValidation,
    KnowledgeLibraryStateRead,
    KnowledgeLogicalExport,
)
from app.modules.users.service import ensure_admin

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge-imports"])
MAX_KNOWLEDGE_IMPORT_BYTES = 5 * 1024 * 1024
MAX_JSON_DEPTH = 32


def _within_depth(value: object, depth: int = 0) -> bool:
    if depth > MAX_JSON_DEPTH:
        return False
    if isinstance(value, dict):
        return all(_within_depth(item, depth + 1) for item in value.values())
    if isinstance(value, list):
        return all(_within_depth(item, depth + 1) for item in value)
    return True


async def _payload(request: Request) -> KnowledgeImportRequest:
    length = request.headers.get("content-length")
    if length and (not length.isdigit() or int(length) > MAX_KNOWLEDGE_IMPORT_BYTES):
        raise ApiError(413, "payload_too_large", "Knowledge import is too large")
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_KNOWLEDGE_IMPORT_BYTES:
            raise ApiError(413, "payload_too_large", "Knowledge import is too large")
        chunks.append(chunk)
    try:
        raw = json.loads(b"".join(chunks))
        if not _within_depth(raw):
            raise ApiError(422, "validation_error", "Request validation failed")
        return KnowledgeImportRequest.model_validate(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError, TypeError, RecursionError):
        raise ApiError(422, "validation_error", "Request validation failed") from None


ImportPayload = Annotated[KnowledgeImportRequest, Depends(_payload)]
IMPORT_REQUEST_OPENAPI = {
    "requestBody": {
        "required": True,
        "content": {"application/json": {"schema": KnowledgeImportRequest.model_json_schema()}},
    }
}


@router.get("/library-state", response_model=KnowledgeLibraryStateRead)
def library_state_endpoint(database: Database, context: QueryContext) -> KnowledgeLibraryStateRead:
    ensure_admin(context.user)
    state = get_library_state(database)
    return KnowledgeLibraryStateRead(
        status=state.status,
        version=state.version,
        activated_at=state.activated_at,
    )


@router.post(
    "/imports/validate",
    response_model=KnowledgeImportValidation,
    openapi_extra=IMPORT_REQUEST_OPENAPI,
)
def validate_import_endpoint(
    payload: ImportPayload,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
) -> KnowledgeImportValidation:
    report = validate_import(database, context.user, payload)
    database.rollback()
    return report


@router.post(
    "/imports",
    response_model=KnowledgeImportResult,
    status_code=status.HTTP_201_CREATED,
    openapi_extra=IMPORT_REQUEST_OPENAPI,
)
def import_endpoint(
    response: Response,
    request: Request,
    payload: ImportPayload,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
) -> KnowledgeImportResult:
    try:
        result = import_knowledge(database, context.user, payload, request_now(request))
        database.commit()
    except IntegrityError as error:
        database.rollback()
        try:
            result = import_knowledge(database, context.user, payload, request_now(request))
        except ApiError:
            database.rollback()
            raise ApiError(
                409, "import_conflict", "Knowledge import conflicts with current data"
            ) from error
        database.rollback()
        if not result.idempotent_replay:
            raise ApiError(
                409, "import_conflict", "Knowledge import conflicts with current data"
            ) from error
    if result.idempotent_replay:
        response.status_code = status.HTTP_200_OK
    return result


@router.get("/export", response_model=KnowledgeLogicalExport)
def export_endpoint(
    request: Request,
    response: Response,
    database: Database,
    context: QueryContext,
) -> KnowledgeLogicalExport:
    database.commit()
    if database.get_bind().dialect.name == "postgresql":
        database.connection(execution_options={"isolation_level": "REPEATABLE READ"})
    result = logical_export(database, context.user, request_now(request))
    database.commit()
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Disposition"] = 'attachment; filename="knowledge-backup.json"'
    response.headers["X-Content-Type-Options"] = "nosniff"
    return result
