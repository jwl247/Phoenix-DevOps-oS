# Dashboard: folder bar across the top, and launching the Console and HUD

## What changed

**Folder bar.** It now runs across the top, under the title bar, side by side:
**HOME · ROOT · PHOENIX**, then your 6 slots.

- **Every file shows.** Each one drops down to every entry in its folder: hidden files
  included, nothing filtered, folders first, with sizes.
- **ROOT** on Windows is every drive (C:, D:, E:, F:, and so on); on Linux it's `/`.
- **Getting around:** one click on a folder goes in, `↑` goes up, one click on a file selects it, and `↗` on a file opens it. No double-clicks.
- **Drag between any two dropdowns,** or onto a folder row:
  - A plain drag **copies**. The original stays where it was.
  - **Shift**-drag **moves**.
  - Ctrl-click selects several items, which then drag together.
- **`✎` renames** a file or folder in place. Enter saves, Esc cancels, and an existing name is refused.
- **Files dragged in from Explorer are copied,** never moved.
- **To set a slot,** drop a folder from Explorer onto an empty `+` slot. `◉` makes it the
  working directory (the shell and Claude follow it). `×` clears the slot; the folder
  itself is never touched.

**Console and HUD buttons.** These are the first two buttons in the right column. Each
shows whether its app is running.

- **CONSOLE** starts `portal/server.py` if it's down, through your `PhoenixPortal` task,
  or through `pythonw` if there's no task. Then it opens the Console in its own window,
  which has no access to the dashboard's internals.
- **HUD** starts `hud\bin\...\Hud.exe`, using the newest build. If the HUD's source is
  newer than that build, it tells you to rebuild.

**Repo location bug fixed.** The dashboard looked for the repo in
`~\Phoenix\Phoenix-DevOps-oS`, but yours is `F:\Phoenix\Phoenix-DevOps-oS`. Unless
`PHOENIX_ROOT` was set, every repo path it used pointed at nothing: Office, ScriptForge,
the intake and help commands, and now the Console and HUD. It now uses the repo it
lives in.

## Safety rules (checked in the main process, `slot-transfer.js`)

- **Nothing is ever overwritten.** If the name is taken, that item is skipped and the
  dropdown says why.
- **A folder can't go inside itself.**
- **Nothing is ever moved out of `breach_coms4`.** Copying from it is fine.
- **Operating-system folders are protected.** Windows, Program Files, ProgramData, the
  Recycle Bin and System Volume Information can never receive files or be moved. A drive
  root can't be moved either.
- **A move to another drive is checked before the original goes.** The copy's size and
  SHA-256 must match for every file, or the copy is removed and the original stays.

## Tested

- **`node slot-transfer.test.js`:** 22 rule checks (including rename) pass on real folders, including a
  simulated cross-drive move and a bad copy.
- **The real dashboard in Electron (Linux, under xvfb):**
  - The bar sits under the title bar.
  - HOME and ROOT list everything.
  - Slot A shows all 43 entries, including the hidden one.
  - A real mouse drag moves A → B, and a drag onto a subfolder works.
  - A name clash is refused, with the reason shown and nothing overwritten.
  - Navigating in and up works.
  - Clearing a slot leaves its folder alone.
  - CONSOLE starts the Console and opens it in a locked window (no Node access), and
    reuses that window instead of opening a second one.
- **Not testable here (Windows only):** the drive list on ROOT, the `PhoenixPortal` task,
  `Hud.exe`, and dropping files in from Explorer. Check those first.

## Install

```powershell
cd F:\Phoenix\Phoenix-DevOps-oS
Copy-Item tentative-wares\dashboard\*.js, tentative-wares\dashboard\*.css, tentative-wares\dashboard\index.html dashboard\ -Force
cd dashboard; npm start
```

Your current slot folders carry over, since they're in the same
`~\.phoenix\hud-dropdown-slots.json`.
