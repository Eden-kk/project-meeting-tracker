-- 0021_meetings_finalized_summary.sql
--
-- Persist the summary paragraph produced by the `meeting-finalization` Hermes
-- skill so the SPA's Summary tab can render it without re-invoking the LLM.
-- Populated by `hermes_runtime._finalize_inner` right before status flips to
-- `finalized`. Idempotent: re-finalize overwrites.

ALTER TABLE meetings
    ADD COLUMN IF NOT EXISTS finalized_summary TEXT NULL;
