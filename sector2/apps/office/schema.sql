-- sector2/apps/office/schema.sql
-- Phoenix Office — D1 Schema Additions
-- DB: phoenix_dev_db (D1)
-- Apply by hand (no migration framework in this repo — matches
-- sector2/package-handler/peer-review/schema.sql's precedent):
--   wrangler d1 execute phoenix_dev_db --file=sector2/apps/office/schema.sql
--
-- Principle: these are REFERENCE/custody rows, not the source of truth.
-- The .office file itself (lib/file-format.js) is authoritative — losing
-- either table below must never invalidate a document's own embedded
-- proof. See DESIGN.md "Self-sovereign truth".
-- Version: 1.0.0

-- ══════════════════════════════════════════════════════════════════════════════
-- TABLE: office_authors
-- Canonical author identity, pluggable across credential types (DESIGN.md
-- "Authorship = pluggable identity, Phoenix's own always sovereign").
-- One author_id can carry multiple linked credentials — a Phoenix hardware
-- fingerprint, a Windows account, a Google sign-in — so the same person's
-- documents forged from different machines/sign-in methods still resolve
-- to one identity. The Phoenix fingerprint option must always work with
-- zero rows in this table at all — it's the sovereign fallback, not
-- dependent on this D1 table existing or being reachable.
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS office_authors (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  author_id         TEXT    NOT NULL,               -- canonical identity, shared across credentials
  credential_type   TEXT    NOT NULL                -- fingerprint | windows | google
                      CHECK(credential_type IN ('fingerprint','windows','google')),
  credential_value  TEXT    NOT NULL,               -- the fingerprint hash / Windows SID / Google sub
  linked_at         TEXT    NOT NULL DEFAULT (datetime('now')),
  UNIQUE(credential_type, credential_value)          -- one fingerprint/SID/sub can't attach to two authors
);

-- Fast lookup of every credential belonging to one author
CREATE INDEX IF NOT EXISTS idx_authors_author_id ON office_authors(author_id);

-- ══════════════════════════════════════════════════════════════════════════════
-- TABLE: office_documents
-- Custody/reference record for a signed (or in-progress) Office document.
-- hex/b58 mirror the TAV address embedded in the .office file's own header
-- (lib/file-format.js) — this row is a pointer and audit trail, not the
-- proof itself. counterparty contact is denormalized here on purpose
-- (DESIGN.md: captured on the document, never looked up via account) so
-- the notification path (notify.js) never depends on this table either.
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS office_documents (
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

CREATE INDEX IF NOT EXISTS idx_documents_author ON office_documents(author_id);
CREATE INDEX IF NOT EXISTS idx_documents_state  ON office_documents(state);
CREATE INDEX IF NOT EXISTS idx_documents_supersedes ON office_documents(supersedes_hex);
