# HUD Voice Setup (Milestone 3)

Voice (push-to-talk → local Whisper STT → Claude → local Piper TTS) is code-complete
and wired into `Hud.exe`, but the two local models it depends on are **not** committed
to the repo — same treatment as Ollama's local models. Without them, the HUD still
launches fine and the hotkey is armed but inert; the AI Chat pane shows a `[SYS]` line
explaining what's missing.

## 1. Whisper (speech-to-text)

Download a ggml model from the whisper.cpp Hugging Face repo:
https://huggingface.co/ggerganov/whisper.cpp/tree/main

Recommended for a responsive push-to-talk clip on CPU: **`ggml-base.en.bin`**
(English-only, ~140 MB). `ggml-small.en.bin` is more accurate but slower per clip.

Place it at:
```
E:\Phoenix\voice-models\whisper\ggml-base.en.bin
```
(matches the "E: = Claude Operational Zone / models" convention already used for
`OLLAMA_MODELS`). Override the path with `PHOENIX_WHISPER_MODEL_PATH` in
`~/.phoenix/phoenix.env` if you'd rather put it somewhere else or use a different model.

## 2. Piper (text-to-speech)

Download a Windows release from https://github.com/rhasspy/piper/releases
(grab `piper_windows_amd64.zip`, extract it) and a voice model from
https://huggingface.co/rhasspy/piper-voices (each voice is a `.onnx` file plus a
matching `.onnx.json` config — download both, same folder).

Recommended starting voice: **`en_US-lessac-medium`**.

Place everything at:
```
E:\Phoenix\voice-models\piper\piper.exe
E:\Phoenix\voice-models\piper\en_US-lessac-medium.onnx
E:\Phoenix\voice-models\piper\en_US-lessac-medium.onnx.json
```
Override with `PHOENIX_PIPER_DIR` / `PHOENIX_PIPER_VOICE` in `~/.phoenix/phoenix.env`
(`PHOENIX_PIPER_VOICE` is just the `.onnx` filename; its `.json` config must sit next
to it).

## 3. Optional: change the push-to-talk key

Default is **Right Ctrl**. Override with `PHOENIX_VOICE_HOTKEY` in
`~/.phoenix/phoenix.env`, using any `System.Windows.Input.Key` enum name
(e.g. `PHOENIX_VOICE_HOTKEY=CapsLock`).

## 4. Using it

Hold the hotkey, speak, release — the transcript appears in the AI Chat pane exactly
like typed input, Claude's reply streams in as text, and (once Piper is installed)
gets spoken aloud. The scanner bar at the top of the HUD shows state: red sweep while
listening, amber pulse while thinking, cyan sweep while speaking. Pressing the hotkey
again while it's still speaking interrupts playback and starts a new recording
(barge-in).

The **CLI** button next to the close button shows/hides the CLAUDE CLI pane — once
voice is confirmed working, that pane no longer has to stay open all the time.


## Settings (in `~/.phoenix/phoenix.env`, no rebuild needed — just reopen the HUD)
| Setting | Default | What it does |
|---|---|---|
| `PHOENIX_VOICE_HOTKEY` | `RightCtrl` | the hold-to-talk key |
| `PHOENIX_VOICE_MIC` | first input device | any part of the mic's name, e.g. `V8S` |
| `PHOENIX_VOICE_PACE` | `1.15` | her speaking pace: 1.0 = natural, bigger = slower (0.7–2.0) |
| `PHOENIX_VOICE_SENTENCE_PAUSE` | `0.3` | seconds of silence between sentences |

## When voice doesn't work
Every failure now writes a `[SYS] voice: …` line in H.L.K-10's pane (and in
`E:\Phoenix\hud-live-monitor\chat-log.txt`): the mic that wouldn't start,
"didn't catch anything" with how loud the recording was (around -80 dB means
the mic is sending silence: check it's on, unmuted, gain up), speech
recognition errors, or the voice failing to speak. The startup line names the
key and the mic in use.
