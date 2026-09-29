# Phoenix-DevOps-oS — connections index

Read this before exploring. The directories linked to a `CONNECTIONS.md` below have one
with full detail (purpose, dependencies, commands, what it calls / is called by, known
issues). The rows marked "no per-dir doc yet" (hud/, phoenix-office/, portal/, hands/,
press-room/, pbm-consulting-website/) do not — audit CONN-F01. This file is just the map.

Baseline: written 2026-09-12; STALE/FALSE rows corrected 2026-09-29 against the Round 2
functionality audit (`docs/compliance/pentest/2026-09-28-round2-functionality.md`, CONN
section). Facts drift; re-verify anything load-bearing before trusting it blindly.
`sector2/package-handler/parse-connections.js` turns these files into the Atlas.

| Dir | What it is | Key fact |
|---|---|---|
| [sector1](sector1/CONNECTIONS.md) | Boot, kernel, auth, security | Guardian/honeypot security system resurrected 2026-09-09, wired into `main_kernel.py` + `phoenix_auth.py`. `sector1/grub/` is a second, unconfirmed-live USys implementation — ask before assuming it's dead. |
| [sector2](sector2/CONNECTIONS.md) | Intake authority, package handler, clone pool, apps (LifeFirst, Office, ScriptForge) | Canonical intake pipeline lives at `sector2/package-handler/intake.sh`. `sector2/frank/frank_save.py`'s drive-tiering logic is built but never called. |
| [sector3](sector3/CONNECTIONS.md) | Comms/networking, systemd services | `sector3/workers/packages-worker/` is a **stale, dead duplicate** of the real worker at `sector2/package-handler/worker/` — don't edit it thinking it's live. |
| [sector4](sector4/CONNECTIONS.md) | Helix/Frank core engine, vault | `sector4/intake/intake.sh`'s zsh-glob syntax error was fixed 2026-09-21 (`43c27ad`: shebang now zsh, glob replaced by `find`). `usys intake` still routes here while `usys clone` goes to `sector2/package-handler/intake.sh`; whether that is a mis-route or sector 4's own pipeline is an open call for Jerry (audit CONN-F08). |
| [dashboard](dashboard/CONNECTIONS.md) | Electron desktop command center | `main.js` sector paths are lowercase `sector1`–`sector4` (the old `SECTOR4` casing bug was fixed 2026-09-29). |
| [scripts](scripts/CONNECTIONS.md) | `usys.ps1` — the global CLI | `bin/*` and the dashboard call through here; `tools/clone.sh` and `scripts/hsf-intake.sh` call `sector2/package-handler/intake.sh` directly. The `usys run debian` elevation failure is handled (falls back to tcg acceleration). |
| [tools](tools/CONNECTIONS.md) | Utility scripts + `poc/` distro-boot sandbox | `tools/poc/` is where Debian/Ubuntu QEMU boot manifests + launchers live. |
| [bin](bin/CONNECTIONS.md) | Global CLI wrappers (installed on PATH) | Thin shims into `scripts/` and `tools/`; `bin/usys` has a dead fallback to a nonexistent `scripts/usys.sh`. |
| [bootstrap](bootstrap/CONNECTIONS.md) | Minimal `lol install` bootstrapper | Self-contained, zero references from the rest of the repo — confirm with Jerry whether it's active. |
| [docs](docs/CONNECTIONS.md) | Documentation | Contains the *previous* attempt at a connections doc (`PHOENIX_SYSTEM_SUMMARY_STATUS_CONNECTIONS.md`); its wrong worker/bindings references were corrected 2026-09-25, but this file supersedes it. |
| [archive](archive/CONNECTIONS.md) | Fossil/consolidation dumps | Intentionally dead history, excluded from intake by design. Not a bug bucket to "clean up." |
| [phoenix-core](phoenix-core/CONNECTIONS.md) | Standalone C intake engine (`phoenix-helix-c`) | Legacy/parallel to the bash intake pipeline; its `tools/intake.py` is explicitly deprecated. |
| [deploy](deploy/CONNECTIONS.md) | Local translator promotion script | `deploy/deploy.sh` only `sudo cp`s `sector3/translator/translator.sh` into `/etc/systemd`; the rsync/ssh dashboard push is `sector3/services/push-dashboard.sh`/`.ps1`, not this. |
| [pbm-consulting-website](pbm-consulting-website/) | pbmconsultingservice.com (Workers static assets) + `worker/` (pbm-leads-worker: lead form, Turnstile, email code) + `radar-worker/` (Set-Aside Radar, see its README) | Three separate deploys from one folder; `.assetsignore` keeps both worker folders out of the public site. No per-dir doc yet. |
| [hud](hud/) | The real Phoenix HUD (WPF, C#): live monitor, CLI pane, voice; `hud.checks/` is its check harness | Not the Electron dashboard (that stays as-is). No per-dir doc yet. |
| [phoenix-office](phoenix-office/) | Standalone sister product of Office (Secretariat, Legal Hold, Project Assist) with its own D1/R2/worker | Separate from `sector2/apps/office/`. No per-dir doc yet. |
| [portal](portal/) | Phoenix Console: the one dashboard served on Phoenix Net (`server.py` + `web/`) | Every machine opens this page instead of installing a dashboard. No per-dir doc yet. |
| [hands](hands/) | H.L.K's hands: the small per-PC helper (`hands.py`, `phoenix-hands.service`) that does what a web page can't; the Console (click) and H.L.K (voice) drive it through one fixed tool list with base/ask/never tiers | Every call logged to `~/.unitedsys/logs/hands.jsonl`. No per-dir doc yet. |
| [press-room](press-room/) | Blog posts, outreach and legal drafts, social calendar (text only) | No code. No per-dir doc yet. |

**Root files not covered above:** `CLAUDE.md` (canonical law — read every session), `SESSION_STATE.md`
(narrower "where we left off" snapshot), `install.ps1`/`install.sh` (unified installer),
`status.sh` (repo-wide status check, predates `usys status`), `README.md`, `BOB.md`,
`PHOENIX_BUILD_MASTER.md`, `LICENSE`, `.gitattributes` (LF for everything that runs on
Linux), `.metadata/`. There is no `clonepool` entry at the repo root; the pool lives at
`$CLONEPOOL_DIR` on each machine (E:/F: drift is an open question for Jerry).
