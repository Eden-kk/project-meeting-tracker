"""meetings: extend status CHECK constraint to allow 'finalizing' + 'normalizing'."""
from pathlib import Path

from alembic import op

revision = "0012_meeting_status_finalizing"
down_revision = "0011_meeting_last_finalize_error"
branch_labels = None
depends_on = None


def _sql(name: str) -> str:
    return (Path(__file__).resolve().parents[2] / "migrations" / name).read_text()


def upgrade() -> None:
    op.execute(_sql("0012_meeting_status_finalizing.sql"))


def downgrade() -> None:
    op.execute("ALTER TABLE meetings DROP CONSTRAINT IF EXISTS meetings_status_check;")
    op.execute(
        "ALTER TABLE meetings ADD CONSTRAINT meetings_status_check "
        "CHECK (status IN ('live','processing','ready','finalized','failed'));"
    )
