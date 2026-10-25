from datetime import date, datetime, timedelta
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.errors import ApiError, api_error_handler
from app.db.session import get_db
from app.modules.auth.authorization import (
    bootstrap_first_owner,
    can_create_group,
    can_manage_accounts,
    can_read_group,
    can_read_student,
    can_update_group,
    can_update_student,
    change_user_access,
    curator_for_new_group,
    deactivate_user,
    reassign_group,
    reassign_groups_and_deactivate,
    require_admin,
    require_group_read,
    require_group_update,
    require_owner,
    require_student_read,
    require_student_update,
    transfer_ownership,
)
from app.modules.auth.dependencies import require_business_user
from app.modules.auth.models import AuthSession
from app.modules.groups.models import Group, GroupStatus
from app.modules.students.models import Student
from app.modules.users.models import User, UserRole


def make_user(
    login: str,
    role: UserRole,
    *,
    is_owner: bool = False,
    is_active: bool = True,
) -> User:
    return User(
        login=login,
        role=role,
        password_hash="synthetic-password-hash",
        is_owner=is_owner,
        is_active=is_active,
        must_change_password=False,
    )


def make_group(name: str, curator: User, *, status: GroupStatus = GroupStatus.ACTIVE) -> Group:
    return Group(name=name, starts_at=date(2026, 10, 1), status=status, curator=curator)


def seed_access_graph(session: Session):
    owner = make_user("product-owner", UserRole.ADMIN, is_owner=True)
    assigned = make_user("assigned-curator", UserRole.ADMIN)
    other = make_user("other-curator", UserRole.ADMIN)
    learner = make_user("learner", UserRole.STUDENT)
    stranger = make_user("other-learner", UserRole.STUDENT)
    assigned_group = make_group("Assigned", assigned)
    second_assigned_group = make_group("Second assigned", assigned)
    other_group = make_group("Other", other)
    profile = Student(name="Learner profile", group=assigned_group, user=learner)
    foreign_profile = Student(name="Other profile", group=other_group, user=stranger)
    session.add_all(
        [
            owner,
            assigned,
            other,
            learner,
            stranger,
            assigned_group,
            second_assigned_group,
            other_group,
            profile,
            foreign_profile,
        ]
    )
    session.commit()
    return {
        "owner": owner,
        "assigned": assigned,
        "other": other,
        "learner": learner,
        "assigned_group": assigned_group,
        "second_assigned_group": second_assigned_group,
        "other_group": other_group,
        "profile": profile,
        "foreign_profile": foreign_profile,
    }


def test_owner_can_read_and_update_every_group(session: Session) -> None:
    graph = seed_access_graph(session)

    for cohort in (graph["assigned_group"], graph["other_group"]):
        assert can_read_group(graph["owner"], cohort, session)
        assert can_update_group(graph["owner"], cohort)
    assert can_read_student(graph["owner"], graph["foreign_profile"])
    assert can_update_student(graph["owner"], graph["foreign_profile"])


def test_curator_reads_all_groups_but_updates_only_multiple_assigned_groups(
    session: Session,
) -> None:
    graph = seed_access_graph(session)
    curator = graph["assigned"]

    assert can_read_group(curator, graph["other_group"], session)
    assert can_update_group(curator, graph["assigned_group"])
    assert can_update_group(curator, graph["second_assigned_group"])
    assert not can_update_group(curator, graph["other_group"])
    assert can_update_student(curator, graph["profile"])
    assert not can_update_student(curator, graph["foreign_profile"])
    assert can_create_group(curator)
    assert curator_for_new_group(curator) is curator


def test_arbitrary_new_admin_gets_permissions_from_database_assignment(session: Session) -> None:
    graph = seed_access_graph(session)
    new_curator = make_user("new-curator-47", UserRole.ADMIN)
    cohort = make_group("New assignment", new_curator)
    session.add(cohort)
    session.commit()

    assert can_update_group(new_curator, cohort)
    assert not can_update_group(graph["assigned"], cohort)


def test_student_reads_only_own_profile_and_group_even_after_archive(session: Session) -> None:
    graph = seed_access_graph(session)
    learner = graph["learner"]

    assert can_read_student(learner, graph["profile"])
    assert can_read_group(learner, graph["assigned_group"], session)
    assert not can_read_student(learner, graph["foreign_profile"])
    assert not can_read_group(learner, graph["other_group"], session)
    graph["assigned_group"].status = GroupStatus.ARCHIVED
    assert can_read_student(learner, graph["profile"])
    assert can_read_group(learner, graph["assigned_group"], session)
    assert not can_update_student(learner, graph["profile"])
    assert not can_update_group(learner, graph["assigned_group"])


