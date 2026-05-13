"""meetings: add soft-delete deleted_at column and partial active index."""
from alembic import op

revision = "0024_meeting_deleted_at"
down_revision = "0023_workspaces_orchestrator_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE meetings ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ NULL;"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS meetings_active_idx"
        " ON meetings (id) WHERE deleted_at IS NULL;"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS meetings_active_idx;")
    op.execute("ALTER TABLE meetings DROP COLUMN IF EXISTS deleted_at;")
