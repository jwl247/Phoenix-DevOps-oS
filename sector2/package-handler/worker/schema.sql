-- schema.sql — phoenix_dev_db, the tables packages-worker (index.js) reads and writes.
-- Apply to a NEW account/database:
--   wrangler d1 execute phoenix_dev_db --remote --file=schema.sql        (idempotent)
--
-- PROVENANCE (be honest about it): written 2026-09-28 from every SQL
-- statement in index.js plus the column comments there, because no schema
-- file ever existed for these tables (README "Standalone-readiness" item 1).
-- The live phoenix_dev_db on the main account is the source of truth until
-- the desk step `wrangler d1 export phoenix_dev_db --remote --no-data
-- --output sector2/package-handler/worker/schema.live.sql` is run and diffed
-- against this file. Tables the worker never touches (files, dependencies,
-- installed, history, aliases, kernel_slots, sideloads, rotation_log,
-- subscribers, feed_log, layer_assignments, system_telemetry,
-- system_snapshots, entry_points from the 2026-06 dump in sector1/grub/) are
-- NOT here on purpose; Office's office_* tables belong to office-notify-worker.

-- ── clonepool: CURRENT state of every intaked thing, one row per hex_id ──────
CREATE TABLE IF NOT EXISTS clonepool (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  hex_id        TEXT    NOT NULL UNIQUE,        -- to_hex(basename) (filename-hex-v1) — known collision, S2CORE-F09
  b58           TEXT,
  name          TEXT    NOT NULL,
  original_name TEXT,
  pool_path     TEXT,                           -- local path on the intaking machine (informational)
  sidecar_path  TEXT,
  header_qr     TEXT,                           -- USYS:<b58>:HEADER[:<loc_hex>]
  footer_qr     TEXT,                           -- USYS:<b58>:FOOTER:<hex>[:<loc_hex>]
  hash_sha3     TEXT,                           -- SHA3-512 of the current bytes (integrity baseline)
  hash_blake2   TEXT,                           -- BLAKE2b-512 of the same
  sha3_fp       TEXT,
  blake2_fp     TEXT,
  state         TEXT    NOT NULL DEFAULT 'white',   -- white | grey | black
  tier          INTEGER NOT NULL DEFAULT 1,         -- 1..4 (T1 newest .. T4), rotate_clonepool_tiers
  size          INTEGER NOT NULL DEFAULT 0,
  version       TEXT    NOT NULL DEFAULT 'v1',      -- the pool's local label
  source_path   TEXT,
  notes         TEXT,
  addr_scheme   TEXT    NOT NULL DEFAULT 'filename-hex-v1',   -- content-v2 once a hash is present
  sensitive     INTEGER NOT NULL DEFAULT 0,
  qr_valid      INTEGER NOT NULL DEFAULT 0,
  verified_at   TEXT,
  intaked_at    TEXT    NOT NULL DEFAULT (datetime('now')),
  updated_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_clonepool_name  ON clonepool(name);
CREATE INDEX IF NOT EXISTS idx_clonepool_state ON clonepool(state);
CREATE INDEX IF NOT EXISTS idx_clonepool_tier  ON clonepool(tier);

-- ── custody: append-only chain of evidence (never updated, never deleted) ────
CREATE TABLE IF NOT EXISTS custody (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  hex_id     TEXT NOT NULL,
  name       TEXT NOT NULL,
  qr_top     TEXT,
  qr_bottom  TEXT,
  state      TEXT NOT NULL DEFAULT 'white',
  action     TEXT NOT NULL,                     -- intake | dir_intake | clone_out | pull | self_register | backend_install ...
  actor      TEXT NOT NULL DEFAULT 'usys',
  validated  INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_custody_hex ON custody(hex_id);

-- ── glossary: the human catalog (hex == clonepool.hex_id) ────────────────────
CREATE TABLE IF NOT EXISTS glossary (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  hex          TEXT NOT NULL UNIQUE,
  b58          TEXT,
  name         TEXT NOT NULL,
  category_hex TEXT,
  description  TEXT,
  state        TEXT NOT NULL DEFAULT 'white',
  version      TEXT,
  platform     TEXT,
  backend      TEXT,
  size         INTEGER NOT NULL DEFAULT 0,
  pool_path    TEXT,
  sidecar      TEXT,
  amended      INTEGER NOT NULL DEFAULT 0,
  intaked_at   TEXT NOT NULL DEFAULT (datetime('now')),
  grace_until  TEXT,
  evicted_at   TEXT,
  notes        TEXT
);
CREATE INDEX IF NOT EXISTS idx_glossary_name ON glossary(name);

CREATE TABLE IF NOT EXISTS categories (
  hex         TEXT PRIMARY KEY,                 -- to_hex(category name), e.g. 73637269707473 = scripts
  name        TEXT NOT NULL UNIQUE,
  description TEXT
);
INSERT OR IGNORE INTO categories (hex, name, description) VALUES
  ('73637269707473', 'scripts', 'shell, python, node, powershell scripts'),
  ('7061636b61676573', 'packages', 'installed packages reported by translator.sh backends'),
  ('6469726563746f7279', 'directory', 'directory snapshots'),
  ('636f6e66696773', 'configs', 'configuration files'),
  ('646f6373', 'docs', 'documentation');

-- ── packages / versions / deps: the version ledger ───────────────────────────
-- versions.package references packages(name); index.js satisfies the FK with
-- INSERT OR IGNORE INTO packages (name), so name is the only NOT NULL column.
CREATE TABLE IF NOT EXISTS packages (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  name        TEXT NOT NULL UNIQUE,
  version     TEXT,
  description TEXT,
  category    TEXT,
  author      TEXT,
  license     TEXT,
  layer       TEXT DEFAULT 'both',
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS versions (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  package     TEXT NOT NULL REFERENCES packages(name),
  version     TEXT NOT NULL,                    -- ledger ordinal vN: distinct contents ever seen for the name
  store_path  TEXT NOT NULL,                    -- <hex_id>/versions/<sha3[0:16]>  (R2 key of the bytes)
  hash_sha3   TEXT NOT NULL,
  hash_blake2 TEXT,
  size        INTEGER NOT NULL DEFAULT 0,
  note        TEXT,                             -- 'pool:vN <notes>' (the pool's local label, since 2026-09-28)
  signed_by   TEXT,
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_versions_package ON versions(package, created_at);
CREATE INDEX IF NOT EXISTS idx_versions_hash    ON versions(hash_sha3);

CREATE TABLE IF NOT EXISTS deps (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  package     TEXT NOT NULL,
  depends_on  TEXT NOT NULL,
  version_req TEXT,
  optional    INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(package, depends_on)
);

-- ── connections: the CONNECTIONS.md graph (Atlas) ────────────────────────────
CREATE TABLE IF NOT EXISTS connections (
  hex         TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  path        TEXT NOT NULL,
  area        TEXT,
  description TEXT,
  key_fact    TEXT,
  source_file TEXT,
  state       TEXT NOT NULL DEFAULT 'white',
  links       TEXT,                             -- JSON list of hexes
  updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_connections_area ON connections(area);
CREATE INDEX IF NOT EXISTS idx_connections_path ON connections(path);

-- ── toc: table of contents (read-only in the worker) ─────────────────────────
CREATE TABLE IF NOT EXISTS toc (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  title       TEXT NOT NULL,
  parent_id   INTEGER REFERENCES toc(id),
  position    INTEGER,
  description TEXT,
  layer       TEXT DEFAULT 'both'
);
CREATE TABLE IF NOT EXISTS toc_entries (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  toc_id      INTEGER NOT NULL REFERENCES toc(id) ON DELETE CASCADE,
  package_id  INTEGER NOT NULL REFERENCES packages(id) ON DELETE CASCADE,
  position    INTEGER
);

-- ── peer review (identical to ../peer-review/schema.sql; kept in one file so
--    one `d1 execute` stands the whole worker up) ────────────────────────────
CREATE TABLE IF NOT EXISTS submissions (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  hex            TEXT    NOT NULL UNIQUE,
  name           TEXT    NOT NULL,
  description    TEXT    DEFAULT '',
  category       TEXT    DEFAULT NULL,
  platform       TEXT    DEFAULT NULL,
  submitter      TEXT    DEFAULT 'anonymous',
  artifact_url   TEXT    DEFAULT NULL,
  status         TEXT    NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected','revoked')),
  submitted_at   TEXT    NOT NULL DEFAULT (datetime('now')),
  reviewed_at    TEXT    DEFAULT NULL
);
CREATE TABLE IF NOT EXISTS reviews (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  submission_hex  TEXT    NOT NULL,
  reviewer        TEXT    NOT NULL DEFAULT 'anonymous',
  vote            TEXT    NOT NULL CHECK(vote IN ('approve','reject','abstain')),
  notes           TEXT    DEFAULT NULL,
  voted_at        TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_reviews_hex ON reviews(submission_hex);
CREATE TABLE IF NOT EXISTS revocations (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  hex            TEXT    NOT NULL UNIQUE,
  reason         TEXT    NOT NULL DEFAULT 'no reason provided',
  revoked_by     TEXT    NOT NULL DEFAULT 'admin',
  superseded_by  TEXT    DEFAULT NULL,
  revoked_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS advertisement_feed (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  hex            TEXT    NOT NULL UNIQUE,
  name           TEXT    NOT NULL,
  description    TEXT    DEFAULT '',
  category       TEXT    DEFAULT NULL,
  platform       TEXT    DEFAULT NULL,
  approvals      INTEGER DEFAULT 0,
  artifact_url   TEXT    DEFAULT NULL,
  qr_data        TEXT    DEFAULT NULL,
  revoked        INTEGER NOT NULL DEFAULT 0,
  revoked_at     TEXT    DEFAULT NULL,
  advertised_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_feed_category ON advertisement_feed(category);
CREATE INDEX IF NOT EXISTS idx_feed_platform ON advertisement_feed(platform);
CREATE INDEX IF NOT EXISTS idx_feed_revoked  ON advertisement_feed(revoked);