def test_inactive_users_have_no_permissions(session: Session) -> None:
    graph = seed_access_graph(session)
    inactive_owner = make_user("inactive-owner", UserRole.ADMIN, is_owner=True, is_active=False)
    inactive_curator = make_user("inactive-curator", UserRole.ADMIN, is_active=False)
    inactive_student = make_user("inactive-student", UserRole.STUDENT, is_active=False)

    assert not can_read_group(inactive_owner, graph["assigned_group"], session)
    assert not can_update_group(inactive_curator, graph["assigned_group"])
    assert not can_read_student(inactive_student, graph["profile"])
    assert not can_create_group(inactive_curator)
    assert not can_manage_accounts(inactive_owner)


@pytest.fixture
def authorization_client(session: Session):
    graph = seed_access_graph(session)
    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)

    def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[require_business_user] = lambda: graph["learner"]

    @app.get("/groups/{group_id}")
    def read_group(group: Annotated[Group, Depends(require_group_read)]) -> dict[str, str]:
        return {"id": group.id}

    @app.patch("/groups/{group_id}")
    def update_group(group: Annotated[Group, Depends(require_group_update)]) -> dict[str, str]:
        return {"id": group.id}

    @app.get("/students/{student_id}")
    def read_student(student: Annotated[Student, Depends(require_student_read)]) -> dict[str, str]:
        return {"id": student.id}

    @app.patch("/students/{student_id}")
    def update_student(
        student: Annotated[Student, Depends(require_student_update)],
    ) -> dict[str, str]:
        return {"id": student.id}

    with TestClient(app) as client:
        yield client, app, graph


def test_dependencies_hide_foreign_objects_and_reject_writes_to_readable_objects(
    authorization_client,
) -> None:
    client, app, graph = authorization_client

    assert client.get(f"/students/{graph['profile'].id}").status_code == 200
    assert client.get(f"/students/{graph['foreign_profile'].id}").status_code == 404
    assert client.get(f"/groups/{graph['other_group'].id}").status_code == 404
    assert client.get("/groups/client-supplied-missing-id").status_code == 404
    assert client.patch(f"/students/{graph['profile'].id}").status_code == 403

    app.dependency_overrides[require_business_user] = lambda: graph["assigned"]
    assert client.get(f"/groups/{graph['other_group'].id}").status_code == 200
    assert client.patch(f"/groups/{graph['assigned_group'].id}").status_code == 200
    assert client.patch(f"/groups/{graph['other_group'].id}").status_code == 403
    assert client.patch(f"/students/{graph['profile'].id}").status_code == 200
    assert client.patch(f"/students/{graph['foreign_profile'].id}").status_code == 403
    assert client.patch("/groups/missing-group").status_code == 404
    assert client.patch("/students/missing-student").status_code == 404


def test_reassignment_immediately_changes_update_permissions(session: Session) -> None:
    graph = seed_access_graph(session)
    cohort = graph["assigned_group"]

    reassign_group(graph["owner"], cohort, graph["other"], session)
    session.commit()

    assert not can_update_group(graph["assigned"], cohort)
    assert can_update_group(graph["other"], cohort)


def test_only_owner_can_reassign_to_an_active_admin(session: Session) -> None:
    graph = seed_access_graph(session)
    inactive_admin = make_user("inactive-target", UserRole.ADMIN, is_active=False)
    student = make_user("student-target", UserRole.STUDENT)

    with pytest.raises(ApiError) as forbidden:
        reassign_group(graph["assigned"], graph["assigned_group"], graph["other"], session)
    assert forbidden.value.status_code == 403

    for invalid_target in (inactive_admin, student):
        with pytest.raises(ApiError) as invalid:
            reassign_group(graph["owner"], graph["assigned_group"], invalid_target, session)
        assert invalid.value.status_code == 422


