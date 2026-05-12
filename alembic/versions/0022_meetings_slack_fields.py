"""meetings: add finalized_summary + slack_thread_ts for Slack bot MVP."""
from pathlib import Path

from alembic import op

revision = "0022_meetings_slack_fields"
down_revision = "0021_meeting_interview_fields"
branch_labels = None
depends_on = None


def _sql(name: str) -> str:
    return (Path(__file__).resolve().parents[2] / "migrations" / name).read_text()


def upgrade() -> None:
    op.execute(_sql("0022_meetings_slack_fields.sql"))


def downgrade() -> None:
    op.execute(
        "ALTER TABLE meetings"
        " DROP COLUMN IF EXISTS finalized_summary,"
        " DROP COLUMN IF EXISTS slack_thread_ts;"
    )
