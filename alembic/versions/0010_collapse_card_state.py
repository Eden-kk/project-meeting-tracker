"""memory_cards: drop state + needs_review; add hidden_at + superseded_by_id.

Phase-3 redesign — see migrations/0010_collapse_card_state.sql for the
intentional flattening note.
"""
from pathlib import Path

from alembic import op

revision = "0010_collapse_card_state"
down_revision = "0007_meetings_title"
branch_labels = None
depends_on = None


def _sql(name: str) -> str:
    return (Path(__file__).resolve().parents[2] / "migrations" / name).read_text()


def upgrade() -> None:
    op.execute(_sql("0010_collapse_card_state.sql"))


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS idx_cards_superseded_by;
        DROP INDEX IF EXISTS idx_cards_hidden_at;
        ALTER TABLE memory_cards DROP COLUMN IF EXISTS superseded_by_id;
        ALTER TABLE memory_cards DROP COLUMN IF EXISTS hidden_at;
        ALTER TABLE memory_cards
            ADD COLUMN state TEXT NOT NULL DEFAULT 'draft' CHECK (state IN (
                'candidate', 'draft', 'committed', 'rejected'));
        ALTER TABLE memory_cards
            ADD COLUMN needs_review BOOLEAN NOT NULL DEFAULT TRUE;
        CREATE INDEX idx_cards_state ON memory_cards(meeting_id, state);
        """
    )
