"""seed Phase-1 dev workspace + user.

Phase 1 has no auth; the import route hardcodes created_by=u_dev under
ws_dev. Remove this migration when auth lands.
"""
from alembic import op

revision = "0006_seed_dev_workspace"
down_revision = "0005_governance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO workspaces (id, name) VALUES ('ws_dev', 'Dev Workspace') "
        "ON CONFLICT (id) DO NOTHING;"
    )
    op.execute(
        "INSERT INTO users (id, workspace_id, email, display_name) "
        "VALUES ('u_dev', 'ws_dev', 'dev@tracker.local', 'Dev User') "
        "ON CONFLICT (id) DO NOTHING;"
    )


def downgrade() -> None:
    op.execute("DELETE FROM users WHERE id = 'u_dev';")
    op.execute("DELETE FROM workspaces WHERE id = 'ws_dev';")
