"""meetings: add nullable zoom_meeting_number column for zoom-bot correlation.

No DDL change to source_type — the schema declares it as free-form Text NOT
NULL (models/db.py:60,176), so inserting source_type='zoom_bot' works against
today's schema without an enum/CHECK extension.
"""
from alembic import op

revision = "0025_meeting_source_zoom_bot"
down_revision = "0024_meeting_deleted_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE meetings ADD COLUMN IF NOT EXISTS zoom_meeting_number TEXT NULL;"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS meetings_zoom_meeting_number_idx"
        " ON meetings (zoom_meeting_number) WHERE zoom_meeting_number IS NOT NULL;"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS meetings_zoom_meeting_number_idx;")
    op.execute("ALTER TABLE meetings DROP COLUMN IF EXISTS zoom_meeting_number;")
