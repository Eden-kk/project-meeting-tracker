-- 0022_meetings_slack_fields.sql
--
-- Slack bot MVP: persist the finalize-summary text on the meeting row
-- so the Slack notifier can read it without a second LLM call, and
-- record the Slack thread timestamp so a future re-post / reply step
-- can target the same thread.

ALTER TABLE meetings
    ADD COLUMN finalized_summary TEXT NULL,
    ADD COLUMN slack_thread_ts TEXT NULL;
