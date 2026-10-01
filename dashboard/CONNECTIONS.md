# dashboard — Electron desktop command center

Written 2026-09-12; buttons section updated 2026-09-30. Verify against current code before
trusting a specific line number.

## What it is
The Phoenix "Command Center" Electron app. Legacy: kept running, not developed; the
Phoenix Console (`portal/`) is the front door and `hud/` is the HUD (decided 2026-09-26).
Buttons cut that day (HUD MODE, TELEMETRY, DEBIAN ENGINE, HELIX STATUS, PHORONIX, WATCH/INTAKE
DOWNLOADS, PHOENIX GUIDE, VENV, CLONEPOOL; MAP, SECTOR MAP, task/report stubs, CLAUDE and
GUIDE tabs) were removed 2026-09-30; sector switches, THROUGHPUT, YOU WERE HERE and the
meters are hidden. What's left: AI CHAT, HELP CHAT, SETTINGS (Config Centralizer), CODES
(CLI + RUNIT), SHELL (real terminal via `terminal-pty.js`), GLOSSARY; right column GOOGLE,
STEAM, SCRIPTFORGE, OFFICE, RUN, OPEN PS7, OPEN FILE EXPLORER, DRIVER UPDATES (opens Windows
Update's driver list; the user picks), SCREENSHOT, LIVE MONITOR. Main files: `main.js` (Electron main process), `preload.js`, `index.html`,
`dashboard.js`, `hud-*.js/.css`, `button-generator.js`/`action-buttons.js`,
`config-centralizer.js`, launchers (`office-launcher.js`, `scriptforge-launcher.js`,
`google-launcher.js`, `steam-launcher.js`), `manual/PHOENIX_MANUAL.md` +
`manual/LAURIE_GUIDE.md`.

## Dependencies
`dashboard/package.json` — name `phoenix-dashboard`. Deps: `@homebridge/node-pty-prebuilt-multiarch`,
`@xterm/addon-fit`, `@xterm/xterm`, `electron ^28.3.3`, `leaflet`. Dev dep:
`electron-builder ^24.9.1`. Has its own `package-lock.json` — this is a self-contained npm
project, NOT governed by any repo-root package.json (there isn't one).

## Commands / entry points
- `npm start` (→ `electron .`) inside `dashboard/` — primary way to launch it.
- `npm run build` / `build-win` / `build-mac` / `build-linux` — electron-builder packaging.
- `dashboard/start.ps1` — self-elevates via UAC, launches Electron (used for autostart).
- `dashboard/start-desktop.sh` — Linux/Ubuntu launch counterpart.
- `sector3/services/phoenix-dashboard.service` — systemd unit for headless/server autostart.
- `sector3/services/install-dashboard-windows.ps1` — installs the Windows autostart task.

## Connects to / connected from
- `main.js` → folder-browser slot mapping into `sector1/`, `sector2/`, `sector3/`, and
  `sector4/`.
- `scriptforge-launcher.js` → `sector2/apps/scriptforge/index.html`.
- `office-launcher.js` → `sector2/apps/office/index.html` + that app's `preload.js`
  (IPC channel names cross-checked against `office-launcher.js`/`index.html`/`button-generator.js`).
- `config-centralizer.js` scans the local filesystem for credential files — system-wide,
  not repo-scoped.
- Reads `~/.phoenix/phoenix.env` for `PHOENIX_ROOT`, `CLONEPOOL_DIR`, etc. — shares config
  surface with `scripts/usys.ps1` but no direct file import.
- `office-launcher.js` → `sector2/package-handler/intake.sh` (Office "save" goes through intake).
- `main.js` → `scripts/usys.ps1` (the CODES CLI and RUN only accept `help`, `usys …`, `intake …`).
- `main.js` → `sector2/package-handler/worker/index.js` (glossary/custody reads, CF Access headers).

## Known issues (verified, not guessed)
- `ps7-shell.js` is dead code — superseded by `terminal-pty.js` (2026-08-30) but still
  present in the tree, not removed.
- Root-level `dashboardzip1.zip` (187MB, sits outside `dashboard/` at the repo root) is a
  stale backup with a known gap: it got a D1 custody row but no R2 blob (Cloudflare's
  request-body size cap) — flagged for a multipart-PUT fix, not yet done.
- Dead `THROUGHPUT: -- ops/sec` stat in the HUD status bar — the deployed worker (v3.4.0)
  has no `/stats` route; needs removing or repointing at `/toc`.
- "PREV/NEXT TASK" and "REPORTS" panes intentionally show a "soon" tag — not bugs, don't
  try to "fix" these into working features without checking with Jerry first.
