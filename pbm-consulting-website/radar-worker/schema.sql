-- pbm_radar_db — Set-Aside Radar
-- Apply: wrangler d1 execute pbm_radar_db --remote --file=schema.sql

CREATE TABLE IF NOT EXISTS opportunities (
  notice_id         TEXT PRIMARY KEY,
  title             TEXT NOT NULL,
  sol_number        TEXT,
  agency            TEXT,
  posted_date       TEXT NOT NULL,          -- YYYY-MM-DD
  response_deadline TEXT,                   -- as SAM gives it (ISO w/ offset) or NULL
  naics             TEXT,
  set_aside         TEXT NOT NULL,          -- SAM typeOfSetAside code (SBA, 8A, HZC, WOSB, ...)
  set_aside_desc    TEXT,
  ptype             TEXT,                   -- o k p r s a u g i, '?' = unknown wording
  pop_state         TEXT,
  pop_city          TEXT,
  ui_link           TEXT,
  fetched_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_opp_posted ON opportunities(posted_date);

CREATE TABLE IF NOT EXISTS subscribers (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  email       TEXT NOT NULL UNIQUE,
  name        TEXT,
  naics       TEXT NOT NULL,                -- JSON list; prefixes allowed ("2381")
  certs       TEXT NOT NULL,                -- JSON list of cert keys (small, 8a, hubzone, wosb, edwosb, ...)
  states      TEXT NOT NULL DEFAULT '[]',   -- JSON list; [] = nationwide
  ptypes      TEXT NOT NULL DEFAULT '["o","k","p","r"]',
  mode        TEXT NOT NULL DEFAULT 'certified' CHECK (mode IN ('certified','planning')),
  active      INTEGER NOT NULL DEFAULT 1,
  unsub_token TEXT NOT NULL UNIQUE,
  created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sent_matches (
  subscriber_id INTEGER NOT NULL REFERENCES subscribers(id),
  notice_id     TEXT NOT NULL,
  sent_at       TEXT NOT NULL,
  PRIMARY KEY (subscriber_id, notice_id)
);
CREATE INDEX IF NOT EXISTS idx_sent_at ON sent_matches(subscriber_id, sent_at);

-- One row per run: the honest record of what Radar actually checked.
CREATE TABLE IF NOT EXISTS runs (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  run_date        TEXT NOT NULL,            -- Chicago date the run happened
  posted_date     TEXT NOT NULL,            -- the SAM posted date it covered
  dry             INTEGER NOT NULL DEFAULT 0,
  requests_used   INTEGER NOT NULL DEFAULT 0,
  notices_seen    INTEGER NOT NULL DEFAULT 0,
  set_asides_kept INTEGER NOT NULL DEFAULT 0,
  capped          INTEGER NOT NULL DEFAULT 0,
  matches_json    TEXT,
  error           TEXT,
  created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_date ON runs(run_date);
