import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from threading import Barrier
from threading import Event as ThreadEvent

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.session import build_engine, get_db
from app.main import create_app
from app.modules.groups.models import Group, GroupStatus
from app.modules.legacy_io.models import ImportRun
from app.modules.legacy_io.service import restore_backup
from app.modules.strategies.models import StrategyTask
from app.modules.students.models import Student
from app.modules.users.models import User, UserRole
from tests import test_groups_students_api as group_cases
from tests import test_legacy_import_export as import_cases
from tests import test_meetings_homeworks_api as homework_cases
from tests import test_strategies_tasks_api as strategy_cases
from tests import test_user_management_api as user_cases

POSTGRES_URL = os.getenv("KURATORSKAYA_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="KURATORSKAYA_TEST_POSTGRES_URL is required for PostgreSQL integration tests",
)
BACKEND_DIR = Path(__file__).resolve().parents[1]


def _require_disposable_database_url(value: str) -> None:
    url = make_url(value)
    if url.get_backend_name() != "postgresql" or not (
        url.database and url.database.lower().endswith("_test")
    ):
        raise ValueError("PostgreSQL integration tests require a disposable test database")


if POSTGRES_URL:
    _require_disposable_database_url(POSTGRES_URL)


def test_postgresql_test_url_must_name_disposable_database() -> None:
    with pytest.raises(ValueError, match="disposable test database"):
        _require_disposable_database_url(
            "postgresql+psycopg://crm:password@db.example/kuratorskaya"
        )


def _alembic_config_for(database_url: str) -> Config:
    config = Config(BACKEND_DIR / "alembic.ini")
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    config.attributes["database_url"] = database_url
    return config


def _alembic_config() -> Config:
    assert POSTGRES_URL is not None
    return _alembic_config_for(POSTGRES_URL)


@pytest.fixture(autouse=True)
def clean_postgresql_schema() -> None:
    assert POSTGRES_URL is not None
    engine = create_engine(POSTGRES_URL)
    try:
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
        yield
    finally:
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
        engine.dispose()


def test_postgresql_clean_upgrade_metadata_and_downgrade() -> None:
    assert POSTGRES_URL is not None
    config = _alembic_config()

    command.upgrade(config, "head")
    command.check(config)

    engine = create_engine(POSTGRES_URL)
    try:
        assert set(inspect(engine).get_table_names()) >= {
            "users",
            "groups",
            "students",
            "strategies",
            "strategy_tasks",
            "task_history",
            "homeworks",
            "homework_items",
            "homework_history",
            "import_runs",
            "legacy_id_mappings",
        }
    finally:
        engine.dispose()

    command.downgrade(config, "base")
    engine = create_engine(POSTGRES_URL)
    try:
        assert inspect(engine).get_table_names() == ["alembic_version"]
    finally:
        engine.dispose()


def test_postgresql_upgrade_from_previous_head_preserves_existing_data() -> None:
    assert POSTGRES_URL is not None
    config = _alembic_config()
    command.upgrade(config, "20261026_0008")
    engine = create_engine(POSTGRES_URL)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO users (
                        id, login, normalized_login, role, password_hash,
                        must_change_password, is_active, is_owner
                    ) VALUES ('owner', 'owner', 'owner', 'admin', 'hash', false, true, true)
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO groups (
                        id, curator_id, curator_role, name, starts_at, status, version
                    ) VALUES ('group', 'owner', 'admin', 'Group', '2026-01-01', 'active', 1)
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO students (id, group_id, user_role, name, version)
                    VALUES ('student', 'group', 'student', 'Student', 1)
                    """
                )
            )
    finally:
        engine.dispose()

    command.upgrade(config, "head")
    engine = create_engine(POSTGRES_URL)
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT name FROM students WHERE id = 'student'")) == (
                "Student"
            )
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "20261028_0009"
            )
    finally:
        engine.dispose()


def test_postgresql_upgrade_rejects_existing_inactive_curator() -> None:
    assert POSTGRES_URL is not None
    config = _alembic_config()
    command.upgrade(config, "20261023_0003")
    engine = create_engine(POSTGRES_URL)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO users (
                        id, login, normalized_login, role, password_hash,
                        must_change_password, is_active, is_owner
                    ) VALUES (
                        'inactive', 'inactive', 'inactive', 'admin', 'hash', false, false, false
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO groups (
                        id, curator_id, curator_role, name, starts_at, status
                    ) VALUES ('group', 'inactive', 'admin', 'Group', '2026-01-01', 'active')
                    """
                )
            )
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match="must be reassigned to an active admin"):
        command.upgrade(config, "head")

    engine = create_engine(POSTGRES_URL)
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "20261023_0003"
            )
    finally:
        engine.dispose()


