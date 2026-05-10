-- 0004_memory.sql
-- Meeting patterns, dynamic schemas, memory cards, meeting notes.
-- Source of truth: design-doc §16.

CREATE TABLE meeting_patterns (
    id                  TEXT PRIMARY KEY,
    meeting_id          TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    primary_pattern     TEXT NOT NULL,
    secondary_patterns  JSONB NOT NULL DEFAULT '[]'::jsonb,
    interaction_style   TEXT,
    confidence          DOUBLE PRECISION NOT NULL,
    reason              TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_patterns_meeting ON meeting_patterns(meeting_id);

CREATE TABLE dynamic_schemas (
    id              TEXT PRIMARY KEY,
    meeting_id      TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    selected_blocks JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_schemas_meeting ON dynamic_schemas(meeting_id);

CREATE TABLE memory_cards (
    id                TEXT PRIMARY KEY,
    meeting_id        TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    state             TEXT NOT NULL CHECK (state IN (
                           'candidate', 'draft', 'committed', 'rejected')),
    type              TEXT NOT NULL CHECK (type IN (
                           'decision', 'action_item', 'pain_point', 'quote',
                           'requirement', 'risk', 'open_question', 'technical_detail')),
    title             TEXT NOT NULL,
    content           TEXT NOT NULL,
    source_chunk_ids  JSONB NOT NULL,
    source_start_ms   BIGINT,
    source_end_ms     BIGINT,
    speakers_json     JSONB,
    confidence        DOUBLE PRECISION NOT NULL,
    needs_review      BOOLEAN NOT NULL DEFAULT TRUE,
    created_by_agent  TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_cards_meeting ON memory_cards(meeting_id);
CREATE INDEX idx_cards_state   ON memory_cards(meeting_id, state);
CREATE INDEX idx_cards_type    ON memory_cards(meeting_id, type);

CREATE TABLE meeting_notes (
    id           TEXT PRIMARY KEY,
    meeting_id   TEXT NOT NULL UNIQUE REFERENCES meetings(id) ON DELETE CASCADE,
    summary      TEXT,
    body_json    JSONB,
    finalized_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
