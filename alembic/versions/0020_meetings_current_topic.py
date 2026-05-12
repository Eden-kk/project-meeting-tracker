"""meetings: add current_topic for the Wave-8.6 30-s tracker."""
from pathlib import Path

from alembic import op

revision = "0020_meetings_current_topic"
down_revision = "0019_meetings_speaker_label_map"
branch_labels = None
depends_on = None


def _sql(name: str) -> str:
    return (Path(__file__).resolve().parents[2] / "migrations" / name).read_text()


def upgrade() -> None:
    op.execute(_sql("0020_meetings_current_topic.sql"))


def downgrade() -> None:
    op.execute("ALTER TABLE meetings DROP COLUMN IF EXISTS current_topic;")
