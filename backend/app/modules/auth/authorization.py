from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Annotated

from fastapi import Depends, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.db.session import get_db
from app.modules.auth.dependencies import require_business_user, utc_now
from app.modules.auth.models import AuthSession
from app.modules.groups.models import Group
from app.modules.students.models import Student
from app.modules.users.models import User, UserRole


def is_active_admin(user: User) -> bool:
    return user.is_active and user.role is UserRole.ADMIN


def is_owner(user: User) -> bool:
    return is_active_admin(user) and user.is_owner


def can_create_group(actor: User) -> bool:
    return is_active_admin(actor)


def can_manage_accounts(actor: User) -> bool:
    return is_owner(actor)


def _active_owner_exists(database: Session, *, excluding_user_id: str | None = None) -> bool:
    statement = select(User.id).where(
        User.role == UserRole.ADMIN,
        User.is_owner.is_(True),
        User.is_active.is_(True),
    )
    if excluding_user_id is not None:
        statement = statement.where(User.id != excluding_user_id)
    return database.scalar(statement.limit(1)) is not None


def _ensure_another_active_owner(target: User, database: Session) -> None:
    if is_owner(target) and not _active_owner_exists(
        database,
        excluding_user_id=target.id,
    ):
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "last_owner_required",
            "At least one active owner must remain",
        )


def require_admin(
    actor: Annotated[User, Depends(require_business_user)],
) -> User:
    if not is_active_admin(actor):
        raise _forbidden()
    return actor


def require_owner(
    actor: Annotated[User, Depends(require_business_user)],
) -> User:
    if not is_owner(actor):
        raise _forbidden()
    return actor


def curator_for_new_group(actor: User) -> User:
    if not can_create_group(actor):
        raise _forbidden()
    return actor


def bootstrap_first_owner(target: User, database: Session) -> None:
    if _active_owner_exists(database):
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "owner_already_exists",
            "An active owner already exists",
        )
    if not is_active_admin(target):
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_owner",
            "Owner must be an active admin",
        )
    target.is_owner = True


def change_user_access(
    actor: User,
    target: User,
    database: Session,
    *,
    role: UserRole,
    is_owner: bool,
) -> None:
    if not can_manage_accounts(actor):
        raise _forbidden()
    remains_active_owner = target.is_active and role is UserRole.ADMIN and is_owner
    if is_owner and not remains_active_owner:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_owner",
            "Owner must be an active admin",
        )
    if not remains_active_owner:
        _ensure_another_active_owner(target, database)
    target.role = role
    target.is_owner = is_owner


def transfer_ownership(actor: User, successor: User, database: Session) -> None:
    if not is_owner(actor):
        raise _forbidden()
    if not is_active_admin(successor):
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_owner",
            "Owner must be an active admin",
        )
    if actor.id == successor.id:
        return
    with database.begin_nested():
        successor.is_owner = True
        database.flush()
        change_user_access(
            actor,
            actor,
            database,
            role=UserRole.ADMIN,
            is_owner=False,
        )
        database.flush()


def can_read_group(actor: User, group: Group, database: Session) -> bool:
    if not actor.is_active:
        return False
    if actor.role is UserRole.ADMIN:
        return True
    if actor.role is not UserRole.STUDENT:
        return False
    return (
        database.scalar(
            select(Student.id).where(
                Student.user_id == actor.id,
                Student.group_id == group.id,
            )
        )
        is not None
    )


def can_update_group(actor: User, group: Group) -> bool:
    return is_active_admin(actor) and (actor.is_owner or group.curator_id == actor.id)


def can_read_student(actor: User, student: Student) -> bool:
    if not actor.is_active:
        return False
    if actor.role is UserRole.ADMIN:
        return True
    return actor.role is UserRole.STUDENT and student.user_id == actor.id


def can_update_student(actor: User, student: Student) -> bool:
    return is_active_admin(actor) and (actor.is_owner or student.group.curator_id == actor.id)


