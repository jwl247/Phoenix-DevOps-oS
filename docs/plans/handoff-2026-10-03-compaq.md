# Handoff — 2026-10-03, cloud session → Claude on pbm-compaq

Written by the cloud session (branch `claude/youthful-ritchie-f42a4a`) for the Claude session
Jerry opens on **pbm-compaq**. Read CLAUDE.md first (AI SAFETY RULES especially: no
modprobe/udev, never touch breach_coms readonly state, ask before restarting anything). Then this.

Jerry says **Helix is repaired on the Compaq.** Confirm that first, in his terms, before
building on it (`sudo -n dmsetup status`, `systemctl status 'helix@*'`), and write down
what "repaired" means in the session log.

## 0. Get the work

```bash
cd ~/Phoenix-DevOps-oS            # or wherever the repo lives on the box
git fetch origin claude/youthful-ritchie-f42a4a
git checkout claude/youthful-ritchie-f42a4a
```

Commits on this branch since main (newest first):
- `1c856a6` intake.sh: keys off curl's command line (A2-N1) + no silent death on a missing D1 value
- `08f8d09` / `e9d11f6` universal kernel `scripts/phx-kernel.ps1` (+ `bingo`), tests 35/35
- `974f793` meshd survives switchboard outages at boot; hands/H.L.K IP_FREEBIND (A2-N6)

Nothing here is merged. Jerry decides when to open a PR.

## 1. FIRST — the demo Jerry asked for (he'll be satisfied when he sees it)

"A process pulled from R2, a functioning program pulled down, used briefly."
The cloud session got as far as reading the real R2 bytes of `helix_vram.py` and
`test_helix_vram.py` through the Cloudflare API, but had no worker keys and no way to
land and run them. On the Compaq it's the real thing:

1. pwsh on the box: `pwsh -v`. If missing, the portable tarball works with no installer
   (`powershell-7.4.6-linux-x64.tar.gz` from GitHub releases into `/opt/pwsh`) — tell Jerry
   before installing anything.
2. Keys: the box already has a per-plane `PHOENIX_AUTH` for the **road-test plane**
   (jerry.leftwich1 account, `phoenix-roadtest`), not our main pool. Either point the kernel at
   that plane (whatever `worker-bootstrap.sh` used) or at our pool with keys from Jerry's vault.
   Keys go in `~/.phoenix/kernel.env` (chmod 600) — **never on a command line** (A2-N1).
3. `pwsh -File scripts/phx-kernel.ps1 install`, open a new pwsh, `bingo` → status shows keys + pool.
4. Pull something real and use it. Best demo, if the plane has them: `test_helix_vram.py`
   needs `helix_vram.py` beside it, so pull both through the cache, then run the tests.
   Simplest honest demo: type a pooled command name, approve once, watch it run, type it again
   (no prompt, no network), `bingo log` to show the audit trail.
5. Show Jerry the output. Record it (session log + `bingo log` excerpt).

D1 facts (our pool, `phoenix_dev_db`): `helix_vram.py` hex `68656c69785f7672616d2e7079`, v1,
intaked **2026-06-14** — that may be OLDER than the repo's canonical `sector1/helix/helix_vram.py`
(heat-rank fix 2026-09-28). If the pulled tests fail against the pulled helix_vram, that's a
real finding: re-intake the canonical file. `test_helix_vram.py` hex
`746573745f68656c69785f7672616d2e7079`, v1, 2026-09-28. Both have SHA3 rows.

## 2. Deploy today's fixes to this box (Jerry's go for each restart)

- **meshd** (not self-updating): copy `sector3/phoenix-net/meshd/meshd.py` →
  `/opt/phoenix-mesh/meshd.py`, `systemctl restart phoenix-meshd`, then `python3 meshd.py status`.
  Then a reboot test is what proves the fix: the mesh must come up from the saved config even
  before the switchboard answers (`journalctl -u phoenix-meshd -b` shows "restored wg-phx ...").
- **hands — do NOT hand-copy.** `hands.py` re-imports the pool's version (currently v3) from the
  hub every 5 min and would undo a manual copy. Correct path: on the **Precision**, intake the new
  `hands/hands.py` (`scripts/hsf-intake.sh hands/hands.py`); the Console relays it; boxes swap in
  ≤5 min after checking SHA3 + compile. Then confirm on this box: no Errno 99 loop after a reboot
  (`journalctl -u phoenix-hands -b | grep -c 'Errno 99'` should be 0).
- **H.L.K** (`sector3/hlk/hlk.py`, IP_FREEBIND): same pool path as hands, or `hlk-up.sh`.
- **intake.sh changed** → it must be re-intaked (custody) or `worker-bootstrap.sh` will refuse/
  keep the old one: `scripts/hsf-intake.sh sector2/package-handler/intake.sh` from the Precision.

## 3. Finish A2-N1 (today's plan row: Sat 10/3 security round)

