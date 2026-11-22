from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.modules.knowledge.models import KnowledgeLibraryState, KnowledgeLibraryStatus


def get_library_state(database: Session, *, for_update: bool = False) -> KnowledgeLibraryState:
    statement = select(KnowledgeLibraryState).where(KnowledgeLibraryState.id == 1)
    if for_update:
        statement = statement.with_for_update()
    state = database.scalar(statement)
    if state is None:
        return KnowledgeLibraryState(id=1, status=KnowledgeLibraryStatus.PENDING, version=1)
    return state


def require_library_active(database: Session, *, for_update: bool = False) -> KnowledgeLibraryState:
    state = get_library_state(database, for_update=for_update)
    if state.status is not KnowledgeLibraryStatus.ACTIVE:
        raise ApiError(409, "knowledge_library_pending", "Knowledge library is not active")
    return state
