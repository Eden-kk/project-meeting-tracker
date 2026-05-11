"""merge_waves

Revision ID: 89120ca5f335
Revises: 0013_action_items_index, 0014_card_audit_reason, 0014_search_tsv_cards
Create Date: 2026-05-11 14:32:41.480129

"""
from alembic import op
import sqlalchemy as sa


revision = '89120ca5f335'
down_revision = ('0013_action_items_index', '0014_card_audit_reason', '0014_search_tsv_cards')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
