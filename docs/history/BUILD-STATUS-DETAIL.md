# Phoenix BUILD STATUS (full detail)
# Moved out of CLAUDE.md 2026-09-27. CLAUDE.md keeps a one-line-per-item summary.


### Phase 1 — External Ubuntu base (CURRENT)
- [ ] Ubuntu Server minimal + HWE kernel on external drive
- [ ] Prometheus installed
- [ ] Nextcloud installed
- [ ] PowerShell installed
- [ ] SSH access confirmed from PS7 (no WSL, not planned)

### Phase 2 — Sector 1 (Boot/Kernel)
- [ ] frank3_slot_a.c + frank3_slot_b.c placed in sector1/kernels/
- [ ] Makefile placed
- [ ] helix stack placed in sector1/helix/
- [ ] phoenix_auth.py placed in sector1/auth/
- [ ] concierge placed in sector1/concierge/

### Phase 3 — Sector 4 (Helix + Frank engine)
- [ ] Frank placed and confirmed immovable
- [ ] Helix engine running — confirm 300k+ ops/sec
- [ ] breach_coms drive map confirmed on external
- [ ] Clone pool initialized
- [ ] D1 worker URL set and syncing

### Phase 4 — Sector 2 (Package handler + clone pool)
- [ ] Phoenix-Package_handler migrated into sector2/
- [ ] intake.sh operational on external
- [x] packages-worker deployed and healthy (v3.4+ with /stats endpoint)
- [x] Import method tested end-to-end (C core ingress → D1 + R2 + local sidecar.json)
- [x] R2 upload wired into the bash intake.sh pipeline (was documented as canonical, never actually bound/uploaded to before 2026-08-22 — confirmed via byte-identical fetch-back)
- [x] Content-hash integrity system — SHA3-512 + BLAKE2b baseline set at intake (`clonepool.hash_sha3`/`hash_blake2`), re-checked at `intake clone` time via `POST /clonepool/:hex/validate`, gates clone-to-workdir/hot-swap on mismatch (see sector2/package-handler/README.md § Integrity Verification) — **was silently broken since introduction**, fixed 2026-09-20 (see SESSION LOG)
- [x] Real per-file version history — `versions` table + immutable per-content R2 keys (`/clonepool/:hex/versions/:hashPrefix`), auto-logged on every genuine content change via `POST /clonepool`. NOT time-windowed/auto-evicting yet — see `project_versioning_true_state` memory for the honest scope line. **Correction 2026-09-29 (round-2 audit XCUT-F15):** the per-version R2 bytes behind those keys had never been uploaded as of the 2026-09-28 audit — `intake.sh`'s only R2 writer (`upload_to_r2`) PUT `/clonepool/<hex>` (latest) only, and 7 of 7 live `versions` rows probed on 2026-09-28 returned 404 from R2 while the same hex's latest object returned 200. Until the fix is verified live, per-file history is a D1 ledger only: per-version bytes exist in the local pool, R2 holds latest. **Measured 2026-10-07 (Round 4 XCUT-F37, read-only):** the backfill did happen — D1 `versions` = 464 rows → 433 distinct `store_path` keys; R2 `phoenix-clonepool` = 944 objects, 430 `/versions/` keys; 429 of 433 paths have their R2 key, 4 do not (a `test_500` test row, `tier_rotation_test.txt`, an `index.html`, and the 2 GB `llama3.2-3b-q4km.gguf` whose version copy failed 2026-10-07), and 1 R2 version key has no row. Key presence only: the bytes behind each key were not re-hashed against D1's SHA3-512. CLAUDE.md BUILD STATUS's "408 older rows have none" is out of date (the backfill restored them 2026-09-29).
- [x] Tier placement + 4-day rotation/eviction — `T1`(newest)→T2→T3→T4→evicted, `rotate_clonepool_tiers()` wired into `intake prune`, R2 untouched by moves (hex-keyed, tier-agnostic). **Correction 2026-09-29 (XCUT-F16):** manual-only, never scheduled — `intake prune` is the sole caller and nothing invokes it (`usys.ps1`, the dashboard, `hsf-intake.sh`, the `.service`/`.timer` files, the installers and Windows Task Scheduler all checked 2026-09-28); rotation has never run on a schedule.
- [x] Dependency graph — `deps` table + `GET/POST /deps`, `translator.sh`'s new `deps` verb across all 9 backends, wired into `intake_from_backend()`
- [x] Location-aware QR — header/footer QR strings now carry a hex-encoded relative path segment, self-describing without a D1 round trip
- [x] Clone pool pull-down (R2 → local) — the pipeline only ever pushed before 2026-09-04. First fix: a dedicated, never-before-deployed `phoenix-clonepool-r2` worker (GET/PUT/HEAD `/object/:hex`), deliberately kept separate from packages-worker per Jerry's call at the time. **Superseded 2026-09-21 (git-divergence reconciliation):** packages-worker itself gained a real R2 binding + full PUT/GET/DELETE `/clonepool/:hex` handling, built independently in a stale checkout on 2026-09-20 before the two histories were known to have diverged — same underlying `phoenix-clonepool` bucket, more complete (adds the `/versions` sub-route + tier-move PATCH support), already deployed and tested (0 D1/R2 failures on a full re-intake). Jerry's call on reconciliation: keep the integrated version, retire `phoenix-clonepool-r2` (code kept at `sector2/package-handler/r2-worker/` for rollback, no longer called by `intake.sh`). `usys open <name>.lol` remains the context-sensitive alias — existing local file = old intake-to-vault behavior; missing local file whose base name matches a pool entry = clone-to-workdir. Proven live end-to-end (byte-identical SHA256) from a fresh, non-dashboard PowerShell session outside the repo — genuinely global, not scoped to the embedded shell.
- [x] `usys`/`phx`/`clone`/`.lol`/`.phx` now load in every new terminal, not just the dashboard's embedded SHELL — `C:\Users\jwlef\Documents\PowerShell\Microsoft.PowerShell_profile.ps1` didn't exist before 2026-09-04; created it (guarded, falls back to `~/.phoenix/phoenix.env` → hardcoded path, never breaks an ordinary terminal if the repo's missing). Existing open terminals need reopening (or `. $PROFILE`) to pick it up.
- [x] Security Gap 1 — every GET route gated + a leftover Cloudflare Access "bypass, everyone" policy (dated 2026-03-27, silently defeating Access this whole time) removed, service-token policy fixed (needed its own `non_identity` decision, not folded into the identity `allow` policy). Deployed and verified live 2026-09-21.
- [x] Security Gap 2 (content encryption) — CLOSED 2026-09-21 as a deliberate posture decision, not a build: rely on Gap 1's access control + R2's own server-side encryption, no custom client-side encryption layer. Pen test planned later to validate against real findings — see NEXT SESSION + `project_security_gap_plan` memory.
- [ ] Propagator rebuilt in sector2/propagator/

### Phase 5 — Sector 3 (Comms/networking)
- [ ] romeo.py + juliet.py + dbl_juliet.py placed
- [ ] translator.sh placed — OUTPUT ONLY rule enforced
- [ ] quadengine.py placed
- [x] phoenix-dashboard.service written → sector3/services/phoenix-dashboard.service
- [ ] All .service + .target files deployed via install-units.sh on Ubuntu

### Phase 6 — Apps (Entourage)
- [x] Dashboard Electron app — real D1/R2 data, Claude HUD, boot-time auth modal
  (**SUPERSEDED 2026-09-19/20 — see the next line.** The 2026-09-19 plan below
  this note said dashboard/ IS the HUD and would just get renamed. That
  direction was dropped: Jerry's actual call was "electron is a fabulous
  dashboard but not a HUD" — dashboard/ keeps its name and stays exactly
  as-is (still in daily use, deliberately untouched by HUD work), and a real,
  separate WPF project at `hud/` is the actual HUD. No dashboard/ → hud/
  rename ever happened or is planned.)
- [x] **Real HUD — `hud/` (WPF, .NET 9), NOT the Electron dashboard.** Genuinely
  transparent overlay window (`AllowsTransparency`, per-pixel alpha, desktop
  shows through). Milestone 1 (2026-09-19): Live Monitor (continuous desktop
  capture) + AI Chat pane ("H.L.K-10"), sharing the same `~/.phoenix/ai_auth.json`
  the Electron dashboard uses. Milestone 2 (2026-09-21): a real interactive
  Claude Code CLI pane (ConPTY-backed, `EasyWindowsTerminalControl` — the
  actual Windows Terminal render backend) — H.L.K-10 can work, not just watch.
  Solved a real WPF constraint along the way (transparent windows can't host
  native controls — "airspace" — so the CLI pane is a separate, synced
  companion window, now the standing pattern for any future native-hosting
  pane). Milestone 3 (2026-09-22): voice — push-to-talk via a `WH_KEYBOARD_LL`
  global hook (not `RegisterHotKey`, for a real key-up signal), local Whisper
  STT (CPU runtime explicitly pinned per the GPU-blacklist rule below), local
  Piper TTS (chosen over Windows SAPI for real voice quality), a KITT-scanner/
  Cylon-eye `KnightRiderBar` indicator (pure WPF, no companion window needed),
  and barge-in (talking over a reply stops it, starts a new capture). Voice
  reuses `AiChatService`'s existing full-tool `"subscription"` CLI path rather
  than parsing the CLI pane's terminal output — why the CLI pane no longer has
  to stay permanently visible (new manual show/hide toggle added, left
  visible-by-default pending live testing). **LIVE-VERIFIED 2026-09-22** —
  Whisper (`ggml-base.en.bin`) + Piper (`en_US-lessac-medium`, confirmed
  female voice) models installed to `E:\Phoenix\voice-models\`, hotkey held,
  spoken question transcribed into the chat pane, Claude's reply came back
  and Jerry heard it spoken aloud. Scanner-bar animation states and barge-in
  not yet separately confirmed. Two real bugs found+fixed getting there: (1)
  `AiChatService.FindClaudeCli()` only checked the npm-global `claude.cmd`
  path (doesn't exist on this machine) — same class of bug Milestone 2 had
  already fixed once in `ClaudeCliWindow.xaml.cs`, just not ported to this
  second, separate CLI-resolution copy; now checks `~/.local/bin/claude.exe`
  first. This is why the very first live attempt heard the mic fine but got
  no reply at all (Ollama down -> "helpdesk" provider fell through to a CLI
  path that silently couldn't find `claude`). (2) Live Monitor and the AI
  chat/voice loop had no wiring between them — Jerry: "they have to tie
  together" / "specifficly you" / "claude code in the hud". Fixed: every
  ~3s, `MainWindow` now saves the current Live Monitor frame to
  `E:\Phoenix\hud-live-monitor\current.png`; `AiChatService.SendAsync` passes
  that path through — the Claude API path attaches it as a real vision
  content block, the CLI paths get a text note pointing at the file (`Read`
  is never in the restricted CLI's disallowed-tools list). Proven live: this
  session Read that file directly mid-conversation and saw Jerry's real
  desktop. Also fixed, same pass: chat text was unreadable (Jerry: "the text
  needs to be bright yellow... i cant read it very well") — root cause
  wasn't just color, the rest of the HUD is deliberately near-transparent
  (`HudPanel` style, 28% opacity) so text contrast varied with whatever was
  behind the HUD on the desktop; gave the chat log its own ~90%-opaque
  backing panel plus bright-yellow (`#FFFF00`) text. See
  `project_hud_architecture_pending` memory, don't re-derive.
- [x] Claude HUD wired — subscription / API key / Ollama (three-tier, nobody excluded)
- [x] Helix memory on both ends — helix_packet.js (JS) + ClaudeMemory (Python, QuadralingualPacket)
- [ ] MapTiler integration — MAP nav pane still the filesystem browser; MapTiler wiring lives on `checkpoint/real-terminal-2026-08-30` if wanted (needs `PHOENIX_MAPTILER_KEY`)
- [x] Glossary pane built in the HUD — search + category/state filters + version history, live against the worker (backend confirmed 2026-08-21, see docs/GLOSSARY.md)
- [x] Atlas connections library — `connections` D1 table + `/connections`, `/connections/:id`, `/connections/:id/related` (8-neighbor "snow globe") on packages-worker, parsed from all 13 CONNECTIONS.md files (`sector2/package-handler/parse-connections.js`, 37 nodes). Claude answers Atlas questions directly via `.claude/skills/atlas/SKILL.md` — no coded panel, same pattern as Glossary in chat. See docs/ATLAS.md. Built 2026-09-25.
- [x] REAL embedded terminal — **SHELL** pane, `terminal-pty.js` (xterm.js + node-pty prebuilt ConPTY). Persistent pwsh/bash in the working dir with full profile+PATH. Replaces the spawn-per-command `ps7-shell.js` fake (2026-08-30)
- [x] **CLAUDE hotline** — CLAUDE pane = interactive Claude Code in a PTY, in the working dir, on the Claude.ai subscription. Proven live via CDP (2026-08-30)
- [x] Unified working directory — the active folder slot IS the working dir; SHELL + CLAUDE open there and `cd` to follow when it changes (2026-08-30)
- [x] Laurie's Guide = a gentle guided conversation (the GUIDE tab), gated to `PHOENIX_PROFILE=laurie` — her own system prompt (patient, one-step-at-a-time, "it's easier than it sounds"), chat-only chain (Ollama → restricted Claude CLI, never the full-tool path), first-open welcome, "plain-text version" escape hatch. Everyone else gets the dev manual in GUIDE until it's vetted (2026-08-30)
- [x] HUD glass + HUD-mode toggle (frameless translucent overlay over the desktop), declarative button generator, PoC buttons (Debian/Helix/Phoronix/Watch-Downloads), Google/Chrome launcher, `--disable-gpu-sandbox` launch fix (2026-08-30 morning)
- [x] Dedicated Claude "subscription" mode in dashboard chat — real Claude Code CLI with `--dangerously-skip-permissions`, fully separated from Ollama (no fallback, no interference); real SSE streaming added for the plain API-key path too
- [x] Live Monitor panel — on-demand desktop/window screen capture (desktopCapturer) streamed to Claude chat, separate capture destination from the watched screenshots folder so the two don't storm each other
- [x] Clonepool panel converted to async (fs.promises) with search + result capping — was freezing the whole Electron main process once the pool passed ~15k files
- [x] Clonepool made available at the repo root as a Windows directory junction (already gitignored); PS7 shell dot-sources `scripts/usys.ps1` so `clone`/`usys` work inside it (previously silently missing under `-NoProfile`)
- [x] ScriptForge — given a real home at `sector2/apps/scriptforge/` (was loose in `tools/`, unwired, undocumented); sandboxed its console-execution tab (was running pasted code with full page access) and added a CONVERT tab (JSON⇄CSV, beautify/minify, Base64, URL-encode); wired into the dashboard as a SCRIPTFORGE button opening its own isolated Electron window (2026-09-05, verified live via CDP)
- [ ] Desktop (shade UI, drawer filesystem) — dashboard transforms into this
- [x] **Config Centralizer → Settings tab — DONE, 2026-09-05.** See Phase 4 entry above for full detail. Real scanner recovered from an old claude.ai conversation, ported to Node (`dashboard/config-centralizer.js`), a real bug fixed in the port (bare-named credential files), wired into `#hud-pane-settings`, verified live: 113 real files found on this machine.
- [x] Office (dual browser pane) — **usable end to end as of 2026-09-07.** Phase 1 + Phase 2 Modules 1-2 (file format, D1 schema), **Module 3** (notification transport — `office-notify-worker` + `tamper-guard.js`), **Module 5** (pluggable identity — `lib/identity.js`), **Module 6** (dual-pane UI, `OFFICE` dashboard button), **Module 7** (the EASY pass — autosave, seal-on-sign, template picker, reference-pull) all built. 51 tests. Only **Module 4** (LibreOffice/Frank/Helix invisible format-following) remains, and it's not on the critical path. **M3 `office-notify-worker` deployed live 2026-09-09** (schema applied, `PHOENIX_AUTH` synced, cron on, `/notify`+`/ack` smoke-verified against real D1) — pending live checks now just: set `RESEND_API_KEY` (Jerry) for real send + one GUI OFFICE-button click. See `sector2/apps/office/DESIGN.md` + `PLAN-modules-3-6.md`.
- [ ] Sketchpad/Concepts
- [ ] Music Notation Transcriber
- [ ] Review Platform

### Phase 7 — GRUB + polish
- [ ] Custom Phoenix GRUB theme
- [ ] Boot entries configured
- [ ] Vault recovery pointer in GRUB
- [ ] External drive boots clean as Phoenix