@pytest.fixture
def postgresql_learning_api() -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    assert POSTGRES_URL is not None
    command.upgrade(_alembic_config(), "head")
    engine = build_engine(POSTGRES_URL)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(
        environment="test",
        database_url=POSTGRES_URL,
        auth_argon2_time_cost=1,
        auth_argon2_memory_cost=1024,
        auth_argon2_parallelism=1,
        _env_file=None,
    )
    application = create_app(settings)

    def override_db() -> Iterator[Session]:
        with factory() as database:
            yield database

    application.dependency_overrides[get_db] = override_db
    with TestClient(application) as client:
        yield client, factory
    engine.dispose()


@pytest.mark.parametrize("first_operation", ["manual", "submission"])
def test_postgresql_task_update_and_submission_are_linearizable(
    postgresql_learning_api: tuple[TestClient, sessionmaker[Session]],
    first_operation: str,
) -> None:
    homework_cases.test_task_status_and_homework_submission_are_linearizable(
        postgresql_learning_api, first_operation
    )


def test_postgresql_shared_task_review_is_serialized(
    postgresql_learning_api: tuple[TestClient, sessionmaker[Session]],
) -> None:
    homework_cases.test_concurrent_homeworks_cannot_review_the_same_task(postgresql_learning_api)


def test_postgresql_legacy_import_is_concurrently_idempotent(
    postgresql_learning_api: tuple[TestClient, sessionmaker[Session]],
) -> None:
    import_cases.test_concurrent_identical_import_is_idempotent(postgresql_learning_api)


def test_postgresql_legacy_import_authorization_and_csrf(
    postgresql_learning_api: tuple[TestClient, sessionmaker[Session]],
) -> None:
    import_cases.test_validate_is_owner_only_and_writes_nothing(postgresql_learning_api)


def test_postgresql_legacy_import_rolls_back_after_audit_failure(
    postgresql_learning_api: tuple[TestClient, sessionmaker[Session]], monkeypatch
) -> None:
    import_cases.test_failure_after_writes_rolls_back_entities_and_import_run(
        postgresql_learning_api, monkeypatch
    )


