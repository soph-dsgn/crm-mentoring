from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.modules.knowledge.library import get_library_state
from app.modules.knowledge.models import (
    KnowledgeDocument,
    KnowledgeFavorite,
    KnowledgeImportMapping,
    KnowledgeImportMode,
    KnowledgeImportRun,
    KnowledgeKind,
    KnowledgeLibraryState,
    KnowledgeLibraryStatus,
    KnowledgeSourceFormat,
)
from app.modules.knowledge.sanitizer import sanitize_knowledge_html
from app.modules.knowledge.schemas import (
    KnowledgeExportDocument,
    KnowledgeExportFavorite,
    KnowledgeExportImportRun,
    KnowledgeExportMapping,
    KnowledgeImportIssue,
    KnowledgeImportItem,
    KnowledgeImportRequest,
    KnowledgeImportResult,
    KnowledgeImportValidation,
    KnowledgeLibraryStateRead,
    KnowledgeLogicalExport,
)
from app.modules.users.audit import AuditAction
from app.modules.users.models import User
from app.modules.users.service import ensure_admin, ensure_owner, record_audit

MAX_IMPORT_ITEMS = 5000
KNOWLEDGE_DATA_ROOT_FIELDS = {"version", "prompts", "chapters", "importedAt"}
PARSED_ROOT_FIELDS = {"version", "documents", "importedAt"}
KNOWLEDGE_RECORD_FIELDS = {
    "id",
    "title",
    "category",
    "html",
    "text",
    "sourceId",
    "sourceRevision",
    "sourceHash",
    "edited",
    "deleted",
    "favorite",
    "updatedAt",
    "order",
}
PARSED_RECORD_FIELDS = KNOWLEDGE_RECORD_FIELDS | {"kind", "format"}
PARSED_FORMATS = {"docx", "html", "markdown"}


@dataclass
class _Candidate:
    source_key: str
    kind: KnowledgeKind
    title: str
    category: str | None
    html: str
    plain_text: str
    position: int
    archived: bool
    favorite: bool
    fingerprint: str
    classification: str = "new"
    target_id: str | None = None
    target_version: int | None = None
    expected_version: int | None = None
    conflict_code: str | None = None
    resolved: bool = False
    duplicate_of_source_key: str | None = None


@dataclass
class _Plan:
    report: KnowledgeImportValidation
    candidates: list[_Candidate]


