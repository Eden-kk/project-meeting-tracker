-- 0010_meeting_status_live.sql
-- Phase 3 / Wave 6.1: ensure meetings.status accepts 'live'.
--
-- The original 0002_conversations.sql already lists 'live' in the CHECK
-- constraint, so this migration is a no-op on fresh schemas. It exists so
-- that environments stamped from older snapshots — where 'live' might be
-- absent — converge to the same constraint without manual intervention.
--
-- Idempotent: drops the old check (if any) and recreates it with the
-- canonical set including 'live'.

ALTER TABLE meetings DROP CONSTRAINT IF EXISTS meetings_status_check;
ALTER TABLE meetings ADD CONSTRAINT meetings_status_check
    CHECK (status IN ('live', 'processing', 'ready', 'finalized', 'failed'));
