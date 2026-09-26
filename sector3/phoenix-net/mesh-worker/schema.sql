-- phoenix_mesh — Phoenix Mesh switchboard (sector3/phoenix-net/mesh-worker)
-- The registry of the Phoenix family: who's in, their WireGuard PUBLIC key,
-- their mesh address, where they can be reached right now. Private keys are
-- never here: they never leave the device they belong to.

CREATE TABLE IF NOT EXISTS mesh_devices (
  device_id    TEXT PRIMARY KEY,                 -- uuid
  name         TEXT NOT NULL UNIQUE,             -- short name, becomes <name>.phx
  owner_email  TEXT NOT NULL,
  pubkey       TEXT NOT NULL UNIQUE,             -- WireGuard public key (base64, 44 chars)
  mesh_ip      TEXT NOT NULL UNIQUE,             -- 10.47.0.x
  kind         TEXT NOT NULL DEFAULT 'agent'     -- agent (runs phoenix-meshd) | static (phone: fixed config)
                 CHECK(kind IN ('agent','static')),
  hub          INTEGER NOT NULL DEFAULT 0,       -- 1 = static devices (phones) link to this one
  token_hash   TEXT NOT NULL,                    -- SHA-256 of the device token; the token itself is shown once
  endpoints    TEXT NOT NULL DEFAULT '[]',       -- JSON [{addr, port, family, scope}] the device can be reached on
  listen_port  INTEGER NOT NULL DEFAULT 51820,
  created_at   TEXT NOT NULL DEFAULT (datetime('now')),
  last_seen    TEXT DEFAULT NULL,
  revoked_at   TEXT DEFAULT NULL
);

-- Every link measured, ingress and egress (Jerry's rule: judge how fragile
-- each link is). Append-only; one row per link per heartbeat report.
CREATE TABLE IF NOT EXISTS mesh_link_health (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  at             TEXT NOT NULL DEFAULT (datetime('now')),
  from_device    TEXT NOT NULL,                  -- reporting device name
  to_device      TEXT NOT NULL,                  -- peer name
  path           TEXT NOT NULL CHECK(path IN ('direct','fallback','down')),
  handshake_age  INTEGER DEFAULT NULL,           -- seconds since last WireGuard handshake
  rtt_ms         REAL DEFAULT NULL,
  rx_bytes       INTEGER DEFAULT NULL,           -- ingress, cumulative from wg
  tx_bytes       INTEGER DEFAULT NULL,           -- egress, cumulative from wg
  endpoint       TEXT DEFAULT NULL               -- which endpoint the direct link used
);
CREATE INDEX IF NOT EXISTS idx_link_health_at ON mesh_link_health(at);
CREATE INDEX IF NOT EXISTS idx_link_health_pair ON mesh_link_health(from_device, to_device, at);
