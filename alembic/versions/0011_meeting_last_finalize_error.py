"""meetings: add last_finalize_error column for the auto-finalize path."""
from pathlib import Path

from alembic import op

revision = "0011_meeting_last_finalize_error"
down_revision = "0010_collapse_card_state"
branch_labels = None
depends_on = None


def _sql(name: str) -> str:
    return (Path(__file__).resolve().parents[2] / "migrations" / name).read_text()


def upgrade() -> None:
    op.execute(_sql("0011_meeting_last_finalize_error.sql"))


def downgrade() -> None:
    op.execute("ALTER TABLE meetings DROP COLUMN IF EXISTS last_finalize_error;")
