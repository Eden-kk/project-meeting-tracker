"""memory_cards: partial index on (type) where hidden_at IS NULL.

Backs the cross-meeting action-items + open-questions dashboards (Wave
5.1 / 5.2). See migrations/0013_action_items_index.sql for the rationale.
"""
from pathlib import Path

from alembic import op

revision = "0013_action_items_index"
down_revision = "0012_meeting_status_finalizing"
branch_labels = None
depends_on = None


def _sql(name: str) -> str:
    return (Path(__file__).resolve().parents[2] / "migrations" / name).read_text()


def upgrade() -> None:
    op.execute(_sql("0013_action_items_index.sql"))


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_memory_cards_type_visible;")
