# Compaq road test — Phoenix from the cloud, a worker on the ground

**Status:** BUILT AND RUNNING on pbm-compaq, 2026-09-29. Phases 0–4 are done and measured (§3b, §3c): the data plane, the seed, two Helix instances, the H.L.K clone (imported from R2, `phoenix-hlk.service`), and the cold start. Next: warm on write for ingress, the upload diagnosis, and a model tier for H.L.K (Jerry's call). Phase 5 (the process) follows.
**Question it answers (Jerry, 2026-09-29):** can a machine come up from nothing and run as a Phoenix worker, pulling what it needs from Phoenix in R2 and pushing results back, with H.L.K directing it? This is the delivery shape Monster Phoenix needs. Measure it and decide.
**Hard rule:** our system stays unaffected. That means the jw.leftwich1 Cloudflare account (its R2, D1, workers and tunnel), the Precision, pbm3 and the HP. The only exception is the Round 2 audit fixes.

## 1. Shape

```
  CONTROL PLANE (ours, unchanged)            DATA PLANE (jerry.leftwich1 account)
  ───────────────────────────────            ─────────────────────────────────────
  Precision ── Phoenix Mesh ──┐              roadtest-worker  (packages-worker code,
  (watch + steer only)        │                 same API: /clonepool, /custody, versions)
                              │                 ├─ R2  phoenix-roadtest   (blobs + versions/)
                              ▼                 └─ D1  phoenix-roadtest   (custody, glossary)
                    ┌──────── pbm-compaq ────────┐          ▲            │
                    │  H.L.K clone (phoenix-hlk) │   push   │            │ pull
                    │    reads + directs         │──────────┘            ▼
                    │  helix-egress (Toshiba) ◄──┤          helix-ingress (Seagate)
                    └────────────────────────────┘
  cool-term-cdc4 (jerry account, reused) = telemetry/snapshot sink the H.L.K clone reports to
```

- **Ingress Helix** (Seagate 1 TB, serial WQ992JYZ; today's `helix` device) holds everything pulled from R2. Repeat reads come from RAM or the SSD, not the network or the disk.
- **Egress Helix** (Toshiba 698 GB, serial Z3NHC2OHT, wiped 09-29) stages everything headed back to R2: results, new versions and custody receipts. Each is written through to disk before it is pushed.
- **The H.L.K clone** runs on the Compaq. It decides what to pull, what to push, and when. It follows the same tiers as the HUD: reads and status run on their own; a push that changes R2 or D1 asks first.
- **The Compaq stays in our mesh** (Jerry, 09-29) so we can watch and control it. The mesh carries control only. No data-plane credentials for our account go on the box.

## 2. Phases

### Phase 0 — data plane on the jerry account (no effect on ours)
1. Create R2 bucket `phoenix-roadtest` and D1 database `phoenix-roadtest`, then load `sector2/package-handler/worker/schema.sql` into it.
2. Deploy the packages-worker **3.5.0** code (commit `ee737be`) as `roadtest-worker` on the jerry account. Use a new wrangler config file that points at the jerry account's bucket and D1, and set its own `PHOENIX_AUTH` secret. It must not share any secret with our worker.
3. Put Cloudflare Access (service token) in front of it on the jerry account. It never runs open.
4. **Box credential:** a second, narrow token or service token for the Compaq only. It covers this worker and this bucket, nothing else. `CF_JERRY_API_TOKEN` (admin-ish) stays in the vault on the Precision and never goes to the box.
5. **Account cleanup, done 2026-09-29 (Jerry: "nothing in that account should be active unless we made it active today"):**
   - `cool-term-cdc4` taken off workers.dev and preview URLs (its public URL returns 404; the code is kept).
   - Tunnels `authenticcoder` and `authenticcoder.com` deleted.
   - `lifefirst` renamed `phoenix-roadtest-ingress` (id `a7ff3d38…`) and `lifefirst-server` renamed `phoenix-roadtest-egress` (id `1cb7ae41…`). Both got fresh tunnel secrets, so every old connector token is dead. Both are now remote-managed, with config `http_status:404` only (they answer nothing).
   - None of our account's DNS records pointed at any of these four tunnels (checked first).
6. Rework `cool-term-cdc4`:
   - bind it to a new D1 (its `7e72f6ba…` database is gone);
   - fix the `env.DB` / `db` binding mismatch;
   - add auth, since today it has none (CORS `*`, open POST).

   After that it receives telemetry, snapshots and kernel-slot reports from the H.L.K clone.

**Proof:** `GET /health` on roadtest-worker, and an empty D1 with the full schema. Our worker's `/health` counts are unchanged before and after.

### Phase 1 — seed Phoenix into it
7. From the Precision, run `intake.sh` against the **roadtest** worker with `WORKER_URL`, `PHOENIX_AUTH` and `CF_ACCESS_*` for the roadtest worker. Use a **scratch `CLONEPOOL_DIR`**, not E:, so our local pool is untouched.
8. What goes in, the "operations set" (CLAUDE.md AI SAFETY RULE 6: the engine team is the apps):
   - Helix: `sector1/helix/`, `sector1/kernels/` (dm-helix, Frank3 slots, `helix_boot.sh`), CoPES guardians;
   - Frank: `sector2/frank/`;
   - paging / Doppelganger: `sector4/paging.py`;
   - the Sector 3 services the audit found missing on the box;
   - `sector2/package-handler/intake.sh`;
   - the H.L.K clone (Phase 3).

   Each item is tagged with the repo commit it came from.

**Proof:** a D1 custody row for every file, a SHA3-512 match on a spot check, and our D1 and R2 untouched.

### Phase 2 — two Helix instances on the Compaq
9. `helix_boot.sh` is single-instance today (`NAME=helix` is hardcoded). Make it per-instance, with `/etc/default/helix-ingress` and `/etc/default/helix-egress` and one systemd unit per instance. dm-helix already keeps per-device state (`hx_ctr` allocates its own Dandelion and strands), so the kernel needs no change.
10. **Set RAM explicitly: about 3.5 GB of Strand A each.** `auto` means half the machine's RAM *per instance*, so two instances on auto would claim all 15 GB.
11. **Ingress:** the existing Seagate origin and Strand B image, renamed `helix-ingress`. It stays mounted, but at a new path (a new `/srv/...` mount replacing `/srv/bench`).
12. **Egress:** a GPT partition on the Toshiba with partlabel `helix-egress`, found by serial. Its own Strand B image goes on the SSD. The filesystem is made by hand, once, as the boot script expects.

**Proof:** both devices report `double dandelion` in `dmsetup status`, both survive a reboot, and the existing paging, hands and mesh services still run.

### Decision 2026-09-29 — ingress gets the shared memory, egress stays simple
Jerry: "the ingress … need[s] a shared memory so data [it has] read she has read too", and "ingress, not egress".
- **Ingress: read-through equals known.** Everything ingress pulls lands straight in her RAM strand (Strand A), so it is warm on first use, not second. That needs dm-helix to **warm on write** for the ingress instance, a small kernel change. H.L.K also records each pulled item in one shared index keyed by content hash (the SHA3 Phoenix already carries), so H.L.K knows what she holds. Why: M2 showed a freshly pulled 64 MiB file re-read at disk speed (117 MiB/s), because she had not "read" it yet.
- **Egress: kept simple.** Unmanaged (plain disk), or Helix with no shared memory, whichever measures better. Why: M4 showed Helix barely changes write speed (16 MiB push 289 s managed vs 272 s unmanaged), and the upload line is the limit.
- **Peering:** the shared memory sits in the middle, in H.L.K. Ingress and egress never talk to each other directly (the 09-28 shape). Before that can work, the kernel must publish each instance's Dandelion separately: today the two instances overwrite one shared slot (`dm_helix.c:81-83`, `:1050`, `:1296`).
- **Not decided, just captured:** the paging manager follows machine load instead of Helix heat, and still presents to Helix in her terms. "Unbind her strands" is an open question.

### Phase 3 — the H.L.K clone
13. Port H.L.K's loop (`hud/AiChatService.cs`: model tiers, ACTION parsing, stricter yes-gate, history cap) to a Linux Python service, `phoenix-hlk`, beside hands.
14. Its tools are declared, not a raw shell:
    - `pull(name|hex)`: runs `intake clone`, R2 → ingress. Automatic.
    - `helix_status()`: both instances. Automatic.
    - `verify(hex)`: SHA3 against D1. Automatic.
    - `stage(path)` → egress. Automatic.
    - `push(path)`: egress → R2 + D1. **Asks first.**
    - `report()`: telemetry to `cool-term-cdc4`. Automatic.
15. Model tiers stay the same three (subscription, API, Ollama). Ollama is pbm3's or the Compaq's own CPU, as the always-works fallback (CLAUDE.md rule 14).
16. **The H.L.K clone reaches the Compaq by the import method.** It is itself pulled from roadtest R2 by `intake clone`. That is the test.

### Phase 4 — the cold-start run (the actual test)
17. Start from a blank `/opt/phoenix-roadtest` on the Compaq, holding only the box credential.
18. Run `intake clone` for the H.L.K clone. H.L.K comes up and pulls the rest of the operations set through ingress. It runs a job, then pushes results through egress.

### Phase 5 — if it passes, it becomes a process (Jerry, 2026-09-29)
"The connection from R2 (jerry.leftwich1) to the Compaq will have to become a process if good, including building the tunnels etc." The Compaq run is the first instance of a repeatable procedure, not a one-off. So:
19. **Every step in Phases 0–4 is built as a script from the start, never as hand-typed commands:** create or bind the bucket and D1, deploy the worker, create the tunnels and their configs, issue the box credential, set up the two Helix instances, bootstrap the H.L.K clone. Each script can run again safely (it checks before it creates) and logs to custody.
20. **Tunnels are created by the process, not by hand.** Per machine: an ingress and an egress tunnel, each with its own secret and remote config, and the connector token handed only to that machine. Retiring a machine means rotating or deleting its tunnels, the same steps as the 2026-09-29 cleanup.
21. **One entry point:** a `usys` verb (working name `usys worker up <machine>` / `usys worker down <machine>`) that runs the whole chain for a new machine and reports M1–M7 at the end. The game client path is this same process.
22. **A runbook** (`docs/runbooks/worker-up.md`) written from the real run, with every command's expected output, so the process can be checked or run by hand if the automation breaks.

## 3. What gets measured (docs/helix/BENCHMARKS.md precision rule)

| # | Measure | Why it matters for the game |
|---|---|---|
| M1 | Cold start: blank dir → H.L.K answering (seconds) | how fast a new client or worker comes up |
| M2 | Pull throughput, first pull vs repeat (MB/s) | the first asset load vs a warm one through ingress Helix |
| M3 | Small-object fetch latency p50/p95 (ms), 1 KB–1 MB | game-asset-sized requests |
| M4 | Push throughput and time to D1 receipt | how fast results or state get back to the authority |
| M5 | Verify failures (must be 0) and refusals on a tampered blob (must be refused) | integrity under a hostile network |
| M6 | Both Helix instances: hit rate, heat, evictions under the run | whether the ingress/egress split earns its keep |
| M7 | Our system untouched: our worker's `/health` counts, our R2 object count, E: pool file count, identical before and after | the hard rule |

Pass or fail lines for M1–M4 are Jerry's call. Proposed starting points: M1 < 5 min, M3 p95 < 250 ms warm, M5 = 0 failures and 100% of tampered blobs refused, M7 = identical.

## 3b. Results — run 2026-09-29 on pbm-compaq (`sector3/worker-up/roadtest-measure.sh`, nanosecond clocks)

| # | Measure | Result | Proposed line | |
|---|---|---|---|---|
| M1 | Cold start: blank dir → operations set (intake.sh + 6 items, 73 files) | **40.3 s**, 73/73 byte-identical to git (first run 143 s, before the parallel pulls) | < 5 min | pass |
| M2 | Pull 64 MiB R2 → ingress, hash-checked | **14.39 s = 4.45 MiB/s** (~37 Mbit/s) | — | — |
| M2 | Re-read after pull, page cache dropped | 0.548 s = **117 MiB/s** (disk speed: she hadn't read it yet → the ingress decision above) | — | gap |
| M2 | Re-read, warm | 0.0148 s = 4,330 MiB/s (Linux page cache, not a Helix number) | — | — |
| M3 | Small object p50 / p95, one kept-alive connection | 1 KiB 87 / **113 ms** · 16 KiB 100 / **235 ms** · 256 KiB 141 / 302 ms · 1 MiB 305 / 496 ms | p95 < 250 ms | pass ≤ 16 KiB, fail ≥ 256 KiB |
| M3 | Same, a new connection each request | 1 KiB 218 / 298 ms … 1 MiB 765 / 995 ms | — | why H.L.K holds one connection open |
| M4 | Push egress → R2 + D1 receipt (64 KiB + 1 MiB + 16 MiB) | managed **0.05 MiB/s** (314.6 s) · unmanaged **0.06 MiB/s** (292.3 s); staging on the egress disk 22.1 vs 17.6 MiB/s | — | the big problem: upload |
| M5 | Tampered object in R2 | **refused**; clones again after restore | 100 % refused | pass |
| M6 | Both Helix instances' counters | recorded around every phase in `results.json`; the shared Dandelion slot is mixed between the two instances (kernel bug) | — | fix |
| M7 | Our system untouched | our D1 custody 2077 / clonepool 531 / glossary 276 / versions 410, our R2 464 objects, E: pool 228 files — identical before and after Phases 0–1 | identical | pass (re-check at the end) |

Also found and fixed along the way (system fixes):
- a directory could not be cloned from R2 at all;
- a re-intaked directory lost its unchanged files;
- directory intake dropped Makefiles, `.target` units and extensionless scripts;
- seeding shipped Windows CRLF bytes;
- a folder's files were pulled one at a time (now in parallel);
- the paging unit pulled the single Helix back up;
- a race loading the modules at boot;
- the road-test key was printed during a check and has been rotated.

## 3c. Phase 3 live run — H.L.K on pbm-compaq, 2026-09-29

The box imported H.L.K from Phoenix in R2 (4.5 s, checked against D1) and runs it as `phoenix-hlk.service` on `10.47.0.3:8472`. The one allowed caller is the Precision (`10.47.0.2`), and every call needs the 0600 token; without it, HTTP 401 over the mesh.

| Step | Result |
|---|---|
| pull `kernels` | 16 files, 2.92 s |
| prefetch `helix`, `frank`, `security` (background, in parallel) | 13 / 4 / 12 files, 6.39 / 1.58 / 1.96 s |
| read everything just pulled, page cache dropped | **hit_rate_now 23.2 %**: pulled data is NOT yet warm, which confirms the ingress decision (warm on write) |
| stage → push asks → confirm yes | pushed; D1 receipt `1bc321caf9dc8d12` = local; 2.67 s |
| update H.L.K itself | the box re-imported 0.1.1 by itself once clone checked Phoenix for newer versions |
| audit | asked / declined / ran-with-confirmation all logged |
| M7, our system | unchanged at the end: D1 2077 / 531 / 276 / 410, R2 464, E: pool 228 |

Found and fixed during Phase 3 (system fixes):
- Cloudflare 403s Python's default user agent (error 1010), which broke the push receipt check.
- `intake clone` never refreshed a stale local copy: a directory was cloned from its old snapshot, and a stale file read as an "INTEGRITY FAILURE". Phoenix is now the authority on every clone.
- dm-helix's shared Dandelion slot was overwritten by every instance and zeroed by any removal.

## 3d. Upload diagnosis and fix — 2026-09-29

The slow push (M4, ~0.9 Mbit/s) was **not Phoenix**. Measured on the Compaq:

| Test | Result |
|---|---|
| raw upload straight to Cloudflare (no worker, no intake) | 0.88–1.08 Mbit/s: the same as the worker path |
| Precision, same router, raw upload | 6.6–8.5 Mbit/s: the house uplink is fine |
| Compaq over the LAN: sending / receiving | 6.7 / 44.5 Mbit/s: one-directional |
| NIC: e1000e 82579LM, gigabit card | linked at 100 Mbit, advertising only 10/100 (downshifted), zero local errors |
| TCP retransmits during an upload | **4.6 %** (healthy is under 0.1 %) |
| offload (TSO/GSO) on vs off | no difference, so not the known e1000e bug |
| congestion control CUBIC → **BBR** | **1.07 → 20–26 Mbit/s** up |
| 16 MiB push egress → R2 + D1 receipt | **289.3 s → 20.7 s** (14×) |

**Fixed in software:** `sector3/worker-up/net-tune.sh` sets BBR + fq on the worker, persisted in `/etc/sysctl.d/90-phoenix-bbr.conf`, applied on pbm-compaq; `net-tune.sh revert` undoes it. Every worker should get it: the game-client shape runs over lossy home, Starlink and mobile links.

**Still worth doing by hand (Jerry):** swap the Compaq's network cable, and use another router or switch port, ideally a gigabit one. A gigabit card downshifted to 10/100 with send-only loss points at a bad cable pair or a bad port.

**Next, noted:** each push uploads the bytes twice (the current key plus the per-version key). A server-side copy in the worker would halve push time.

## 4. Rollback (every phase)

- **Phase 0:** delete the roadtest bucket, D1 and worker on the jerry account. Ours was never touched.
- **Phase 2:** disable the per-instance units and restore the single-instance `/etc/default/helix` + `helix.service`. The data is safe: dm-helix is write-through, so the Seagate origin is always complete.
- **Phase 3/4:** stop `phoenix-hlk` and remove `/opt/phoenix-roadtest`.

## 5. Open questions for Jerry

1. **Measurement pass lines (§3).** Use the proposals, or set your own?
2. **Ingress/egress tunnels:** these are now `phoenix-roadtest-ingress` and `phoenix-roadtest-egress` on the jerry account, repurposed 2026-09-29 and answering nothing yet. Use them from the first run, or start with plain HTTPS to the worker and add the tunnels as a measured second run (M1–M4 with and without tunnels)?
3. **Push confirmations:** where does "ask first" land while the Precision is not being expanded? Options: a mesh-only page on the Compaq (like the Console), or the existing hands/Console confirmation path.
4. **Bench data:** `/srv/bench` holds 232 MB from the old verdict work. Keep it on ingress, or clear it?
5. **The Helix verdict** (lean Phoronix restart) is still owed on the single-instance setup. Run it before Phase 2 changes the box, so there is a before/after?
