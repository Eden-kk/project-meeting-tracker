"""workspaces: add description + last_meeting_at for the orchestrator."""
from pathlib import Path

from alembic import op

revision = "0023_workspaces_orchestrator_fields"
down_revision = "0022_meeting_interview_fields"
branch_labels = None
depends_on = None


def _sql(name: str) -> str:
    return (Path(__file__).resolve().parents[2] / "migrations" / name).read_text()


def upgrade() -> None:
    op.execute(_sql("0023_workspaces_orchestrator_fields.sql"))


def downgrade() -> None:
    op.execute(
        "ALTER TABLE workspaces "
        "DROP COLUMN IF EXISTS description, "
        "DROP COLUMN IF EXISTS last_meeting_at;"
    )
