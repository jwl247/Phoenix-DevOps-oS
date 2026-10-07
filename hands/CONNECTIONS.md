# hands — H.L.K's hands (per-machine action helper)

Written 2026-09-29 (Round 2 fix pass, CONN-F01) from the code in this folder. Verify against
current code before trusting a specific line number.

## What it is
The small helper on each Phoenix machine that does the jobs a web page can't. The Phoenix
Console (click) and H.L.K (voice) drive the same fixed list of tools, under the CLAUDE.md
permission tiers: base (runs), ask (needs a real yes), never (not a tool at all). Standard
library only; every call is logged to `~/.unitedsys/logs/hands.jsonl`.
- `hands/hands.py` — the helper. Windows tools: status, open_app (allow-list), screenshot, restart_pc, cancel_restart. Linux tools: status, services, restart_service (mesh agent `nebula` / Ollama only), restart_pc, cancel_restart. HTTP `GET /tools`, `GET /log`, `POST /run`; token-gated; `--mesh --allow-from` for boxes; self-update from the hub's clone-pool relay, SHA3-checked and compile-checked, atomic swap.
- `install_remote.py` — installs hands on a headless box over SSH (bytes over stdin, CRLF stripped), makes the box's token on the box, stores it in `~/.phoenix/hands-tokens.json` on the hub (owner-only).
- `phoenix-hands.service` — systemd unit on the boxes: `/opt/phoenix-hands/hands.py --mesh --allow-from 10.42.0.1 --update-from http://10.42.0.1:8470/pool/hands.py` (10.42.0.1 = PBMII, the Console's PC, on the Phoenix Mesh = Nebula 10.42.0.0/16, `sector3/mesh/hosts.json`; the update hop runs inside Nebula, which authenticates + encrypts it). `--mesh` reads this box's 10.42.x address from the Nebula interface (`nebula1`; Windows adapter `PhoenixMesh`) and waits, logging, until it is up.
- `test_hands.py` — 7 tests (tiers, fixed per-platform tool list, audit log, self-update refusal paths); runs on Windows and Linux.

## Dependencies
Python 3 standard library. On the boxes: systemd, root (restart / service control).

## Commands / entry points
- `python hands/hands.py [--port 8471]` (this PC; Windows task `PhoenixHands`, 127.0.0.1).
- `python hands/install_remote.py NAME --ssh ALIAS` (e.g. `compaq --ssh pbm-compaq`).
- `python hands/test_hands.py`.

## Connects to / connected from
- `portal/server.py` → `hands/hands.py` (the Console's Actions tab calls each machine's hands with that machine's token).
- `hands/hands.py` → `portal/server.py` (self-update: fetches `/pool/hands.py` from the hub, which verifies it against D1 custody first).
- `hands/install_remote.py` → `hands/phoenix-hands.service` (installed on the box with the script).
- `hands/hands.py` → `sector3/mesh/phoenix_net.py` (Nebula: reads its mesh address from the Nebula interface; restart_service can restart `nebula`). The old WireGuard agent `sector3/phoenix-net/meshd/` and Tailscale are RETIRED (2026-10-05).

## Known issues (verified, not guessed)
- On the boxes hands runs as root with self-update; the trust anchor is the hub + its vault
  keys (the box checks the hub's `X-Phoenix-SHA3`, the hub checks D1). By design, recorded
  as S34OPS-F40 (needs Jerry if defence-in-depth is wanted).
