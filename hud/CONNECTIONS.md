# hud — the real Phoenix HUD (H.L.K-10)

Written 2026-09-30 (CONN-F01) from the code in this folder. Verify against current code
before trusting a specific line number.

## What it is
A see-through WPF (.NET 9) overlay over the whole screen. Jerry talks to H.L.K-10 by voice
or text, it sees the screen, and it acts on the machines through the hands. This is the HUD;
the Electron `dashboard/` is a separate app and stays as-is.
- **Two windows (Jerry, 2026-10-07/08):** the **HUD = KITT, the eye + docks** (`HudOverlay.xaml(.cs)`; `Hud.exe --eye` at logon; docks only on command — voice "open the dock", the eye's right-click menu, the tray, or the Console's DOCKS button; security can lock them) and the **Console = the button panel** (`MainWindow`, opened from the tray bird).
- **Console buttons (2026-10-08):** the "USYS — ONE WORD" panel (`UsysButtons.cs` + `MainWindow.Easy_Click`): IMPORT, INTAKE S, INTAKE C, INTAKE C ▸ FOLDER, GET, RUN, OPEN, CLOSET, STATUS, START, STOP, LOG, DOCKS, HELP — each runs one `usys` command (`scripts/usys.ps1`, `-File`, args as argv) in a PS7 window that stays open. Title bar: EXPLORER / TERMINAL (`ConsoleActions.cs`), SUITS + GLOSSARY (`SuitLookup.cs` over `Desktop/PoolClient.cs`: pool + Atlas search, code read-only and SHA3-checked against D1 custody; sensitive rows never shown), COMMANDS (`CheatSheet.cs` = `usys help`, else `docs/COMMANDS.md`, else the pool copy).
- `MainWindow.xaml` / `MainWindow.xaml.cs` — the Console: Live Monitor, H.L.K-10 chat pane, CLAUDE CODE pane, the KITT scanner bar, the buttons above. Saves the screen frame and both transcripts to `E:\Phoenix\hud-live-monitor\` (`current.png`, `chat-log.txt`, `claude-code-log.txt`) so any Claude session can read them.
- `AiChatService.cs` — H.L.K-10's brain: the provider chain helpdesk → Ollama → Claude CLI → subscription, read from `~/.phoenix/ai_auth.json` + `~/.phoenix/phoenix.env` (same files and order as the dashboard). The Ollama path uses a fixed JSON reply shape so a local model can't invent results.
- `HandsClient.cs` — H.L.K-10's hands: fetches the tool list from the Phoenix Console (`/api/hands`, refreshed in the background every minute) and runs one `ACTION` at a time; ask-tier tools only run on the user's own yes.
- `ClaudeCodeSession.cs` — the CLAUDE CODE pane: full Claude Code (`claude -p`, stream-json, `--resume`), subscription only.
- `ScreenCaptureService.cs` — the Live Monitor screen capture.
- `Voice/` — push-to-talk (Right Ctrl, `PushToTalkHotkey.cs`), microphone (`MicrophoneCapture.cs`), local Whisper speech-to-text on CPU (`WhisperTranscriber.cs`), local Piper voice (`PiperTextToSpeech.cs`), text cleanup before speaking (`SpeechTextSanitizer.cs`), barge-in and state (`VoiceController.cs`), model checks (`VoiceSetup.cs`).
- `Controls/KnightRiderBar.xaml` — the scanner bar: red listening, amber thinking, cyan speaking.
- `VOICE_SETUP.md` / `setup-voice.ps1` — one-time install of the Whisper and Piper models to `E:\Phoenix\voice-models\` (not in the repo).
- `hud.checks/Program.cs` — the check harness: `dotnet run --project hud.checks -- --live` runs the live checks (Claude subscription + Ollama).

## Dependencies
.NET 9 SDK; NuGet NAudio, Whisper.net (CPU runtime pinned, no GPU), Whisper.net.Runtime.
Piper and the Whisper model on disk. Claude Code CLI at `~/.local/bin/claude.exe`; Ollama on
`localhost:11434` for the local tier.

## Commands / entry points
- `dotnet build hud` then run `hud\bin\...\Hud.exe` (restart the HUD to pick up changes).
- `pwsh hud/setup-voice.ps1` (first install of the voice models).
- `dotnet run --project hud.checks -- --live`.

## Connects to / connected from
- `hud/HandsClient.cs` → `portal/server.py` (tool list and actions go through the Phoenix Console).
- `portal/server.py` → `hands/hands.py` (the Console passes each action to that machine's hands).
- `hud/AiChatService.cs` → `dashboard/main.js` (shares its config files and provider order; no code shared).
- `hud/ClaudeCodeSession.cs` → the Claude Code CLI (claude.exe in the user's local bin folder, outside the repo).

## Known issues (verified, not guessed)
- For about the first 20 seconds after the HUD starts, the tool list hasn't arrived yet, so a
  message sent then goes without tools (chat only). Longer while a machine on the hands list
  is down: the Console waits up to 40 s per dead machine (pbm3, down since 2026-09-27).
- The subscription path has full Bash by design, so it could call the Console directly
  instead of using `ACTION`; the prompt steers it, nothing hard-blocks it.
