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

-- ══════════════════════════════════════════════════════════════════════════════
-- TABLE: office_jobs   (2026-09-24)
-- Saved customer/job profiles — Jerry's ask: "picking a saved profile at
-- the top that auto fills." A job is a reusable bundle of field values
-- (customer_name, job_site, phone, etc.) picked once from a dropdown when
-- starting a new document, instead of retyping the same customer/site
-- info on every work order, inspection, invoice. Per-author (jobs you've
-- saved are yours; there's no cross-author sharing here, same scoping as
-- documents). Stored server-side (not a local file) on purpose — same
-- "recoverable from any machine" principle as everything else in this
-- worker, not a per-install convenience that vanishes on reinstall.
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS office_jobs (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id        TEXT    NOT NULL UNIQUE,        -- client-generated stable id, survives a label rename
  author_id     TEXT    NOT NULL,
  label         TEXT    NOT NULL,               -- what shows in the dropdown, e.g. "Dave — 123 Main St reroof"
  fields        TEXT    NOT NULL,               -- JSON: { customer_name: "...", job_site: "...", ... }
  counterparty  TEXT    DEFAULT NULL,           -- JSON: { phone, carrier, email }
  created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
  updated_at    TEXT    DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_author ON office_jobs(author_id);

-- MIGRATION — apply once against the already-deployed DB:
--   wrangler d1 execute phoenix_office_db --file=schema.sql --remote
-- (CREATE TABLE/INDEX IF NOT EXISTS — safe to re-run against a DB that
-- already has the other tables above.)

-- ══════════════════════════════════════════════════════════════════════════════
-- PROJECT ASSIST TABLES   (2026-09-25)
-- A construction-PM module on top of the same document engine: a project
-- groups multiple documents (proposal, schedule, safety plan, work orders)
-- across phases, with a guided-choice checklist engine and an append-only
-- decision audit trail. office_jobs above is untouched — it stays the
-- lightweight saved-autofill-profile mechanism for one-off documents;
-- office_projects.job_id is an optional one-way seed link at creation only,
-- not a replacement for it.
-- ══════════════════════════════════════════════════════════════════════════════

-- TABLE: office_projects
-- The project entity. bid_factors is a JSON blob (lib/bid-factors.js is the
-- single source of truth for what keys it holds) rather than a normalized
-- table on purpose — the bid-influencing factor list is known to keep
-- growing (labor-needs sub-factors especially), and a blob absorbs new
-- factors with zero migration. Same author_id scoping as office_documents/
-- office_jobs — no tenant_id yet, but nothing here forecloses adding one.
CREATE TABLE IF NOT EXISTS office_projects (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id    TEXT    NOT NULL UNIQUE,        -- client-generated uuid, same idiom as office_jobs.job_id
  author_id     TEXT    NOT NULL,
  job_id        TEXT    DEFAULT NULL,           -- optional seed link -> office_jobs.job_id, one-way only
  name          TEXT    NOT NULL,
  status        TEXT    NOT NULL DEFAULT 'BID'
                  CHECK(status IN ('BID','AWARDED','ACTIVE','COMPLETE','CANCELLED')),
  bid_factors   TEXT    NOT NULL DEFAULT '{}',
  counterparty  TEXT    DEFAULT NULL,           -- JSON: { phone, carrier, email }
  created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
  updated_at    TEXT    DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_projects_author ON office_projects(author_id);
CREATE INDEX IF NOT EXISTS idx_projects_status ON office_projects(status);

-- TABLE: office_project_phases
-- phase_type is deliberately free text (no CHECK) so the taxonomy stays
-- extensible without a migration per new phase name. lifecycle_stage groups
-- phases against real PM doctrine (PMI/PMBOK process groups) — see
-- lib/project.js's STANDARD_PHASE_TEMPLATE. Note there is no
-- 'MONITORING_CONTROLLING' stage: PMBOK defines M&C as concurrent with
-- Execution, not a sequential step after it, so it's represented by the
-- checklist/decision tables below running continuously alongside every
-- Execution-stage phase, not as its own phase row.
CREATE TABLE IF NOT EXISTS office_project_phases (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  phase_id         TEXT    NOT NULL UNIQUE,
  project_id       TEXT    NOT NULL,               -- FK -> office_projects.project_id
  phase_type       TEXT    NOT NULL,
  lifecycle_stage  TEXT    NOT NULL,               -- INITIATION | PLANNING | EXECUTION | CLOSING
  label            TEXT    NOT NULL,
  sequence         INTEGER NOT NULL,
  state            TEXT    NOT NULL DEFAULT 'NOT_STARTED'
                     CHECK(state IN ('NOT_STARTED','IN_PROGRESS','COMPLETE')),
  estimated_cost   REAL    DEFAULT NULL,
  actual_cost      REAL    DEFAULT NULL,
  risk_level       TEXT    DEFAULT NULL,           -- low | medium | high — documented in code, not DB-enforced (same posture as phase_type)
  risk_notes       TEXT    DEFAULT NULL,
  started_at       TEXT    DEFAULT NULL,
  completed_at     TEXT    DEFAULT NULL,
  created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
  updated_at       TEXT    DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_phases_project ON office_project_phases(project_id);

-- TABLE: office_checklist_catalog
-- Seeded, hand-curated reference data — the "menu" a phase's checklist gets
-- instantiated from (see worker/seed-checklist-catalog.sql). phase_type
-- 'general' applies to any phase. source_type is the guided-choice engine's
-- multi-source validation: OSHA/federal, Oklahoma state code, the client's
-- own spec/contract, and general PM best practice — the app never infers
-- compliance itself, it only surfaces which source a given item comes from.
CREATE TABLE IF NOT EXISTS office_checklist_catalog (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  catalog_id  TEXT    NOT NULL UNIQUE,             -- stable key, e.g. 'osha-1926-501-fall-protection'
  phase_type  TEXT    NOT NULL,
  source_type TEXT    NOT NULL CHECK(source_type IN ('OSHA','OK_STATE','CLIENT_SPEC','PM_BEST_PRACTICE')),
  source_ref  TEXT    DEFAULT NULL,                -- citation, e.g. '29 CFR 1926.501(b)(1)'
  label       TEXT    NOT NULL,
  guidance    TEXT    DEFAULT NULL,                -- what "satisfied" looks like
  active      INTEGER NOT NULL DEFAULT 1,
  created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_checklist_catalog_phase_type ON office_checklist_catalog(phase_type);

-- TABLE: office_phase_checklist_items
-- One row per item instantiated onto a real phase (copied from the catalog
-- at phase-creation time, or added ad-hoc with catalog_id NULL) — editing
-- the catalog later never silently changes an already-in-progress project's
-- checklist. disposition/decided_by/rationale here are the denormalized
-- CURRENT status (fast render); office_checklist_decisions below is the
-- real append-only history, same relationship office_documents.legal_hold
-- has to office_legal_holds.
CREATE TABLE IF NOT EXISTS office_phase_checklist_items (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id        TEXT    NOT NULL UNIQUE,
  phase_id       TEXT    NOT NULL,                 -- FK -> office_project_phases.phase_id
  catalog_id     TEXT    DEFAULT NULL,              -- FK -> office_checklist_catalog.catalog_id, NULL if ad-hoc
  source_type    TEXT    NOT NULL CHECK(source_type IN ('OSHA','OK_STATE','CLIENT_SPEC','PM_BEST_PRACTICE')),
  source_ref     TEXT    DEFAULT NULL,
  label          TEXT    NOT NULL,
  sequence       INTEGER NOT NULL DEFAULT 0,
  disposition    TEXT    NOT NULL DEFAULT 'open' CHECK(disposition IN ('open','satisfied','not_applicable')),
  decided_by     TEXT    DEFAULT NULL,             -- author_id
  decided_at     TEXT    DEFAULT NULL,
  rationale      TEXT    DEFAULT NULL,
  linked_doc_hex TEXT    DEFAULT NULL,             -- optional pointer to office_documents.hex evidencing satisfaction
  created_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_checklist_items_phase ON office_phase_checklist_items(phase_id);

-- TABLE: office_checklist_decisions
-- APPEND-ONLY. This IS the SBA/HUBZone self-performance evidence record —
-- who decided what, when, against which source, and why — never
-- overwritten, same append-only posture as office_legal_holds. Every write
-- to office_phase_checklist_items.disposition above must have a matching
-- row here; the app enforces this as a two-write per decision, it is not
-- DB-enforced (D1/SQLite triggers add complexity this scale doesn't need).
CREATE TABLE IF NOT EXISTS office_checklist_decisions (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id        TEXT    NOT NULL,
  disposition    TEXT    NOT NULL CHECK(disposition IN ('open','satisfied','not_applicable')),
  by             TEXT    NOT NULL,                 -- author_id
  rationale      TEXT    DEFAULT NULL,
  linked_doc_hex TEXT    DEFAULT NULL,
  at             TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_checklist_decisions_item ON office_checklist_decisions(item_id);

-- office_documents gains three nullable columns so a document can (optionally)
-- belong to a project/phase. Nullable FK columns, not a join table: a
-- document belongs to at most one project at a time (a proposal is written
-- for one project; a correction is already handled by supersedes_hex) —
-- same idiom as the existing supersedes_hex soft-FK, not a new relationship
-- shape. Purely additive; does not touch hex/hash_sha3/hash_blake2 or any
-- existing tamper-evidence guarantee.
--   wrangler d1 execute phoenix_office_db --command="ALTER TABLE office_documents ADD COLUMN project_id TEXT DEFAULT NULL" --remote
--   wrangler d1 execute phoenix_office_db --command="ALTER TABLE office_documents ADD COLUMN phase_id TEXT DEFAULT NULL" --remote
--   wrangler d1 execute phoenix_office_db --command="ALTER TABLE office_documents ADD COLUMN doc_role TEXT DEFAULT NULL" --remote
--   wrangler d1 execute phoenix_office_db --file=schema.sql --remote   (picks up the 5 new tables above, all CREATE IF NOT EXISTS)
--   wrangler d1 execute phoenix_office_db --file=worker/seed-checklist-catalog.sql --remote   (INSERT OR IGNORE, safe to re-run)
CREATE INDEX IF NOT EXISTS idx_documents_project ON office_documents(project_id);
CREATE INDEX IF NOT EXISTS idx_documents_phase   ON office_documents(phase_id);
