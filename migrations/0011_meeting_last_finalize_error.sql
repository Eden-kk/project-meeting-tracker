-- 0011_meeting_last_finalize_error.sql
--
-- Phase-3 auto-finalize: after `import_route` parses a meeting, the
-- storage-router schedules `hermes_runtime.run_meeting_finalization` as a
-- FastAPI BackgroundTask. The status flow becomes:
--
--   processing → normalizing → ready → finalizing → finalized
--
-- On finalize failure the dispatcher reverts status to `ready` so the
-- user can re-trigger, and stores the failure reason here so the UI /
-- ops can show it without spelunking the logs.

ALTER TABLE meetings
    ADD COLUMN last_finalize_error TEXT NULL;
