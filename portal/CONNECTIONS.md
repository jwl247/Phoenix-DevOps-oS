# portal — the Phoenix Console (one page for the whole mesh)

Written 2026-09-29 (Round 2 fix pass, CONN-F01) from the code in this folder. Verify against
current code before trusting a specific line number.

## What it is
A small local web app on Jerry's PC (the hub) showing every Phoenix machine, its links and
services, plus an Actions tab per machine that drives that machine's hands. Opens from any
Phoenix machine at `precision.phx:8470`. Python standard library only.
- `server.py` — the server: binds 127.0.0.1 + the mesh address only, Host allow-list (421), CSP `default-src 'self'`, POSTs need `X-Phoenix-Console: 1` + JSON; reads switchboard state with MESH_ADMIN from the vault (never sent to the browser); relays hands calls; serves `/pool/hands.py` to boxes only after checking the bytes' SHA3-512 against D1 custody.
- `web/index.html` — the page (machines, links, services, actions).
- `web/app.js` — page logic; builds DOM with `textContent`/`setAttribute`, no `innerHTML`.
- `web/style.css` — light/dark token styles.
- `test_server.py` — 4 tests (machine summary, link summary, time formats, HTTP Host guard + CSP + only the page's own files).
- `README.md` — how it runs (task `PhoenixPortal`, firewall rule "Phoenix Portal (mesh only)", caching).

## Dependencies
Python 3 standard library; the vault file (MESH_ADMIN, MESH_WORKER_URL, PHOENIX_AUTH,
CF_ACCESS_*); `~/.phoenix/hands.token` and `~/.phoenix/hands-tokens.json` for hands calls.

## Commands / entry points
- `python portal/server.py` (Windows task `PhoenixPortal` at logon); `--local-only` + `PHOENIX_CONSOLE_WEB` for a test copy.
- `python portal/test_server.py`.

## Connects to / connected from
- `portal/server.py` → `sector3/phoenix-net/mesh-worker/index.js` (family, links, health — admin key).
- `portal/server.py` → `hands/hands.py` (Actions: this PC on 127.0.0.1, the boxes on their mesh address, each with its own token).
- `portal/server.py` → `sector2/package-handler/worker/index.js` (`/clonepool/<hex>?meta=true` custody hash, then the bytes — the same meta-then-verify pattern `usys pull` now uses).
- `hands/hands.py` → `portal/server.py` (`/pool/hands.py` self-update relay).
- `portal/web/app.js` → `portal/server.py` (same-origin JSON API only).

## Known issues (verified, not guessed)
- None open in code; README/footer wording was brought in line with the live Actions tab and
  the test-copy mode on 2026-09-29 (S34OPS-F38).
