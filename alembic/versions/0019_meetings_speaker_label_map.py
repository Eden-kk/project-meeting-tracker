"""meetings: add speaker_label_map for live-rename persistence (Wave 8.4)."""
from pathlib import Path

from alembic import op

revision = "0019_meetings_speaker_label_map"
down_revision = "0015_meeting_live_summary"
branch_labels = None
depends_on = None


def _sql(name: str) -> str:
    return (Path(__file__).resolve().parents[2] / "migrations" / name).read_text()


def upgrade() -> None:
    op.execute(_sql("0019_meetings_speaker_label_map.sql"))


def downgrade() -> None:
    op.execute("ALTER TABLE meetings DROP COLUMN IF EXISTS speaker_label_map;")
