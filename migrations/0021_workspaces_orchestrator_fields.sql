-- 0021_workspaces_orchestrator_fields.sql
--
-- Per-project orchestrator (Slack-bot follow-up): add two nullable columns
-- on `workspaces` so the orchestrator can render a registry prompt and
-- apply a freshness heuristic when fanning out to subagents.
--
--   description    — short user-authored project description (200 chars-ish),
--                    rendered into the orchestrator system prompt.
--   last_meeting_at — denormalized from meetings.finalized_at; updated by
--                    storage_router.hermes_runtime._finalize_inner.

ALTER TABLE workspaces
    ADD COLUMN description TEXT NULL,
    ADD COLUMN last_meeting_at TIMESTAMPTZ NULL;
