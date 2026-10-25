from __future__ import annotations

from datetime import datetime

from fastapi import status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.modules.auth.authorization import (
    can_update_student,
    deactivate_user,
    is_active_admin,
    is_owner,
    reassign_group,
    reassign_groups_and_deactivate,
    transfer_ownership,
)
from app.modules.auth.models import AuthSession
from app.modules.auth.passwords import PasswordManager, generate_temporary_password
from app.modules.groups.models import Group
from app.modules.students.models import Student
from app.modules.users.audit import AuditAction, AuditEvent
from app.modules.users.models import User, UserRole


def _forbidden() -> ApiError:
    return ApiError(status.HTTP_403_FORBIDDEN, "forbidden", "Operation not permitted")


def _not_found(resource: str) -> ApiError:
    return ApiError(status.HTTP_404_NOT_FOUND, "not_found", f"{resource} not found")


def _conflict(code: str, message: str) -> ApiError:
    return ApiError(status.HTTP_409_CONFLICT, code, message)


def ensure_business_actor(actor: User) -> None:
    if not actor.is_active:
        raise _forbidden()
    if actor.must_change_password:
        raise ApiError(
            status.HTTP_403_FORBIDDEN,
            "password_change_required",
            "Password change required",
        )


def ensure_owner(actor: User) -> None:
    ensure_business_actor(actor)
    if not is_owner(actor):
        raise _forbidden()


def ensure_admin(actor: User) -> None:
    ensure_business_actor(actor)
    if not is_active_admin(actor):
        raise _forbidden()


def record_audit(
    database: Session,
    *,
    actor: User,
    action: AuditAction,
    target_user_id: str | None = None,
    target_group_id: str | None = None,
    details: dict[str, object] | None = None,
) -> None:
    database.add(
        AuditEvent(
            actor_user_id=actor.id,
            target_user_id=target_user_id,
            target_group_id=target_group_id,
            action=action,
            details=details or {},
        )
    )


def create_curator(
    database: Session,
    manager: PasswordManager,
    actor: User,
    login: str,
) -> tuple[User, str]:
    ensure_owner(actor)
    temporary_password = generate_temporary_password()
    user = User(
        login=login,
        role=UserRole.ADMIN,
        password_hash=manager.hash(temporary_password),
        is_owner=False,
        is_active=True,
        must_change_password=True,
    )
    database.add(user)
    database.flush()
    record_audit(
        database,
        actor=actor,
        action=AuditAction.CURATOR_CREATED,
        target_user_id=user.id,
    )
    return user, temporary_password


def list_curators(database: Session, actor: User) -> list[User]:
    ensure_admin(actor)
    return list(
        database.scalars(
            select(User).where(User.role == UserRole.ADMIN).order_by(User.created_at, User.id)
        )
    )


def get_curator(database: Session, actor: User, user_id: str) -> User:
    ensure_owner(actor)
    user = database.get(User, user_id)
    if user is None or user.role is not UserRole.ADMIN:
        raise _not_found("Curator")
    return user


def _managed_student(database: Session, actor: User, student_id: str) -> Student:
    ensure_admin(actor)
    student = database.get(Student, student_id)
    if student is None or not can_update_student(actor, student):
        raise _not_found("Student")
    return student


def create_student_account(
    database: Session,
    manager: PasswordManager,
    actor: User,
    student_id: str,
    login: str,
) -> tuple[Student, User, str]:
    student = _managed_student(database, actor, student_id)
    if student.user_id is not None:
        raise _conflict("student_account_exists", "Student already has an account")
    temporary_password = generate_temporary_password()
    user = User(
        login=login,
        role=UserRole.STUDENT,
        password_hash=manager.hash(temporary_password),
        is_owner=False,
        is_active=True,
        must_change_password=True,
    )
    database.add(user)
    database.flush()
    result = database.execute(
        update(Student)
        .where(Student.id == student.id, Student.user_id.is_(None))
        .values(
            user_id=user.id,
            user_role=UserRole.STUDENT,
            version=Student.version + 1,
            updated_at=func.now(),
        )
    )
    if result.rowcount != 1:
        raise _conflict("student_account_exists", "Student already has an account")
    database.flush()
    database.refresh(student)
    record_audit(
        database,
        actor=actor,
        action=AuditAction.STUDENT_ACCOUNT_CREATED,
        target_user_id=user.id,
        details={"student_id": student.id},
    )
    return student, user, temporary_password


def get_student_account(database: Session, actor: User, student_id: str) -> tuple[Student, User]:
    student = _managed_student(database, actor, student_id)
    if student.user_id is None:
        raise _not_found("Student account")
    user = database.get(User, student.user_id)
    if user is None:
        raise _not_found("Student account")
    return student, user


