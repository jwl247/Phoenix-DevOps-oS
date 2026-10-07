# The HUD: the eye and the docks

**Framed by Jerry, 2026-10-07** ("let me frame it, then you build however you want"). Claude builds.
Replaces the earlier pane-based picture. `dashboard/` (Electron) is retired as the daily surface:
**the Console takes its place.**

## Jerry's frame, in his words
- "the ideal setup puts the **docks as the foundation**, drag and drop from there to the entire desktop"
- "with the docks **invisible or not even present until** you, per case, import them or whatever"
- "they have to be **drop-down capable** to some extent so it's not hard to find the file you're looking for"
- "so **the only visible thing is the Cylon eye (or KITT)**, whichever"
- "the **chat box should be a drop-down**, so **voice will be the primary tool** used to talk"
- "the only other thing would be a **button panel**, but all that can be **Console**; the Console takes the
  dashboard's place now, and **Jarvis is callable from there**"
- "**you are automatic upon boot** for me" — Claude on the subscription; "no API yet, that's coming, but money isn't right"

## What gets built
| # | Piece | Behaviour | Done when (run as Jerry) |
|---|---|---|---|
| 1 | **The eye** | The only thing always on screen: a small scanner bar (Cylon sweep / KITT voice bar), click-through, always on top. States: idle sweep, **listening**, **thinking**, **speaking** (pulses with the voice), **needs you** (a decision is waiting). | Cold boot shows only the eye; it changes state as Jerry talks and as Claude answers. |
| 2 | **Voice first** | Push-to-talk (hotkey or click the eye) → Claude answers out loud. Voice already exists (HUD M3); it becomes the main path. | A spoken question gets a spoken answer with the chat closed. |
| 3 | **Chat as a drop-down** | Clicking the eye (or a hotkey) drops the chat down from it; it folds away again. Not shown otherwise. | Chat opens/closes from the eye; the conversation is the same one voice uses. |
| 4 | **The docks** | Invisible, not drawn, until called: a file dragged toward a screen edge, or "open the dock" by voice. Each dock is a drop-down tree (pinned places: repo sectors, pool, Downloads, Desktop, recent) so files are easy to find. Drag from a dock to anywhere on the desktop; drop onto a dock for intake / ask Claude / send. Rule 10 holds: sensitive files never intake from a drop. | Drag a file to an edge: the dock appears; find a file 3 levels deep in the drop-down and drag it to the desktop; drop a file on the dock and intake it. |
| 5 | **Claude at boot** | At Jerry's logon: the eye starts, and a Claude Code session (subscription) starts with it, ready for voice. No API key tier yet. | Reboot PBMII: the eye is there and answers without Jerry starting anything. |
| 6 | **The Console = the button panel** | The Console replaces the dashboard for buttons (machines, services, hands). Adds **Ask Jarvis** (through his gate). Opened by voice ("open the console"), from the eye's menu, or `usys console`. | Ask Jarvis from the Console and get his answer; every former dashboard button Jerry uses has a Console home. |

## Order
eye (1) → voice + drop-down chat (2, 3) → docks (4) → boot (5) → Console + Jarvis (6). Each piece is
built, then broken as a user would, before the next. Jerry's in-progress right-edge dock (uncommitted
`HudOverlay.xaml(.cs)`) is kept and built on.

## Rules it keeps
Validate once at the door (intake does it, not the dock) · rule 10 (no sensitive intake from a drop) ·
no spies (sight stays opt-in with a visible light; screenshots stay local, Jerry's account only) ·
speed (the eye is cheap: no polling loops, no window repaints when idle).

## Modular: one platform, editions with different tools (Jerry, 2026-10-07)
"your HUD platform needs modular in the sense that its game implementation won't have all the tools I am
privileged enough to use." So: a **core** every edition gets (the eye, voice, drop-down chat, docks) and
**modules** an edition switches on or off. Nothing outside a module's switch can reach its tool.

| Module | Jerry (`full`) | Game (`game`) |
|---|---|---|
| eye, voice, chat, docks (core) | yes | yes |
| intake / clone pool from a dock | yes | no |
| Console (button panel, hands on other machines) | yes | no |
| Claude Code with tools (the subscription CLI) | yes | no — the game's AI gets only the game's own tools |
| Jarvis | yes | later, as the game's own companion, not Jerry's |
| dock places | repo, pool, imports, Desktop, Downloads, Documents, screenshots | the game's folders only |

The edition comes from `~/.phoenix/hud-profile.json` (`{"edition": "full"}`), default `full` on Jerry's
PC; a game build ships `game` and never the full module code paths (checked at every entry point).
