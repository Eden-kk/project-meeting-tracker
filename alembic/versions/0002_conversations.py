"""conversations: artifacts, meetings, meeting_sources."""
from pathlib import Path

from alembic import op

revision = "0002_conversations"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def _sql(name: str) -> str:
    return (Path(__file__).resolve().parents[2] / "migrations" / name).read_text()


def upgrade() -> None:
    op.execute(_sql("0002_conversations.sql"))


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS meeting_sources, meetings, conversation_artifacts CASCADE;")
