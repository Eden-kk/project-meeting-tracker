"""meetings: add live_summary + last_live_extraction_end_ms columns.

Mirrors migrations/0015_meeting_live_summary.sql.

Wave 6.3 introduces the periodic agent loop: every ~120s during a
``live`` meeting we (a) refresh ``live_summary`` from the transcript-so-far
and (b) extract draft cards over the SINCE-marked transcript window.
Both columns are nullable; only the live extractor writes them.

Down-revision is the merge node so this slots cleanly on top of all
prior wave heads.
"""
from pathlib import Path

from alembic import op

revision = "0015_meeting_live_summary"
down_revision = "89120ca5f335"
branch_labels = None
depends_on = None


def _sql(name: str) -> str:
    return (Path(__file__).resolve().parents[2] / "migrations" / name).read_text()


def upgrade() -> None:
    op.execute(_sql("0015_meeting_live_summary.sql"))


def downgrade() -> None:
    op.execute(
        "ALTER TABLE meetings "
        "DROP COLUMN IF EXISTS live_summary, "
        "DROP COLUMN IF EXISTS last_live_extraction_end_ms;"
    )
