-- Migration 0012 — extend meetings.status CHECK constraint to permit the
-- 'finalizing' state introduced by the auto-finalize background task.
--
-- The original constraint allowed live | processing | ready | finalized | failed.
-- Auto-finalize sets status='finalizing' BETWEEN ready and finalized while the
-- BackgroundTask is mid-run, so the constraint must include it. Also adds
-- 'normalizing' because the dispatcher uses it for the parse-complete step
-- and we shouldn't have it implicit. Idempotent via DROP IF EXISTS + ADD.

ALTER TABLE meetings DROP CONSTRAINT IF EXISTS meetings_status_check;
ALTER TABLE meetings ADD CONSTRAINT meetings_status_check
    CHECK (status IN ('live','processing','normalizing','ready','finalizing','finalized','failed'));
