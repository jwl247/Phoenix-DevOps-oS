-- sector2/apps/lifefirst/meds-worker/schema.sql
-- Applies to D1: lifefirst-db (6a24691c-0970-441f-81f9-9746475c3cef)
--   wrangler d1 execute lifefirst-db --remote --file=schema.sql
--
-- Laurie's medication guardrail. Adaptive once-a-day model (Jerry's design,
-- 2026-09-09): the reminder is anchored to when she last actually took the
-- dose, not a fixed clock time. She can ACKNOWLEDGE a dose; she cannot turn
-- the guardrail off, snooze it forever, or change the window — that control
-- lives with Jerry (see memory: laurie-medication-guardrail).
--
-- Shares lifefirst-db with lifefirst-mcp but owns only these 3 tables.
-- Losing them loses the medication history, nothing else in Life First.
-- Version: 1.0.0

-- ─────────────────────────────────────────────────────────────────────────────
-- medication_state — one row per user under a medication guardrail.
-- next_check_at is the load-bearing field: when now >= next_check_at and the
-- user has not confirmed a dose since, the cron fires the alert chain.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS medication_state (
  user_id        INTEGER PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
  med_label      TEXT    NOT NULL DEFAULT 'your medication',
  window_hours   INTEGER NOT NULL DEFAULT 24,          -- once a day = 24
  last_dose_at   TEXT,                                  -- ISO-8601 UTC of the last CONFIRMED dose
  next_check_at  TEXT    NOT NULL,                      -- last_dose_at + window_hours (or 'now' if never dosed)
  grace_minutes  INTEGER NOT NULL DEFAULT 0,           -- how late past next_check_at before the first alert
  active         INTEGER NOT NULL DEFAULT 1,           -- Jerry-only switch; Laurie can't flip this
  updated_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────────────────────────────────────────
-- medication_log — append-only record of every confirmed dose.
-- dose_at is her stated time when known ("took them at 9"), else the moment
-- she acknowledged. recorded_via says which channel confirmed it.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS medication_log (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id       INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  dose_at       TEXT    NOT NULL,                       -- when she took it (ISO-8601 UTC)
  recorded_via  TEXT    NOT NULL                        -- how the dose was confirmed
                  CHECK (recorded_via IN ('assistant','link-ack','pushover-ack','email-ack','sms-reply','manual')),
  recorded_at   TEXT    NOT NULL DEFAULT (datetime('now')),
  note          TEXT
);
CREATE INDEX IF NOT EXISTS idx_medlog_user ON medication_log(user_id, dose_at);

-- ─────────────────────────────────────────────────────────────────────────────
-- med_alerts — one row per reminder cycle. The cron re-sends an open row
-- (acknowledged_at IS NULL) on an escalating cadence, then notifies the
-- caregiver (Jerry) if it stays unacknowledged past the caregiver threshold.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS med_alerts (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id               INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  due_at                TEXT    NOT NULL,               -- the next_check_at this cycle is for
  ack_token             TEXT    NOT NULL UNIQUE,        -- single-use; the /ack/:token link IS the auth
  escalation_level      INTEGER NOT NULL DEFAULT 0,     -- 0..cap, bumped each re-send
  send_count            INTEGER NOT NULL DEFAULT 0,
  channels_last         TEXT,                           -- JSON {pushover:ok|skip|err, email:..., sms:...}
  last_sent_at          TEXT,
  acknowledged_at       TEXT,                           -- set -> cycle closed, dose logged
  acknowledged_via      TEXT,
  caregiver_notified_at TEXT,                           -- set -> Jerry was told she hasn't confirmed
  created_at            TEXT    NOT NULL DEFAULT (datetime('now'))
);
-- the cron's hot query: open alerts, oldest first
CREATE INDEX IF NOT EXISTS idx_medalerts_open ON med_alerts(acknowledged_at, due_at);
