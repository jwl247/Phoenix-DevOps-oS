# phoenix-net — Phoenix Mesh (own WireGuard mesh) + its switchboard

Written 2026-09-29 (Round 2 fix pass, CONN-F01) from the code in this folder; re-checked 2026-09-30
(no code changes since; tests 12/12 and 9/9 re-run). Verify against current code before trusting a
specific line number.

## What it is
Phoenix's own ZeroTier-style network: WireGuard links run directly between Phoenix machines;
a Cloudflare Worker only coordinates (family registry, endpoints, link health). Live since
2026-09-26 (3 boxes + phone). Standard library / no npm dependencies.
- `mesh-worker/index.js` — `phoenix-mesh-worker`, the switchboard: `/health`, admin `/enroll` `/revoke` `/devices` `/links` (Bearer MESH_ADMIN), device `/heartbeat` `/peers` (per-device token, stored SHA-256 only).
- `mesh-worker/schema.sql` — its D1 schema (`mesh_devices`, `mesh_link_health`).
- `mesh-worker/wrangler.jsonc` — own D1 `phoenix_mesh` (binding `MESH_DB`), own secret `MESH_ADMIN` (not PHOENIX_AUTH).
- `mesh-worker/test.mjs` — worker tests against real SQLite (`node:sqlite`), 12/12.
- `meshd/meshd.py` — the per-machine agent (Linux or Windows): makes the WireGuard keypair on the device, heartbeats endpoints, writes the WireGuard config, measures links, keeps `<name>.phx` in the hosts file.
- `meshd/phoenix-meshd.service` — systemd unit, `python3 /opt/phoenix-mesh/meshd.py run --every 30`.
- `meshd/test_meshd.py` — agent tests, 9/9.
- `phoenix-net.py` — admin tool run on Jerry's PC: `enroll` (Linux box over SSH), `enroll-local`, `enroll-phone`, `forget-qr` (deletes the phone's QR/config file, which holds its private key, once scanned), `list`, `links`, `health`, `revoke`.

## Dependencies
Cloudflare Worker + D1 (`wrangler.jsonc`); `wg` (wireguard-tools / WireGuard for Windows) on
every member; Python 3 standard library; Node 22+ for `test.mjs`. Secrets `MESH_ADMIN` +
`MESH_WORKER_URL` come from the vault file (`F:\Phoenix\Vault\secrets\phoenix-secrets.env`
or `PHOENIX_SECRETS`), never the command line.

## Commands / entry points
- `python sector3/phoenix-net/phoenix-net.py enroll NAME --ssh ALIAS [--hub]` (and `enroll-local`, `enroll-phone NAME --hub-name HUB`, `forget-qr NAME`, `list`, `links`, `health`, `revoke`).
- `meshd.py init|token|once|run|status` on each machine (root / Administrator).
- `node sector3/phoenix-net/mesh-worker/test.mjs`, `python sector3/phoenix-net/meshd/test_meshd.py`.

## Connects to / connected from
- `sector3/phoenix-net/phoenix-net.py` → `sector3/phoenix-net/mesh-worker/index.js` (admin routes) and → `sector3/phoenix-net/meshd/meshd.py` (copied to boxes over SSH stdin, CRLF stripped).
- `sector3/phoenix-net/meshd/meshd.py` → `sector3/phoenix-net/mesh-worker/index.js` (device heartbeat/peers).
- `portal/server.py` → `sector3/phoenix-net/mesh-worker/index.js` (the Console reads family/link state with the admin key; the key never reaches the browser).
- `hands/hands.py` → `sector3/phoenix-net/meshd/meshd.py` (reads the device name the agent writes; its restart_service tool can restart the mesh agent).
- `sector3/worker-up/hlk-up.sh` → `sector3/phoenix-net/meshd/meshd.py` (H.L.K on a worker box listens on the mesh address the agent wrote into the box's WireGuard config).

## Known issues (verified, not guessed)
- `mesh-worker/index.js`'s header points at `../README.md` for the tunnel fallback; there is no
  `sector3/phoenix-net/README.md` in the repo.
- The planned switchboard move to its own Cloudflare account is still open (CLAUDE.md NEXT SESSION).