def _request_checksum(payload: KnowledgeImportRequest, actor_id: str) -> str:
    canonical = json.dumps(
        {
            "source": payload.source,
            "source_format": payload.source_format.value,
            "mode": payload.mode.value,
            "actor_user_id": actor_id,
            "resolutions": {
                key: resolution.model_dump(mode="json")
                for key, resolution in sorted(payload.resolutions.items())
            },
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _plan_checksum(
    request_checksum: str,
    state: KnowledgeLibraryState,
    candidates: list[_Candidate],
    issues: list[KnowledgeImportIssue],
) -> str:
    canonical = json.dumps(
        {
            "request_checksum": request_checksum,
            "library": {"status": state.status.value, "version": state.version},
            "items": [
                {
                    "source_key": candidate.source_key,
                    "fingerprint": candidate.fingerprint,
                    "classification": candidate.classification,
                    "target_id": candidate.target_id,
                    "target_version": candidate.target_version,
                    "conflict_code": candidate.conflict_code,
                    "resolved": candidate.resolved,
                    "duplicate_of_source_key": candidate.duplicate_of_source_key,
                }
                for candidate in candidates
            ],
            "issues": [issue.model_dump(mode="json") for issue in issues],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _fingerprint(
    *,
    kind: KnowledgeKind,
    title: str,
    category: str | None,
    html: str,
    position: int,
    archived: bool,
) -> str:
    canonical = json.dumps(
        {
            "kind": kind.value,
            "title": title,
            "category": category,
            "html": html,
            "position": position,
            "archived": archived,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _document_fingerprint(document: KnowledgeDocument) -> str:
    return _fingerprint(
        kind=document.kind,
        title=document.title,
        category=document.category,
        html=document.html,
        position=document.position,
        archived=document.archived_at is not None,
    )


def _authorize(actor: User, mode: KnowledgeImportMode, status: KnowledgeLibraryStatus) -> None:
    ensure_admin(actor)
    if mode is KnowledgeImportMode.INITIAL:
        ensure_owner(actor)
        if status is not KnowledgeLibraryStatus.PENDING:
            raise ApiError(409, "knowledge_library_active", "Knowledge library is already active")
    elif status is not KnowledgeLibraryStatus.ACTIVE:
        raise ApiError(409, "knowledge_library_pending", "Knowledge library is not active")


def _issue(
    issues: list[KnowledgeImportIssue],
    code: str,
    source_key: str | None = None,
    fields: list[str] | None = None,
) -> None:
    issues.append(
        KnowledgeImportIssue(code=code, source_key=source_key, fields=sorted(fields or []))
    )


def _source_rows(
    payload: KnowledgeImportRequest, issues: list[KnowledgeImportIssue]
) -> tuple[int | None, list[tuple[KnowledgeKind | None, dict[str, Any]]]]:
    source = payload.source
    version = source.get("version")
    if version != 1 or isinstance(version, bool):
        _issue(issues, "unsupported_version")
        version = None
    rows: list[tuple[KnowledgeKind | None, dict[str, Any]]] = []
    if payload.source_format is KnowledgeSourceFormat.KNOWLEDGE_DATA_V1:
        unsupported = set(source) - KNOWLEDGE_DATA_ROOT_FIELDS
        if unsupported:
            _issue(issues, "unsupported_field", fields=list(unsupported))
        for field, kind in (("prompts", KnowledgeKind.PROMPT), ("chapters", KnowledgeKind.CHAPTER)):
            collection = source.get(field)
            if not isinstance(collection, list) or len(collection) > MAX_IMPORT_ITEMS:
                _issue(issues, "invalid_collection", field)
                continue
            rows.extend((kind, row) for row in collection if isinstance(row, dict))
            if any(not isinstance(row, dict) for row in collection):
                _issue(issues, "invalid_record", field)
    else:
        unsupported = set(source) - PARSED_ROOT_FIELDS
        if unsupported:
            _issue(issues, "unsupported_field", fields=list(unsupported))
        collection = source.get("documents")
        if not isinstance(collection, list) or len(collection) > MAX_IMPORT_ITEMS:
            _issue(issues, "invalid_collection", "documents")
            return version, rows
        for row in collection:
            if not isinstance(row, dict):
                _issue(issues, "invalid_record", "documents")
                continue
            try:
                kind = KnowledgeKind(row.get("kind"))
            except ValueError:
                kind = None
            if row.get("format") not in PARSED_FORMATS:
                _issue(issues, "unsupported_document_format", str(row.get("id") or ""))
            rows.append((kind, row))
    return version, rows


def _candidate(
    payload: KnowledgeImportRequest,
    kind: KnowledgeKind | None,
    raw: dict[str, Any],
    issues: list[KnowledgeImportIssue],
) -> _Candidate | None:
    legacy_id = raw.get("id")
    source_id = raw.get("sourceId")
    source_key = None
    if kind is not None and isinstance(legacy_id, str) and isinstance(source_id, str):
        identity = hashlib.sha256(f"{source_id}\0{legacy_id}".encode()).hexdigest()
        source_key = f"{kind.value}:{identity}"
    if not source_key or len(source_key) > 768:
        _issue(issues, "invalid_source_identity")
        return None
    allowed = (
        KNOWLEDGE_RECORD_FIELDS
        if payload.source_format is KnowledgeSourceFormat.KNOWLEDGE_DATA_V1
        else PARSED_RECORD_FIELDS
    )
    unsupported = set(raw) - allowed
    if unsupported:
        _issue(issues, "unsupported_field", source_key, list(unsupported))
        return None
    title = raw.get("title")
    html = raw.get("html")
    category = raw.get("category")
    position = raw.get("order", 0)
    if kind is None:
        _issue(issues, "invalid_kind", source_key)
        return None
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 255:
        _issue(issues, "invalid_title", source_key)
        return None
    if category is not None and (
        not isinstance(category, str) or not category.strip() or len(category.strip()) > 100
    ):
        _issue(issues, "invalid_category", source_key)
        return None
    if not isinstance(html, str) or not html or len(html) > 500_000:
        _issue(issues, "invalid_content", source_key)
        return None
    if (
        not isinstance(position, int)
        or isinstance(position, bool)
        or not 0 <= position <= 1_000_000
    ):
        _issue(issues, "invalid_position", source_key)
        return None
    try:
        sanitized_html, plain_text = sanitize_knowledge_html(html)
    except ApiError:
        _issue(issues, "invalid_content", source_key)
        return None
    archived = raw.get("deleted", False)
    favorite = raw.get("favorite", False)
    if not isinstance(archived, bool) or not isinstance(favorite, bool):
        _issue(issues, "invalid_flag", source_key)
        return None
    normalized_category = category.strip() if isinstance(category, str) else None
    normalized_title = title.strip()
    return _Candidate(
        source_key=source_key,
        kind=kind,
        title=normalized_title,
        category=normalized_category,
        html=sanitized_html,
        plain_text=plain_text,
        position=position,
        archived=archived,
        favorite=favorite,
        fingerprint=_fingerprint(
            kind=kind,
            title=normalized_title,
            category=normalized_category,
            html=sanitized_html,
            position=position,
            archived=archived,
        ),
    )


def _build_plan(database: Session, actor: User, payload: KnowledgeImportRequest) -> _Plan:
    state = get_library_state(database)
    _authorize(actor, payload.mode, state.status)
    issues: list[KnowledgeImportIssue] = []
    version, rows = _source_rows(payload, issues)
    candidates: list[_Candidate] = []
    seen: set[str] = set()
    for kind, raw in rows:
        candidate = _candidate(payload, kind, raw, issues)
        if candidate is None:
            continue
        if candidate.source_key in seen:
            _issue(issues, "duplicate_source_key", candidate.source_key)
            continue
        seen.add(candidate.source_key)
        candidates.append(candidate)

    documents = list(database.scalars(select(KnowledgeDocument)))
    documents_by_id = {document.id: document for document in documents}
    documents_by_title: dict[tuple[KnowledgeKind, str], list[KnowledgeDocument]] = {}
    for document in documents:
        documents_by_title.setdefault((document.kind, document.title), []).append(document)
    mappings_by_key: dict[str, KnowledgeImportMapping] = {}
    if seen:
        mappings = list(
            database.scalars(
                select(KnowledgeImportMapping)
                .where(KnowledgeImportMapping.source_key.in_(seen))
                .order_by(
                    KnowledgeImportMapping.created_at.desc(),
                    KnowledgeImportMapping.id.desc(),
                )
            )
        )
        for mapping in mappings:
            mappings_by_key.setdefault(mapping.source_key, mapping)

    items: list[KnowledgeImportItem] = []
    counts = {
        "new_documents": 0,
        "archived_records": 0,
        "exact_duplicates": 0,
        "conflicts": 0,
        "resolved_conflicts": 0,
        "overwritten_documents": 0,
        "skipped_conflicts": 0,
        "unsupported_records": len(issues),
    }
    used_resolutions: set[str] = set()
    source_by_title: dict[tuple[KnowledgeKind, str], _Candidate] = {}
    for candidate in candidates:
        mapping = mappings_by_key.get(candidate.source_key)
        target: KnowledgeDocument | None = None
        conflict_code: str | None = None
        prior_source = source_by_title.get((candidate.kind, candidate.title))
        if prior_source is not None and mapping is None:
            if prior_source.fingerprint == candidate.fingerprint:
                candidate.classification = "exact_duplicate"
                candidate.duplicate_of_source_key = prior_source.source_key
            else:
                conflict_code = "duplicate_source_title"
        elif mapping is not None:
            target = documents_by_id.get(mapping.target_id)
            if target is None:
                conflict_code = "missing_mapped_document"
            elif _document_fingerprint(target) == candidate.fingerprint:
                candidate.classification = "exact_duplicate"
            else:
                conflict_code = "mapped_document_changed"
        else:
            title_matches = documents_by_title.get((candidate.kind, candidate.title), [])
            exact = [
                document
                for document in title_matches
                if _document_fingerprint(document) == candidate.fingerprint
            ]
            if len(exact) == 1 and len(title_matches) == 1:
                target = exact[0]
                candidate.classification = "exact_duplicate"
            elif title_matches:
                target = title_matches[0] if len(title_matches) == 1 else None
                conflict_code = (
                    "same_title_changed" if len(title_matches) == 1 else "ambiguous_title_match"
                )
            else:
                candidate.classification = "archived" if candidate.archived else "new"
        source_by_title.setdefault((candidate.kind, candidate.title), candidate)

        if conflict_code is not None:
            counts["conflicts"] += 1
            candidate.classification = "conflict"
            candidate.conflict_code = conflict_code
            resolution = payload.resolutions.get(candidate.source_key)
            if resolution is None:
                _issue(issues, conflict_code, candidate.source_key)
            else:
                used_resolutions.add(candidate.source_key)
                if resolution.action == "skip":
                    candidate.classification = "skipped"
                    candidate.resolved = True
                    counts["skipped_conflicts"] += 1
                elif resolution.action == "create_copy":
                    candidate.classification = "archived" if candidate.archived else "new"
                    candidate.resolved = True
                    target = None
                elif target is None or target.version != resolution.expected_version:
                    _issue(issues, "version_conflict", candidate.source_key)
                else:
                    candidate.classification = "overwrite"
                    candidate.expected_version = resolution.expected_version
                    candidate.resolved = True
                    counts["overwritten_documents"] += 1
                if candidate.resolved:
                    counts["resolved_conflicts"] += 1
        candidate.target_id = target.id if target is not None else None
        candidate.target_version = target.version if target is not None else None
        if candidate.classification == "exact_duplicate":
            counts["exact_duplicates"] += 1
        elif candidate.classification == "new":
            counts["new_documents"] += 1
        elif candidate.classification == "archived":
            counts["archived_records"] += 1
        items.append(
            KnowledgeImportItem(
                source_key=candidate.source_key,
                classification=candidate.classification,
                target_id=candidate.target_id,
                conflict_code=candidate.conflict_code,
                resolved=candidate.resolved,
            )
        )
    for source_key in set(payload.resolutions) - used_resolutions:
        _issue(issues, "resolution_without_conflict", source_key)
    counts["unsupported_records"] = sum(
        issue.code
        in {
            "unsupported_field",
            "unsupported_version",
            "unsupported_document_format",
            "invalid_collection",
            "invalid_record",
            "invalid_source_identity",
            "invalid_kind",
            "invalid_title",
            "invalid_category",
            "invalid_content",
            "invalid_position",
            "invalid_flag",
            "duplicate_source_key",
        }
        for issue in issues
    )
    report = KnowledgeImportValidation(
        valid=not issues,
        checksum=_plan_checksum(_request_checksum(payload, actor.id), state, candidates, issues),
        source_version=version,
        source_format=payload.source_format,
        mode=payload.mode,
        library_status=state.status,
        counts=counts,
        items=items,
        issues=issues,
    )
    return _Plan(report=report, candidates=candidates)


def validate_import(
    database: Session, actor: User, payload: KnowledgeImportRequest
) -> KnowledgeImportValidation:
    return _build_plan(database, actor, payload).report


def _mapping_result(database: Session, run_id: str) -> dict[str, str]:
    return {
        mapping.source_key: mapping.target_id
        for mapping in database.scalars(
            select(KnowledgeImportMapping).where(KnowledgeImportMapping.import_run_id == run_id)
        )
    }


def _search_text(title: str, plain_text: str) -> str:
    return f"{title} {plain_text}".casefold()


def import_knowledge(
    database: Session,
    actor: User,
    payload: KnowledgeImportRequest,
    now: datetime,
) -> KnowledgeImportResult:
    request_checksum = _request_checksum(payload, actor.id)
    ensure_admin(actor)
    if payload.mode is KnowledgeImportMode.INITIAL:
        ensure_owner(actor)
    # Serialize confirmed imports around the singleton state row. This makes a
    # validation preview stale as soon as another import changes mappings or documents.
    get_library_state(database, for_update=True)
    previous = database.scalar(
        select(KnowledgeImportRun).where(KnowledgeImportRun.request_checksum == request_checksum)
    )
    if previous is not None:
        if not payload.confirm or payload.confirmation_checksum != previous.checksum:
            raise ApiError(
                409, "validation_changed", "Import confirmation does not match the source"
            )
        state = get_library_state(database)
        return KnowledgeImportResult(
            import_run_id=previous.id,
            checksum=previous.checksum,
            counts=previous.counts,
            mappings=_mapping_result(database, previous.id),
            library_status=state.status,
            idempotent_replay=True,
        )
    plan = _build_plan(database, actor, payload)
    if not payload.confirm or payload.confirmation_checksum != plan.report.checksum:
        raise ApiError(409, "validation_changed", "Import confirmation does not match the source")
    if not plan.report.valid:
        raise ApiError(409, "import_conflict", "Knowledge import has unresolved conflicts")

    run = KnowledgeImportRun(
        checksum=plan.report.checksum,
        request_checksum=request_checksum,
        source_version=plan.report.source_version or 0,
        source_format=payload.source_format,
        mode=payload.mode,
        actor_user_id=actor.id,
        counts=plan.report.counts,
        created_at=now,
    )
    database.add(run)
    database.flush()
    mappings: dict[str, str] = {}
    documents_by_source: dict[str, KnowledgeDocument] = {}
    for candidate in plan.candidates:
        if candidate.classification == "skipped":
            continue
        document: KnowledgeDocument | None = None
        if candidate.classification in {"new", "archived"}:
            document = KnowledgeDocument(
                kind=candidate.kind,
                title=candidate.title,
                category=candidate.category,
                html=candidate.html,
                plain_text=candidate.plain_text,
                search_text=_search_text(candidate.title, candidate.plain_text),
                position=candidate.position,
                created_by_user_id=actor.id,
                updated_by_user_id=actor.id,
                archived_at=now if candidate.archived else None,
                created_at=now,
                updated_at=now,
            )
            database.add(document)
            database.flush()
        elif candidate.classification == "overwrite":
            result = database.execute(
                update(KnowledgeDocument)
                .where(
                    KnowledgeDocument.id == candidate.target_id,
                    KnowledgeDocument.version == candidate.expected_version,
                )
                .values(
                    title=candidate.title,
                    category=candidate.category,
                    html=candidate.html,
                    plain_text=candidate.plain_text,
                    search_text=_search_text(candidate.title, candidate.plain_text),
                    position=candidate.position,
                    archived_at=now if candidate.archived else None,
                    updated_by_user_id=actor.id,
                    updated_at=now,
                    version=KnowledgeDocument.version + 1,
                )
            )
            if result.rowcount != 1:
                raise ApiError(409, "version_conflict", "Knowledge document changed")
            database.expire_all()
            document = database.get(KnowledgeDocument, candidate.target_id)
        elif candidate.duplicate_of_source_key is not None:
            document = documents_by_source.get(candidate.duplicate_of_source_key)
        else:
            document = database.get(KnowledgeDocument, candidate.target_id)
        if document is None:
            raise ApiError(409, "import_conflict", "Knowledge import target is unavailable")
        database.add(
            KnowledgeImportMapping(
                import_run_id=run.id,
                source_key=candidate.source_key,
                source_fingerprint=candidate.fingerprint,
                target_id=document.id,
                created_at=now,
            )
        )
        mappings[candidate.source_key] = document.id
        documents_by_source[candidate.source_key] = document
        if candidate.favorite and database.get(KnowledgeFavorite, (actor.id, document.id)) is None:
            database.add(KnowledgeFavorite(user_id=actor.id, document_id=document.id))

    if payload.mode is KnowledgeImportMode.INITIAL:
        result = database.execute(
            update(KnowledgeLibraryState)
            .where(
                KnowledgeLibraryState.id == 1,
                KnowledgeLibraryState.status == KnowledgeLibraryStatus.PENDING,
            )
            .values(
                status=KnowledgeLibraryStatus.ACTIVE,
                activated_at=now,
                activated_by_user_id=actor.id,
                version=KnowledgeLibraryState.version + 1,
                updated_at=now,
            )
        )
        if result.rowcount != 1:
            raise ApiError(409, "knowledge_library_active", "Knowledge library is already active")
        record_audit(
            database,
            actor=actor,
            action=AuditAction.KNOWLEDGE_LIBRARY_ACTIVATED,
            details={"import_run_id": run.id, "checksum": run.checksum},
        )
    record_audit(
        database,
        actor=actor,
        action=AuditAction.KNOWLEDGE_IMPORTED,
        details={"import_run_id": run.id, "checksum": run.checksum, "counts": run.counts},
    )
    return KnowledgeImportResult(
        import_run_id=run.id,
        checksum=run.checksum,
        counts=run.counts,
        mappings=mappings,
        library_status=KnowledgeLibraryStatus.ACTIVE,
        idempotent_replay=False,
    )


def logical_export(database: Session, actor: User, now: datetime) -> KnowledgeLogicalExport:
    ensure_owner(actor)
    state = get_library_state(database)
    documents = list(database.scalars(select(KnowledgeDocument).order_by(KnowledgeDocument.id)))
    favorites = list(
        database.scalars(
            select(KnowledgeFavorite).order_by(
                KnowledgeFavorite.user_id, KnowledgeFavorite.document_id
            )
        )
    )
    import_runs = list(
        database.scalars(select(KnowledgeImportRun).order_by(KnowledgeImportRun.created_at))
    )
    mappings = list(
        database.scalars(
            select(KnowledgeImportMapping).order_by(
                KnowledgeImportMapping.import_run_id,
                KnowledgeImportMapping.source_key,
            )
        )
    )
    return KnowledgeLogicalExport(
        exported_at=now,
        library=KnowledgeLibraryStateRead(
            status=state.status,
            version=state.version,
            activated_at=state.activated_at,
        ),
        documents=[KnowledgeExportDocument.model_validate(document) for document in documents],
        favorites=[
            KnowledgeExportFavorite(user_id=favorite.user_id, document_id=favorite.document_id)
            for favorite in favorites
        ],
        import_runs=[KnowledgeExportImportRun.model_validate(run) for run in import_runs],
        mappings=[KnowledgeExportMapping.model_validate(mapping) for mapping in mappings],
    )
