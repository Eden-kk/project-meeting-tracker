-- 0010_collapse_card_state.sql
--
-- Phase-3 redesign: agent owns card quality, the user does not curate.
-- This migration removes the per-card state machine entirely.
--
-- Behaviour change:
--   * `state` column dropped (any prior 'rejected' rows are mapped to
--     hidden_at = NOW(); any 'draft' / 'committed' rows become live).
--   * `needs_review` column dropped (no human review surface anymore).
--   * `hidden_at TIMESTAMPTZ NULL` added — agent-driven soft delete; the
--     list endpoint filters `hidden_at IS NULL` by default.
--   * `superseded_by_id UUID NULL FK -> memory_cards(id)` added — agent
--     consolidation pass points a duplicate at its canonical winner.
--
-- Intentional flattening: we do NOT preserve draft vs committed semantics
-- because no consumer reads them post-cutover. Reviewers re-import if a
-- card looks wrong.

ALTER TABLE memory_cards
    ADD COLUMN hidden_at         TIMESTAMPTZ NULL,
    ADD COLUMN superseded_by_id  TEXT NULL REFERENCES memory_cards(id) ON DELETE SET NULL;

-- Map legacy `rejected` rows onto the new soft-delete surface before the
-- column disappears so we don't lose the "user said no" signal entirely.
UPDATE memory_cards
   SET hidden_at = NOW()
 WHERE state = 'rejected';

-- Drop the per-card state-machine indexes + constraints + columns.
DROP INDEX IF EXISTS idx_cards_state;
ALTER TABLE memory_cards DROP COLUMN state;
ALTER TABLE memory_cards DROP COLUMN needs_review;

CREATE INDEX idx_cards_hidden_at      ON memory_cards(meeting_id, hidden_at);
CREATE INDEX idx_cards_superseded_by  ON memory_cards(superseded_by_id);
