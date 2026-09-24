-- phoenix-office/worker/schema.sql
-- Phoenix Office (standalone) — D1 Schema
-- DB: phoenix_office_db (D1) — this product's OWN database, not Phoenix's
-- shared phoenix_dev_db. Table shapes cloned unchanged from
-- sector2/apps/office/schema.sql (2026-09-22) — they were already
-- document-identity-keyed, not filename-keyed, so nothing needed fixing here.
-- Apply by hand (no migration framework, matches Phoenix's own precedent):
--   wrangler d1 execute phoenix_office_db --file=schema.sql --remote
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
  title                  TEXT    DEFAULT NULL,           -- human-readable label (first filled field's value), NOT identity — hex/b58 remain the real address. Browse list shows both.
  legal_hold             INTEGER NOT NULL DEFAULT 0,      -- denormalized current status (0/1) — real audit trail lives in office_legal_holds below
  legal_hold_reason      TEXT    DEFAULT NULL,            -- doubles as the legal matter/case reference, same pattern Microsoft 365 ties a hold to an eDiscovery case
  signed_at              TEXT    DEFAULT NULL,
  created_at             TEXT    NOT NULL DEFAULT (datetime('now')),
  updated_at             TEXT    DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_documents_author ON office_documents(author_id);
CREATE INDEX IF NOT EXISTS idx_documents_state  ON office_documents(state);
CREATE INDEX IF NOT EXISTS idx_documents_supersedes ON office_documents(supersedes_hex);

-- ══════════════════════════════════════════════════════════════════════════════
-- TABLE: office_legal_holds   (2026-09-23)
-- Append-only audit trail — the real record of who placed/released a hold,
-- when, and why. office_documents.legal_hold is a denormalized "current
-- status" flag for fast filtering; this table is the actual history, same
-- relationship as versions/custody elsewhere in Phoenix. A document can be
-- placed and released more than once (e.g. two unrelated matters over its
-- life) — each event gets its own permanent row, never overwritten.
--
-- Modeled after Microsoft 365's eDiscovery hold: a hold ties to a legal
-- matter (the `reason` field doubles as the case/matter reference — no
-- separate "cases" table, this product's scale doesn't need one) and
-- preserves everything, including what would otherwise be removed. Since
-- phoenix-office never deletes a sealed document at all, "block deletion"
-- is already unconditionally true — this table's real job is the audit
-- trail + the visible flag, not enforcement against a delete path that
-- doesn't exist.
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS office_legal_holds (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_hex     TEXT    NOT NULL,
  action      TEXT    NOT NULL CHECK(action IN ('placed','released')),
  by          TEXT    NOT NULL,               -- author_id who placed/released it
  reason      TEXT    DEFAULT NULL,           -- doubles as the legal matter/case reference
  at          TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_legal_holds_doc ON office_legal_holds(doc_hex);

-- ══════════════════════════════════════════════════════════════════════════════
-- MIGRATION — apply once against the already-deployed DB (2026-09-23).
-- CREATE TABLE IF NOT EXISTS above only helps a fresh install; this table
-- was already live before the `title`/`legal_hold`/`legal_hold_reason`
-- columns existed. No migration framework here (see the note at the top) —
-- same hand-applied precedent, run each of these once:
--   wrangler d1 execute phoenix_office_db --command="ALTER TABLE office_documents ADD COLUMN title TEXT DEFAULT NULL" --remote
--   wrangler d1 execute phoenix_office_db --command="ALTER TABLE office_documents ADD COLUMN legal_hold INTEGER NOT NULL DEFAULT 0" --remote
--   wrangler d1 execute phoenix_office_db --command="ALTER TABLE office_documents ADD COLUMN legal_hold_reason TEXT DEFAULT NULL" --remote
--   wrangler d1 execute phoenix_office_db --file=schema.sql --remote   (picks up the new office_legal_holds table + index, both CREATE IF NOT EXISTS so safe to re-run)
-- Safe to run even if already applied — D1/SQLite errors cleanly on a
-- duplicate column rather than corrupting anything.
-- ══════════════════════════════════════════════════════════════════════════════

-- ══════════════════════════════════════════════════════════════════════════════
-- TABLE: office_notifications   (Module 3 — 2026-09-07)
-- Append-only log of alteration-attempt notifications and their escalation
-- state. Written by office-notify-worker (sector2/apps/office/notify-worker).
--
-- This is the audit trail that (a) an alteration was attempted against a
-- SIGNED document AND (b) the counterparty was told, and kept being told
-- until they acknowledged. It is NOT the source of truth for the document
-- itself — that stays in the .office file (DESIGN.md "Self-sovereign
-- truth"). Losing this table loses the notification history, nothing else.
--
-- Deliberately NOT dependent on office_authors / office_documents / a Life
-- First user: the counterparty (DESIGN.md's oil-change customer) has no
-- Phoenix account. Contact info is denormalized straight onto the row from
-- the document, exactly as notify.js resolves it.
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS office_notifications (
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

CREATE INDEX IF NOT EXISTS idx_notif_doc  ON office_notifications(doc_hex);
-- the scheduled re-scan's hot query: unacknowledged, not yet maxed, ordered by staleness
CREATE INDEX IF NOT EXISTS idx_notif_open ON office_notifications(acknowledged_at, last_sent_at);
