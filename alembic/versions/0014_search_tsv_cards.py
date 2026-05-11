"""memory_cards: add search_tsv tsvector column + GIN index for FTS."""
from pathlib import Path

from alembic import op

revision = "0014_search_tsv_cards"
down_revision = "0013_search_tsv_segments"
branch_labels = None
depends_on = None


def _sql(name: str) -> str:
    return (Path(__file__).resolve().parents[2] / "migrations" / name).read_text()


def upgrade() -> None:
    op.execute(_sql("0014_search_tsv_cards.sql"))


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS ix_memory_cards_tsv;
        ALTER TABLE memory_cards DROP COLUMN IF EXISTS search_tsv;
        """
    )
