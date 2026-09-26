# Phoenix Portal — the WPF dashboard rebuild

## Context
The Electron dashboard (`dashboard/`) is rebuilt on the HUD's framework, WPF /
.NET 9 (decided 2026-09-25: "electron seems fragile with phoenix's asks"). The
Round 2 audit backs it: EOL Electron 28, self-elevation from exFAT F:, a page
that can reach a full shell, and 8+ dead buttons.

What it IS (Jerry, 2026-09-26): a **portal / front door for everyone**; later
the **workstation** on the virtual network, entered with "your key". Its job
now: **set up your work environment** and **provide the files you need
instantly**. Office and the HUD stay their own apps; the portal **employs**
them (starts them, knows they're running, hands them work).

New folder **`portal/`** (the old `dashboard/` stays untouched and in daily use
until the portal reaches parity and Jerry signs off).

## Decisions (Jerry, 2026-09-26)
**Cut** (now the HUD's or the AI's job, not buttons): sector switches/actions,
MAP, SECTOR MAP, CODES CLI, manual-as-GUIDE, meters, VENV, Debian/Phoronix
(PoC retires until needed), HELIX STATUS, CLONEPOOL browser, WATCH/INTAKE
DOWNLOADS, TELEMETRY, HUD MODE, THROUGHPUT/YOU WERE HERE, task/report stubs,
**CLAUDE hotline** (Claude Code lives in the HUD).

**Kept:** AI Chat (it IS the guide, Secretariat-style), provider picker, SHELL,
folder slots, GLOSSARY (descriptions, never code), RUNIT (reworked: plain),
SCREENSHOT, LIVE MONITOR, OFFICE button (new phoenix-office), SCRIPTFORGE,
launchers (Chrome, Steam, PS7, Bash, GitHub Desktop, Explorer), Config
Centralizer **only if proven working live first**.

**Rules:** no self-elevation (admin per action only) · default AI tier is not
full-tool Claude reading the screen · one shared library for HUD + portal ·
Office gets "open this file" · Laurie designs her own profile, her call on all
of it · **Phoenix Net (the virtual network) is built FIRST** · forum later.

**Existing .lol plumbing to build on, not replace:** `bootstrap/lol-bootstrap.ps1`
/ `.sh` (installs the `lol` command) and `install.ps1`'s `.lol`/`.phx` file
association → `usys open`.

**.lol rules** (everything ends in `.lol`, so Windows always routes it to usys;
the front decides): `example.py.lol` pull to working dir · `.lolexample.py.lol`
intake file · `.lol_direxample.lol` intake directory.

## Build phases (in order; each phase ends working, tested, committed)

### Phase 0 — Phoenix Net: the virtual network everything lives on (FIRST)
Jerry, 2026-09-26: "add the virtual network now because that makes tying it all
together easier ... its going to all live there." Decisions (2026-09-26):
**Cloudflare now, self-owned WireGuard later** (Jerry: "if half the work is done
for cloudflare we can migrate to self hosted later") · **hub = this PC (the
Precision)**: the Pavilion is inoperable (Jerry, 2026-09-26). The hub runs only
the `cloudflared` connector (outbound service, not a VPN), next to the existing
`Phoenix_win8_26` tunnel, untouched. Backup copy of the tunnel on a second
machine (the Compaq suggested: tiny, outbound-only) is a later add.
**Devices that must reach Phoenix Net:** this PC, the Compaq, pbm3, and
**Jerry's phone (Galaxy S23 FE, WARP app)**. The phone already runs Helix:
noted for a future bridge, not needed for Phase 0.
**Jerry's rules for the tunnels (2026-09-26):** connections run **ingress and
egress by the tunnels** (sector 3's Romeo in / Juliet out), each measured, so
we can judge how fragile each link is. WireGuard clashes with the VPN already in
use: the later WireGuard phase has to be built around that. WARP is also a
VPN-style client, so each device's WARP is tested against that VPN before
anything depends on it.
Home: `sector3/phoenix-net/` (sector 3 = comms/networking).
Why Cloudflare first: Access (email identity + service tokens) and tunnels
already exist, and a tunnel **dials out**, so it beats Starlink's CGNAT with no
relay server.
- **THE ONE RULE (keeps the later move cheap):** apps and services address
  each other by **Phoenix names** (`pavilion.phx`, `compaq.phx`, `portal.phx`…),
  never by Cloudflare-specific features or raw addresses. The names live in one
  file `phoenix-net` owns. Swapping to WireGuard later changes pipes, not apps.
- **0a Hub bring-up (this PC):** a dedicated `phoenix-net` tunnel, run by the
  `cloudflared` connector as its own Windows service. Separate from the existing
  Life First and `Phoenix_win8_26` tunnels (not touched).
- **0b The route:** the tunnel routes Phoenix's private network (the LAN
  192.168.1.0/24 and this PC's direct-cable 192.168.137.0/24, where pbm3 lives)
  to enrolled devices only. Each link's ingress/egress health is logged.
- **0c Join devices ("your key"):** Cloudflare WARP client on the Compaq, pbm3,
  **Jerry's phone**, and later Laurie's machine. Each tested against the VPN
  already in use first. Enrollment through
  Cloudflare Access with your email identity; only enrolled devices reach
  Phoenix Net. `phoenix-net` tool = one script that enrolls/lists/removes a
  device and keeps the Phoenix names file.
- **0d Firewalls:** box firewalls allow SSH/services from the Phoenix Net path
  only; nothing new opened to the internet.
- **0e** Phoenix services (portal, Office, HUD bridges, Frank) use Phoenix
  names. The portal shows who's online.

### Later phase — Phoenix Net goes self-owned (WireGuard)
Same Phoenix names, same `phoenix-net` tool interface; the Pavilion becomes a
WireGuard hub (`10.47.0.0/24`), devices swap WARP for the WireGuard client
(open source). Remote reach through CGNAT: IPv6 test first, small replaceable
relay if needed. Cloudflare stays only as a public front door if still wanted.

### Phase 1 — One shared brain: `shared/Phoenix.Shared` (net9.0-windows class library)
Move, don't rewrite, from `hud/`:
- `AiChatService.cs` (+ `AiAuthConfig`), `ScreenCaptureService.cs`,
  `Voice/*` (PushToTalkHotkey, MicrophoneCapture, WhisperTranscriber,
  PiperTextToSpeech, SpeechTextSanitizer, VoiceController, VoiceSetup),
  `Controls/KnightRiderBar`.
- Merge the duplicates into one each: `ClaudeCli.Find()` (today:
  `AiChatService.FindClaudeCli`, `ClaudeCliWindow.ResolveClaudeCli`) and
  `PhoenixEnv` (today: `AiChatService.LoadConfig` + `VoiceSetup.ReadPhoenixEnv`).
- Fix while moving (audit UI-F08): Ollama model from config, not hardcoded
  `"llama3"`; chat history capped at 20 turns like the dashboard.
- `hud/Hud.csproj` references the library. **The HUD must behave exactly as
  before.**

### Phase 2 — Portal skeleton: `portal/Portal.csproj` (WPF, opaque window)
- Plain opaque window (no transparency, so the terminal hosts inline: no
  companion-window workaround needed). Left rail of the kept features.
- **Runs as a normal user.** No UAC relaunch, no `RunLevel Highest`.
- Profile from `PHOENIX_PROFILE` (default = Jerry's full workstation). Laurie's
  profile is a placeholder until she designs it.

### Phase 3 — Set up your environment (the core job)
- **Folder slots (6):** drop a folder in; the active one is the working
  directory for everything. Same `~/.phoenix/hud-dropdown-slots.json` file the
  old dashboard uses, so both agree during the overlap.
- **SHELL:** `EasyWindowsTerminalControl` inline, pwsh in the active slot,
  `cd`s when the slot changes (logic from `dashboard/terminal-pty.js`).
- **Launchers + employ Office and the HUD:** find and start phoenix-office
  (installed exe) and `Hud.exe`; show running / not running; plus Chrome,
  Steam, PS7, Bash, GitHub Desktop, Explorer. ScriptForge opens in the browser
  (single-file HTML; its console already runs in a sandboxed iframe).

### Phase 4 — AI Chat is the guide
- Chat pane on `Phoenix.Shared.AiChatService`, provider picker.
- **Default tier = helpdesk (Ollama, then restricted CLI).** Full-tool
  subscription only when chosen, and never auto-fed the live screen.
- Secretariat-style declared tools (open a slot, pull a file, launch Office /
  HUD, search glossary): base tier runs, anything touching the outside world
  asks. Same schema Ollama-local can drive (CLAUDE.md rule 14).

### Phase 5 — Files instantly: the .lol rules (`scripts/usys.ps1`)
- `Invoke-UsysOpen` (usys.ps1:804): parse the name, not guess by existence:
  - `name.ext.lol` → `Invoke-UsysPull` to the working dir (exists today at :828)
  - `.lolname.ext.lol` → `Invoke-UsysIntakeFile` (Sector 2, canonical, :715)
  - `.lol_dirname.lol` → directory intake via Sector 2 (`scripts/hsf-intake.sh` path)
- Today's existing-file branch calls `Invoke-UsysIntake` (Sector 4), which
  refuses on this PC (no breach_coms4 mount): replaced by the Sector 2 calls.
- Portal: drop a file/folder on the portal = same rules. Tests added to the
  usys Pester suite.

### Phase 6 — Glossary, Runit, Screenshot, Live Monitor
- **GLOSSARY:** search the worker's `/glossary` (with the CF-Access headers,
  as `dashboard/hud-layout-backend.js` does); show name, what it is, where it
  lives, history. **No source code shown.**
- **RUNIT, plain:** drop or pick one file → it runs **in the SHELL pane** where
  you see it (not a hidden process); only files inside PHOENIX_ROOT or the
  clone pool, same limits as `dashboard/main.js:99-160`. Specifics from Jerry.
- **SCREENSHOT / LIVE MONITOR:** on `ScreenCaptureService`; captures stay in
  the user's own profile folder (not the world-writable `E:\...`, audit UI-S07).

### Phase 7 — Office accepts "open this file" (`phoenix-office/main.js`)
- Single-instance lock + read a document path from the command line / second
  instance; open it only if it's an Office document (path confined like
  `insideWorkdir`). Portal and HUD hand documents over this way.

### Phase 8 — Config Centralizer: prove it or drop it
- Run the existing scanner (`dashboard/config-centralizer.js`) live in front of
  Jerry. Works and he wants it → port to the portal. Otherwise it's dropped.

### Phase 9 — Install + switchover
- Publish to `%LOCALAPPDATA%\Programs\Phoenix Portal` (ACL'd, not exFAT F:),
  Start-menu entry, **non-elevated** logon task.
- Parity checklist signed off by Jerry → then the old `PhoenixDesktop` task is
  pointed at the portal. The Electron dashboard is kept, not deleted.

### Later (named, not built now)
Laurie's profile (she designs it) · Forum · Phoenix Net → self-owned WireGuard
· Desktop shade UI / drawer filesystem.

## Verification
- Phase 0: every enrolled machine reaches every other by its Phoenix name;
  SSH to the Compaq over Phoenix Net; a removed device loses access at once;
  from outside the house (phone off Wi-Fi) the phone reaches the Pavilion;
  a device that isn't enrolled can't reach anything.
- Phase 1: `dotnet build hud` clean; launch the HUD: chat reply, voice
  round-trip, Live Monitor frame, CLI pane — same as before.
- Phase 2+: `dotnet build portal` clean; launch **not elevated** (`whoami
  /groups` in the portal's SHELL shows no Administrators-enabled group).
- Each kept feature click-tested live on this PC; screenshot proof read back.
- Phase 5: Pester tests for the three .lol forms + a live pull/intake round
  trip (D1 row + R2 byte-identical fetch-back).
- Phase 7: `Phoenix Office.exe <doc>` opens that document; a second launch
  focuses the first window.
- Every phase: commit + push; old dashboard still starts and works.