def test_deactivation_requires_reassignment_and_revokes_active_sessions(session: Session) -> None:
    graph = seed_access_graph(session)
    former_curator = graph["assigned"]
    now = datetime(2026, 10, 22, 12, 0, 0)
    auth_session = AuthSession(
        user=former_curator,
        token_hash="a" * 64,
        csrf_token_hash="b" * 64,
        created_at=now,
        last_activity_at=now,
        absolute_expires_at=now + timedelta(days=30),
    )
    session.add(auth_session)
    session.commit()

    with pytest.raises(ApiError) as orphaned:
        deactivate_user(graph["owner"], former_curator, session, now=now)
    assert orphaned.value.status_code == 409

    reassign_group(graph["owner"], graph["assigned_group"], graph["other"], session)
    reassign_group(graph["owner"], graph["second_assigned_group"], graph["other"], session)
    deactivate_user(graph["owner"], former_curator, session, now=now)
    session.commit()

    persisted = session.scalar(select(User).where(User.id == former_curator.id))
    persisted_session = session.scalar(
        select(AuthSession).where(AuthSession.user_id == former_curator.id)
    )
    assert persisted is not None and not persisted.is_active
    assert persisted.deactivated_at == now
    assert persisted_session is not None and persisted_session.revoked_at == now
    assert graph["assigned_group"].curator_id == graph["other"].id


def test_non_owner_cannot_deactivate_users_or_escalate_privileges(session: Session) -> None:
    graph = seed_access_graph(session)

    assert can_manage_accounts(graph["owner"])
    assert not can_manage_accounts(graph["assigned"])
    assert not can_manage_accounts(graph["learner"])
    assert require_admin(graph["assigned"]) is graph["assigned"]
    assert require_owner(graph["owner"]) is graph["owner"]
    for actor in (graph["assigned"], graph["learner"]):
        with pytest.raises(ApiError) as forbidden_owner:
            require_owner(actor)
        assert forbidden_owner.value.status_code == 403
    with pytest.raises(ApiError) as forbidden_group_creation:
        curator_for_new_group(graph["learner"])
    assert forbidden_group_creation.value.status_code == 403
    with pytest.raises(ApiError) as forbidden:
        deactivate_user(graph["assigned"], graph["other"], session)
    assert forbidden.value.status_code == 403


def test_owner_can_deactivate_unassigned_user_without_explicit_timestamp(session: Session) -> None:
    graph = seed_access_graph(session)
    unassigned = make_user("unassigned-curator", UserRole.ADMIN)
    session.add(unassigned)
    session.commit()

    deactivate_user(graph["owner"], unassigned, session)
    session.commit()

    assert unassigned.is_active is False
    assert unassigned.deactivated_at is not None


def test_cannot_deactivate_or_demote_the_last_active_owner(session: Session) -> None:
    graph = seed_access_graph(session)
    owner = graph["owner"]

    with pytest.raises(ApiError) as deactivation:
        deactivate_user(owner, owner, session)
    assert deactivation.value.status_code == 409

    for role, owner_flag in (
        (UserRole.ADMIN, False),
        (UserRole.STUDENT, False),
    ):
        with pytest.raises(ApiError) as access_change:
            change_user_access(
                owner,
                owner,
                session,
                role=role,
                is_owner=owner_flag,
            )
        assert access_change.value.status_code == 409

    session.refresh(owner)
    assert owner.is_active is True
    assert owner.role is UserRole.ADMIN
    assert owner.is_owner is True


def test_owner_transfer_allows_revoking_and_deactivating_former_owner(session: Session) -> None:
    graph = seed_access_graph(session)
    former_owner = graph["owner"]
    successor = graph["other"]

    transfer_ownership(former_owner, successor, session)
    deactivate_user(successor, former_owner, session)
    session.commit()

    assert successor.is_owner is True
    assert successor.is_active is True
    assert former_owner.is_owner is False
    assert former_owner.is_active is False


def test_ordinary_admin_cannot_promote_self_to_owner(session: Session) -> None:
    graph = seed_access_graph(session)
    admin = graph["assigned"]

    with pytest.raises(ApiError) as forbidden:
        change_user_access(
            admin,
            admin,
            session,
            role=UserRole.ADMIN,
            is_owner=True,
        )

    assert forbidden.value.status_code == 403
    assert admin.is_owner is False


def test_owner_services_reject_invalid_actors_and_targets(session: Session) -> None:
    graph = seed_access_graph(session)
    inactive_admin = make_user("inactive-successor", UserRole.ADMIN, is_active=False)

    with pytest.raises(ApiError) as admin_required:
        require_admin(graph["learner"])
    assert admin_required.value.status_code == 403

    with pytest.raises(ApiError) as transfer_forbidden:
        transfer_ownership(graph["assigned"], graph["other"], session)
    assert transfer_forbidden.value.status_code == 403

    with pytest.raises(ApiError) as invalid_successor:
        transfer_ownership(graph["owner"], inactive_admin, session)
    assert invalid_successor.value.status_code == 422

    transfer_ownership(graph["owner"], graph["owner"], session)
    assert graph["owner"].is_owner is True

    with pytest.raises(ApiError) as invalid_owner_role:
        change_user_access(
            graph["owner"],
            graph["other"],
            session,
            role=UserRole.STUDENT,
            is_owner=True,
        )
    assert invalid_owner_role.value.status_code == 422


