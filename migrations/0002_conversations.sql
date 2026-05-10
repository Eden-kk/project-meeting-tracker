-- 0002_conversations.sql
-- Postgres dialect (TIMESTAMPTZ, JSONB, partial indexes). SQLite is not a supported target.
-- Conversation artifacts, meetings, meeting sources.
-- Source of truth: design-doc §16.

CREATE TABLE conversation_artifacts (
    id                 TEXT PRIMARY KEY,
    workspace_id       TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    source_type        TEXT NOT NULL CHECK (source_type IN (
                            'live_voice', 'zoom_rtms', 'voice_file',
                            'transcript_file', 'pasted_transcript')),
    capture_mode       TEXT NOT NULL CHECK (capture_mode IN ('live', 'imported')),
    title              TEXT NOT NULL,
    created_by         TEXT NOT NULL REFERENCES users(id),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    raw_file_url       TEXT,
    raw_text           TEXT,
    processing_status  TEXT NOT NULL DEFAULT 'received' CHECK (processing_status IN (
                            'received', 'transcribing', 'diarizing', 'parsing',
                            'normalizing', 'extracting', 'ready', 'failed')),
    visibility         TEXT NOT NULL DEFAULT 'private' CHECK (visibility IN (
                            'private', 'workspace', 'shared')),
    labels             JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE INDEX idx_artifacts_workspace ON conversation_artifacts(workspace_id);
CREATE INDEX idx_artifacts_status    ON conversation_artifacts(processing_status);

CREATE TABLE meetings (
    id                TEXT PRIMARY KEY,
    artifact_id       TEXT NOT NULL UNIQUE REFERENCES conversation_artifacts(id) ON DELETE CASCADE,
    status            TEXT NOT NULL CHECK (status IN (
                           'live', 'processing', 'ready', 'finalized', 'failed')),
    started_at        TIMESTAMPTZ,
    ended_at          TIMESTAMPTZ,
    detected_pattern  JSONB,
    current_schema    JSONB,
    evidence_quality  TEXT NOT NULL DEFAULT 'unknown' CHECK (evidence_quality IN (
                           'unknown', 'high', 'medium', 'low', 'lowest')),
    finalized_at      TIMESTAMPTZ
);

CREATE INDEX idx_meetings_status ON meetings(status);

CREATE TABLE meeting_sources (
    id            TEXT PRIMARY KEY,
    meeting_id    TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    source_kind   TEXT NOT NULL CHECK (source_kind IN (
                       'mic', 'zoom_rtms', 'file_upload', 'paste')),
    metadata      JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_meeting_sources_meeting ON meeting_sources(meeting_id);