Done in `intake.sh` (14 calls → `curl -H @file`, 0600, removed on exit; proven with a /proc
cmdline watcher: 12 requests carried keys, 0 processes showed one). Still on argv:
- `sector3/worker-up/dataplane-up.sh` (2), `roadtest-measure.sh` (5), `worker-bootstrap.sh` (2)
- `sector2/package-handler/rotate-phoenix-auth.sh` (3) — careful, it rotates the live key
- `install.sh` (1)
- `sector2/apps/lifefirst/deploy_lifefirst.sh` — retired fossil (CLAUDE.md): leave it, note it.
Same pattern as intake.sh (copy the `AUTH_HDR_FILE` block). Prove each the same way: a stub
worker + a watcher scanning `/proc/*/cmdline` for the secret, with the secret kept in a file so
the watcher can't match its own command (the cloud session tripped on that twice).
Then file the round in `docs/compliance/pentest/` and mark A2-N1 and A2-N6 fixed-in-code.

Also found today in intake.sh and fixed: under `set -euo pipefail`, a `grep` that finds no
`hash_sha3` in a worker reply killed the whole run **silently** (offline, or a Phoenix that
doesn't know the file). Look for the same pattern in the worker-up scripts.

## 4. After that, in this order (Jerry's plan: money → Laurie → build; gate Thu 10/8)

1. `cd sector2/package-handler && node parse-connections.js` — Atlas refresh owed
   (phoenix-net + scripts CONNECTIONS.md edited). Needs the four keys from the vault.
2. Sun 10/4 clone pool done · Mon 10/5 `usys worker up` · **Tue 10/6 the deciding test, Helix vs
   standard caching — on this box, now that Helix is repaired** (working set > RAM; page cache,
   bcache/lvmcache; keep what's an advantage).
3. The genie (Jerry wants it IN THE HUD): (a) PS7-native intake that writes exactly the same
   D1/R2 records as intake.sh, so `intake <folder>` works with no bash; (b) a genie line on the
   HUD's KnightRider bar — command-shaped input runs in pwsh with the kernel loaded,
   plain English goes to H.L.K → hands tools, Ollama-local first; the HUD has NO PS7 pane today
   (its CLI pane is a Claude Code session, `hud/ClaudeCodeSession.cs`); (c) zsh kernel
   (`command_not_found_handler`) for the Chromebook/Linux boxes.

## 5. Things learned today that the next session should not re-discover

- **Mesh is healthy, not broken.** precision↔compaq direct ~99.5% of 24 h at ~2 ms; pbm3 "down"
  only because it's off. Tailscale rejected (vendor rule: their control plane + Google/MS SSO).
  `mesh_link_health` is never pruned (~600 MB/yr) — needs a cron + deploy, Jerry's call.
- **The kernel**: `scripts/phx-kernel.ps1` hooks PowerShell's CommandNotFoundAction, acts only on
  origin `Runspace` (typed at the prompt), looks up `<name>.ps1/.exe/.py/.js/.sh` by hex id
  (= the filename's bytes as hex, same as intake.sh `to_hex`), pulls R2 to a side file, SHA3-512
  must equal D1 or nothing is kept, asks once, caches in `~/.phoenix/kernel`, runs offline after.
  Built-in portable SHA3 for builds without OS support. Management command: **`bingo`**.
  Typing `intake` today would pull the pool's stale `intake.ps1` (v1, 2026-08-21, a bash wrapper).
- **Frank is not in the import path** — `intake.sh` never calls Frank; CLAUDE.md's "1. Frank
  registers the file" is wrong or unbuilt. The 9/22 session-log line calling
  `sector1/kernel/phoenix_core.py` a clone-pool importer is wrong: it's a 4-port remote shell.
- **GitHub repos**: 9 empty (all created and never pushed — last push = creation minute), 3
  README-only. `just-stuff` was emptied 2026-07-04 by a scripted sweep under Jerry's identity
  (same commit title in 5 repos in 2 min, no AI trailer) and is **restored** (`ca091e0`, a
  stock Seelen UI install). Jerry believes someone is erasing his data; the evidence so far says
  no outsider, but only his security log (`action:git.push` 2026-07-04 04:50–05:40 CT,
  `repo.destroy`) can settle it. Firmware he remembers was never in any repo history — GitHub
  rejects files >100 MB, which fits the empty repos.
- **Laurie**: tutorial page "Laurie's Budget Week" (claude.ai artifact 8eKPmfNMFw7SgW64FNNtdZ,
  private) — 5 days, uses the Life First MCP budget tools; her 6 categories exist, 0 bills.
  Her `/laurie` page has no budget screen (today/notifications only) — a vendor-free budget
  screen there is the long-term fix.
- **PBM / Radar**: the site already sells Radar publicly ($9.99/mo, beta). Jerry sells the consult
  to blue-collar trades (his own people) — offer to write the flyer + 30-second pitch in his voice.
- **Estate**: suggested a special-needs trust / ABLE account so Laurie's share can't cost her SSI,
  and registering the copyright (copyright.gov). Not acted on; Jerry's call.

## 6. End of session (CLAUDE.md protocol)

Session entry in `docs/history/SESSION-LOG.md`, BUILD STATUS one-liners, NEXT SESSION top items,
push. If any CONNECTIONS.md changed, run parse-connections.js before pushing.
