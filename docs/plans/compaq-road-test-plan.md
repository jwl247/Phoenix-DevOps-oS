# Compaq road test — Phoenix from the cloud, a worker on the ground

**Status:** PLAN — written 2026-09-29, not approved, nothing built. Build starts only on Jerry's "build".
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
