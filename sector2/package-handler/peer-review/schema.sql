-- peer-review/schema.sql
-- Phoenix Package Handler — D1 Schema Additions
-- Peer Review Platform: Opt-In Distribution + Review + Hex + QR Verification
-- DB: phoenix_dev_db (D1)
-- Principle: the hex is the identity. Review attaches judgment, not content.
--            Nothing is pushed. Availability is advertised. Users pull only what they choose.
-- Version: 1.0.0

-- ══════════════════════════════════════════════════════════════════════════════
-- TABLE: submissions
-- Artifacts submitted by community members for peer review.
-- hex is the canonical SHA-256 identity of the artifact — immutable, permanent.
-- status: pending → approved | rejected → revoked
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS submissions (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  hex            TEXT    NOT NULL UNIQUE,         -- SHA-256 content hash (canonical ID)
  name           TEXT    NOT NULL,                -- human-readable artifact name
  description    TEXT    DEFAULT '',              -- what this artifact does
  category       TEXT    DEFAULT NULL,            -- optional category (matches glossary)
  platform       TEXT    DEFAULT NULL,            -- linux | macos | windows | all
  submitter      TEXT    DEFAULT 'anonymous',     -- submitter handle or ID
  artifact_url   TEXT    DEFAULT NULL,            -- optional pull URL (not the content — just a pointer)
  status         TEXT    NOT NULL DEFAULT 'pending'  -- pending | approved | rejected | revoked
                   CHECK(status IN ('pending','approved','rejected','revoked')),
  submitted_at   TEXT    NOT NULL DEFAULT (datetime('now')),
  reviewed_at    TEXT    DEFAULT NULL             -- timestamp of final status change
);

-- ══════════════════════════════════════════════════════════════════════════════
-- TABLE: reviews
-- Individual votes cast on a submission.
-- Multi-party review: each reviewer casts one vote.
-- Review does NOT modify content — only attaches judgment metadata.
-- Auto-approval threshold is configurable in worker logic (default: 2 approvals).
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS reviews (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  submission_hex  TEXT    NOT NULL,               -- FK → submissions.hex
  reviewer        TEXT    NOT NULL DEFAULT 'anonymous',
  vote            TEXT    NOT NULL                -- approve | reject | abstain
                    CHECK(vote IN ('approve','reject','abstain')),
  notes           TEXT    DEFAULT NULL,           -- optional reviewer commentary
  voted_at        TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Index for fast vote tallying per artifact
CREATE INDEX IF NOT EXISTS idx_reviews_hex ON reviews(submission_hex);

-- ══════════════════════════════════════════════════════════════════════════════
-- TABLE: revocations
-- Public log of revoked artifacts.
-- Revocation does NOT delete — identity == hash, old artifacts remain addressable.
-- Status changes in registry only. Clonepool retains all versions.
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS revocations (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  hex            TEXT    NOT NULL UNIQUE,         -- revoked artifact hex
  reason         TEXT    NOT NULL DEFAULT 'no reason provided',
  revoked_by     TEXT    NOT NULL DEFAULT 'admin',
  superseded_by  TEXT    DEFAULT NULL,            -- hex of replacement artifact (if any)
  revoked_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ══════════════════════════════════════════════════════════════════════════════
-- TABLE: advertisement_feed
-- Approved artifacts whose availability is advertised.
-- This is NOT a delivery channel — it is an availability signal only.
-- "Available" ≠ "Delivered". Users opt-in to pull. Marginal cost per user → 0.
-- QR codes encode the hex hash as a pointer — never the content.
-- ══════════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS advertisement_feed (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  hex            TEXT    NOT NULL UNIQUE,         -- canonical SHA-256 hash
  name           TEXT    NOT NULL,
  description    TEXT    DEFAULT '',
  category       TEXT    DEFAULT NULL,
  platform       TEXT    DEFAULT NULL,
  approvals      INTEGER DEFAULT 0,              -- vote count at time of approval
  artifact_url   TEXT    DEFAULT NULL,           -- optional pull pointer (not the content)
  qr_data        TEXT    DEFAULT NULL,           -- QR encodes hex or resolver URL (NOT the content)
  revoked        INTEGER NOT NULL DEFAULT 0,     -- 0 = active, 1 = revoked (never deleted)
  revoked_at     TEXT    DEFAULT NULL,
  advertised_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Index for feed queries
CREATE INDEX IF NOT EXISTS idx_feed_category ON advertisement_feed(category);
CREATE INDEX IF NOT EXISTS idx_feed_platform ON advertisement_feed(platform);
CREATE INDEX IF NOT EXISTS idx_feed_revoked  ON advertisement_feed(revoked);

-- ══════════════════════════════════════════════════════════════════════════════
-- VERIFICATION PATHS (reference — enforced in worker logic, not SQL)
-- ══════════════════════════════════════════════════════════════════════════════
--
--  GET /verify/:hex
--    → hex not in submissions              → status: unknown
--    → hex in revocations                  → status: revoked  (verified: false)
--    → submissions.status = 'approved'     → status: verified (verified: true)
--    → submissions.status = 'pending'      → status: pending  (verified: false)
--    → submissions.status = 'rejected'     → status: rejected (verified: false)
--
--  QR Layer:
--    QR encodes hash OR resolvable reference — NOT the content.
--    Bridges physical ↔ digital. Scan → resolver → /verify/:hex.
--
--  Update Signal:
--    advertisement_feed row advertised → "Available" signal only.
--    No payload delivered. User fetches if they choose. Integrity verified against hex.
--
-- ══════════════════════════════════════════════════════════════════════════════
-- ECONOMIC MODEL (non-goals documented here for clarity)
-- ══════════════════════════════════════════════════════════════════════════════
--
--  ✓  Opt-in pull — users pull only what they choose
--  ✓  Near-zero marginal cost per additional user
--  ✓  Mirrors/caches amortize distribution cost
--  ✓  Revocation without deletion
--  ✓  Verification decoupled from delivery
--
--  ✗  NOT DRM
--  ✗  NOT identity enforcement
--  ✗  NOT entitlement management
--  ✗  NOT automatic updates (signal ≠ delivery)
--
-- See PEER_REVIEW.md for the full 9-stage lifecycle specification.
