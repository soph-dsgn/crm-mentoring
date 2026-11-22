from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, exists, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.api.pagination import decode_cursor, encode_cursor
from app.modules.knowledge.library import require_library_active
from app.modules.knowledge.models import KnowledgeDocument, KnowledgeFavorite, KnowledgeKind
from app.modules.knowledge.sanitizer import sanitize_knowledge_html
from app.modules.knowledge.schemas import KnowledgeCreate, KnowledgeUpdate
from app.modules.users.audit import AuditAction
from app.modules.users.models import User
from app.modules.users.service import ensure_admin, record_audit


def _not_found() -> ApiError:
    return ApiError(404, "not_found", "Knowledge document not found")


def _conflict(code: str, message: str) -> ApiError:
    return ApiError(409, code, message)


def _search_text(title: str, plain_text: str) -> str:
    return f"{title} {plain_text}".casefold()


def _favorite_exists(actor: User):
    return exists().where(
        KnowledgeFavorite.user_id == actor.id,
        KnowledgeFavorite.document_id == KnowledgeDocument.id,
    )


def get_document(
    database: Session, actor: User, document_id: str
) -> tuple[KnowledgeDocument, bool]:
    ensure_admin(actor)
    require_library_active(database)
    document = database.get(KnowledgeDocument, document_id)
    if document is None:
        raise _not_found()
    favorite = database.get(KnowledgeFavorite, (actor.id, document.id)) is not None
    return document, favorite


def list_documents(
    database: Session,
    actor: User,
    *,
    kind: KnowledgeKind | None,
    category: str | None,
    query: str | None,
    favorite: bool | None,
    include_archived: bool,
    cursor: str | None,
    limit: int,
) -> tuple[list[tuple[KnowledgeDocument, bool]], str | None]:
    ensure_admin(actor)
    require_library_active(database)
    conditions = []
    if kind is not None:
        conditions.append(KnowledgeDocument.kind == kind)
    if category is not None:
        conditions.append(KnowledgeDocument.category == category)
    if query:
        conditions.append(KnowledgeDocument.search_text.contains(query.casefold(), autoescape=True))
    if not include_archived:
        conditions.append(KnowledgeDocument.archived_at.is_(None))
    favorite_condition = _favorite_exists(actor)
    if favorite is True:
        conditions.append(favorite_condition)
    elif favorite is False:
        conditions.append(~favorite_condition)

    cursor_id = decode_cursor(cursor)
    if cursor_id is not None:
        valid_cursor = database.scalar(
            select(KnowledgeDocument.id).where(
                KnowledgeDocument.id == cursor_id,
                *conditions,
            )
        )
        if valid_cursor is None:
            raise ApiError(422, "invalid_cursor", "Pagination cursor is invalid")
        conditions.append(KnowledgeDocument.id > cursor_id)

    rows = list(
        database.scalars(
            select(KnowledgeDocument)
            .where(*conditions)
            .order_by(KnowledgeDocument.id)
            .limit(limit + 1)
        )
    )
    has_more = len(rows) > limit
    documents = rows[:limit]
    favorite_ids = (
        set(
            database.scalars(
                select(KnowledgeFavorite.document_id).where(
                    KnowledgeFavorite.user_id == actor.id,
                    KnowledgeFavorite.document_id.in_([document.id for document in documents]),
                )
            )
        )
        if documents
        else set()
    )
    items = [(document, document.id in favorite_ids) for document in documents]
    return items, encode_cursor(documents[-1].id) if has_more else None


def create_document(
    database: Session,
    actor: User,
    payload: KnowledgeCreate,
) -> KnowledgeDocument:
    ensure_admin(actor)
    require_library_active(database, for_update=True)
    sanitized_html, plain_text = sanitize_knowledge_html(payload.html)
    document = KnowledgeDocument(
        kind=payload.kind,
        title=payload.title,
        category=payload.category,
        html=sanitized_html,
        plain_text=plain_text,
        search_text=_search_text(payload.title, plain_text),
        position=payload.position,
        created_by_user_id=actor.id,
        updated_by_user_id=actor.id,
    )
    database.add(document)
    database.flush()
    record_audit(
        database,
        actor=actor,
        action=AuditAction.KNOWLEDGE_CREATED,
        details={"document_id": document.id, "version": document.version},
    )
    return document


