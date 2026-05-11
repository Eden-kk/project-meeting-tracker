-- 0014_card_audit_reason.sql
--
-- Wave 2.1 — agent audit pass support.
--
-- Adds `audit_reason TEXT NULL` to memory_cards so the audit pass can record
-- WHY a card was downgraded or hidden. The column is nullable; only the
-- audit-pass routes write it. The list endpoint does not surface it directly;
-- it's read on demand for admin / debug views and joined into card payloads
-- when present.

ALTER TABLE memory_cards
    ADD COLUMN audit_reason TEXT NULL;
