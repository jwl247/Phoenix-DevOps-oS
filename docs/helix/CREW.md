# The crew — one sailor per sector (2026-09-28)

Jerry: "like one per sector, only job is to verify and take care of that sector, like sailors on a
ship, you're the captain." This is that. A sailor is a **read-only watch**. It verifies its deck and
reports to the captain. It never fixes, reverts, restarts, deploys or heals anything: an agent with
write access that "protects" code is the exact shape of the session that cost three PCs.

## What runs

| Piece | File | Job |
|---|---|---|
| Roster | `sector4/guardian/crew.json` | each sector's deck: watched paths, box services, heartbeat files, `scripts/verify.sh` checks |
| Sailor engine | `sector4/guardian/sailor.py` | one process per sector: drift, never-list scan, services + heartbeats (box only), optional checks, report to the ledger |
| Gangway | `sector4/guardian/gangway.py` + `.claude/settings.json` | PreToolUse hook on every Claude Code Bash call in this repo: the never-list blocks the command before it runs (exit 2, reason shown) |
| Units | `sector3/services/phoenix-sailor@.service` | `phoenix-sailor@sector1..4`, `ProtectSystem=strict`: the kernel makes everything but `/var/lib/phoenix/crew` and the ledger read-only for the sailor |
| Muster | `tools/crew/muster.sh` | every sailor runs one watch, deck report to stdout, exit = findings |
| Claude sailors | `.claude/agents/sailor-sector{1..4}.md` | read-only subagents (Read/Grep/Glob/Bash, model sonnet): run their sailor, read the ledger, write the captain's report. Change `model:` to `haiku` to make them cheaper |
| Tests | `sector4/guardian/test_sailor.py` | 10 tests: commission/watch/drift/never-list/prose-not-a-finding/box vs container/write guard/muster/daemon SIGTERM/gangway block + sailor allowlist |

## A watch, step by step
1. **Drift.** Hash (SHA3-512) every file on the deck. In a git tree with no baseline: `git status --porcelain` on the deck's paths. On a box (no `.git`): compare against the baseline written by `sailor.py <sector> commission`, which `install-team.sh` runs after every deploy. Modified / new / missing each become a finding.
2. **Never-list.** CLAUDE.md's AI SAFETY RULES as command shapes: setting a drive readonly (the blockdev, hdparm and remount forms against a breach_coms mount), storage-driver blacklist lines, redirects or tee into the modprobe.d or udev rules.d directories, a filesystem format or recursive delete aimed at a breach_coms drive or the master vault mount, and secrets on disk (Stripe keys, webhook secrets, AWS keys, private keys). Prose about the rules is not a finding; the command shape is. `file:line` on every hit. `sailor.py rules` prints the exact patterns.
3. **Services + heartbeats.** Only where systemd is PID 1 (`PHOENIX_SAILOR_BOX=1` forces it, `0` disables it): `systemctl is-active` for the deck's units, age of its heartbeat files. In a container or CI this is a recorded skip, not a pass.
4. **Checks** (`--checks`, muster only, not the daemon: the unit's read-only tree would fail tests that write): each deck's `scripts/verify.sh --only <check>`.
5. **Report.** `verification/<date>/crew-<sector>.log`, a `crew-<sector>` row in `summary.json` (result = number of findings), and `<home>/<sector>.heartbeat.json`. `sailor.py <sector> status` prints the last one.

`_write()` is the only write path in the engine and refuses any target outside the crew home or the ledger; the unit enforces the same at the kernel. Exit code = findings (capped at 125), so a sailor is usable as a gate.

## Commands
```
python3 sector4/guardian/sailor.py sector2 watch            # one watch
python3 sector4/guardian/sailor.py sector2 watch --checks   # + the deck's verify.sh checks
python3 sector4/guardian/sailor.py muster                   # all decks (verify.sh runs this as crew-muster)
tools/crew/muster.sh --checks
sudo systemctl status phoenix-sailor@sector1                # on the Compaq after install-team.sh
sudo -E PHOENIX_CREW_HOME=/var/lib/phoenix/crew python3 /opt/phoenix/sector4/guardian/sailor.py sector1 commission   # re-baseline after an APPROVED change only
```
In a Claude Code session: "ask sailor-sector3 to verify its deck" runs the subagent.

## The gangway, honestly
- It reads the hook JSON, matches the Bash command against the never-list, and blocks with the rule quoted. Deterministic, no model, no network. It blocked its own author twice in the first ten minutes after install (a test file and this very document quoted the shapes): files that must quote them go in through the Write/Edit tools, which the hook does not police, and are listed in `crew.json` `rule_exempt` so the sailors do not flag them either.
- When the hook input carries `agent_type` = `sailor-*`, the command must also match the sailor allowlist (sailor.py, verify.sh, read-only git, cat/grep/find/ls…). If a Claude Code build does not pass that field, the never-list still applies to everyone and the sailor's read-only-ness rests on its tool list (no Edit/Write) plus its prompt. That is the floor, stated plainly.
- The hook runs in **every** session on this checkout, including Jerry's own. That is the point (CLAUDE.md, "never automatic, no exceptions"). To run one of those commands legitimately, run it outside Claude Code, by hand, as the captain.

## What the captain still does
- Branch protection on GitHub (required check `verify`, one review, no force-push), signed commits, CODEOWNERS on `sector1/kernels`, `sector3/services`, `sector4/`. Settings clicks only Jerry can make; `docs/history/NEXT-SESSION-BACKLOG.md` carries the item.
- Decide on every finding. A sailor reports; it does not decide.
