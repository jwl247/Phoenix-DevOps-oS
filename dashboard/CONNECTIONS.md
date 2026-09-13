# dashboard — Electron desktop command center

Written 2026-09-12. Verify against current code before trusting a specific line number.

## What it is
The Phoenix "Command Center" Electron app: real terminal (SHELL pane via `terminal-pty.js`),
a Claude Code hotline (CLAUDE pane), sector file browser, clonepool browser, HUD-mode glass
overlay, Office/ScriptForge launchers, Config Centralizer (Settings tab), Live Monitor
screen capture. Main files: `main.js` (Electron main process), `preload.js`, `index.html`,
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
  `SECTOR4`/`sector4` (see known casing bug below).
- `scriptforge-launcher.js` → `sector2/apps/scriptforge/index.html`.
- `office-launcher.js` → `sector2/apps/office/index.html` + that app's `preload.js`
  (IPC channel names cross-checked against `office-launcher.js`/`index.html`/`button-generator.js`).
- `config-centralizer.js` scans the local filesystem for credential files — system-wide,
  not repo-scoped.
- Reads `~/.phoenix/phoenix.env` for `PHOENIX_ROOT`, `CLONEPOOL_DIR`, etc. — shares config
  surface with `scripts/usys.ps1` but no direct file import.

## Known issues (verified, not guessed)
- `main.js` (~line 374) references `'SECTOR4'` uppercase while the real directory is
  lowercase `sector4/` — only "works" on case-insensitive Windows NTFS.
- `ps7-shell.js` is dead code — superseded by `terminal-pty.js` (2026-08-30) but still
  present in the tree, not removed.
- Root-level `dashboardzip1.zip` (187MB, sits outside `dashboard/` at the repo root) is a
  stale backup with a known gap: it got a D1 custody row but no R2 blob (Cloudflare's
  request-body size cap) — flagged for a multipart-PUT fix, not yet done.
- Dead `THROUGHPUT: -- ops/sec` stat in the HUD status bar — the deployed worker (v3.4.0)
  has no `/stats` route; needs removing or repointing at `/toc`.
- "PREV/NEXT TASK" and "REPORTS" panes intentionally show a "soon" tag — not bugs, don't
  try to "fix" these into working features without checking with Jerry first.
