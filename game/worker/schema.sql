-- schema.sql — sacrifice_world (D1) — Sacrifice game state
-- Phoenix DevOps OS | jwl247 | GPL v3
--
-- world_history is the permanent record (GDD §11.2/§11.4): append-only and
-- chained — the database itself refuses an UPDATE, a DELETE, or a row that
-- does not follow the last one. named_ground and territory are the current
-- state, projected from history rows in the same transaction; every row
-- points back at the history entry (seq) that set it.
-- Re-runnable: IF NOT EXISTS everywhere.

CREATE TABLE IF NOT EXISTS world_history (
  seq         INTEGER PRIMARY KEY CHECK (seq >= 1),
  entry_hash  TEXT NOT NULL UNIQUE CHECK (length(entry_hash) = 128),
  prev_hash   TEXT NOT NULL CHECK (length(prev_hash) = 128),
  type        TEXT NOT NULL,
  theater     TEXT,
  canonical   TEXT NOT NULL,
  received_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS wh_type    ON world_history (type, seq);
CREATE INDEX IF NOT EXISTS wh_theater ON world_history (theater, seq);

CREATE TRIGGER IF NOT EXISTS wh_no_update BEFORE UPDATE ON world_history
BEGIN SELECT RAISE(ABORT, 'world history is append-only'); END;

CREATE TRIGGER IF NOT EXISTS wh_no_delete BEFORE DELETE ON world_history
BEGIN SELECT RAISE(ABORT, 'world history is append-only'); END;

CREATE TRIGGER IF NOT EXISTS wh_chain BEFORE INSERT ON world_history
WHEN NEW.seq <> COALESCE((SELECT MAX(seq) FROM world_history), 0) + 1
  OR NEW.prev_hash <> COALESCE(
       (SELECT entry_hash FROM world_history ORDER BY seq DESC LIMIT 1),
       '00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000')
BEGIN SELECT RAISE(ABORT, 'world history chain broken'); END;


CREATE TABLE IF NOT EXISTS named_ground (
  ground_id     TEXT PRIMARY KEY,
  ao_id         TEXT NOT NULL,
  theater       TEXT NOT NULL,
  name          TEXT NOT NULL,
  lon           REAL NOT NULL CHECK (lon BETWEEN -180 AND 180),
  lat           REAL NOT NULL CHECK (lat BETWEEN -90 AND 90),
  kind          TEXT NOT NULL CHECK (kind IN ('officer_fallen', 'player_named')),
  player_id     TEXT NOT NULL,
  callsign      TEXT NOT NULL,
  battle_id     TEXT NOT NULL,
  casualties    INTEGER NOT NULL,
  ts            REAL NOT NULL,
  superseded_by TEXT,
  seq           INTEGER NOT NULL REFERENCES world_history (seq)
);
CREATE INDEX IF NOT EXISTS ng_theater ON named_ground (theater, superseded_by);

-- GDD §11.1: an officer's ground is never renamed.
CREATE TRIGGER IF NOT EXISTS ng_officer_permanent BEFORE UPDATE OF superseded_by ON named_ground
WHEN OLD.kind = 'officer_fallen'
BEGIN SELECT RAISE(ABORT, 'an officer''s ground is never renamed'); END;

-- Only superseded_by may ever change, and only once.
CREATE TRIGGER IF NOT EXISTS ng_frozen BEFORE UPDATE ON named_ground
WHEN NEW.name IS NOT OLD.name OR NEW.lon IS NOT OLD.lon OR NEW.lat IS NOT OLD.lat
  OR NEW.kind IS NOT OLD.kind OR NEW.player_id IS NOT OLD.player_id
  OR OLD.superseded_by IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'named ground is permanent'); END;

CREATE TRIGGER IF NOT EXISTS ng_no_delete BEFORE DELETE ON named_ground
BEGIN SELECT RAISE(ABORT, 'named ground is permanent'); END;


CREATE TABLE IF NOT EXISTS territory (
  ao_id               TEXT PRIMARY KEY,
  theater             TEXT NOT NULL,
  name                TEXT NOT NULL,
  polygon             TEXT NOT NULL,          -- JSON [[lon, lat], ...]
  control             TEXT NOT NULL CHECK (control IN ('neutral', 'held', 'contested')),
  controller_id       TEXT,
  controller_callsign TEXT,
  held_since          REAL,
  contested_by        TEXT,
  seq                 INTEGER NOT NULL REFERENCES world_history (seq)
);
CREATE INDEX IF NOT EXISTS terr_theater ON territory (theater);

CREATE TRIGGER IF NOT EXISTS terr_no_delete BEFORE DELETE ON territory
BEGIN SELECT RAISE(ABORT, 'ground is not undrawn'); END;
