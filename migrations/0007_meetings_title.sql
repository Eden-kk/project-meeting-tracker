-- 0007_meetings_title.sql
-- Adds Meeting.title (the API list endpoint and frontend show this; was
-- previously cached in browser localStorage). Empty string means "untitled"
-- so the column can stay NOT NULL for schema clarity (UI substitutes
-- "Untitled meeting" at render time).

ALTER TABLE meetings ADD COLUMN title TEXT NOT NULL DEFAULT '';