def test_bootstrap_rejects_inactive_or_non_admin_candidate(session: Session) -> None:
    for candidate in (
        make_user("inactive-bootstrap", UserRole.ADMIN, is_active=False),
        make_user("student-bootstrap", UserRole.STUDENT),
    ):
        with pytest.raises(ApiError) as invalid:
            bootstrap_first_owner(candidate, session)
        assert invalid.value.status_code == 422
        assert candidate.is_owner is False


def test_first_owner_can_be_bootstrapped_only_when_none_exists(session: Session) -> None:
    candidate = make_user("initial-owner", UserRole.ADMIN)
    session.add(candidate)
    session.commit()

    bootstrap_first_owner(candidate, session)
    session.commit()
    assert candidate.is_owner is True

    another = make_user("later-admin", UserRole.ADMIN)
    session.add(another)
    session.commit()
    with pytest.raises(ApiError) as already_initialized:
        bootstrap_first_owner(another, session)
    assert already_initialized.value.status_code == 409
    assert another.is_owner is False


def test_failed_session_revocation_rolls_back_deactivation_and_reassignment(
    session: Session,
    monkeypatch,
) -> None:
    graph = seed_access_graph(session)
    former_curator = graph["assigned"]
    cohort = graph["assigned_group"]
    original_execute = Session.execute

    def fail_revocation(database_session: Session, statement, *args, **kwargs):
        if isinstance(statement, type(update(AuthSession))):
            raise RuntimeError("simulated session revocation failure")
        return original_execute(database_session, statement, *args, **kwargs)

    monkeypatch.setattr(Session, "execute", fail_revocation)
    with pytest.raises(RuntimeError, match="simulated session revocation failure"):
        reassign_groups_and_deactivate(
            graph["owner"],
            former_curator,
            [
                (cohort, graph["other"]),
                (graph["second_assigned_group"], graph["other"]),
            ],
            session,
        )
    session.expire_all()

    persisted_curator = session.get(User, former_curator.id)
    persisted_group = session.get(Group, cohort.id)
    assert persisted_curator is not None and persisted_curator.is_active is True
    assert persisted_group is not None and persisted_group.curator_id == former_curator.id


def test_reassignment_and_deactivation_service_does_not_commit(
    session: Session,
    monkeypatch,
) -> None:
    graph = seed_access_graph(session)

    def unexpected_commit(_: Session) -> None:
        raise AssertionError("service must not commit")

    monkeypatch.setattr(Session, "commit", unexpected_commit)
    reassign_groups_and_deactivate(
        graph["owner"],
        graph["assigned"],
        [
            (graph["assigned_group"], graph["other"]),
            (graph["second_assigned_group"], graph["other"]),
        ],
        session,
    )

    assert graph["assigned"].is_active is False
    assert graph["assigned_group"].curator_id == graph["other"].id
    session.rollback()


def test_reassignment_service_rejects_stale_curator_assignment(session: Session) -> None:
    graph = seed_access_graph(session)

    with pytest.raises(ApiError) as stale:
        reassign_groups_and_deactivate(
            graph["owner"],
            graph["assigned"],
            [(graph["other_group"], graph["owner"])],
            session,
        )

    assert stale.value.status_code == 409
    assert graph["other_group"].curator_id == graph["other"].id
    assert graph["assigned"].is_active is True


def test_reassignment_service_rejects_assignment_changed_behind_stale_orm_object(
    session: Session,
) -> None:
    graph = seed_access_graph(session)
    group = graph["assigned_group"]
    former_curator = graph["assigned"]
    replacement = graph["other"]
    requested_successor = graph["owner"]
    session.execute(
        update(Group)
        .where(Group.id == group.id)
        .values(curator_id=replacement.id, curator_role=UserRole.ADMIN)
        .execution_options(synchronize_session=False)
    )
    assert group.curator_id == former_curator.id

    with pytest.raises(ApiError) as stale:
        reassign_groups_and_deactivate(
            graph["owner"],
            former_curator,
            [(group, requested_successor)],
            session,
        )

    assert stale.value.status_code == 409
    assert stale.value.code == "curator_assignment_changed"
    session.expire_all()
    assert session.get(Group, group.id).curator_id == replacement.id
    assert session.get(User, former_curator.id).is_active is True
