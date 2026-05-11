"""memory: meeting_patterns, dynamic_schemas, memory_cards, meeting_notes."""
from pathlib import Path

from alembic import op

revision = "0004_memory"
down_revision = "0003_transcripts"
branch_labels = None
depends_on = None


def _sql(name: str) -> str:
    return (Path(__file__).resolve().parents[2] / "migrations" / name).read_text()


def upgrade() -> None:
    op.execute(_sql("0004_memory.sql"))


def downgrade() -> None:
    op.execute(
        "DROP TABLE IF EXISTS meeting_notes, memory_cards, dynamic_schemas, meeting_patterns CASCADE;"
    )
