-- Grants add-on for an EXISTING pbm_radar_db (schema.sql has it for a fresh one).
-- Apply once: wrangler d1 execute pbm_radar_db --remote --file=migrations/2026-09-28-grants.sql
ALTER TABLE subscribers ADD COLUMN grants INTEGER NOT NULL DEFAULT 0;
ALTER TABLE subscribers ADD COLUMN grant_eligibility TEXT NOT NULL DEFAULT '["23"]';
ALTER TABLE subscribers ADD COLUMN grant_categories TEXT NOT NULL DEFAULT '[]';
ALTER TABLE subscribers ADD COLUMN grant_keywords TEXT NOT NULL DEFAULT '[]';
ALTER TABLE subscribers ADD COLUMN grant_min_award INTEGER NOT NULL DEFAULT 0;
ALTER TABLE runs ADD COLUMN kind TEXT NOT NULL DEFAULT 'radar';
CREATE TABLE IF NOT EXISTS grants (
  opp_id TEXT PRIMARY KEY, number TEXT, title TEXT NOT NULL, agency TEXT, agency_code TEXT,
  open_date TEXT NOT NULL, close_date TEXT, status TEXT,
  eligibilities TEXT NOT NULL DEFAULT '[]', categories TEXT NOT NULL DEFAULT '[]',
  award_ceiling INTEGER, ui_link TEXT, fetched_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_grants_open ON grants(open_date);
CREATE TABLE IF NOT EXISTS grant_matches (
  subscriber_id INTEGER NOT NULL REFERENCES subscribers(id), opp_id TEXT NOT NULL, sent_at TEXT NOT NULL,
  PRIMARY KEY (subscriber_id, opp_id)
);
ALTER TABLE applications ADD COLUMN grants INTEGER NOT NULL DEFAULT 0;
ALTER TABLE applications ADD COLUMN grant_eligibility TEXT NOT NULL DEFAULT '[]';
ALTER TABLE applications ADD COLUMN grant_categories TEXT NOT NULL DEFAULT '[]';
ALTER TABLE applications ADD COLUMN grant_keywords TEXT NOT NULL DEFAULT '[]';
ALTER TABLE applications ADD COLUMN grant_min_award INTEGER NOT NULL DEFAULT 0;