def update_document(
    database: Session,
    actor: User,
    document: KnowledgeDocument,
    payload: KnowledgeUpdate,
    now: datetime,
) -> KnowledgeDocument:
    ensure_admin(actor)
    require_library_active(database, for_update=True)
    if document.archived_at is not None:
        raise _conflict("document_archived", "Archived Knowledge document is read-only")
    values = payload.model_dump(exclude={"expected_version"}, exclude_unset=True)
    if "html" in values:
        sanitized_html, plain_text = sanitize_knowledge_html(values["html"])
        values["html"] = sanitized_html
        values["plain_text"] = plain_text
    title = values.get("title", document.title)
    plain_text = values.get("plain_text", document.plain_text)
    values.update(
        search_text=_search_text(title, plain_text),
        updated_by_user_id=actor.id,
        updated_at=now,
        version=KnowledgeDocument.version + 1,
    )
    result = database.execute(
        update(KnowledgeDocument)
        .where(
            KnowledgeDocument.id == document.id,
            KnowledgeDocument.version == payload.expected_version,
            KnowledgeDocument.archived_at.is_(None),
        )
        .values(**values)
    )
    if result.rowcount != 1:
        database.expire_all()
        raise _conflict("version_conflict", "Knowledge document changed by another request")
    database.expire_all()
    updated = database.get(KnowledgeDocument, document.id)
    if updated is None:
        raise _not_found()
    record_audit(
        database,
        actor=actor,
        action=AuditAction.KNOWLEDGE_UPDATED,
        details={"document_id": updated.id, "version": updated.version},
    )
    return updated


def _change_archive_state(
    database: Session,
    actor: User,
    document: KnowledgeDocument,
    *,
    expected_version: int,
    archived_at: datetime | None,
    now: datetime,
) -> KnowledgeDocument:
    ensure_admin(actor)
    require_library_active(database, for_update=True)
    if (document.archived_at is None) == (archived_at is None):
        code = "document_not_archived" if archived_at is None else "document_archived"
        raise _conflict(code, "Knowledge document is already in the requested state")
    result = database.execute(
        update(KnowledgeDocument)
        .where(
            KnowledgeDocument.id == document.id,
            KnowledgeDocument.version == expected_version,
        )
        .values(
            archived_at=archived_at,
            updated_by_user_id=actor.id,
            updated_at=now,
            version=KnowledgeDocument.version + 1,
        )
    )
    if result.rowcount != 1:
        database.expire_all()
        raise _conflict("version_conflict", "Knowledge document changed by another request")
    database.expire_all()
    updated = database.get(KnowledgeDocument, document.id)
    if updated is None:
        raise _not_found()
    action = (
        AuditAction.KNOWLEDGE_ARCHIVED
        if archived_at is not None
        else AuditAction.KNOWLEDGE_RESTORED
    )
    record_audit(
        database,
        actor=actor,
        action=action,
        details={"document_id": updated.id, "version": updated.version},
    )
    return updated


def archive_document(
    database: Session,
    actor: User,
    document: KnowledgeDocument,
    expected_version: int,
    now: datetime,
) -> KnowledgeDocument:
    return _change_archive_state(
        database,
        actor,
        document,
        expected_version=expected_version,
        archived_at=now,
        now=now,
    )


def restore_document(
    database: Session,
    actor: User,
    document: KnowledgeDocument,
    expected_version: int,
    now: datetime,
) -> KnowledgeDocument:
    return _change_archive_state(
        database,
        actor,
        document,
        expected_version=expected_version,
        archived_at=None,
        now=now,
    )


def add_favorite(database: Session, actor: User, document: KnowledgeDocument) -> None:
    ensure_admin(actor)
    require_library_active(database, for_update=True)
    if database.get(KnowledgeFavorite, (actor.id, document.id)) is not None:
        return
    try:
        with database.begin_nested():
            database.add(KnowledgeFavorite(user_id=actor.id, document_id=document.id))
            database.flush()
    except IntegrityError:
        # A concurrent identical request already created the personal favorite.
        pass


def remove_favorite(database: Session, actor: User, document: KnowledgeDocument) -> None:
    ensure_admin(actor)
    require_library_active(database, for_update=True)
    database.execute(
        delete(KnowledgeFavorite).where(
            KnowledgeFavorite.user_id == actor.id,
            KnowledgeFavorite.document_id == document.id,
        )
    )
