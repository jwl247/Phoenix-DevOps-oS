# Handoff — 2026-10-07 evening (read this first, then CLAUDE.md NEXT SESSION)

Everything below is committed and pushed (`main`, last commit after 04edd4f). Context ran to ~72%, so this
session ended clean on Jerry's call.

## 0. Start the next session with
```
Read docs/history/HANDOFF-2026-10-07-evening.md and CLAUDE.md, then build the rest of the Console list
(§3) in order. Fix without asking, re-run every change the way I would, commit + push as you go. Ask me
only for real decisions, in plain text, never popups.
```

## 1. Done today (all verified as a user; details in docs/compliance/pentest/2026-10-07-round4-addendum-4.md)
- **Engine swap finished**: Jarvis on llama.cpp on pbmIII; **Ollama removed from pbmIII** (it had been answering all along — NEW-F1). Jarvis hardened (tunnel-only UI user, pinned host key, per-caller lock, warm-up, units exposure ~1.3), **30-day purge** timer live. Engine, OpenJarvis src, 2 GB model in R2.
- **Fix waves 1–5**: everything Claude could do is done (~40 findings). **Cloudflare Access restored** on packages-worker (both hostnames, 302 anonymous / 200 with token). **packages-worker 3.8.2 live** (write-once versions, Jerry deployed). `rotate-key` now also rotates the Access secret (token in the vault via `setup-rotate-token.ps1`).
- **Nebula**: hands/Console/H.L.K on 10.42; PBMII firewall + Nebula 8470 open to servers only; Console reachable from pbmIII.
- **pbmIII**: nomodeset permanent (recovery entry not covered — offered, not done).
- **Rule 10 enforced at the intake door** (sensitive = a yes typed at a terminal only). Sensor 1.4.0 (watches its own code; off/lock are chained alerts; `security lock-hud`).
- **PS7 commands**: `g`, `pulse`, `pb3`/`aws1`/`box`, `snap`/`lastsnap`, `repo`, `..`/`...`, `glog`/`gst`, `here`, `pool`; WT copy-on-select on. **`/look`** slash command. Desktop **Screenshot to Claude** icon (folder = Jerry's account only). Buddy-heal console flash fixed.
- **The HUD, rebuilt to Jerry's frame** (`docs/plans/hud-eye-and-docks.md`): the **eye** is the only thing on screen (bigger, sight light red/green), **voice first** (Right Ctrl), chat drops down, **docks only on command** ("open the dock"/"door" — left = home, right = Phoenix root + pool + drives), **lockable by security**, **Jarvis by name**, **editions** (full/game), starts at logon (`Hud.exe --eye`), **the Console in the tray** (Phoenix bird) + a **Run box**. Jerry confirmed voice + docks work.

- **Slash-insensitive paths** (late): one rule in 3 copies that agree, scripts/phoenix-paths.ps1 (`px`), bin/phoenix-paths.sh, scripts/phoenix_paths.py; wired into usys, g, intake, clone. A bare `/c` is a flag, never a drive. Captured: **drives sequential on every PC** (by label; backlog; design with Jerry; rule 9).

## 2. Jerry's decisions today (also in memory)
Validate once at the door, no redundant checks · next phase = BUILD (build map: https://claude.ai/artifact/DMPqiZBA7newLdjzNXGf9Y) · jerry.leftwich1 = game only · defense pieces → immutable hot-swappable suits (plan: `docs/plans/defense-suits-immutable.md`) · HUD frame + modular editions + docks on command + lockable by security · game companion is called **David** · `.lol` → usys later · live screen streaming is the sight goal (`/look` is the stopgap).

## 3. NEXT — the rest of the Console list, in order (Jerry's calls in the HUD plan)
1. **Suit look-up** (replaces "clone pool look-up"): search suits in the pool by name/what they do; open, import (= run) from the result.
2. **Glossary shows the code** (Atlas/glossary entry → the file's code, read-only).
3. **Import = run a suit** (genie import) as a tray/Console action.
4. **Jarvis = the guide** (no Phoenix Guide): give him Atlas for look-ups (read-only), so "Jarvis, where is X" answers from the graph.
5. Talk out any other easy buttons with Jerry; Jerry-only admin buttons (rotate-key, lock-hud) only behind a typed confirm, if he wants them.
6. Then **live sight** (streaming, green light) → the build map's lifts.

## 4. Waiting on Jerry
Recovery-entry nomodeset (yes/no) · Windows local engine for PBMII (lift 5) · DASH-F24 · Radar cancel path · qcow2 + vault.enc sensitive · delete `C:\Program Files\Git\opt\` · phone node (Android or iPhone).

## 5. Gotchas learned today
- Bash heredocs here eat `\\` and turn `\r` in Python strings into a carriage return → write edit scripts with the Write tool; check with grep after.
- Editing `intake.sh` while a long intake runs: bash reads shifted bytes at the end (harmless once the work is done).
- WPF + WinForms: enable WinForms for NotifyIcon but `<Using Remove="System.Windows.Forms"/>`.
- Restarting the HUD = stop `Hud`, `dotnet build -c Release`, start `Hud.exe --eye` (the running exe locks the build).
- The permission check blocks `wrangler deploy` and security-weakening reverts from Claude even with Jerry's go: Jerry runs those (`!` prefix) or says the exact words.
- Another session (the HUD's own Claude) may edit HUD files between your reads: re-read before editing (today: dock/"door" STT fix).
