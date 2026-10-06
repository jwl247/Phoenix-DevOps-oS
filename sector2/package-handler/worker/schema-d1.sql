-- Phoenix custody D1 schema (packages-worker's PHOENIX_DB), structure only, no data.
-- Exported 2026-09-29 from phoenix_dev_db with: wrangler d1 export phoenix_dev_db --remote --no-data
-- 50 tables, 35 indexes. Used by sector3/worker-up/dataplane-up.sh to stand up a new data plane.
-- Re-export after any live schema change so this file stays the truth.

PRAGMA defer_foreign_keys=TRUE;
CREATE TABLE dependencies (     id               INTEGER PRIMARY KEY,     package_id       INTEGER NOT NULL,     depends_on_name  TEXT NOT NULL,     min_version      TEXT,     max_version      TEXT,     layer            TEXT DEFAULT 'both' );
CREATE TABLE installed (     id            INTEGER PRIMARY KEY,     package_id    INTEGER NOT NULL,     installed_at  TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),     install_path  TEXT NOT NULL,     installed_by  TEXT,     layer         TEXT , backend TEXT DEFAULT 'direct');
CREATE TABLE history (     id          INTEGER PRIMARY KEY,     action      TEXT NOT NULL,     package_id  INTEGER,     target_dir  TEXT,     timestamp   TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),     status      TEXT,     layer       TEXT,     notes       TEXT );
CREATE TABLE toc (     id          INTEGER PRIMARY KEY,     title       TEXT NOT NULL,     parent_id   INTEGER,     position    INTEGER,     description TEXT,     layer       TEXT DEFAULT 'both' );
CREATE TABLE toc_entries (     id          INTEGER PRIMARY KEY,     toc_id      INTEGER NOT NULL,     package_id  INTEGER NOT NULL,     position    INTEGER );
CREATE TABLE aliases (     id          INTEGER PRIMARY KEY,     alias       TEXT NOT NULL UNIQUE,     target_type TEXT NOT NULL,     target_id   INTEGER,     target_name TEXT,     layer       TEXT DEFAULT 'both',     created_at  TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) );
CREATE TABLE kernel_slots (     id          INTEGER PRIMARY KEY,     slot        INTEGER UNIQUE NOT NULL,     kernel_id   INTEGER,     status      TEXT,     kernel_type TEXT,     loaded_at   TEXT,     checksum    TEXT,     layer       TEXT DEFAULT 'both',     notes       TEXT );
CREATE TABLE sideloads (     id          INTEGER PRIMARY KEY,     slot        INTEGER NOT NULL,     package_id  INTEGER NOT NULL,     priority    INTEGER,     status      TEXT,     layer       TEXT DEFAULT 'both' );
CREATE TABLE rotation_log (     id            INTEGER PRIMARY KEY,     from_slot     INTEGER,     to_slot       INTEGER,     trigger       TEXT,     traffic_load  REAL,     layer         TEXT,     timestamp     TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),     success       INTEGER );
CREATE TABLE subscribers (     id              INTEGER PRIMARY KEY,     name            TEXT NOT NULL,     service         TEXT NOT NULL,     tunnel_in       TEXT,     tunnel_out      TEXT,     status          TEXT,     provisioned_at  TEXT,     last_fed        TEXT,     layer           TEXT DEFAULT 'both' );
CREATE TABLE feed_log (     id            INTEGER PRIMARY KEY,     subscriber_id INTEGER NOT NULL,     package_id    INTEGER,     action        TEXT,     status        TEXT,     bytes_moved   INTEGER,     timestamp     TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) );
CREATE TABLE layer_assignments (     id           INTEGER PRIMARY KEY,     service      TEXT NOT NULL,     layer        TEXT NOT NULL,     native_call  TEXT,     can_migrate  INTEGER DEFAULT 1,     reason       TEXT );
CREATE TABLE system_telemetry (     id            INTEGER PRIMARY KEY,     metric        TEXT NOT NULL,     value         REAL NOT NULL,     layer         TEXT,     slot          INTEGER,     subscriber_id INTEGER,     timestamp     TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) );
CREATE TABLE system_snapshots (     id         INTEGER PRIMARY KEY,     label      TEXT NOT NULL,     layer      TEXT,     state      TEXT,     checksum   TEXT,     is_good    INTEGER DEFAULT 1,     created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')) );
CREATE TABLE entry_points (     id      INTEGER PRIMARY KEY,     name    TEXT UNIQUE NOT NULL,     status  TEXT DEFAULT 'reserved',     module  TEXT,     layer   TEXT DEFAULT 'both',     config  TEXT,     notes   TEXT );
CREATE TABLE files (     id           INTEGER PRIMARY KEY AUTOINCREMENT,     package_id   INTEGER NOT NULL REFERENCES packages(id) ON DELETE CASCADE,     filename     TEXT NOT NULL,     filepath     TEXT NOT NULL,     filetype     TEXT,     checksum     TEXT,     size_bytes   INTEGER,     content      BLOB,     layer        TEXT DEFAULT 'both' );
CREATE TABLE versions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    package     TEXT    NOT NULL,
    version     TEXT    NOT NULL,
    store_path  TEXT    NOT NULL,
    hash_sha3   TEXT,
    hash_blake2 TEXT,
    size        INTEGER,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    note        TEXT    DEFAULT '',
    signed_by   TEXT,
    FOREIGN KEY (package) REFERENCES packages(name) ON DELETE CASCADE
);
CREATE TABLE swaplog (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    package     TEXT    NOT NULL,
    from_ver    TEXT,
    to_ver      TEXT,
    action      TEXT    NOT NULL,
    ts          DATETIME DEFAULT CURRENT_TIMESTAMP,
    note        TEXT    DEFAULT '',
    user_id     TEXT
);
CREATE TABLE audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          DATETIME DEFAULT CURRENT_TIMESTAMP,
    action      TEXT    NOT NULL,
    target_type TEXT,
    target_id   TEXT,
    user_id     TEXT,
    machine     TEXT,
    ip          TEXT,
    detail      TEXT,
    result      TEXT
);
CREATE TABLE repair_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          DATETIME DEFAULT CURRENT_TIMESTAMP,
    package     TEXT,
    hex_id      TEXT,
    issue       TEXT,
    action_taken TEXT,
    result      TEXT,
    user_id     TEXT
);
CREATE TABLE clonepool (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    hex_id        TEXT    NOT NULL UNIQUE,
    b58           TEXT    NOT NULL,
    name          TEXT    NOT NULL,
    original_name TEXT,
    pool_path     TEXT,
    sidecar_path  TEXT,
    header_qr     TEXT,
    footer_qr     TEXT,
    hash_sha3     TEXT,
    hash_blake2   TEXT,
    sha3_fp       TEXT,
    blake2_fp     TEXT,
    state         TEXT    DEFAULT 'white',
    tier          INTEGER DEFAULT 1,
    size          INTEGER,
    version       TEXT,
    source_path   TEXT,
    intaked_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME,
    qr_valid      INTEGER DEFAULT 0,
    notes         TEXT
, addr_scheme TEXT, superseded_by TEXT, superseded_at DATETIME, verified_at DATETIME, hash_alg TEXT, sensitive INTEGER DEFAULT 0);
CREATE TABLE quarantine (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    hex_id      TEXT,
    name        TEXT,
    reason      TEXT,
    flagged_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    flagged_by  TEXT,
    resolved    INTEGER DEFAULT 0,
    resolved_at DATETIME,
    resolved_by TEXT,
    notes       TEXT
);
CREATE TABLE mirrors (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    hex_id        TEXT    NOT NULL,
    location      TEXT    NOT NULL,
    mirror_type   TEXT    DEFAULT 'local',
    last_verified DATETIME,
    available     INTEGER DEFAULT 1,
    notes         TEXT,
    FOREIGN KEY (hex_id) REFERENCES clonepool(hex_id)
);
CREATE TABLE categories (
    hex         TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    description TEXT DEFAULT ''
);
-- Seeded from production 2026-10-03: glossary.category_hex REFERENCES categories(hex),
-- so a D1 built from this file without these rows failed every glossary write (500).
-- hex = hex(name) except 'subsystem' (= hex('subsys')), kept exactly as production has it.
INSERT OR IGNORE INTO categories (hex, name, description) VALUES ('73797374656d', 'system', 'OS tools, daemons, kernel-level');
INSERT OR IGNORE INTO categories (hex, name, description) VALUES ('6e6574776f726b', 'network', 'VPN, firewall, comms, protocols');
INSERT OR IGNORE INTO categories (hex, name, description) VALUES ('7365637572697479', 'security', 'auth, hashing, verification, hardening');
INSERT OR IGNORE INTO categories (hex, name, description) VALUES ('73746f72616765', 'storage', 'clonepool, vaults, drives, filesystems');
INSERT OR IGNORE INTO categories (hex, name, description) VALUES ('72756e74696d65', 'runtime', 'interpreters, language runtimes');
INSERT OR IGNORE INTO categories (hex, name, description) VALUES ('746f6f6c73', 'tools', 'CLI utilities, dev tools, helpers');
INSERT OR IGNORE INTO categories (hex, name, description) VALUES ('6672616d65776f726b', 'framework', 'Phoenix, Helix, Propagator components');
INSERT OR IGNORE INTO categories (hex, name, description) VALUES ('6461746162617365', 'database', 'SQLite, D1, catalog, schemas');
INSERT OR IGNORE INTO categories (hex, name, description) VALUES ('73637269707473', 'scripts', 'shell scripts, automation, wrappers');
INSERT OR IGNORE INTO categories (hex, name, description) VALUES ('6d65646961', 'media', 'images, QR codes, visual assets');
INSERT OR IGNORE INTO categories (hex, name, description) VALUES ('74797065', 'type', 'file type classification');
INSERT OR IGNORE INTO categories (hex, name, description) VALUES ('756e6b6e6f776e', 'unknown', 'uncategorized, needs review');
INSERT OR IGNORE INTO categories (hex, name, description) VALUES ('7061636b61676573', 'packages', 'installed packages from any backend');
INSERT OR IGNORE INTO categories (hex, name, description) VALUES ('66696c6573', 'files', 'individual files intaked from outside');
INSERT OR IGNORE INTO categories (hex, name, description) VALUES ('737562737973', 'subsystem', 'Frank, sectors, conductors, props');
INSERT OR IGNORE INTO categories (hex, name, description) VALUES ('776f726b657273', 'workers', 'Cloudflare workers');
INSERT OR IGNORE INTO categories (hex, name, description) VALUES ('6469726563746f7279', 'directory', 'Directory-level snapshot entries from intake_directory');
CREATE TABLE signatures (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    hex_id     TEXT    NOT NULL,
    package    TEXT,
    version    TEXT,
    signed_by  TEXT,
    signature  TEXT,
    method     TEXT    DEFAULT 'ed25519',
    signed_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    valid      INTEGER DEFAULT 1
);
CREATE TABLE vulnerability_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    package     TEXT    NOT NULL,
    cve_id      TEXT,
    severity    TEXT,
    description TEXT,
    detected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    resolved    INTEGER DEFAULT 0,
    resolved_at DATETIME,
    notes       TEXT
);
CREATE TABLE health_checks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    package     TEXT,
    hex_id      TEXT,
    checked_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    hash_match  INTEGER,
    pool_exists INTEGER,
    sidecar_ok  INTEGER,
    qr_valid    INTEGER,
    result      TEXT,
    notes       TEXT
);
CREATE TABLE metrics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          DATETIME DEFAULT CURRENT_TIMESTAMP,
    event_type  TEXT    NOT NULL,
    package     TEXT,
    backend     TEXT,
    platform    TEXT,
    duration_ms INTEGER,
    success     INTEGER,
    detail      TEXT
);
CREATE TABLE sync_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           DATETIME DEFAULT CURRENT_TIMESTAMP,
    direction    TEXT,
    target       TEXT,
    records_sent INTEGER,
    records_recv INTEGER,
    status       TEXT,
    error        TEXT,
    machine      TEXT
);
CREATE TABLE environments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    description TEXT,
    active      INTEGER DEFAULT 1,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE manifests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    description TEXT,
    environment TEXT    DEFAULT 'prod',
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME,
    content     TEXT,
    active      INTEGER DEFAULT 1
);
CREATE TABLE hooks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    package     TEXT    NOT NULL,
    hook_type   TEXT    NOT NULL,
    script      TEXT    NOT NULL,
    active      INTEGER DEFAULT 1,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    notes       TEXT
);
CREATE TABLE owners (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    package     TEXT    NOT NULL,
    owner_name  TEXT,
    owner_email TEXT,
    role        TEXT,
    assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    notes       TEXT
);
CREATE TABLE notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type TEXT    NOT NULL,
    target_id   TEXT    NOT NULL,
    note        TEXT    NOT NULL,
    written_by  TEXT,
    written_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    important   INTEGER DEFAULT 0
);
CREATE TABLE packages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL UNIQUE,
    version      TEXT,
    backend      TEXT,
    platform     TEXT,
    installed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME,
    hash_sha3    TEXT,
    hash_blake2  TEXT,
    manifest     TEXT,
    hex_id       TEXT,
    b58          TEXT,
    pool_path    TEXT,
    sidecar_path TEXT,
    state        TEXT    DEFAULT 'white',
    tier         INTEGER DEFAULT 1,
    environment  TEXT    DEFAULT 'prod',
    owner        TEXT,
    notes        TEXT,
    description  TEXT    DEFAULT ''
);
CREATE TABLE deps (
    package     TEXT NOT NULL,
    depends_on  TEXT NOT NULL,
    version_req TEXT,
    optional    INTEGER DEFAULT 0,
    PRIMARY KEY (package, depends_on)
);
CREATE TABLE backends (
    name        TEXT PRIMARY KEY,
    platform    TEXT,
    available   INTEGER DEFAULT 0,
    last_check  DATETIME,
    priority    INTEGER DEFAULT 5,
    notes       TEXT
);
CREATE TABLE transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    action      TEXT    NOT NULL,
    package     TEXT    NOT NULL,
    status      TEXT    NOT NULL,
    backend     TEXT,
    duration_ms INTEGER,
    timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP,
    error       TEXT,
    machine     TEXT,
    user_id     TEXT
);
CREATE TABLE glossary (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    hex          TEXT    NOT NULL UNIQUE,
    b58          TEXT,
    name         TEXT    NOT NULL,
    category_hex TEXT    REFERENCES categories(hex),
    description  TEXT    DEFAULT '',
    state        TEXT    DEFAULT 'white',
    version      TEXT,
    platform     TEXT,
    backend      TEXT,
    size         INTEGER,
    pool_path    TEXT,
    sidecar      TEXT,
    amended      INTEGER DEFAULT 0,
    intaked_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    grace_until  DATETIME,
    evicted_at   DATETIME,
    notes        TEXT
);
CREATE TABLE custody (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, hex_id TEXT NOT NULL, qr_top TEXT, qr_bottom TEXT, state TEXT DEFAULT 'white', action TEXT, actor TEXT, validated INTEGER DEFAULT 0, intaked_at DATETIME DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE glossary_access_requests (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  name        TEXT NOT NULL,
  github      TEXT NOT NULL,
  email       TEXT NOT NULL,
  role        TEXT,
  reason      TEXT,
  status      TEXT NOT NULL DEFAULT 'pending',
  token       TEXT UNIQUE,
  requested_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  approved_by  TEXT,
  approved_at  TEXT,
  denied_at    TEXT,
  notes        TEXT
);
CREATE TABLE glossary_access_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  token       TEXT,
  name        TEXT,
  github      TEXT,
  path        TEXT,
  accessed_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  ip          TEXT,
  result      TEXT NOT NULL DEFAULT 'granted'
);
CREATE TABLE submissions (id INTEGER PRIMARY KEY AUTOINCREMENT, hex TEXT NOT NULL UNIQUE, name TEXT NOT NULL, description TEXT DEFAULT '', category TEXT DEFAULT NULL, platform TEXT DEFAULT NULL, submitter TEXT DEFAULT 'anonymous', artifact_url TEXT DEFAULT NULL, status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected','revoked')), submitted_at TEXT NOT NULL DEFAULT (datetime('now')), reviewed_at TEXT DEFAULT NULL, submission_type TEXT DEFAULT 'artifact', content TEXT, tags TEXT);
CREATE TABLE reviews (id INTEGER PRIMARY KEY AUTOINCREMENT, submission_hex TEXT NOT NULL, reviewer TEXT NOT NULL DEFAULT 'anonymous', vote TEXT NOT NULL CHECK(vote IN ('approve','reject','abstain')), notes TEXT DEFAULT NULL, voted_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE revocations (id INTEGER PRIMARY KEY AUTOINCREMENT, hex TEXT NOT NULL UNIQUE, reason TEXT NOT NULL DEFAULT 'no reason provided', revoked_by TEXT NOT NULL DEFAULT 'admin', superseded_by TEXT DEFAULT NULL, revoked_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE advertisement_feed (id INTEGER PRIMARY KEY AUTOINCREMENT, hex TEXT NOT NULL UNIQUE, name TEXT NOT NULL, description TEXT DEFAULT '', category TEXT DEFAULT NULL, platform TEXT DEFAULT NULL, approvals INTEGER DEFAULT 0, artifact_url TEXT DEFAULT NULL, qr_data TEXT DEFAULT NULL, revoked INTEGER NOT NULL DEFAULT 0, revoked_at TEXT DEFAULT NULL, advertised_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE office_authors (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  author_id         TEXT    NOT NULL,               -- canonical identity, shared across credentials
  credential_type   TEXT    NOT NULL                -- fingerprint | windows | google
                      CHECK(credential_type IN ('fingerprint','windows','google')),
  credential_value  TEXT    NOT NULL,               -- the fingerprint hash / Windows SID / Google sub
  linked_at         TEXT    NOT NULL DEFAULT (datetime('now')),
  UNIQUE(credential_type, credential_value)          -- one fingerprint/SID/sub can't attach to two authors
);
CREATE TABLE office_documents (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  hex                    TEXT    NOT NULL UNIQUE,        -- document identity hash (file-format.js documentIdentityHash)
  b58                    TEXT    DEFAULT NULL,           -- short TAV address, matches the file's header QR
  state                  TEXT    NOT NULL DEFAULT 'DRAFT'
                           CHECK(state IN ('DRAFT','PENDING_REVIEW','SIGNED')),
  author_id              TEXT    NOT NULL,               -- FK -> office_authors.author_id
  counterparty_phone     TEXT    DEFAULT NULL,
  counterparty_carrier   TEXT    DEFAULT NULL,
  counterparty_email     TEXT    DEFAULT NULL,
  hash_sha3              TEXT    DEFAULT NULL,           -- set at signing — the tamper-detection baseline
  hash_blake2            TEXT    DEFAULT NULL,
  supersedes_hex         TEXT    DEFAULT NULL,           -- set on a change order; the hex it corrects
  file_path              TEXT    DEFAULT NULL,           -- where the .office file actually lives (local path or R2 pointer)
  signed_at              TEXT    DEFAULT NULL,
  created_at             TEXT    NOT NULL DEFAULT (datetime('now')),
  updated_at             TEXT    DEFAULT NULL
);
CREATE TABLE office_notifications (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_hex           TEXT    NOT NULL,               -- document identity (mirrors office_documents.hex / the .office header)
  doc_hash          TEXT    DEFAULT NULL,           -- the signed-baseline hash the attempt failed against
  attempt_field     TEXT    DEFAULT NULL,           -- which field the alteration targeted, if known
  attempt_at        TEXT    NOT NULL,               -- when the tamper was detected (ISO 8601)
  to_address        TEXT    NOT NULL,               -- resolved send target: carrier SMS-gateway address or plain email
  via               TEXT    NOT NULL                -- how it's delivered
                      CHECK(via IN ('sms-gateway','email')),
  ack_token         TEXT    NOT NULL UNIQUE,        -- single-use token; the ack link IS the auth, no account needed
  escalation_level  INTEGER NOT NULL DEFAULT 1      -- 1..5, bumped by the scheduled re-scan; caps at 5 and keeps sending
                      CHECK(escalation_level BETWEEN 1 AND 5),
  send_count        INTEGER NOT NULL DEFAULT 0,     -- total sends (initial + every escalation)
  last_sent_at      TEXT    DEFAULT NULL,
  last_error        TEXT    DEFAULT NULL,           -- transport error from the most recent send attempt, if any
  acknowledged_at   TEXT    DEFAULT NULL,           -- set when the ack link is hit; stops all further escalation
  created_at        TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE connections (
  hex          TEXT PRIMARY KEY,
  name         TEXT NOT NULL,
  path         TEXT NOT NULL,
  area         TEXT,
  description  TEXT,
  key_fact     TEXT,
  source_file  TEXT,
  state        TEXT DEFAULT 'white',
  links        TEXT DEFAULT '[]',
  updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_versions_package  ON versions(package);
CREATE INDEX idx_audit_ts          ON audit_log(ts);
CREATE INDEX idx_audit_target      ON audit_log(target_id);
CREATE INDEX idx_clonepool_hex     ON clonepool(hex_id);
CREATE INDEX idx_clonepool_name    ON clonepool(name);
CREATE INDEX idx_clonepool_state   ON clonepool(state);
CREATE INDEX idx_health_package    ON health_checks(package);
CREATE INDEX idx_vuln_package      ON vulnerability_log(package);
CREATE INDEX idx_swaplog_package   ON swaplog(package);
CREATE INDEX idx_metrics_ts        ON metrics(ts);
CREATE INDEX idx_sync_ts           ON sync_log(ts);
CREATE INDEX idx_packages_name     ON packages(name);
CREATE INDEX idx_packages_hex      ON packages(hex_id);
CREATE INDEX idx_packages_state    ON packages(state);
CREATE INDEX idx_transactions_pkg  ON transactions(package);
CREATE INDEX idx_transactions_ts   ON transactions(timestamp);
CREATE INDEX idx_glossary_name     ON glossary(name);
CREATE INDEX idx_glossary_hex      ON glossary(hex);
CREATE INDEX idx_glossary_state    ON glossary(state);
CREATE INDEX idx_glossary_category ON glossary(category_hex);
CREATE INDEX idx_gar_status ON glossary_access_requests(status);
CREATE INDEX idx_gar_token  ON glossary_access_requests(token);
CREATE INDEX idx_gal_token  ON glossary_access_log(token, accessed_at);
CREATE INDEX idx_reviews_hex ON reviews(submission_hex);
CREATE INDEX idx_feed_category ON advertisement_feed(category);
CREATE INDEX idx_feed_platform ON advertisement_feed(platform);
CREATE INDEX idx_feed_revoked ON advertisement_feed(revoked);
CREATE INDEX idx_authors_author_id ON office_authors(author_id);
CREATE INDEX idx_documents_author ON office_documents(author_id);
CREATE INDEX idx_documents_state  ON office_documents(state);
CREATE INDEX idx_documents_supersedes ON office_documents(supersedes_hex);
CREATE INDEX idx_notif_doc  ON office_notifications(doc_hex);
CREATE INDEX idx_notif_open ON office_notifications(acknowledged_at, last_sent_at);
CREATE INDEX idx_connections_area ON connections(area);
CREATE INDEX idx_connections_name ON connections(name);
