# Phoenix-DevOps-oS — connections index

Read this before exploring. Each top-level directory has its own `CONNECTIONS.md` with
full detail (purpose, dependencies, commands, what it calls / is called by, known issues).
This file is just the map. Master index for the whole `Phoenix\` tree (this repo plus the
peripheral folders next to it) is at `D:\Users\jwlef\Phoenix\CONNECTIONS.md`.

Baseline: written 2026-09-12, git commit at time of writing — see `git log -1
CONNECTIONS.md` for the exact commit this was accurate as of. Facts drift; re-verify
anything load-bearing before trusting it blindly.

| Dir | What it is | Key fact |
|---|---|---|
| [sector1](sector1/CONNECTIONS.md) | Boot, kernel, auth, security | Guardian/honeypot security system resurrected 2026-09-09, wired into `main_kernel.py` + `phoenix_auth.py`. `sector1/grub/` is a second, unconfirmed-live USys implementation — ask before assuming it's dead. |
| [sector2](sector2/CONNECTIONS.md) | Intake authority, package handler, clone pool, apps (LifeFirst, Office, ScriptForge) | Canonical intake pipeline lives at `sector2/package-handler/intake.sh`. `sector2/frank/frank_save.py`'s drive-tiering logic is built but never called. |
| [sector3](sector3/CONNECTIONS.md) | Comms/networking, systemd services | `sector3/workers/packages-worker/` is a **stale, dead duplicate** of the real worker at `sector2/package-handler/worker/` — don't edit it thinking it's live. |
| [sector4](sector4/CONNECTIONS.md) | Helix/Frank core engine, vault | `sector4/intake/intake.sh` has a real bash syntax error (zsh glob on line 59) — broken, and `usys intake` currently mis-routes here. Use `usys clone` instead. |
| [dashboard](dashboard/CONNECTIONS.md) | Electron desktop command center | `main.js` has a `SECTOR4` vs `sector4` casing bug (works on Windows NTFS, would break on case-sensitive filesystems). |
| [scripts](scripts/CONNECTIONS.md) | `usys.ps1` — the global CLI | Everything (`bin/*`, `tools/*`, the dashboard) eventually calls through here. `usys run debian` currently fails live with an elevation error — see memory `phoenix-debian-boot-elevation-bug`, not yet fixed. |
| [tools](tools/CONNECTIONS.md) | Utility scripts + `poc/` distro-boot sandbox | `tools/poc/` is where Debian/Ubuntu QEMU boot manifests + launchers live. |
| [bin](bin/CONNECTIONS.md) | Global CLI wrappers (installed on PATH) | Thin shims into `scripts/` and `tools/`; `bin/usys` has a dead fallback to a nonexistent `scripts/usys.sh`. |
| [bootstrap](bootstrap/CONNECTIONS.md) | Minimal `lol install` bootstrapper | Self-contained, zero references from the rest of the repo — confirm with Jerry whether it's active. |
| [docs](docs/CONNECTIONS.md) | Documentation | Contains the *previous* attempt at a connections doc (`PHOENIX_SYSTEM_SUMMARY_STATUS_CONNECTIONS.md`) — already known stale, this file supersedes it. |
| [archive](archive/CONNECTIONS.md) | Fossil/consolidation dumps | Intentionally dead history, excluded from intake by design. Not a bug bucket to "clean up." |
| [phoenix-core](phoenix-core/CONNECTIONS.md) | Standalone C intake engine (`phoenix-helix-c`) | Legacy/parallel to the bash intake pipeline; its `tools/intake.py` is explicitly deprecated. |
| [deploy](deploy/CONNECTIONS.md) | Remote Ubuntu deploy scripts | `deploy.sh` pushes `sector3/services/` + `dashboard/` to a remote box over rsync/ssh. |

**Root files not covered above:** `CLAUDE.md` (canonical law — read every session), `SESSION_STATE.md`
(narrower "where we left off" snapshot), `install.ps1`/`install.sh` (unified installer),
`status.sh` (repo-wide status check, predates `usys status`). `clonepool` at repo root is a
symlink to `/e/Phoenix/clonepool` — don't follow it expecting repo content.
