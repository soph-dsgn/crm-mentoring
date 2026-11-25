from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.exc import IntegrityError

from app.api.errors import ApiError
from app.api.routes._shared import (
    Database,
    MutationContext,
    SameOrigin,
    commit,
    raise_integrity_conflict,
)
from app.modules.auth.dependencies import request_now
from app.modules.strategies.notion_import import (
    MAX_PDF_BYTES,
    apply_strategy_import,
    parse_notion_pdf,
)
from app.modules.strategies.schemas import (
    StrategyImportApply,
    StrategyImportDraft,
    StrategyImportResult,
    StrategyRead,
)
from app.modules.strategies.service import get_student_for_strategy

router = APIRouter(prefix="/api/v1", tags=["strategy-imports"])


async def _pdf_body(request: Request) -> bytes:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/pdf":
        raise ApiError(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "unsupported_file", "Upload a PDF document"
        )
    length = request.headers.get("content-length")
    if length and (not length.isdigit() or int(length) > MAX_PDF_BYTES):
        raise ApiError(413, "payload_too_large", "PDF document is too large")
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_PDF_BYTES:
            raise ApiError(413, "payload_too_large", "PDF document is too large")
        chunks.append(chunk)
    return b"".join(chunks)


PdfBody = Annotated[bytes, Depends(_pdf_body)]
PDF_REQUEST_OPENAPI = {
    "requestBody": {
        "required": True,
        "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
    }
}


@router.post(
    "/students/{student_id}/strategy-import/preview",
    response_model=StrategyImportDraft,
    openapi_extra=PDF_REQUEST_OPENAPI,
)
def preview_strategy_import_endpoint(
    student_id: str,
    body: PdfBody,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
) -> StrategyImportDraft:
    get_student_for_strategy(database, context.user, student_id, write=True)
    database.commit()
    return parse_notion_pdf(body)


@router.post(
    "/students/{student_id}/strategy-import",
    response_model=StrategyImportResult,
    status_code=status.HTTP_201_CREATED,
)
def apply_strategy_import_endpoint(
    student_id: str,
    payload: StrategyImportApply,
    request: Request,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
) -> StrategyImportResult:
    student = get_student_for_strategy(database, context.user, student_id, write=True)
    try:
        strategy, task_count = apply_strategy_import(
            database, context.user, student, payload, request_now(request)
        )
    except IntegrityError as error:
        raise_integrity_conflict(database, error)
    commit(database)
    database.refresh(strategy)
    database.refresh(student)
    return StrategyImportResult(
        strategy=StrategyRead.model_validate(strategy),
        student_version=student.version,
        section_count=len(payload.sections),
        task_count=task_count,
    )
