"""add authentication sessions and login throttling

Revision ID: 20261022_0002
Revises: 20261022_0001
Create Date: 2026-10-22 22:00:00
"""

import re
import unicodedata
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261022_0002"
down_revision: str | None = "20261022_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LOGIN_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")


def _validated_existing_logins() -> list[tuple[str, str]]:
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, login FROM users")).mappings()
    normalized_to_id: dict[str, str] = {}
    normalized_logins: list[tuple[str, str]] = []
    for row in rows:
        normalized = unicodedata.normalize("NFKC", row["login"]).strip().casefold()
        if not LOGIN_PATTERN.fullmatch(normalized):
            raise RuntimeError(f"User {row['id']} has a login incompatible with authentication")
        previous_id = normalized_to_id.get(normalized)
        if previous_id is not None:
            raise RuntimeError(
                f"Users {previous_id} and {row['id']} have case-insensitively duplicate logins"
            )
        normalized_to_id[normalized] = row["id"]
        normalized_logins.append((row["id"], normalized))
    return normalized_logins


def _store_normalized_logins(normalized_logins: list[tuple[str, str]]) -> None:
    connection = op.get_bind()
    for user_id, normalized in normalized_logins:
        connection.execute(
            sa.text("UPDATE users SET normalized_login = :login WHERE id = :user_id"),
            {"login": normalized, "user_id": user_id},
        )


def upgrade() -> None:
    normalized_logins = _validated_existing_logins()

    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("normalized_login", sa.String(length=64), nullable=True))

    _store_normalized_logins(normalized_logins)

    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("normalized_login", existing_type=sa.String(length=64), nullable=False)
        batch_op.create_unique_constraint("uq_users_normalized_login", ["normalized_login"])

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_auth_sessions_user_id_users"),
            onupdate="RESTRICT",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_auth_sessions_token_hash")),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"], unique=False)

    op.create_table(
        "login_attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("login_key", sa.String(length=64), nullable=False),
        sa.Column("client_key", sa.String(length=64), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_login_attempts")),
    )
    op.create_index(
        "ix_login_attempts_login_time",
        "login_attempts",
        ["login_key", "attempted_at"],
        unique=False,
    )
    op.create_index(
        "ix_login_attempts_client_time",
        "login_attempts",
        ["client_key", "attempted_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_login_attempts_client_time", table_name="login_attempts")
    op.drop_index("ix_login_attempts_login_time", table_name="login_attempts")
    op.drop_table("login_attempts")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("uq_users_normalized_login", type_="unique")
        batch_op.drop_column("normalized_login")
