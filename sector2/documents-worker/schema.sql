-- documents-worker D1 schema — Phoenix DevOps OS
-- The document IS the import process. Forged, not created.
-- Self-contained: manifest sealed at forge defines all possible operations.
-- Compliance: SOC 2 / HIPAA / GDPR
--
-- Deploy: wrangler d1 execute phoenix_dev_db --remote --file=schema.sql

-- ── Core documents table ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS documents (
  -- Identity (TAV = hash(content + manifest) → first 8 bytes → base58)
  tav              TEXT    PRIMARY KEY,
  sha256           TEXT    NOT NULL,        -- hash of content only
  manifest_hash    TEXT    NOT NULL,        -- hash of manifest JSON (tamper detection)
  combined_hash    TEXT    NOT NULL,        -- hash(content + manifest) = TAV source
  sha3_note        TEXT,                    -- SHA3-512 from intake.sh if provided

  -- Content
  filename         TEXT    NOT NULL,
  size_bytes       INTEGER NOT NULL,
  mime_type        TEXT    NOT NULL DEFAULT 'application/octet-stream',
  r2_key           TEXT    NOT NULL,        -- R2 object key (= tav)

  -- Ownership
  owner            TEXT    NOT NULL DEFAULT 'system',

  -- Forge manifest (sealed at forge, immutable)
  -- JSON: { version, can_read, can_convert, can_execute, can_version,
  --         can_review, can_index, can_transmit, can_share,
  --         expires_at, life_first, witness_required }
  manifest         TEXT    NOT NULL DEFAULT '{}',

  -- Forge stage: draft → proposed → forged
  forge_stage      TEXT    NOT NULL DEFAULT 'draft',
  forged_at        TEXT,                    -- ISO UTC, set when stage = forged
  forge_receipt_id INTEGER,                 -- FK to forge_receipts

  -- Document identity metadata
  title            TEXT,
  description      TEXT,
  sector           TEXT,
  tags             TEXT    NOT NULL DEFAULT '[]',

  -- Compliance classification
  privacy          TEXT    NOT NULL DEFAULT 'private',
  classification   TEXT    NOT NULL DEFAULT 'internal',

  -- Encryption
  encrypted        INTEGER NOT NULL DEFAULT 0,
  encrypted_key_id TEXT,

  -- Versioning / document family
  version          INTEGER NOT NULL DEFAULT 1,
  parent_tav       TEXT,                    -- previous version
  conversion_of    TEXT,                    -- source doc if this is a conversion
  conversion_fmt   TEXT,                    -- format that was requested

  -- Lifecycle
  status           TEXT    NOT NULL DEFAULT 'active',
  mutable          INTEGER NOT NULL DEFAULT 0,
  created_at       TEXT    NOT NULL,
  archived_at      TEXT,
  retain_until     TEXT,
  legal_hold       INTEGER NOT NULL DEFAULT 0,

  FOREIGN KEY (parent_tav)    REFERENCES documents(tav),
  FOREIGN KEY (conversion_of) REFERENCES documents(tav),
  CHECK (forge_stage   IN ('draft','proposed','forged')),
  CHECK (privacy       IN ('public','internal','private','restricted')),
  CHECK (classification IN ('public','internal','confidential','restricted')),
  CHECK (status        IN ('active','archived')),
  CHECK (mutable       IN (0,1)),
  CHECK (encrypted     IN (0,1)),
  CHECK (legal_hold    IN (0,1))
);

