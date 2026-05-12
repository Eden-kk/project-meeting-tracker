-- 0019_meetings_speaker_label_map.sql
--
-- Wave 8.4: per-meeting friendly speaker names. The map is applied at
-- read time on `GET /api/live-meetings/{id}/segments` (and the static
-- segments endpoint) so renaming a speaker never rewrites historical
-- rows. Shape: {"speaker_2": "Alice", "speaker_3": "Bob"}.

ALTER TABLE meetings
    ADD COLUMN speaker_label_map JSONB NULL;
