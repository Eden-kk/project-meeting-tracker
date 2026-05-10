-- 0005_governance.sql
-- Postgres dialect (TIMESTAMPTZ, JSONB, partial indexes). SQLite is not a supported target.
-- Sharing + audit logs.
-- Source of truth: design-doc §16, §19.

CREATE TABLE shares (
    id            TEXT PRIMARY KEY,
    meeting_id    TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    grantee_id    TEXT REFERENCES users(id),
    grantee_kind  TEXT NOT NULL CHECK (grantee_kind IN ('user', 'workspace')),
    permission    TEXT NOT NULL CHECK (permission IN ('view', 'comment', 'edit')),
    created_by    TEXT NOT NULL REFERENCES users(id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_shares_meeting ON shares(meeting_id);
CREATE INDEX idx_shares_grantee ON shares(grantee_id);

CREATE TABLE audit_logs (
    id           BIGSERIAL PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    actor_id     TEXT REFERENCES users(id),
    actor_kind   TEXT NOT NULL CHECK (actor_kind IN ('user', 'agent', 'system')),
    action       TEXT NOT NULL,
    target_kind  TEXT NOT NULL,
    target_id    TEXT,
    metadata     JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_workspace_time ON audit_logs(workspace_id, created_at DESC);
CREATE INDEX idx_audit_target         ON audit_logs(target_kind, target_id);
