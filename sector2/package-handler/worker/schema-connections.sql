-- Atlas: the connections library.
-- One row per component/feature documented in a CONNECTIONS.md file (root
-- index + one per sector/dir). `links` is a JSON array of hex ids this node
-- points at (parsed from "Connects to / connected from" sections) — the
-- edges GET /connections/:id/related walks to build the 8-neighbor
-- "snow globe" view. Populated by sector2/package-handler/parse-connections.js.

CREATE TABLE IF NOT EXISTS connections (
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

CREATE INDEX IF NOT EXISTS idx_connections_area ON connections(area);
CREATE INDEX IF NOT EXISTS idx_connections_name ON connections(name);
