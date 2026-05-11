"""memory_cards: add audit_reason column for the Wave 2.1 audit pass.

Mirrors migrations/0014_card_audit_reason.sql.

Note: numbered 0014 because the live tracker DB at the start of Wave 2
had a foreign branch-numbered 0013_action_items_index applied out of
band. To avoid colliding with that revision we take 0014. Our migration
still chains off 0012_meeting_status_finalizing in code; ops applies it
to live by running `alembic stamp 0014_card_audit_reason` after running
the raw SQL (the stamp is what `alembic upgrade head` will look for on
future automated runs).
"""
from pathlib import Path

from alembic import op

revision = "0014_card_audit_reason"
down_revision = "0012_meeting_status_finalizing"
branch_labels = None
depends_on = None


def _sql(name: str) -> str:
    return (Path(__file__).resolve().parents[2] / "migrations" / name).read_text()


def upgrade() -> None:
    op.execute(_sql("0014_card_audit_reason.sql"))


def downgrade() -> None:
    op.execute("ALTER TABLE memory_cards DROP COLUMN IF EXISTS audit_reason;")