def deactivate_student_account(
    database: Session,
    actor: User,
    student_id: str,
    now: datetime,
) -> User:
    student, user = get_student_account(database, actor, student_id)
    if not user.is_active:
        raise _conflict("user_inactive", "User is already inactive")
    user.is_active = False
    user.deactivated_at = now
    database.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    record_audit(
        database,
        actor=actor,
        action=AuditAction.USER_DEACTIVATED,
        target_user_id=user.id,
        details={"student_id": student.id},
    )
    return user


def _resettable_user(database: Session, actor: User, user_id: str) -> User:
    ensure_admin(actor)
    target = database.get(User, user_id)
    if target is None:
        raise _not_found("User")
    if is_owner(actor):
        return target
    if target.role is not UserRole.STUDENT:
        raise _not_found("User")
    student = database.scalar(select(Student).where(Student.user_id == target.id))
    if student is None or not can_update_student(actor, student):
        raise _not_found("User")
    return target


def reset_password(
    database: Session,
    manager: PasswordManager,
    actor: User,
    user_id: str,
    now: datetime,
) -> tuple[User, str]:
    target = _resettable_user(database, actor, user_id)
    if not target.is_active:
        raise _conflict("user_inactive", "Cannot reset an inactive account")
    temporary_password = generate_temporary_password()
    target.password_hash = manager.hash(temporary_password)
    target.must_change_password = True
    database.execute(
        update(AuthSession)
        .where(AuthSession.user_id == target.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    record_audit(
        database,
        actor=actor,
        action=AuditAction.PASSWORD_RESET,
        target_user_id=target.id,
    )
    return target, temporary_password


def deactivate_curator(
    database: Session,
    actor: User,
    user_id: str,
    now: datetime,
) -> User:
    target = get_curator(database, actor, user_id)
    if not target.is_active:
        raise _conflict("user_inactive", "User is already inactive")
    deactivate_user(actor, target, database, now=now)
    record_audit(
        database,
        actor=actor,
        action=AuditAction.USER_DEACTIVATED,
        target_user_id=target.id,
    )
    return target


def assign_group(
    database: Session,
    actor: User,
    group_id: str,
    curator_id: str,
) -> Group:
    ensure_owner(actor)
    group = database.get(Group, group_id)
    if group is None:
        raise _not_found("Group")
    curator = database.get(User, curator_id)
    if curator is None:
        raise _not_found("Curator")
    previous_curator_id = group.curator_id
    reassign_group(actor, group, curator, database)
    record_audit(
        database,
        actor=actor,
        action=AuditAction.CURATOR_REASSIGNED,
        target_user_id=curator.id,
        target_group_id=group.id,
        details={"previous_curator_id": previous_curator_id},
    )
    return group


def offboard_curator(
    database: Session,
    actor: User,
    user_id: str,
    successor_id: str,
    now: datetime,
) -> tuple[User, list[str]]:
    target = get_curator(database, actor, user_id)
    successor = database.get(User, successor_id)
    if successor is None:
        raise _not_found("Curator")
    if target.id == successor.id:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_curator",
            "Successor must be a different active admin",
        )
    groups = list(database.scalars(select(Group).where(Group.curator_id == target.id)))
    reassign_groups_and_deactivate(
        actor,
        target,
        [(group, successor) for group in groups],
        database,
        now=now,
    )
    for group in groups:
        record_audit(
            database,
            actor=actor,
            action=AuditAction.CURATOR_REASSIGNED,
            target_user_id=successor.id,
            target_group_id=group.id,
            details={"previous_curator_id": target.id},
        )
    record_audit(
        database,
        actor=actor,
        action=AuditAction.CURATOR_OFFBOARDED,
        target_user_id=target.id,
        details={"successor_curator_id": successor.id, "group_count": len(groups)},
    )
    return target, [group.id for group in groups]


def transfer_owner(database: Session, actor: User, successor_id: str) -> User:
    ensure_owner(actor)
    successor = database.get(User, successor_id)
    if successor is None or successor.role is not UserRole.ADMIN:
        raise _not_found("Curator")
    if successor.id == actor.id:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_owner",
            "Successor must be a different active admin",
        )
    previous_owner_id = actor.id
    transfer_ownership(actor, successor, database)
    record_audit(
        database,
        actor=actor,
        action=AuditAction.OWNER_TRANSFERRED,
        target_user_id=successor.id,
        details={"previous_owner_id": previous_owner_id},
    )
    return successor
