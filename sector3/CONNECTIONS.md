# sector3 — Comms/networking, systemd services, Phoenix Mesh, the worker road test

Rewritten 2026-09-29 (Round 2 fix pass: S34OPS-F23/F27/F34/F35/F36, CONN-F01/F02/F19).
Updated 2026-09-30: `worker-up/` and `hlk/` (road test, commits a19b07a → 5fa4cd6) mapped from the code.
Verify against current code before trusting a specific line number.

## What it is
- `quadengine/quadengine.py` — the quadralingual comms engine.
- `romeo_juliet/` — `romeo.py` (ingress), `juliet.py`/`dbl_juliet.py` (egress); loopback-bound by default, need pyzmq.
- `phone-node/phoenix_phone.py` — Life First's phone side (Termux, stdlib only), 2026-10-03: `say`/`voice`/`where` send addressed check-ins to the brain's Helix-I over the Phoenix Mesh with the `HELIX_SOCKET_TOKEN` handshake; `listen` holds a Helix-E stream and turns each reply for `PHOENIX_WHO` into a termux notification (optionally spoken). Brain unreachable → check-ins wait in `~/.phoenix/phone/outbox.jsonl` and drain when it's back. Config `~/.phoenix/phone.env` (0600). Sandbox-tested against the real kernel with fake termux-api commands.
- `phone-node/phone-setup.sh` — one-time Termux setup: packages, worker keys typed hidden into a 0600 curl header file (`curl -H @file`, never argv — A2-N1), `phoenix_phone.py` pulled from the clonepool and SHA3-512-checked against D1 (refuses mismatch / no baseline / no bytes), `phone.env` (brain address must be Tailscale 100.64.0.0/10 or *.ts.net), `lifefirst` shortcut, start-at-boot via Termux:Boot. `--with-kernel`: proot Debian + python3 + PowerShell 7 arm64; stops before cloning the kernel tree (needs sector1/sector4 intaked as verified directory snapshots first). Linted (bash -n, shellcheck clean); not yet run on a phone.
- `translator/translator.sh` — 9 package backends; fires on OUTPUT only, never on intake (Critical Rule #2 in root CLAUDE.md — do not call this from an intake path).
- `services/` — 20 systemd unit files (17 `.service` incl. the `helix@.service` template, 3 `.target`), `install-units.sh` (explicit allow-list), and the dashboard deploy scripts (`deploy-dashboard.sh`, `push-dashboard.ps1`/`.sh`, `install-dashboard-windows.ps1`, `scout-ubuntu.sh`).
- `services/helix@.service` — one named kernel Helix per instance (`helix@ingress`, `helix@egress`): runs `helix_boot.sh start|stop <instance>`, settings in `/etc/default/helix-<instance>`; conflicts with the single `helix.service`, so a box uses one layout or the other.
- `services/phoenix-paging.service` — the paging manager (`sector4/paging.py`); ordered after either Helix layout but no longer pulls `helix.service` up (that used to stop the ingress/egress pair, 2026-09-29).
- `phoenix-net/` — Phoenix Mesh: switchboard worker, per-machine agent, admin tool (own CONNECTIONS.md).
- `mesh/` — **the healers** (Nebula mesh 10.42.0.0/16; `hosts.json` lists each box and its `buddies`). Added to the map 2026-10-09 (it had no entry).
- `mesh/phoenix_net.py` — mesh admin + `heal-local`: task **Phoenix Mesh Heal** (SYSTEM, 5 min) heals THIS box's mesh (known-good config restore, nebula restart, lighthouse ping). Log `F:\Phoenix\mesh\heal.log`.
- `mesh/phoenix_buddy.py` — task **Phoenix Buddy Heal** (`run --me pbmii`, as jwlef, 5 min): heals its SISTERS over the mesh through their `peer_agent.sh` (status → restore the signed mesh known-good from its version store → `heal` → check; Wake-on-LAN when unreachable). **2026-10-09: also heals THIS box's kernel** — down → `genie up`; DEGRADED with Helix ports free → `genie restart`; a port held by another program → never killed, logged as name#pid, healed the pass after it is gone; `lol stop` leaves `~/.phoenix/genie/stopped-on-purpose` and it stays down until `lol start`. Walked live: deliberate stop, crash, port squatter. Log `F:\Phoenix\mesh\buddy.log` (changes only; same problem retried hourly).
- `mesh/peer_agent.sh` — the door a sister heals a Linux box through (`/usr/local/sbin/phoenix-peer-agent`, forced command for `phoenix-peer`): `status`, `heal`, `export mesh`, `restore mesh <hash>` (installs only if hash AND config signature check out).
- `worker-up/` — the road test, "Phoenix from the cloud, a worker on the ground" (plan: `docs/plans/compaq-road-test-plan.md`): scripts that put Phoenix into R2 + D1 on another Cloudflare account and turn a blank Linux box (first one: pbm-compaq) into a worker that pulls it down. Run by hand today, one step per script; a single `usys worker up/down` entry point is planned, not built.
- `worker-up/dataplane-up.sh` — stands up (or with `check`, only verifies) a Phoenix data plane on a Cloudflare account: an R2 bucket, a D1 database loaded with the custody schema, and packages-worker deployed under its own name with its own PHOENIX_AUTH, then proves `/health` 200 and `/stats` 401 without the key. Re-runnable; redeploys only when the worker code changed.
- `worker-up/seed-dataplane.sh` — fills a data plane with the operations set through the import method (intake.sh), from the committed bytes (git archive, so no Windows CRLF leaks to Linux), in a sandbox (own home, catalog, logs, pool) so our own Phoenix is untouched. Refuses if the listed files have uncommitted changes.
- `worker-up/operations-set.txt` — the list of what a worker needs from Phoenix: Helix kernel + userspace, the CoPES security guardians, Frank, the paging manager, the systemd units, intake.sh itself, and H.L.K. The engine team travels together (AI Safety Rule 6).
- `worker-up/worker-bootstrap.sh` — the only file a blank box needs: pulls intake.sh from R2, checks it against its SHA3-512 in D1, then uses it to clone each named item; writes nanosecond timings to `bootstrap.jsonl` (measurement M1). Box key lives in `~/.phoenix-worker/` on the box.
- `worker-up/helix-pair-up.sh` — run as root on the box: turns its single Helix into an ingress/egress pair (ingress over the existing `helix-origin` partition with warm-on-write on, egress over a second disk it partitions only if blank), picks disks by serial, never touches the OS disk or udev/modprobe settings. Live on pbm-compaq since 2026-09-29.
- `worker-up/hlk-up.sh` — run as root: installs and starts H.L.K as `phoenix-hlk.service` on the box, listening on 127.0.0.1 and the box's mesh address (port 8472), with one allowed remote caller.
- `worker-up/model-up.sh` — run as root: gives H.L.K a local model from archives the box already imported from Phoenix (no internet model library, no paid API) — unpacks the Ollama CPU runtime + model, runs it as a box-level `phoenix-ollama.service` on 127.0.0.1:11434 with the model pinned in memory, and switches H.L.K to it. On pbm-compaq: llama3.2:3b.
- `worker-up/net-tune.sh` — run as root: sets BBR congestion control + fq, persisted in `/etc/sysctl.d/90-phoenix-bbr.conf`; `revert` undoes it. Fixed pbm-compaq's lossy uplink (a 16 MiB push went 289 s → 20.7 s).
- `worker-up/roadtest-measure.sh` — measurements M2–M6 on the worker: pull from R2 into ingress (cold and warm re-read), push through egress Helix-managed vs not, small-object latency, a tamper check (altered R2 bytes must be refused), and both Helix instances' counters; results in `<workdir>/measure/results.json`.
- `hlk/hlk.py` — H.L.K on a worker box (0.2.2), the third of the triplet with ingress and egress Helix: a small HTTP server with declared tools — status, warm, pull, prefetch, jobs, verify, stage run without asking; push (R2 + D1 receipt) waits for an explicit yes on `/confirm`. Keeps one shared index of what the box holds, reads both Helix counters, logs every call to `audit.jsonl`. Every tool works with no model; a model (local Ollama, or the Anthropic API if configured) drives the same tools through `/chat`. Token-gated.
- `hlk/test_hlk.py` — H.L.K's own tests with intake/dmsetup stood in (tiers, pull safety, names, index, status parsing, token gate); 26/26 passing on 2026-09-30.
- `hlk/eval_models.py` — read-only check of which local Ollama model can drive H.L.K's tools on a box: speed and whether it picks the right tool for six sample requests.
- `workers/packages-worker/` — a stale duplicate of the live worker, see Known issues.

## Dependencies
- `sector3/phoenix-net/mesh-worker/wrangler.jsonc` — own D1 `phoenix_mesh`, own secret `MESH_ADMIN`.
- `sector3/workers/packages-worker/wrangler.jsonc` — stale: D1 `DEV_DB`→`phoenix_dev_db`,
  `CATALOG_DB`→`phoenix-catalog` (deleted 2026-09-25), R2 `CLONEPOOL_BUCKET`. Not what is deployed.
- romeo/juliet/quadengine need `pyzmq` (not installed on the Windows box; no requirements file here). Live-tested 2026-10-03 (sandbox, pyzmq): 5 messages into Romeo → 2 correctly rejected (missing `id`; `pre_translated` — "translation is output only"), 3 out of Juliet, `romeo_ingress` 5 rows / `juliet_egress` 3 rows. Repo copies differ from their v1 clonepool baselines — re-intake (v2) pending.
- `worker-up/dataplane-up.sh`: env `CF_API_TOKEN` + `CF_ACCOUNT_ID` for the TARGET account, `npx wrangler`, `curl`, `python`.
  State outside the repo in `~/.phoenix/worker-up/<name>/` (generated wrangler config, the data plane's own auth, deployed hash, URL).
- On the worker box: `bash`, `curl`, `openssl` (SHA3-512), root for the Helix/H.L.K/model/net steps, the mesh agent
  (`/etc/phoenix-mesh/wg-phx.conf`) for H.L.K's mesh address, and `sudo -n dmsetup status` for the H.L.K user.
- `hlk/hlk.py`: Python 3 standard library only, Linux. Model tier from `/etc/default/phoenix-hlk` (`HLK_MODEL=ollama|api`).

## Commands / entry points
- `sudo sector3/services/install-units.sh <unit> …` — installs only allow-listed units
  (`helix.service`, `phoenix-paging.service`, `phoenix-helix-kernel.service`); no args prints usage.
  `helix@.service` is not on that list — `helix-pair-up.sh` installs it.
- `sector3/services/push-dashboard.ps1 -UbuntuHost … -UbuntuUser …` (Windows, PS7) — scouts the
  box (`scout-ubuntu.sh`), `scp`s `sector3/services/` + `dashboard/`, runs `deploy-dashboard.sh`
  there, installs Claude Code. `push-dashboard.sh <host> [user]` is the bash twin.
- `sector3/services/install-dashboard-windows.ps1` — Windows dashboard autostart (called from repo-root `install.ps1`).
- `sector3/translator/translator.sh <verb> [pkg]` — promoted to `/etc/systemd/system/translator.sh` by `deploy/deploy.sh`.
- Road test, in order (on our PC, then on the box):
  1. `sector3/worker-up/dataplane-up.sh <name> [check]` (e.g. `phoenix-roadtest` on the jerry.leftwich1 account).
  2. `sector3/worker-up/seed-dataplane.sh <name> [list-file]`.
  3. On the box: `worker-bootstrap.sh <workdir> <name> …` (e.g. `kernels helix frank hlk …`).
  4. `sudo helix-pair-up.sh <ingress-serial> <egress-serial> [check]`.
  5. `sudo net-tune.sh [revert]`.
  6. `sudo hlk-up.sh <user> <workdir> <egress-dir> <allow-from-mesh-ip>`.
  7. `sudo model-up.sh <user> <workdir> <runtime-archive> <model-archive> <model-name>`.
  8. `roadtest-measure.sh <workdir>`.
- `python3 sector3/hlk/hlk.py [--port 8472] [--mesh|--bind IP] --allow-from IP` — H.L.K by hand; `python3 sector3/hlk/test_hlk.py`; `python3 sector3/hlk/eval_models.py [--url …] model …`.

## Connects to / connected from
- `sector3/services/push-dashboard.ps1` → `sector3/services/scout-ubuntu.sh` → `sector3/services/deploy-dashboard.sh` (remote) → `dashboard/`.
- `sector3/services/push-dashboard.sh` → `sector3/services/deploy-dashboard.sh` (remote).
- `deploy/deploy.sh` → `sector3/translator/translator.sh` (local copy into systemd dirs).
- `sector3/phone-node/phoenix_phone.py` → `sector1/helix-lightning/helixi.py` (check-ins into Helix-I ch1 over the mesh) and → `sector1/helix-lightning/helixe.py` (replies from ch5).
- `sector3/phone-node/phone-setup.sh` → `sector2/package-handler/worker/index.js` (`/whoami`, `/clonepool/:hex?meta=true` baseline, `/clonepool/:hex` bytes).
- `sector3/romeo_juliet/juliet.py` → `sector3/translator/translator.sh` (output translation; promoted copy first, repo copy as fallback).
- `install.ps1` → `sector3/services/install-dashboard-windows.ps1`.
- `sector3/services/phoenix-paging.service` → `sector4/paging.py`; `sector3/services/helix.service` → `sector1/kernels/helix_boot.sh`.
- `sector3/services/helix@.service` → `sector1/kernels/helix_boot.sh` (start/stop one named instance).
- `portal/server.py` → `sector3/phoenix-net/mesh-worker/index.js`.
- `dashboard/main.js` → `sector4/` (its sector slot map sends slots 1–3 to sector1–3 and slot 4 to sector4).
- `sector3/worker-up/dataplane-up.sh` → `sector2/package-handler/worker/index.js` (deploys it under the data plane's own name) and → `sector2/package-handler/worker/schema-d1.sql` (loads it into the new D1). Talks only to the Cloudflare API of the target account.
- `sector3/worker-up/seed-dataplane.sh` → `sector3/worker-up/operations-set.txt` (what to send) → `sector2/package-handler/intake.sh` (sends it, sandboxed).
- `sector3/worker-up/worker-bootstrap.sh` → `sector2/package-handler/intake.sh` (the copy it pulls from R2 and checks against D1, then runs to clone everything else).
- `sector3/worker-up/helix-pair-up.sh` → `sector3/services/helix@.service` (installs it, enables ingress + egress) → `sector1/kernels/helix_boot.sh` (needs the multi-instance version on the box).
- `sector3/worker-up/helix-pair-up.sh` → `sector3/services/phoenix-paging.service` (stops it during the hand-over, starts it again).
- `sector3/worker-up/hlk-up.sh` → `sector3/hlk/hlk.py` (runs the imported copy as a service; reads the mesh address the mesh agent wrote).
- `sector3/worker-up/model-up.sh` → `sector3/hlk/hlk.py` (switches its model tier to the local Ollama).
- `sector3/worker-up/roadtest-measure.sh` → `sector2/package-handler/intake.sh` (pushes and clones through it for every measurement).
- `sector3/hlk/hlk.py` → `sector2/package-handler/intake.sh` (pull = intake clone, push = intake, keys in the environment only).
- `sector3/hlk/hlk.py` → `sector1/kernels/helix_boot.sh` (reads the Helix instances it brings up, through dmsetup status).
- `sector3/hlk/eval_models.py` → `sector3/hlk/hlk.py` (uses its real decision path); `sector3/hlk/test_hlk.py` → `sector3/hlk/hlk.py`.

## Known issues (verified, not guessed)
- `romeo_juliet/romeo.py` and `juliet.py` crash at start on a machine with no `~/.catalog/` (`sqlite3.OperationalError: unable to open database file`) — neither creates the folder before `catalog_init()`. PBMII has it; a fresh box (phone node, compaq) does not. Fix: `os.makedirs(os.path.dirname(CATALOG_DB), exist_ok=True)` before the connect (found 2026-10-03; **fixed 2026-10-07**, tested with an empty home).
- Helix-E (`sector1/helix-lightning/helixe.py`) and Juliet both describe themselves as THE output-translation boundary — two egress paths claim the same rule. Which owns it is Jerry's call (2026-10-03).
- **`sector3/workers/packages-worker/` is a stale duplicate.** The live worker is
  `sector2/package-handler/worker/index.js`. It shares the name `packages-worker` and has no
  auth on its `/custody`, `/clonepool`, `/packages` GETs; its `wrangler.jsonc` `main` points at
  a nonexistent file so a deploy fails loudly. Deleting the folder is Jerry's call (S34OPS-F44).
- 9 units (`phoenix-auto-config`, `-frankenhelix`, `-frank-helix`, `-intent-parser`,
  `-propagator`, `-mega-security`, `-unoserver`, `-doc-worker`, `-scheduler`) point at
  `/home/jwl247/projects/phoenix` paths that are missing or moved (S34OPS-F04);
  `install-units.sh` refuses them. `frank3-slot-a/b.service` (kernel modules) need Jerry (F05).
- `phoenix-unoserver.service` is waiting on Office Module 4 on purpose.
- `deploy-dashboard.sh` still installs Node with an unpinned `curl … nodesource | sudo bash`
  (S34OPS-F35, noted in place).
- Keys on `curl`'s command line (A2-N1, open): `dataplane-up.sh` passes the Cloudflare API token,
  and `worker-bootstrap.sh` / `roadtest-measure.sh` pass the box's PHOENIX_AUTH, as `-H` arguments,
  visible in the process list while curl runs. `seed-dataplane.sh` and `hlk.py` already pass keys
  through the environment.
- `roadtest-measure.sh`'s tamper check (M5) overwrites one object in the data plane's R2 and puts
  it back afterwards — point it only at a road-test data plane, never at our own.
- Two different `phoenix-ollama.service` files share one name: the repo template in `services/`
  (a user unit for the dashboard Help Desk, written by `deploy-dashboard.sh`) and the box-level
  unit `model-up.sh` generates for H.L.K. Different scopes, so they don't overwrite each other,
  but don't confuse them.
- `phoenix-hands` used to restart-loop (~11×, Errno 99) after boot until meshd (RETIRED) brought
  the mesh address up. Since 2026-10-07 (S34OPS-F45) it reads its 10.42.x address from Nebula's
  `nebula1` and waits (logging every 5 min) until it exists before binding; unit is `After=nebula.service`
  (A2-N6). `phoenix-hlk.service` binds the mesh address the same
  way (`--bind`) and relies on the same restart-until-it-works.
- The planned `usys worker up/down` entry point and its runbook (`docs/runbooks/worker-up.md`) do
  not exist yet; the steps above are run by hand.
