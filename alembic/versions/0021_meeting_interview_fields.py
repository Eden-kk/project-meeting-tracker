"""meetings: add interviewee_name, interviewee_role, suggested_questions for Q1."""
from pathlib import Path

from alembic import op

revision = "0021_meeting_interview_fields"
down_revision = "0020_meetings_current_topic"
branch_labels = None
depends_on = None


def _sql(name: str) -> str:
    return (Path(__file__).resolve().parents[2] / "migrations" / name).read_text()


def upgrade() -> None:
    op.execute(_sql("0021_meeting_interview_fields.sql"))


def downgrade() -> None:
    op.execute(
        "ALTER TABLE meetings"
        " DROP COLUMN IF EXISTS interviewee_name,"
        " DROP COLUMN IF EXISTS interviewee_role,"
        " DROP COLUMN IF EXISTS suggested_questions;"
    )
