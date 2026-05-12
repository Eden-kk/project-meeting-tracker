"""meetings: persist the finalize-skill summary so the Summary tab can render it."""
from pathlib import Path

from alembic import op

revision = "0021_meetings_finalized_summary"
down_revision = "0020_meetings_current_topic"
branch_labels = None
depends_on = None


def _sql(name: str) -> str:
    return (Path(__file__).resolve().parents[2] / "migrations" / name).read_text()


def upgrade() -> None:
    op.execute(_sql("0021_meetings_finalized_summary.sql"))


def downgrade() -> None:
    op.execute("ALTER TABLE meetings DROP COLUMN IF EXISTS finalized_summary;")
