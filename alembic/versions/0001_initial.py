"""initial: workspaces + users."""
from pathlib import Path

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def _sql(name: str) -> str:
    return (Path(__file__).resolve().parents[2] / "migrations" / name).read_text()


def upgrade() -> None:
    op.execute(_sql("0001_initial.sql"))


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS users, workspaces CASCADE;")
