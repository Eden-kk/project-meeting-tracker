"""Fence import attempts and allow local cancellation."""
from alembic import op

revision = "0026_import_attempts"
down_revision = "0025_meeting_source_zoom_bot"
branch_labels = None
depends_on = None


def _constraints(cancelled: bool) -> None:
    extra = ", 'cancelled'" if cancelled else ""
    for table, column, states in (
        ("conversation_artifacts", "processing_status",
         "'received','transcribing','diarizing','parsing','normalizing','extracting','ready','failed'"),
        ("meetings", "status", "'live','processing','normalizing','ready','finalizing','finalized','failed'"),
    ):
        name = f"{table}_{column}_check"
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
        op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({column} IN ({states}{extra}))")


def upgrade() -> None:
    op.execute("ALTER TABLE conversation_artifacts ADD COLUMN processing_attempt TEXT, "
               "ADD COLUMN processing_attempts BIGINT NOT NULL DEFAULT 0, "
               "ADD COLUMN processing_error TEXT")
    # Legacy in-flight/failed jobs may already have invoked remote compute.
    op.execute("UPDATE conversation_artifacts SET processing_attempts = 1 "
               "WHERE capture_mode = 'imported' AND processing_status <> 'received'")
    _constraints(True)


def downgrade() -> None:
    # Fail safely if cancelled records exist rather than silently rewriting history.
    _constraints(False)
    op.execute("ALTER TABLE conversation_artifacts DROP COLUMN processing_attempt, "
               "DROP COLUMN processing_attempts, DROP COLUMN processing_error")
