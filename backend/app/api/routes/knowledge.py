from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import BaseModel, ValidationError

from app.api.errors import ApiError
from app.api.routes._shared import Database, MutationContext, QueryContext, SameOrigin, commit
from app.modules.auth.dependencies import request_now
from app.modules.knowledge.models import KnowledgeDocument, KnowledgeKind
from app.modules.knowledge.schemas import (
    KnowledgeCreate,
    KnowledgeDocumentList,
    KnowledgeDocumentRead,
    KnowledgeDocumentSummary,
    KnowledgeUpdate,
    VersionRequest,
)
from app.modules.knowledge.service import (
    add_favorite,
    archive_document,
    create_document,
    get_document,
    list_documents,
    remove_favorite,
    restore_document,
    update_document,
)

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])
MAX_KNOWLEDGE_REQUEST_BYTES = 1024 * 1024
MAX_JSON_DEPTH = 24


def _within_depth(value: object, depth: int = 0) -> bool:
    if depth > MAX_JSON_DEPTH:
        return False
    if isinstance(value, dict):
        return all(_within_depth(item, depth + 1) for item in value.values())
    if isinstance(value, list):
        return all(_within_depth(item, depth + 1) for item in value)
    return True


async def _payload[ModelT: BaseModel](request: Request, model: type[ModelT]) -> ModelT:
    length = request.headers.get("content-length")
    if length and (not length.isdigit() or int(length) > MAX_KNOWLEDGE_REQUEST_BYTES):
        raise ApiError(413, "payload_too_large", "Knowledge request is too large")
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_KNOWLEDGE_REQUEST_BYTES:
            raise ApiError(413, "payload_too_large", "Knowledge request is too large")
        chunks.append(chunk)
    body = b"".join(chunks)
    try:
        raw = json.loads(body)
        if not _within_depth(raw):
            raise ApiError(422, "validation_error", "Request validation failed")
        return model.model_validate(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, ValidationError, TypeError, RecursionError):
        raise ApiError(422, "validation_error", "Request validation failed") from None


async def _create_payload(request: Request) -> KnowledgeCreate:
    return await _payload(request, KnowledgeCreate)


async def _update_payload(request: Request) -> KnowledgeUpdate:
    return await _payload(request, KnowledgeUpdate)


async def _version_payload(request: Request) -> VersionRequest:
    return await _payload(request, VersionRequest)


CreatePayload = Annotated[KnowledgeCreate, Depends(_create_payload)]
UpdatePayload = Annotated[KnowledgeUpdate, Depends(_update_payload)]
VersionPayload = Annotated[VersionRequest, Depends(_version_payload)]
CREATE_REQUEST_OPENAPI = {
    "requestBody": {
        "required": True,
        "content": {"application/json": {"schema": KnowledgeCreate.model_json_schema()}},
    }
}
UPDATE_REQUEST_OPENAPI = {
    "requestBody": {
        "required": True,
        "content": {"application/json": {"schema": KnowledgeUpdate.model_json_schema()}},
    }
}
VERSION_REQUEST_OPENAPI = {
    "requestBody": {
        "required": True,
        "content": {"application/json": {"schema": VersionRequest.model_json_schema()}},
    }
}


def _read(document: KnowledgeDocument, favorite: bool) -> KnowledgeDocumentRead:
    return KnowledgeDocumentRead(
        id=document.id,
        kind=document.kind,
        title=document.title,
        category=document.category,
        html=document.html,
        plain_text=document.plain_text,
        position=document.position,
        archived_at=document.archived_at,
        created_at=document.created_at,
        updated_at=document.updated_at,
        version=document.version,
        is_favorite=favorite,
    )


def _summary(document: KnowledgeDocument, favorite: bool) -> KnowledgeDocumentSummary:
    excerpt = document.plain_text[:240]
    return KnowledgeDocumentSummary(
        id=document.id,
        kind=document.kind,
        title=document.title,
        category=document.category,
        excerpt=excerpt,
        position=document.position,
        archived_at=document.archived_at,
        updated_at=document.updated_at,
        version=document.version,
        is_favorite=favorite,
    )


@router.get("/documents", response_model=KnowledgeDocumentList)
def list_documents_endpoint(
    database: Database,
    context: QueryContext,
    kind: KnowledgeKind | None = None,
    category: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    favorite: bool | None = None,
    include_archived: bool = False,
    cursor: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> KnowledgeDocumentList:
    items, next_cursor = list_documents(
        database,
        context.user,
        kind=kind,
        category=category,
        query=q,
        favorite=favorite,
        include_archived=include_archived,
        cursor=cursor,
        limit=limit,
    )
    database.commit()
    return KnowledgeDocumentList(
        items=[_summary(document, is_favorite) for document, is_favorite in items],
        next_cursor=next_cursor,
    )


@router.post(
    "/documents",
    response_model=KnowledgeDocumentRead,
    status_code=status.HTTP_201_CREATED,
    openapi_extra=CREATE_REQUEST_OPENAPI,
)
def create_document_endpoint(
    payload: CreatePayload,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
) -> KnowledgeDocumentRead:
    document = create_document(database, context.user, payload)
    commit(database)
    return _read(document, False)


@router.get("/documents/{document_id}", response_model=KnowledgeDocumentRead)
def get_document_endpoint(
    document_id: str,
    database: Database,
    context: QueryContext,
) -> KnowledgeDocumentRead:
    document, favorite = get_document(database, context.user, document_id)
    response = _read(document, favorite)
    database.commit()
    return response


@router.patch(
    "/documents/{document_id}",
    response_model=KnowledgeDocumentRead,
    openapi_extra=UPDATE_REQUEST_OPENAPI,
)
def update_document_endpoint(
    document_id: str,
    payload: UpdatePayload,
    request: Request,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
) -> KnowledgeDocumentRead:
    document, favorite = get_document(database, context.user, document_id)
    document = update_document(database, context.user, document, payload, request_now(request))
    commit(database)
    return _read(document, favorite)


@router.post(
    "/documents/{document_id}/archive",
    response_model=KnowledgeDocumentRead,
    openapi_extra=VERSION_REQUEST_OPENAPI,
)
def archive_document_endpoint(
    document_id: str,
    payload: VersionPayload,
    request: Request,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
) -> KnowledgeDocumentRead:
    document, favorite = get_document(database, context.user, document_id)
    document = archive_document(
        database, context.user, document, payload.expected_version, request_now(request)
    )
    commit(database)
    return _read(document, favorite)


@router.post(
    "/documents/{document_id}/restore",
    response_model=KnowledgeDocumentRead,
    openapi_extra=VERSION_REQUEST_OPENAPI,
)
def restore_document_endpoint(
    document_id: str,
    payload: VersionPayload,
    request: Request,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
) -> KnowledgeDocumentRead:
    document, favorite = get_document(database, context.user, document_id)
    document = restore_document(
        database,
        context.user,
        document,
        payload.expected_version,
        request_now(request),
    )
    commit(database)
    return _read(document, favorite)


@router.post("/documents/{document_id}/favorite", status_code=status.HTTP_204_NO_CONTENT)
def favorite_document_endpoint(
    document_id: str,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
) -> Response:
    document, _ = get_document(database, context.user, document_id)
    add_favorite(database, context.user, document)
    commit(database)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/documents/{document_id}/unfavorite", status_code=status.HTTP_204_NO_CONTENT)
def unfavorite_document_endpoint(
    document_id: str,
    database: Database,
    context: MutationContext,
    _: SameOrigin,
) -> Response:
    document, _ = get_document(database, context.user, document_id)
    remove_favorite(database, context.user, document)
    commit(database)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
