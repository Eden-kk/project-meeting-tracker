"""speaker_segments: add search_tsv tsvector column + GIN index for FTS."""
from pathlib import Path

from alembic import op

revision = "0013_search_tsv_segments"
down_revision = "0012_meeting_status_finalizing"
branch_labels = None
depends_on = None


def _sql(name: str) -> str:
    return (Path(__file__).resolve().parents[2] / "migrations" / name).read_text()


def upgrade() -> None:
    op.execute(_sql("0013_search_tsv_segments.sql"))


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS ix_speaker_segments_tsv;
        ALTER TABLE speaker_segments DROP COLUMN IF EXISTS search_tsv;
        """
    )
