"""governance: shares, audit_logs."""
from pathlib import Path

from alembic import op

revision = "0005_governance"
down_revision = "0004_memory"
branch_labels = None
depends_on = None


def _sql(name: str) -> str:
    return (Path(__file__).resolve().parents[2] / "migrations" / name).read_text()


def upgrade() -> None:
    op.execute(_sql("0005_governance.sql"))


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_logs, shares CASCADE;")
