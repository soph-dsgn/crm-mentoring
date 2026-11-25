"""Load a KnowledgeData v1 file (prompts) into the CRM database during migration.

Prompts are shared by every curator and student, so the operator loads them once on the
server instead of each owner moving a browser copy. The command is idempotent: repeating it
with the same file reports the previous run.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.core.config import get_settings
from app.db import models as domain_models  # noqa: F401  (registers all mappers)
from app.db.session import build_engine
from app.modules.knowledge.import_service import (
    KNOWLEDGE_DATA_ROOT_FIELDS,
    import_knowledge,
    validate_import,
)
from app.modules.knowledge.library import get_library_state
from app.modules.knowledge.models import (
    KnowledgeImportMode,
    KnowledgeLibraryStatus,
    KnowledgeSourceFormat,
)
from app.modules.knowledge.schemas import KnowledgeImportRequest, KnowledgeImportResult
from app.modules.users.models import User


def _read_source(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Cannot read KnowledgeData file: {error}") from error
    if not isinstance(raw, dict) or not isinstance(raw.get("prompts"), list):
        raise RuntimeError("File is not a KnowledgeData v1 export with prompts")
    # Exports may carry descriptive fields such as "source"; only the data fields are imported.
    return {key: value for key, value in raw.items() if key in KNOWLEDGE_DATA_ROOT_FIELDS}


def import_knowledge_file(engine: Engine, path: Path, owner_login: str) -> KnowledgeImportResult:
    source = _read_source(path)
    with Session(engine, expire_on_commit=False) as database:
        owner = database.scalar(
            select(User).where(
                User.normalized_login == owner_login.strip().casefold(),
                User.is_owner.is_(True),
                User.is_active.is_(True),
            )
        )
        if owner is None:
            raise RuntimeError("No active owner matches the confirmed login")
        pending = get_library_state(database).status is KnowledgeLibraryStatus.PENDING
        request = KnowledgeImportRequest(
            source=source,
            source_format=KnowledgeSourceFormat.KNOWLEDGE_DATA_V1,
            mode=KnowledgeImportMode.INITIAL if pending else KnowledgeImportMode.ADDITIONAL,
        )
        try:
            report = validate_import(database, owner, request)
            database.rollback()
            if not report.valid:
                codes = sorted({issue.code for issue in report.issues}) or ["conflict"]
                raise RuntimeError(f"KnowledgeData file needs review: {', '.join(codes)}")
            confirmed = request.model_copy(
                update={"confirm": True, "confirmation_checksum": report.checksum}
            )
            result = import_knowledge(database, owner, confirmed, datetime.now(UTC))
            database.commit()
        except ApiError as error:
            database.rollback()
            raise RuntimeError(f"KnowledgeData import failed: {error.code}") from error
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Load shared prompts into the CRM database")
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--owner-login", required=True)
    parser.add_argument("--confirm-database", required=True)
    args = parser.parse_args()
    settings = get_settings()
    database_name = make_url(settings.database_url).database
    if not database_name or args.confirm_database != database_name:
        parser.error("--confirm-database must match the configured database name")
    engine = build_engine(settings.database_url, pool_size=1, max_overflow=0)
    try:
        result = import_knowledge_file(engine, args.file, args.owner_login)
    except RuntimeError as error:
        parser.error(str(error))
    finally:
        engine.dispose()
    if result.idempotent_replay:
        print("This file was already imported; nothing changed.")
    for key, value in sorted(result.counts.items()):
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
