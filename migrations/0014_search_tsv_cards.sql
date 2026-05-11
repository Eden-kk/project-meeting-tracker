-- 0014_search_tsv_cards.sql
--
-- Wave 4.2 — cross-meeting keyword search over memory cards.
-- Adds a STORED generated tsvector column + GIN index for FTS over
-- title || ' ' || content. Same pattern as 0013 for transcript segments.
-- Honoring `hidden_at IS NULL` is the route's responsibility — we
-- intentionally do NOT exclude hidden rows from the index, because
-- admin/audit views may want to search them.
ALTER TABLE memory_cards
    ADD COLUMN search_tsv tsvector
    GENERATED ALWAYS AS (
        to_tsvector(
            'english',
            coalesce(title, '') || ' ' || coalesce(content, '')
        )
    ) STORED;

CREATE INDEX ix_memory_cards_tsv ON memory_cards USING gin(search_tsv);
