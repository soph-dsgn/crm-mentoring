from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.cli.import_knowledge import import_knowledge_file
from app.modules.knowledge.library import get_library_state
from app.modules.knowledge.models import KnowledgeDocument, KnowledgeLibraryStatus
from app.modules.users.models import User, UserRole
from tests.test_bootstrap_owner import migrated_engine
from tests.test_knowledge_import_api import knowledge_data


def add_owner(engine) -> None:
    with Session(engine) as database:
        database.add(
            User(
                login="owner.cli",
                role=UserRole.ADMIN,
                password_hash="x",
                is_owner=True,
                must_change_password=False,
            )
        )
        database.commit()


def write_source(tmp_path: Path, extra: dict | None = None) -> Path:
    source = {**knowledge_data(), "source": "notion export", **(extra or {})}
    path = tmp_path / "knowledge-seed.json"
    path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
    return path


def test_cli_loads_prompts_into_database_once(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    try:
        add_owner(engine)
        path = write_source(tmp_path)

        first = import_knowledge_file(engine, path, "owner.cli")
        again = import_knowledge_file(engine, path, "owner.cli")

        assert first.counts["new_documents"] == 1
        assert again.counts["new_documents"] == 0
        with Session(engine) as database:
            assert database.scalar(select(func.count(KnowledgeDocument.id))) == 1
            assert get_library_state(database).status is KnowledgeLibraryStatus.ACTIVE
    finally:
        engine.dispose()


def test_cli_rejects_unknown_owner_and_invalid_file(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    try:
        add_owner(engine)
        with pytest.raises(RuntimeError, match="No active owner"):
            import_knowledge_file(engine, write_source(tmp_path), "missing")
        broken = tmp_path / "broken.json"
        broken.write_text("[]", encoding="utf-8")
        with pytest.raises(RuntimeError, match="KnowledgeData"):
            import_knowledge_file(engine, broken, "owner.cli")
        with Session(engine) as database:
            assert database.scalar(select(func.count(KnowledgeDocument.id))) == 0
    finally:
        engine.dispose()
