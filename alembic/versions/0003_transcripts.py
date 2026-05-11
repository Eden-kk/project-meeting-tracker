"""transcripts: participants, speaker_segments, transcript_chunks."""
from pathlib import Path

from alembic import op

revision = "0003_transcripts"
down_revision = "0002_conversations"
branch_labels = None
depends_on = None


def _sql(name: str) -> str:
    return (Path(__file__).resolve().parents[2] / "migrations" / name).read_text()


def upgrade() -> None:
    op.execute(_sql("0003_transcripts.sql"))


def downgrade() -> None:
    op.execute(
        "DROP TABLE IF EXISTS transcript_chunks, speaker_segments, participants CASCADE;"
    )
