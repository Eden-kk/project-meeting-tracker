-- 0013_action_items_index.sql
--
-- Wave 5.1 (action-items dashboard) + 5.2 (open-questions dashboard) both
-- run cross-meeting list queries that filter `memory_cards` by `type`
-- with `hidden_at IS NULL`. Existing indexes are per-meeting; a partial
-- index on `(type)` where `hidden_at IS NULL` keeps these dashboards
-- cheap as the card corpus grows.
--
-- The workspace_id scope ride along via a join through `meetings →
-- conversation_artifacts`; that join is already indexed by primary keys
-- so no further index is required here.

CREATE INDEX IF NOT EXISTS ix_memory_cards_type_visible
    ON memory_cards (type)
    WHERE hidden_at IS NULL;
