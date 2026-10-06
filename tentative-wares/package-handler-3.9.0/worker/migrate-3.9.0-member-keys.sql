-- packages-worker 3.9.0 — member keys. Run ONCE against phoenix_dev_db BEFORE deploying 3.9.0:
--   npx wrangler d1 execute phoenix_dev_db --remote --file migrate-3.9.0-member-keys.sql
-- (3.9.0 writes clonepool.owner on every intake; without this column intake would fail.)
-- Existing rows get owner = NULL, which means "the Phoenix owner" (you).
CREATE TABLE IF NOT EXISTS api_keys (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  who           TEXT NOT NULL,
  key_hash      TEXT NOT NULL UNIQUE,          -- SHA-256 of the key; the key itself is never stored
  scopes        TEXT NOT NULL DEFAULT 'read,intake',
  created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
  last_used_at  DATETIME,
  revoked_at    DATETIME
);
CREATE UNIQUE INDEX IF NOT EXISTS api_keys_live_who ON api_keys(who) WHERE revoked_at IS NULL;
ALTER TABLE clonepool ADD COLUMN owner TEXT;
