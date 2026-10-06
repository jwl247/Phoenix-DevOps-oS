# PBMII handoff, evening of 2026-10-03

This follows `2026-10-03-pbmii-handoff.md`. Everything from this evening is in
`F:\Phoenix\Phoenix-DevOps-oS\tentative-wares\`. Each piece passes its own tests, nothing is
wired into the live tree, and **nothing is committed**. The one change outside
`tentative-wares` is `sector1/kernel/genie/genie.ps1`: `genie custody` now reads every
clonepool row, not just the newest 100.

## In tentative-wares

| Ware | State | To go live |
|---|---|---|
| `dashboard/` | Built and tested in Electron on Linux:<br>• The folder bar across the top: HOME · ROOT · PHOENIX + 6 slots. Each drops down to every file in its folder, one click, and you drag between them (drag = copy, Shift = move, ✎ renames). Nothing is ever overwritten, nothing is moved out of breach_coms4, and the OS's own folders are protected.<br>• CONSOLE and HUD launch buttons.<br>• Repo-location fix: the dashboard looked in `~\Phoenix\...` instead of `F:\Phoenix\...`. | `INSTALL.md`, then the Windows checks below |
| `package-handler-3.9.0/` | Member keys: one key per person, read plus intake of their own names, no deletes, revocable. Intake asks before it writes. | `DEPLOY.md`. **The migration runs before the deploy.** |
| `genie-cloud/` | A Genie that needs only R2 + D1 and no kernel. Adds `tour`, `intake`, and owner `key` commands. Its README is written for JW's son. | After 3.9.0 is live: `genie key new <son>` |
| `peer-review/` | Building blocks for the forum: SHA3, passkeys, the two-way Discord bridge, and the forum schema (tests: SHA3 12, passkeys 12, Discord 22, schema 47 rules). | The worker and website are still to build |

## Finishing the Windows dashboard (tonight's last step)

```powershell
cd F:\Phoenix\Phoenix-DevOps-oS
Copy-Item tentative-wares\dashboard\*.js, tentative-wares\dashboard\*.css, tentative-wares\dashboard\index.html dashboard\ -Force
cd dashboard; npm start
```

Check these; they're the parts only Windows can test:

1. **ROOT** drops down to your drives (C:, D:, E:, F:, and so on).
2. Drag a test file from one slot to another (it copies), and Shift-drag one (it moves). Rename one with ✎.
   Try a file whose name already exists at the other end: it should be refused with the reason.
3. Drag a file in from Explorer: it should be **copied**.
4. Drop a folder from Explorer onto an empty `+` slot: that folder becomes the slot.
5. **CONSOLE** opens the Console window. If the Console was stopped, it starts it first
   through the PhoenixPortal task.
6. **HUD** starts the HUD, or says "not built" or that the build is older than its source.

If anything misbehaves, copy back the originals with `git checkout -- dashboard`, since
nothing was committed.

## Written down, not built yet

- **The Console is still on WireGuard,** which was retired on 2026-10-01.
  - `portal/server.py` only listens on 127.0.0.1 and 10.47.0.x.
  - Its firewall rule only allows 10.47.0.0/24.
  - The helpers on the Compaq and pbm3 (`hands.py`) only answer calls from 10.47.0.2.
  - So right now the Console only works on PBMII and can't reach the Compaq.
  - **Next fix:** move all of it to Tailscale (100.64.0.0/10, `tailscale status --json`
    for machines and links), with the same token per machine.
- **One dashboard talking to another.**
  - Today, dashboards share only the cloud pool, through intake and clone.
  - Once the Console and helpers are on Tailscale, the folder bar can have one dropdown
    per machine. You'd drag files between PBMII, the Compaq and the phone, with the same
    no-overwrite and checked-copy rules.
- **Names are global in the pool,** because the hex identity comes from the file name.
  Members can't reuse any name the owner already has. A per-person namespace would change
  the identity scheme, which is Jerry's call.
- **Clutter:** about 100 empty `python_install_*.log` files sit in the repo's top folder.
  Delete them, or add them to `.gitignore`.
- **Debt:** the full `genie.ps1` still has its own copy of the clone and custody code, and
  looks names up through `/search`, which returns at most 20 matches. It should load
  `genie-cloud.ps1` for that half instead.

## Atlas + commands (done tonight, one step left)
`CONNECTIONS.md` is updated in the root, sector1, sector2 (Atlas log + 6 new Session State frames), portal
(WireGuard issue), dashboard, and new `tentative-wares/`. They parse cleanly: the Atlas parser gives 63 rows
and 18 frames from the changed files. `docs/COMMANDS.md` has a new section with every command from today:
what it does, how to use it, and its status. **Your step:** push them to the Atlas:

```powershell
cd F:\Phoenix\Phoenix-DevOps-oS\sector2\package-handler
node parse-connections.js
```

## Commit when the checks pass

```powershell
cd F:\Phoenix\Phoenix-DevOps-oS
git add dashboard tentative-wares sector1/kernel/genie/genie.ps1 CONNECTIONS.md sector1/CONNECTIONS.md sector2/CONNECTIONS.md portal/CONNECTIONS.md docs/COMMANDS.md docs/handoffs CLAUDE.md docs/history/SESSION-LOG.md tentative-wares/CONNECTIONS.md dashboard/CONNECTIONS.md
git commit -m "Dashboard: folder bar across the top (drag between folders), Console/HUD launchers, repo-root fix; tentative wares: package handler 3.9.0 member keys, cloud Genie, peer review blocks"
git push
```

## Next session
Jerry: **the game (Monster Phoenix)**. Start from the GDD v2 in the clonepool (`Monster_Phoenix_GDD_v2.docx`), the game folder in the repo, and the Atlas (`/meta/atlas`). The dashboard Windows checks and commit carry over if they aren't done.

## JERRY'S DESIGN CALL (2026-10-05) — before any of this installs
Nothing in `tentative-wares/` has been verified by Jerry ("that's where it fell apart"). It stays
uncommitted and uninstalled until it is checked against this:
- **Game HUD (the KITT companion in Sacrifice) = H.L.K EXCLUDED.**
- **Dashboard = the opposite: H.L.K INCLUDED.** The dash launches the HUD (the H.L.K overlay) and the
  **Console for whatever mesh** — any machine on the Nebula mesh, not only `127.0.0.1:8470`.
- **The Claude call from the dash is the existing CLAUDE hotline** (`dashboard/terminal-pty.js`) — no new one.
Gap seen 10/5: the staged `phoenix-apps-launcher.js` opens the Console on localhost only — needs the
mesh-host choice (10.42.0.x) before it matches the call.