def test_postgresql_export_uses_one_repeatable_read_snapshot(
    postgresql_learning_api: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = postgresql_learning_api
    owner = import_cases.add_user(client, factory, "export-owner", owner=True)
    group = Group(
        curator_id=owner.id,
        curator_role=UserRole.ADMIN,
        name="Export group",
        starts_at=date(2026, 1, 1),
        status=GroupStatus.ACTIVE,
    )
    with factory.begin() as database:
        database.add(group)
    headers = import_cases.authenticate(client, owner.login)
    engine = factory.kw["bind"]
    group_selected = ThreadEvent()
    continue_export = ThreadEvent()
    blocked = False

    def pause_after_group_select(*args) -> None:
        nonlocal blocked
        statement = args[2]
        if not blocked and "FROM groups" in statement:
            blocked = True
            group_selected.set()
            assert continue_export.wait(10)

    event.listen(engine, "after_cursor_execute", pause_after_group_select)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(client.get, "/api/v1/exports/backup", headers=headers)
            assert group_selected.wait(10)
            with factory.begin() as database:
                database.add(Student(group_id=group.id, name="Concurrent student"))
            continue_export.set()
            response = future.result(timeout=10)
    finally:
        continue_export.set()
        event.remove(engine, "after_cursor_execute", pause_after_group_select)

    assert response.status_code == 200
    assert len(response.json()["data"]["groups"]) == 1
    assert response.json()["data"]["students"] == []
    with factory() as database:
        assert database.scalar(select(func.count(Student.id))) == 1


def test_postgresql_logical_backup_restore_and_downgrade(
    postgresql_learning_api: tuple[TestClient, sessionmaker[Session]],
) -> None:
    assert POSTGRES_URL is not None
    client, factory = postgresql_learning_api
    owner = import_cases.add_user(client, factory, "restore-owner", owner=True)
    headers = import_cases.authenticate(client, owner.login)
    body = import_cases.request_body(owner.id)
    preview = client.post("/api/v1/imports/legacy/validate", json=body, headers=headers).json()
    imported = client.post(
        "/api/v1/imports/legacy",
        json={**body, "confirm": True, "confirmation_checksum": preview["checksum"]},
        headers=headers,
    )
    assert imported.status_code == 201
    backup = client.get("/api/v1/exports/backup", headers=headers).json()

    restore_url = (
        make_url(POSTGRES_URL)
        .set(database="crm_legacy_restore_test")
        .render_as_string(hide_password=False)
    )
    restore_config = _alembic_config_for(restore_url)
    restore_engine = create_engine(restore_url)
    try:
        with restore_engine.begin() as connection:
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
        command.upgrade(restore_config, "head")
        with Session(restore_engine) as database:
            with pytest.raises(ValueError, match="matching users"):
                restore_backup(database, backup)
            database.rollback()
            assert database.scalar(select(func.count(Group.id))) == 0
        with Session(restore_engine) as database, database.begin():
            database.add(
                User(
                    id=owner.id,
                    login="restore-owner",
                    role=UserRole.ADMIN,
                    password_hash="synthetic-test-hash",
                    is_owner=True,
                    is_active=True,
                    must_change_password=True,
                )
            )
        with Session(restore_engine) as database, database.begin():
            counts = restore_backup(database, backup)
            assert counts["groups"] == 1
            assert counts["homework_items"] == 1
        with Session(restore_engine) as database:
            assert database.scalar(select(func.count(Group.id))) == 1
            assert database.scalar(select(func.count(ImportRun.id))) == 1
        command.check(restore_config)
        with restore_engine.begin() as connection:
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
        command.upgrade(restore_config, "head")
        command.downgrade(restore_config, "base")
        assert inspect(restore_engine).get_table_names() == ["alembic_version"]
    finally:
        restore_engine.dispose()


def test_postgresql_shared_tasks_use_consistent_lock_order(
    postgresql_learning_api: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = postgresql_learning_api
    curator = homework_cases.add_user(client, factory, "curator")
    student_user = homework_cases.add_user(client, factory, "student", role="student")
    group = homework_cases.add_group(factory, curator)
    student = homework_cases.add_student(factory, group, "Ученица", user=student_user)
    first_task = homework_cases.add_strategy_task(factory, student, "Первая")
    with factory.begin() as database:
        second_task = StrategyTask(
            strategy_id=first_task.strategy_id,
            section_id=first_task.section_id,
            title="Вторая",
            position=1,
        )
        database.add(second_task)

    curator_headers = homework_cases.authenticate(client, curator.login)

    def create(task_ids: list[str]) -> dict[str, object]:
        response = client.post(
            f"/api/v1/strategies/{first_task.strategy_id}/homeworks",
            json={"title": "ДЗ", "task_ids": task_ids},
            headers=curator_headers,
        )
        assert response.status_code == 201, response.text
        homework = response.json()
        assert (
            homework_cases.transition(client, curator_headers, homework, "issued").status_code
            == 200
        )
        return homework

    first = create([first_task.id, second_task.id])
    second = create([second_task.id, first_task.id])
    first_client = TestClient(client.app)
    second_client = TestClient(client.app)
    first_headers = homework_cases.authenticate(first_client, student_user.login)
    second_headers = homework_cases.authenticate(second_client, student_user.login)
    first_updates = Barrier(2)
    seen_connections: set[int] = set()

    def synchronize_first_task_update(connection, _cursor, statement, *_args) -> None:
        if statement.lstrip().startswith("UPDATE strategy_tasks"):
            connection_id = id(connection)
            if connection_id not in seen_connections:
                seen_connections.add(connection_id)
                first_updates.wait(timeout=10)

    engine = factory.kw["bind"]
    event.listen(engine, "before_cursor_execute", synchronize_first_task_update)

    def submit(test_client: TestClient, headers: dict[str, str], homework: dict) -> int:
        return test_client.post(
            f"/api/v1/homeworks/{homework['id']}/transitions",
            json={
                "expected_version": homework["version"],
                "status": "submitted",
                "submission_text": "Работа",
            },
            headers=headers,
        ).status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = [
                future.result()
                for future in (
                    executor.submit(submit, first_client, first_headers, first),
                    executor.submit(submit, second_client, second_headers, second),
                )
            ]
    finally:
        event.remove(engine, "before_cursor_execute", synchronize_first_task_update)
        first_client.close()
        second_client.close()

    assert sorted(statuses) == [200, 409]


def test_postgresql_homework_records_are_immutable(
    postgresql_learning_api: tuple[TestClient, sessionmaker[Session]],
) -> None:
    homework_cases.test_homework_history_and_items_are_append_only(postgresql_learning_api)


def test_postgresql_homework_snapshot_scope_is_enforced(
    postgresql_learning_api: tuple[TestClient, sessionmaker[Session]],
) -> None:
    homework_cases.test_homework_snapshot_cross_strategy_and_issue_do_not_complete_tasks(
        postgresql_learning_api
    )


def test_postgresql_rejects_direct_cross_strategy_homework_item(
    postgresql_learning_api: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = postgresql_learning_api
    curator = homework_cases.add_user(client, factory, "curator")
    group = homework_cases.add_group(factory, curator)
    first_student = homework_cases.add_student(factory, group, "Первая")
    second_student = homework_cases.add_student(factory, group, "Вторая")
    first_task = homework_cases.add_strategy_task(factory, first_student, "Первая задача")
    second_task = homework_cases.add_strategy_task(factory, second_student, "Чужая задача")
    headers = homework_cases.authenticate(client, curator.login)
    homework = homework_cases.create_homework(client, headers, first_task)

    with (
        pytest.raises(IntegrityError, match="homework_item_strategy_mismatch"),
        factory.begin() as database,
    ):
        database.execute(
            text(
                """
                INSERT INTO homework_items (
                    id, homework_id, strategy_id, task_id, position, title
                ) VALUES (
                    'cross-item', :homework_id, :strategy_id, :task_id, 1, 'Invalid'
                )
                """
            ),
            {
                "homework_id": homework["id"],
                "strategy_id": first_task.strategy_id,
                "task_id": second_task.id,
            },
        )


def test_postgresql_homework_history_failure_rolls_back(
    postgresql_learning_api: tuple[TestClient, sessionmaker[Session]], monkeypatch
) -> None:
    homework_cases.test_homework_rollback_if_history_insert_fails(
        postgresql_learning_api, monkeypatch
    )


def test_postgresql_group_updates_are_serialized(
    postgresql_learning_api: tuple[TestClient, sessionmaker[Session]],
) -> None:
    group_cases.test_concurrent_group_patch_allows_exactly_one_writer(postgresql_learning_api)


def test_postgresql_student_updates_are_serialized(
    postgresql_learning_api: tuple[TestClient, sessionmaker[Session]],
) -> None:
    group_cases.test_concurrent_student_patch_allows_exactly_one_writer(postgresql_learning_api)


def test_postgresql_archived_group_rejects_new_student(
    postgresql_learning_api: tuple[TestClient, sessionmaker[Session]],
) -> None:
    group_cases.test_cannot_create_student_in_archived_group(postgresql_learning_api)


def test_postgresql_strategy_creation_is_serialized(
    postgresql_learning_api: tuple[TestClient, sessionmaker[Session]],
) -> None:
    strategy_cases.test_concurrent_strategy_creation_allows_exactly_one_writer(
        postgresql_learning_api
    )


def test_postgresql_task_reorder_is_serialized(
    postgresql_learning_api: tuple[TestClient, sessionmaker[Session]],
) -> None:
    strategy_cases.test_concurrent_task_reorder_allows_exactly_one_writer(postgresql_learning_api)


def test_postgresql_review_decision_is_serialized(
    postgresql_learning_api: tuple[TestClient, sessionmaker[Session]],
) -> None:
    homework_cases.test_concurrent_acceptance_and_revision_keep_task_consistent(
        postgresql_learning_api
    )


def test_postgresql_offboarding_and_reassignment_are_serialized(
    postgresql_learning_api: tuple[TestClient, sessionmaker[Session]],
) -> None:
    user_cases.test_concurrent_offboarding_and_reassignment_preserve_responsible_curator(
        postgresql_learning_api
    )


def test_postgresql_owner_guard_serializes_concurrent_deactivation() -> None:
    assert POSTGRES_URL is not None
    command.upgrade(_alembic_config(), "head")
    engine = build_engine(POSTGRES_URL)
    try:
        with engine.begin() as connection:
            for owner_id in ("owner-one", "owner-two"):
                connection.execute(
                    text(
                        """
                        INSERT INTO users (
                            id, login, normalized_login, role, password_hash,
                            must_change_password, is_active, is_owner
                        ) VALUES (:id, :id, :id, 'admin', 'hash', false, true, true)
                        """
                    ),
                    {"id": owner_id},
                )

        barrier = Barrier(2)

        def deactivate(owner_id: str) -> bool:
            try:
                with engine.begin() as connection:
                    barrier.wait()
                    connection.execute(
                        text("UPDATE users SET is_active = false WHERE id = :id"),
                        {"id": owner_id},
                    )
                return True
            except IntegrityError:
                return False

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(deactivate, ("owner-one", "owner-two")))

        with engine.connect() as connection:
            active_owners = connection.scalar(
                text("SELECT count(*) FROM users WHERE role = 'admin' AND is_owner AND is_active")
            )
        assert sorted(outcomes) == [False, True]
        assert active_owners == 1
    finally:
        engine.dispose()


def test_postgresql_database_guards_curators_and_archived_groups() -> None:
    assert POSTGRES_URL is not None
    command.upgrade(_alembic_config(), "head")
    engine = build_engine(POSTGRES_URL)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO users (
                        id, login, normalized_login, role, password_hash,
                        must_change_password, is_active, is_owner
                    ) VALUES ('curator', 'curator', 'curator', 'admin', 'hash', false, true, false)
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO groups (
                        id, curator_id, curator_role, name, starts_at, status, version
                    ) VALUES ('group', 'curator', 'admin', 'Group', '2026-01-01', 'active', 1)
                    """
                )
            )

        with (
            pytest.raises(IntegrityError, match="curator_has_groups"),
            engine.begin() as connection,
        ):
            connection.execute(text("UPDATE users SET is_active = false WHERE id = 'curator'"))

        with engine.begin() as connection:
            connection.execute(text("UPDATE groups SET status = 'archived' WHERE id = 'group'"))
        with pytest.raises(IntegrityError, match="group_archived"), engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO students (id, group_id, user_role, name, version)
                    VALUES ('student', 'group', 'student', 'Student', 1)
                    """
                )
            )
    finally:
        engine.dispose()
