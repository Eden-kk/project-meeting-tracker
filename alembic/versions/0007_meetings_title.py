"""meetings: add title column.

The frontend used to keep titles in browser localStorage because the API
had no field for them; this migration moves the title into Postgres so
the new GET /api/meetings list endpoint can return it.
"""
from alembic import op

revision = "0007_meetings_title"
down_revision = "0006_seed_dev_workspace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE meetings ADD COLUMN title TEXT NOT NULL DEFAULT '';")


def downgrade() -> None:
    op.execute("ALTER TABLE meetings DROP COLUMN title;")