CREATE INDEX IF NOT EXISTS idx_doc_owner       ON documents (owner);
CREATE INDEX IF NOT EXISTS idx_doc_sector      ON documents (sector);
CREATE INDEX IF NOT EXISTS idx_doc_mime        ON documents (mime_type);
CREATE INDEX IF NOT EXISTS idx_doc_created     ON documents (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_doc_stage       ON documents (forge_stage);
CREATE INDEX IF NOT EXISTS idx_doc_status      ON documents (status);
CREATE INDEX IF NOT EXISTS idx_doc_parent      ON documents (parent_tav);
CREATE INDEX IF NOT EXISTS idx_doc_conv_of     ON documents (conversion_of);
CREATE INDEX IF NOT EXISTS idx_doc_class       ON documents (classification);

-- ── Forge receipts — immutable record of every forge act ──────────────────────
-- Chain of evidence. Even if a document is archived, the forge receipt remains.

CREATE TABLE IF NOT EXISTS forge_receipts (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  tav              TEXT    NOT NULL,
  forged_by        TEXT    NOT NULL,        -- actor who sealed it
  witnessed_by     TEXT,                    -- second signer (confidential/restricted)
  manifest_hash    TEXT    NOT NULL,        -- at time of forge
  content_hash     TEXT    NOT NULL,        -- sha256 of content at forge
  combined_hash    TEXT    NOT NULL,        -- hash(content+manifest) = TAV source
  forge_ts         TEXT    NOT NULL,        -- ISO UTC
  parent_tav       TEXT,                    -- if forged from another document
  system_state     TEXT                     -- JSON snapshot (kernel version, node, etc.)
);

CREATE INDEX IF NOT EXISTS idx_fr_tav ON forge_receipts (tav);
CREATE INDEX IF NOT EXISTS idx_fr_ts  ON forge_receipts (forge_ts DESC);

-- ── Forge proposals — two-stage witness process for confidential/restricted ───

CREATE TABLE IF NOT EXISTS forge_proposals (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  proposed_tav     TEXT    NOT NULL,        -- TAV that will be assigned on forge
  proposed_by      TEXT    NOT NULL,
  manifest_json    TEXT    NOT NULL,
  content_r2_key   TEXT    NOT NULL,        -- R2 key of staged content
  content_hash     TEXT    NOT NULL,
  filename         TEXT    NOT NULL,
  mime_type        TEXT    NOT NULL,
  owner            TEXT    NOT NULL,
  classification   TEXT    NOT NULL,
  status           TEXT    NOT NULL DEFAULT 'pending_witness',
  proposed_at      TEXT    NOT NULL,
  witnessed_by     TEXT,
  witnessed_at     TEXT,
  expires_at       TEXT    NOT NULL,        -- proposal expires if not witnessed
  metadata_json    TEXT                     -- full intake payload for replay
);

CREATE INDEX IF NOT EXISTS idx_fp_status ON forge_proposals (status);
CREATE INDEX IF NOT EXISTS idx_fp_tav    ON forge_proposals (proposed_tav);

-- ── Compliance: access audit log ──────────────────────────────────────────────
-- Every operation logged. ip_hash = SHA-256 of client IP (no raw IPs stored).

CREATE TABLE IF NOT EXISTS document_access_log (
  id       INTEGER PRIMARY KEY AUTOINCREMENT,
  tav      TEXT    NOT NULL,
  actor    TEXT    NOT NULL,
  action   TEXT    NOT NULL,   -- intake|forge|read|convert|lock|archive|search|witness|deny
  result   TEXT    NOT NULL,   -- ok|denied|error|expired
  ts       TEXT    NOT NULL,
  ip_hash  TEXT,
  detail   TEXT                -- JSON extra context
);

CREATE INDEX IF NOT EXISTS idx_dal_tav    ON document_access_log (tav);
CREATE INDEX IF NOT EXISTS idx_dal_actor  ON document_access_log (actor);
CREATE INDEX IF NOT EXISTS idx_dal_ts     ON document_access_log (ts DESC);
CREATE INDEX IF NOT EXISTS idx_dal_action ON document_access_log (action);

-- ── Capability log — which document capabilities were invoked ─────────────────

CREATE TABLE IF NOT EXISTS capability_log (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  tav        TEXT    NOT NULL,
  capability TEXT    NOT NULL,  -- can_read|can_convert|can_execute|can_transmit|etc.
  actor      TEXT    NOT NULL,
  target     TEXT,              -- e.g. format requested for can_convert
  result     TEXT    NOT NULL,  -- allowed|denied|expired
  ts         TEXT    NOT NULL,
  detail     TEXT
);

CREATE INDEX IF NOT EXISTS idx_cl_tav        ON capability_log (tav);
CREATE INDEX IF NOT EXISTS idx_cl_capability ON capability_log (capability);
CREATE INDEX IF NOT EXISTS idx_cl_result     ON capability_log (result);

-- ── Conversion job queue — LibreOffice headless on phoenix-ext ────────────────

CREATE TABLE IF NOT EXISTS conversion_jobs (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  source_tav    TEXT    NOT NULL,
  source_r2     TEXT    NOT NULL,
  source_mime   TEXT    NOT NULL,
  target_format TEXT    NOT NULL,
  target_ext    TEXT    NOT NULL,
  owner         TEXT    NOT NULL,
  status        TEXT    NOT NULL DEFAULT 'queued',
  result_tav    TEXT,
  error         TEXT,
  queued_at     TEXT    NOT NULL,
  started_at    TEXT,
  completed_at  TEXT,
  FOREIGN KEY (source_tav) REFERENCES documents(tav),
  CHECK (status IN ('queued','running','complete','failed'))
);

CREATE INDEX IF NOT EXISTS idx_cj_status  ON conversion_jobs (status);
CREATE INDEX IF NOT EXISTS idx_cj_source  ON conversion_jobs (source_tav);

-- ── Full-text search ──────────────────────────────────────────────────────────

CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
  tav         UNINDEXED,
  filename,
  title,
  description,
  tags,
  content     = 'documents',
  content_rowid = 'rowid'
);

CREATE TRIGGER IF NOT EXISTS doc_fts_ai AFTER INSERT ON documents
WHEN new.forge_stage = 'forged' BEGIN
  INSERT INTO documents_fts(rowid, tav, filename, title, description, tags)
  VALUES (new.rowid, new.tav, new.filename, new.title, new.description, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS doc_fts_au AFTER UPDATE ON documents
WHEN new.forge_stage = 'forged' BEGIN
  INSERT INTO documents_fts(documents_fts, rowid, tav, filename, title, description, tags)
  VALUES ('delete', old.rowid, old.tav, old.filename, old.title, old.description, old.tags);
  INSERT INTO documents_fts(rowid, tav, filename, title, description, tags)
  VALUES (new.rowid, new.tav, new.filename, new.title, new.description, new.tags);
END;
