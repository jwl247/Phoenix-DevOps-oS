-- Billing columns for an EXISTING pbm_radar_db (schema.sql already has them for a fresh one).
-- Apply once: wrangler d1 execute pbm_radar_db --remote --file=migrations/2026-09-28-billing.sql
-- (D1/SQLite has no ADD COLUMN IF NOT EXISTS; a second run fails harmlessly on "duplicate column".)
ALTER TABLE subscribers ADD COLUMN stripe_customer_id TEXT;
ALTER TABLE subscribers ADD COLUMN stripe_subscription_id TEXT;
ALTER TABLE subscribers ADD COLUMN billing_status TEXT NOT NULL DEFAULT 'beta';
ALTER TABLE subscribers ADD COLUMN billing_updated_at TEXT;
CREATE TABLE IF NOT EXISTS billing_events (
  event_id      TEXT PRIMARY KEY,
  type          TEXT NOT NULL,
  subscriber_id INTEGER REFERENCES subscribers(id),
  received_at   TEXT NOT NULL,
  summary       TEXT
);
