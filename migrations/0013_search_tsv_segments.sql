-- 0013_search_tsv_segments.sql
--
-- Wave 4.1 — cross-meeting keyword search over transcript segments.
-- Adds a STORED generated tsvector column + GIN index for Postgres FTS.
-- Generated columns keep the index maintenance-free (no triggers, no
-- app-side writes); `english` config is fine for the bilingual transcripts
-- we have today (it does no harm to non-English text — just no stemming).
ALTER TABLE speaker_segments
    ADD COLUMN search_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', coalesce(text, ''))) STORED;

CREATE INDEX ix_speaker_segments_tsv ON speaker_segments USING gin(search_tsv);