def _not_found(resource: str) -> ApiError:
    return ApiError(status.HTTP_404_NOT_FOUND, "not_found", f"{resource} not found")


def _forbidden() -> ApiError:
    return ApiError(status.HTTP_403_FORBIDDEN, "forbidden", "Operation not permitted")


def require_group_read(
    group_id: str,
    actor: Annotated[User, Depends(require_business_user)],
    database: Annotated[Session, Depends(get_db)],
) -> Group:
    group = database.get(Group, group_id)
    if group is None or not can_read_group(actor, group, database):
        raise _not_found("Group")
    return group


def require_group_update(
    group_id: str,
    actor: Annotated[User, Depends(require_business_user)],
    database: Annotated[Session, Depends(get_db)],
) -> Group:
    group = database.get(Group, group_id)
    if group is None or not can_read_group(actor, group, database):
        raise _not_found("Group")
    if not can_update_group(actor, group):
        raise _forbidden()
    return group


def require_student_read(
    student_id: str,
    actor: Annotated[User, Depends(require_business_user)],
    database: Annotated[Session, Depends(get_db)],
) -> Student:
    student = database.get(Student, student_id)
    if student is None or not can_read_student(actor, student):
        raise _not_found("Student")
    return student


def require_student_update(
    student_id: str,
    actor: Annotated[User, Depends(require_business_user)],
    database: Annotated[Session, Depends(get_db)],
) -> Student:
    student = database.get(Student, student_id)
    if student is None or not can_read_student(actor, student):
        raise _not_found("Student")
    if not can_update_student(actor, student):
        raise _forbidden()
    return student


def _validate_group_reassignment(actor: User, new_curator: User) -> None:
    if not is_owner(actor):
        raise _forbidden()
    if not is_active_admin(new_curator):
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_curator",
            "Curator must be an active admin",
        )


def reassign_group(actor: User, group: Group, new_curator: User) -> None:
    _validate_group_reassignment(actor, new_curator)
    group.curator = new_curator
    group.curator_id = new_curator.id
    group.curator_role = UserRole.ADMIN


def deactivate_user(
    actor: User,
    target: User,
    database: Session,
    *,
    now: datetime | None = None,
) -> None:
    if not can_manage_accounts(actor):
        raise _forbidden()
    _ensure_another_active_owner(target, database)
    assigned_group_id = database.scalar(
        select(Group.id).where(Group.curator_id == target.id).limit(1)
    )
    if assigned_group_id is not None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "curator_has_groups",
            "Reassign the curator's groups before deactivation",
        )
    deactivated_at = now or utc_now()
    target.is_active = False
    target.deactivated_at = deactivated_at
    database.execute(
        update(AuthSession)
        .where(AuthSession.user_id == target.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=deactivated_at)
    )


def reassign_groups_and_deactivate(
    actor: User,
    target: User,
    reassignments: Sequence[tuple[Group, User]],
    database: Session,
    *,
    now: datetime | None = None,
) -> None:
    with database.begin_nested():
        for group, new_curator in reassignments:
            if group.curator_id != target.id:
                raise ApiError(
                    status.HTTP_409_CONFLICT,
                    "curator_assignment_changed",
                    "Group is no longer assigned to the expected curator",
                )
            _validate_group_reassignment(actor, new_curator)
            result = database.execute(
                update(Group)
                .where(Group.id == group.id, Group.curator_id == target.id)
                .values(curator_id=new_curator.id, curator_role=UserRole.ADMIN)
                .execution_options(synchronize_session=False)
            )
            if result.rowcount != 1:
                raise ApiError(
                    status.HTTP_409_CONFLICT,
                    "curator_assignment_changed",
                    "Group is no longer assigned to the expected curator",
                )
            database.refresh(group)
        database.flush()
        deactivate_user(actor, target, database, now=now)
        database.flush()
