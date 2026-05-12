-- 0015_meeting_live_summary.sql
--
-- Wave 6.3 + 6.4 — periodic agent extraction during live capture.
--
-- Adds two columns to ``meetings`` for the rolling agent loop that runs
-- every ~120s WHILE a meeting is still ``live``:
--
--   live_summary               TEXT NULL
--       The most recent rolling summary produced by the
--       ``live-meeting-summary`` skill. Updated in place on every tick.
--       Cleared at meeting end is NOT required — it remains as the
--       last-known live snapshot until the standard finalize chain
--       overwrites the canonical summary stored elsewhere.
--
--   last_live_extraction_end_ms BIGINT NULL
--       Watermark for the ``live-meeting-extraction`` (6.4) tick. The
--       next tick processes the window
--       [last_live_extraction_end_ms - overlap_ms, now]
--       so boundary-spanning findings are caught by adjacent windows
--       and the consolidation pass at /end merges duplicates.
--       NULL on first tick — extractor uses ``now`` as the initial cap.

ALTER TABLE meetings
    ADD COLUMN live_summary TEXT NULL,
    ADD COLUMN last_live_extraction_end_ms BIGINT NULL;
