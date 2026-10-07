# Phoenix Console

The one dashboard, served on Phoenix Net. Nobody installs a dashboard on their
own machine; every Phoenix machine opens this page (decision 2026-09-26, see
`docs/plans/phoenix-portal-plan.md`).

**Open it:** `http://precision.phx:8470` from any machine on Phoenix Mesh, or
`http://127.0.0.1:8470` on the hub itself.

## v0 (2026-09-26)
- **The plan view:** every machine as a plate, every link as a member. Solid =
  direct, dashed through the hub = relayed, red-oxide with a break = down.
  Each member carries its round-trip time like a dimension.
- **Links, last hour:** each side's share of direct / relayed / down, how
  often it changed, average and worst speed, and a trend line.
- **Services:** the deployed Phoenix workers, Laurie's page, and the hub's own
  Cloudflare tunnel and mesh agent.
- A banner names anything that's down, in plain words.

**Actions** (same night): a tab per machine, each showing only what its own
hands offer (`hands/hands.py`):
- **precision** (this PC, task `PhoenixHands`, 127.0.0.1): open Office / the
  HUD / PowerShell / Explorer, status, screenshot, restart (asks first).
- **compaq, pbm3** (service `phoenix-hands`, on their mesh address, answer
  ONLY 10.42.0.1 (PBMII, Nebula) and only with their own token): status, Phoenix services,
  restart the mesh agent (Nebula) or Ollama (asks first), restart (asks first).
  Installed with `python hands/install_remote.py NAME --ssh ALIAS`; tokens in
  `~/.phoenix/hands-tokens.json` on this PC (owner-only).
Every action lands in that machine's own log (Recent actions). One live page;
a test copy can serve `web-next/` via `PHOENIX_CONSOLE_WEB` and run with
`--local-only` (see `server.py`) without touching the live one.

## How it runs
- `server.py`: Python standard library only. Asks the switchboard
  (`phoenix-mesh-worker`) with the admin key from the vault, and hands the page
  only the finished summary. The key never reaches a browser.
- Listens on `127.0.0.1` and this machine's mesh address only, never the LAN
  or the internet. Firewall rule "Phoenix Portal (mesh only)": TCP 8470 from
  the Nebula mesh, 10.42.0.0/16 (the live rule on PBMII still says 10.47.0.0/24, the retired
  WireGuard range: needs updating). Requests with a foreign Host header get 421.
- Answers are cached (10 s state, 30 s service checks), so it's idle-light.
- Starts at logon: Windows task `PhoenixPortal` (pythonw, runs as the user
  because the vault is owner-only).
- The page (`web/`) loads nothing from the internet: Bahnschrift ships with
  Windows, no scripts from outside (`Content-Security-Policy: default-src 'self'`).

## Tests
`python portal/test_server.py`: summary logic and the HTTP guard.
