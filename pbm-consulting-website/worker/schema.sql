-- pbm-leads-worker schema
-- One row per lead submission. A resubmission from the same email before
-- verifying just gets a fresh code on the existing row (see index.js) --
-- we don't want five half-verified rows for one real business.

CREATE TABLE IF NOT EXISTS leads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  business_name TEXT NOT NULL,
  email TEXT NOT NULL,
  phone TEXT,
  code_hash TEXT NOT NULL,
  code_expires_at TEXT NOT NULL,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  verified_at TEXT,
  hubspot_synced_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(email);
