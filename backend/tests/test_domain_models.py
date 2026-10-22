from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from app.modules.groups.models import Group, GroupStatus
from app.modules.students.models import Student
from app.modules.users.models import User, UserRole


def user(login: str, role: UserRole, *, is_owner: bool = False) -> User:
    return User(
        login=login,
        role=role,
        password_hash="synthetic-password-hash",
        is_owner=is_owner,
    )


def group(name: str, curator: User) -> Group:
    return Group(
        name=name,
        starts_at=date(2026, 10, 1),
        status=GroupStatus.ACTIVE,
        curator=curator,
    )


def test_create_user_with_supported_roles(session: Session) -> None:
    admin = user("curator", UserRole.ADMIN, is_owner=True)
    student_account = user("student-one", UserRole.STUDENT)

    session.add_all([admin, student_account])
    session.commit()

    assert admin.role is UserRole.ADMIN
    assert admin.is_owner is True
    assert student_account.role is UserRole.STUDENT


def test_reject_unsupported_user_role(session: Session) -> None:
    invalid_user = user("mentor", UserRole.ADMIN)
    invalid_user.role = "mentor"  # type: ignore[assignment]
    session.add(invalid_user)

    with pytest.raises((StatementError, IntegrityError)):
        session.commit()


def test_owner_must_have_admin_role(session: Session) -> None:
    session.add(user("student-owner", UserRole.STUDENT, is_owner=True))

    with pytest.raises(IntegrityError):
        session.commit()


def test_login_is_unique(session: Session) -> None:
    session.add_all(
        [
            user("same-login", UserRole.ADMIN),
            user("same-login", UserRole.STUDENT),
        ]
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_group_requires_admin_curator(session: Session) -> None:
    curator = user("group-curator", UserRole.ADMIN)
    cohort = group("October cohort", curator)
    session.add(cohort)
    session.commit()

    assert cohort.curator is curator
    assert curator.curated_groups == [cohort]


def test_one_curator_can_manage_multiple_groups(session: Session) -> None:
    curator = user("multi-curator", UserRole.ADMIN)
    first = group("First cohort", curator)
    second = group("Second cohort", curator)
    session.add_all([first, second])
    session.commit()

    assert {item.id for item in curator.curated_groups} == {first.id, second.id}


def test_group_can_contain_multiple_students(session: Session) -> None:
    curator = user("students-curator", UserRole.ADMIN)
    cohort = group("Students cohort", curator)
    first = Student(name="Student One", group=cohort)
    second = Student(name="Student Two", group=cohort)
    session.add_all([first, second])
    session.commit()

    assert {item.id for item in cohort.students} == {first.id, second.id}
    assert first.group is cohort
    assert second.group is cohort


def test_student_has_exactly_one_group(session: Session) -> None:
    session.add(Student(name="Orphan student"))

    with pytest.raises(IntegrityError):
        session.commit()


def test_student_account_is_nullable_for_legacy_profile(session: Session) -> None:
    curator = user("legacy-profile-curator", UserRole.ADMIN)
    cohort = group("Legacy profile cohort", curator)
    profile = Student(name="Profile without account", group=cohort)
    session.add(profile)
    session.commit()

    assert profile.user_id is None
    assert profile.user is None
    assert profile.user_role is UserRole.STUDENT


def test_student_account_is_unique_and_must_have_student_role(session: Session) -> None:
    curator = user("profile-curator", UserRole.ADMIN)
    cohort = group("Profile cohort", curator)
    account = user("linked-student", UserRole.STUDENT)
    first = Student(name="First profile", group=cohort, user=account)
    second = Student(name="Second profile", group=cohort, user=account)
    session.add_all([first, second])

    with pytest.raises(IntegrityError):
        session.commit()


def test_reject_admin_account_as_student_profile(session: Session) -> None:
    curator = user("admin-profile-curator", UserRole.ADMIN)
    cohort = group("Invalid profile cohort", curator)
    session.add(Student(name="Invalid profile", group=cohort, user=curator))

    with pytest.raises(IntegrityError):
        session.commit()


def test_reject_student_account_as_group_curator(session: Session) -> None:
    student_account = user("invalid-curator", UserRole.STUDENT)
    session.add(group("Invalid curator cohort", student_account))

    with pytest.raises(IntegrityError):
        session.commit()


def test_foreign_keys_reject_missing_group_and_curator(session: Session) -> None:
    session.add(Student(name="Missing group", group_id="missing-group"))

    with pytest.raises(IntegrityError):
        session.commit()

    session.rollback()
    session.add(
        Group(
            name="Missing curator",
            starts_at=date(2026, 10, 1),
            status=GroupStatus.ACTIVE,
            curator_id="missing-user",
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_restrict_deleting_group_with_students_and_curator_with_groups(
    session: Session,
) -> None:
    curator = user("retention-curator", UserRole.ADMIN)
    cohort = group("Retention cohort", curator)
    session.add(Student(name="Retained student", group=cohort))
    session.commit()

    session.delete(cohort)
    with pytest.raises(IntegrityError):
        session.commit()

    session.rollback()
    session.delete(curator)
    with pytest.raises(IntegrityError):
        session.commit()


def test_restrict_deleting_user_linked_to_student_profile(session: Session) -> None:
    curator = user("account-retention-curator", UserRole.ADMIN)
    account = user("retained-student-account", UserRole.STUDENT)
    cohort = group("Account retention cohort", curator)
    session.add(Student(name="Retained profile", group=cohort, user=account))
    session.commit()

    session.delete(account)
    with pytest.raises(IntegrityError):
        session.commit()


@pytest.mark.parametrize(
    ("dependent_kind", "initial_role", "new_role"),
    [
        ("group", UserRole.ADMIN, UserRole.STUDENT),
        ("student", UserRole.STUDENT, UserRole.ADMIN),
    ],
)
def test_restrict_changing_role_used_by_composite_foreign_key(
    session: Session,
    dependent_kind: str,
    initial_role: UserRole,
    new_role: UserRole,
) -> None:
    account = user(f"role-change-{dependent_kind}", initial_role)
    curator = account if dependent_kind == "group" else user("role-change-curator", UserRole.ADMIN)
    cohort = group(f"Role change {dependent_kind}", curator)
    session.add(cohort)
    if dependent_kind == "student":
        session.add(Student(name="Role-linked profile", group=cohort, user=account))
    session.commit()

    with pytest.raises(IntegrityError):
        session.execute(
            text("UPDATE users SET role = :role WHERE id = :user_id"),
            {"role": new_role.value, "user_id": account.id},
        )
        session.commit()


@pytest.mark.parametrize("target", ["group", "curator", "student_account"])
def test_restrict_raw_delete_of_referenced_records(session: Session, target: str) -> None:
    curator = user(f"raw-delete-curator-{target}", UserRole.ADMIN)
    account = user(f"raw-delete-student-{target}", UserRole.STUDENT)
    cohort = group(f"Raw delete {target}", curator)
    session.add(Student(name="Raw delete profile", group=cohort, user=account))
    session.commit()

    table, record_id = {
        "group": ("groups", cohort.id),
        "curator": ("users", curator.id),
        "student_account": ("users", account.id),
    }[target]
    with pytest.raises(IntegrityError):
        session.execute(
            text(f"DELETE FROM {table} WHERE id = :record_id"), {"record_id": record_id}
        )
        session.commit()
