"""Persist the curator task blocker flag."""

import sqlalchemy as sa
from alembic import op

revision = "20261124_0012"
down_revision = "20261122_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "strategy_tasks",
        sa.Column("blocker", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        blocker = "(s.source_metadata -> 'legacy_tasks' -> m.legacy_id ->> 'blocker') = 'true'"
    else:
        # Compare JSON object keys directly so legacy IDs may contain dots or quotes.
        blocker = """
            EXISTS (
                SELECT 1 FROM json_each(s.source_metadata, '$.legacy_tasks') item
                WHERE item.key = m.legacy_id AND json_type(item.value, '$.blocker') = 'true'
            )
        """
    connection.execute(sa.text(f"""
        UPDATE strategy_tasks
        SET blocker = true
        WHERE EXISTS (
            SELECT 1 FROM legacy_id_mappings m
            JOIN strategies s ON s.id = strategy_tasks.strategy_id
            WHERE m.entity_type = 'task' AND m.target_id = strategy_tasks.id AND {blocker}
        )
    """))


def downgrade() -> None:
    op.drop_column("strategy_tasks", "blocker")
