-- 0020_meetings_current_topic.sql
--
-- Wave 8.6: 30-s rolling "currently discussing" topic surface, complementary
-- to Wave 6.3's 2-min running summary. Updated by a per-meeting asyncio
-- task in storage_router/live_topic_tracker.py.

ALTER TABLE meetings
    ADD COLUMN current_topic TEXT NULL;
