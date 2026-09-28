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
  created_at  TEXT NOT NULL,
  -- billing (Stripe, 2026-09-28). $9.99/month, free during the beta; nobody is
  -- charged without being asked: a checkout link is only ever sent by hand
  -- (POST /billing/checkout). Existing databases: migrations/2026-09-28-billing.sql
  stripe_customer_id     TEXT,
  stripe_subscription_id TEXT,
  billing_status         TEXT NOT NULL DEFAULT 'beta'
                         CHECK (billing_status IN ('beta','checkout_sent','trialing','active','past_due','canceled')),
  billing_updated_at     TEXT,
  -- Grants add-on (2026-09-28): paid add-on, admin-set during the beta, set by
  -- the Stripe subscription item afterwards. Eligibility = Grants.gov applicant
  -- type codes (23 small business, 22 for-profit, 21 individuals, 12/13
  -- nonprofits, 07/11 tribal, 99 unrestricted). Empty categories/keywords = all.
  grants            INTEGER NOT NULL DEFAULT 0,
  grant_eligibility TEXT NOT NULL DEFAULT '["23"]',
  grant_categories  TEXT NOT NULL DEFAULT '[]',
  grant_keywords    TEXT NOT NULL DEFAULT '[]',
  grant_min_award   INTEGER NOT NULL DEFAULT 0      -- "about how much do you need" (USD); grants with a smaller ceiling are dropped, unknown ceilings pass
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
  created_at      TEXT NOT NULL,
  kind            TEXT NOT NULL DEFAULT 'radar'   -- radar | grants
);
CREATE INDEX IF NOT EXISTS idx_runs_date ON runs(run_date);

-- Public applications (radar.html). Flow: submit -> email code -> verified
-- (status 'review') -> Jerry/Laurie approve via a one-click link in their
-- notice email (or POST /applications/approve) -> becomes a subscriber.
CREATE TABLE IF NOT EXISTS applications (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  email           TEXT NOT NULL,
  name            TEXT,
  business_name   TEXT NOT NULL,
  naics           TEXT NOT NULL DEFAULT '[]',   -- JSON list, may be empty if they only described their work
  work_desc       TEXT,                         -- "what kind of work do you do" (for Laurie to pick NAICS)
  certs           TEXT NOT NULL DEFAULT '[]',
  states          TEXT NOT NULL DEFAULT '[]',
  mode            TEXT NOT NULL DEFAULT 'planning' CHECK (mode IN ('certified','planning')),
  status          TEXT NOT NULL DEFAULT 'email' CHECK (status IN ('email','review','approved','rejected')),
  code_hash       TEXT,
  code_expires_at TEXT,
  attempt_count   INTEGER NOT NULL DEFAULT 0,
  review_token    TEXT UNIQUE,
  subscriber_id   INTEGER REFERENCES subscribers(id),
  created_at      TEXT NOT NULL,
  verified_at     TEXT,
  reviewed_at     TEXT,
  grants            INTEGER NOT NULL DEFAULT 0,      -- Grants add-on survey (2026-09-28)
  grant_eligibility TEXT NOT NULL DEFAULT '[]',
  grant_categories  TEXT NOT NULL DEFAULT '[]',
  grant_keywords    TEXT NOT NULL DEFAULT '[]',
  grant_min_award   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_app_email ON applications(email);
CREATE INDEX IF NOT EXISTS idx_app_status ON applications(status);

-- Every Stripe webhook event we have acted on, once. The UNIQUE event id is
-- what makes a redelivered webhook a no-op.
CREATE TABLE IF NOT EXISTS billing_events (
  event_id      TEXT PRIMARY KEY,
  type          TEXT NOT NULL,
  subscriber_id INTEGER REFERENCES subscribers(id),
  received_at   TEXT NOT NULL,
  summary       TEXT
);

-- Grants.gov opportunities (the Grants add-on). One row per opportunity id;
-- eligibilities/categories are JSON lists of Grants.gov codes ([] = unknown,
-- let through like an unknown SAM notice type).
CREATE TABLE IF NOT EXISTS grants (
  opp_id         TEXT PRIMARY KEY,
  number         TEXT,
  title          TEXT NOT NULL,
  agency         TEXT,
  agency_code    TEXT,
  open_date      TEXT NOT NULL,          -- YYYY-MM-DD
  close_date     TEXT,                   -- YYYY-MM-DD or NULL (rolling)
  status         TEXT,
  eligibilities  TEXT NOT NULL DEFAULT '[]',
  categories     TEXT NOT NULL DEFAULT '[]',
  award_ceiling  INTEGER,
  ui_link        TEXT,
  fetched_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_grants_open ON grants(open_date);

CREATE TABLE IF NOT EXISTS grant_matches (
  subscriber_id INTEGER NOT NULL REFERENCES subscribers(id),
  opp_id        TEXT NOT NULL,
  sent_at       TEXT NOT NULL,
  PRIMARY KEY (subscriber_id, opp_id)
);
