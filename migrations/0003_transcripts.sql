-- 0003_transcripts.sql
-- Participants, speaker segments, transcript chunks.
-- Source of truth: design-doc §16.

CREATE TABLE participants (
    id            TEXT PRIMARY KEY,
    meeting_id    TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    user_id       TEXT REFERENCES users(id),
    display_name  TEXT,
    speaker_label TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_participants_meeting ON participants(meeting_id);

CREATE TABLE speaker_segments (
    id            TEXT PRIMARY KEY,
    meeting_id    TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    speaker_id    TEXT,
    speaker_name  TEXT,
    start_ms      BIGINT,
    end_ms        BIGINT,
    text          TEXT NOT NULL,
    confidence    DOUBLE PRECISION,
    source_type   TEXT NOT NULL CHECK (source_type IN (
                       'live_voice', 'zoom_rtms', 'voice_file',
                       'transcript_file', 'pasted_transcript')),
    is_final      BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX idx_segments_meeting_time ON speaker_segments(meeting_id, start_ms);

CREATE TABLE transcript_chunks (
    id                   TEXT PRIMARY KEY,
    meeting_id           TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    start_ms             BIGINT,
    end_ms               BIGINT,
    text                 TEXT NOT NULL,
    speaker_turns_json   JSONB,
    is_final             BOOLEAN NOT NULL DEFAULT FALSE,
    processed_by_hermes  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_chunks_meeting_time ON transcript_chunks(meeting_id, start_ms);
CREATE INDEX idx_chunks_unprocessed  ON transcript_chunks(meeting_id, processed_by_hermes)
    WHERE processed_by_hermes = FALSE;
