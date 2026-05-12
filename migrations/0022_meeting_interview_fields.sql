-- 0021_meeting_interview_fields.sql
--
-- Q1 live-interview-questioner: adds optional interviewee context columns
-- and the JSONB column for the latest suggested questions. The questioner
-- loop is gated on `interviewee_name IS NOT NULL` so regular meetings are
-- unaffected.

ALTER TABLE meetings
    ADD COLUMN interviewee_name TEXT NULL,
    ADD COLUMN interviewee_role TEXT NULL,
    ADD COLUMN suggested_questions JSONB NULL;
