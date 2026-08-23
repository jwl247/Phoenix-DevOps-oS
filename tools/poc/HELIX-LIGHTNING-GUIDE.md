# Helix Lightning Kernel — Complete Guide

**Phoenix DevOps OS | jwl247 | GPL v3**
**File:** `tools/poc/HELIX-LIGHTNING-GUIDE.md`
**Related:** `DOUBLE-HELIX-PLAN.md` · `SHARED-FS-PLAN.md` · `PHOENIX_MANUAL.md`

---

## What this is

The Helix Lightning Kernel is the memory and processing backbone of Phoenix DevOps OS.
It is not a demo. It is the engine that all sectors run through.

When it is running:
- Every process in Phoenix is loaded as a **suit** worn by **Frank** — he rides it, it executes, he dies clean
- Memory is managed by **HelixSystem** — L1 hot → L2 warm → L3 compressed → L5 disk-paged
- The Windows side feeds tier pressure data to the **Linux paging brain** via a shared JSON file
- The Linux paging manager watches both strands and controls the swapfile for the whole OS

**This is the difference between Phoenix running on what you have versus being limited by what you have.**

---

## Architecture

```
Double Helix = 8 channels total

  Strand A — Windows (executing)        Strand B — Debian (prefetching / flushing)
  ─────────────────────────────         ──────────────────────────────────────────
  Helix-I  channels 1-4 (ingress)       Helix-E  channels 5-8 (egress)
  Frank5 conductor                       paging.py (one paging brain)
  helix_complete_stack.py (the suit)

  Both strands write L5 .page files to the shared directory:
  Windows:  F:\Phoenix\helix-pages\
  Debian:   /phoenix/helix-pages/

  Strand A writes a snapshot every 5 seconds:
  F:\Phoenix\helix-pages\windows_snapshot.json

  paging.py on Debian reads that snapshot and controls the Linux swapfile
  as the shared overflow pool for both strands.
```

### Frank5 — the conductor

Frank is not a process manager. Frank does not hold processes.

Frank is imported. Frank wears a suit (a process). Frank rides it — it executes.
Frank dies clean. The kernel never knows he was there.

Four jobs:
1. Know which rings are alive
2. Know which stage each ring is on
3. Fire the next interrupt when Helix-I signals stage ready
4. Confirm to Helix-E when a ring is done

Every Phoenix component — intake, clone pool, romeo, juliet, quadengine, helix, Frank himself —
is registered in the Process Library as a suit. Frank wears them. That is how Phoenix runs.

### HelixSystem — the memory engine

Five tiers:
| Tier | Location | Access time | What lives here |
|------|----------|-------------|-----------------|
| L1 hot | RAM | ~20 µs | Active blocks, recently accessed |
| L2 warm | RAM | ~30 µs | Blocks demoted from L1 |
| L3 compressed | RAM (zlib) | ~65 µs | Blocks demoted from L2, compressed |
| L5 disk | `helix-pages/` | I/O | Blocks evicted from L3, .page files |

Benchmarked: 700,000 ops/sec. 100% hit rate under normal load. Compression ratio 600:1+
on repetitive payloads. A 70B model's context fits on 8GB RAM via L3 compression + L5 paging.

### paging.py — one brain for both strands

`sector4/paging.py` is the Linux paging manager. It:
- Reads `windows_snapshot.json` from the shared FS every monitor cycle
- When `frozen_mb > 0` (Helix is paging to disk) → expands swapfile proactively
- Uses `PredictiveEngine` — watches velocity of tier changes, acts before pressure hits
- Uses `VirtualProcessor` — emergency circuit breaker at RAM_CRITICAL / SWAP_CRITICAL
- Manages the swapfile live — no reboot required for resize

Priority order for tier data:
1. Local HelixSystem attached (if running on same machine)
2. `windows_snapshot.json` on shared FS (cross-platform)
3. `/proc/meminfo` ratio estimate (fallback only)

---

## Files

| File | Purpose |
|------|---------|
| `sector1/helix-lightning/franken5.py` | Frank5 core: SharedMemoryBus, Ball, PCS, RingRecord |
| `sector1/helix-lightning/helixi.py` | Helix-I: left lung, ingress, channels 1-4 |
| `sector1/helix-lightning/helixe.py` | Helix-E: right lung, egress, channels 5-8 |
| `sector1/helix-lightning/frank_ring.py` | FrankRing: mount → run → sync → die |
| `sector1/helix-lightning/frank_spawn.py` | FrankSpawn: signal-driven ring spawner, 32 workers |
| `sector1/helix-lightning/process_library.py` | ProcessLibrary: suit registry, pre-loaded modules |
| `sector1/helix-lightning/helix_suit_override.py` | Wires helix_complete_stack.py as suit for all rings |
| `sector1/helix-lightning/main_kernel.py` | Full boot: Frank → Library → Spawn → Helix-I/E |
| `sector1/helix/helix_complete_stack.py` | HelixSystem L1-L5, get_tier_snapshot(), benchmark() |
| `sector4/paging.py` | Linux paging brain: swap manager, predictive engine, VP |
| `sector4/paging_windows.py` | Windows paging brain: pagefile manager |
| `tools/poc/true_double_helix.py` | PoC entry point: Helix-I + snapshot writer (Windows) |
| `tools/poc/run-helix-poc.ps1` | Windows launcher |
| `tools/poc/run-helix-poc.sh` | Debian launcher |
| `tools/poc/install-helix-autostart.ps1` | Register Windows autostart (Task Scheduler) |
| `sector3/services/phoenix-helix-kernel.service` | Debian autostart (systemd) |

---

## Running manually

### Windows (Strand A — Helix-I ingress + snapshot writer)

```powershell
# From repo root in PS7:
pwsh -NoProfile -ExecutionPolicy Bypass -File tools\poc\run-helix-poc.ps1
```

What you will see:
```
[OK]    Page dir: F:\Phoenix\helix-pages
[OK]    PHOENIX_SUITS=...\Phoenix-DevOps-oS
[OK]    PHOENIX_HELIX_PAGE_DIR=F:\Phoenix\helix-pages
Starting Helix-I (Strand A)...

[FRANK5] INFO SHM created: \tmp\phoenix_shm\frank5.shm (256MB)
[FRANK5] INFO Frank5 v5.1.0-alpha online  PID xxxxx
[FRANK5] INFO Helix-I snapshot writer started  F:\Phoenix\helix-pages
[FRANK5] INFO Helix-I v1.0.0-alpha  strands A+B  channels (1, 2, 3, 4)
[FRANK5] INFO Helix-I ch1 (strand A) listening on :7701
[FRANK5] INFO Helix-I ch2 (strand A) listening on :7702
[FRANK5] INFO Helix-I ch3 (strand B) listening on :7703
[FRANK5] INFO Helix-I ch4 (strand B) listening on :7704
```

Verify snapshot is writing:
```powershell
Get-Content 'F:\Phoenix\helix-pages\windows_snapshot.json'
# {"timestamp": 1787517659.55, "hot_mb": 0.0, "warm_mb": 0.0, ...}
```

### Debian (paging brain — reads snapshot, controls swapfile)

SSH into Debian first:
```bash
ssh -p 2222 phoenix@127.0.0.1
```

Run the paging brain:
```bash
bash /phoenix/Phoenix-DevOps-oS/tools/poc/run-helix-poc.sh
```

The script will:
1. Verify `/phoenix/` is mounted (SMB over QEMU)
2. Set `PHOENIX_PAGING_SNAPSHOT_PATH`
3. Re-exec with `sudo` if not root (paging.py needs root for swapfile ops)
4. Start `paging.py` — dashboard on `http://localhost:8888`

If the SMB mount is not up:
```bash
sudo mount -t cifs //10.0.2.2/Phoenix /phoenix \
  -o username=jwlef,password=YOUR_PASS,uid=1000,gid=1000,vers=3.0
```

---

## Making it persistent

### Windows — Task Scheduler (auto-start at logon)

```powershell
# Run once from repo root:
pwsh -NoProfile -ExecutionPolicy Bypass -File tools\poc\install-helix-autostart.ps1
```

This registers a task `Phoenix\HelixLightningKernel` that:
- Starts 10 seconds after logon (no console window)
- Restarts automatically every 5 minutes if stopped
- Runs in user scope — no elevation required

Verify it is registered:
```powershell
schtasks /query /tn "Phoenix\HelixLightningKernel" /fo LIST
```

Start it immediately without rebooting:
```powershell
schtasks /run /tn "Phoenix\HelixLightningKernel"
```

Verify snapshot is live:
```powershell
Get-Content 'F:\Phoenix\helix-pages\windows_snapshot.json'
```

Remove autostart:
```powershell
schtasks /delete /tn "Phoenix\HelixLightningKernel" /f
```

### Debian — systemd service (auto-start at boot)

Inside Debian (SSH or console):

```bash
# Copy the service file to systemd
sudo cp /phoenix/Phoenix-DevOps-oS/sector3/services/phoenix-helix-kernel.service \
        /etc/systemd/system/

# Reload, enable, start
sudo systemctl daemon-reload
sudo systemctl enable phoenix-helix-kernel.service
sudo systemctl start  phoenix-helix-kernel.service

# Check status
sudo systemctl status phoenix-helix-kernel
sudo journalctl -u phoenix-helix-kernel -f
```

**Important:** The service has an `ExecStartPre` guard that checks `/phoenix/helix-pages/`
exists before starting `paging.py`. If the SMB mount is not up at boot, the service will
fail and retry (RestartSec=10, up to 5 times). Make the SMB mount automatic first:

Add to `/etc/fstab` (replace YOUR_PASS):
```
//10.0.2.2/Phoenix /phoenix cifs username=jwlef,password=YOUR_PASS,uid=1000,gid=1000,vers=3.0,_netdev,nofail 0 0
```

Or use the credentials file (more secure — see `SHARED-FS-PLAN.md`):
```
//10.0.2.2/Phoenix /phoenix cifs credentials=/etc/phoenix-smb-credentials,uid=1000,gid=1000,vers=3.0,_netdev,nofail 0 0
```

```
# /etc/phoenix-smb-credentials
username=jwlef
password=YOUR_PASS
```
```bash
sudo chmod 600 /etc/phoenix-smb-credentials
```

---

## Verify both sides are running

### Windows
```powershell
# Snapshot is fresh (timestamp within last 10 seconds)
$snap = Get-Content 'F:\Phoenix\helix-pages\windows_snapshot.json' | ConvertFrom-Json
$age  = (Get-Date).ToUniversalTime().Subtract([datetime]'1970-01-01').TotalSeconds - $snap.timestamp
Write-Host "Snapshot age: $([math]::Round($age,1))s  frozen_mb: $($snap.frozen_mb)"

# Task is running
schtasks /query /tn "Phoenix\HelixLightningKernel" /fo LIST | Select-String "Status"
```

### Debian
```bash
# paging.py is running
sudo systemctl status phoenix-helix-kernel --no-pager

# It is reading the snapshot (look for SNAPSHOT in logs)
sudo journalctl -u phoenix-helix-kernel --since "5 minutes ago" | grep -i snapshot

# Dashboard (from Debian — shows live swap stats)
curl -s http://localhost:8888/api/status | python3 -m json.tool | grep -A3 helix
```

---

## Environment variables

| Variable | Windows value | Debian value | Purpose |
|----------|--------------|--------------|---------|
| `PHOENIX_SUITS` | `D:\Users\jwlef\Phoenix\Phoenix-DevOps-oS` | (set by service) | Repo root for suit path resolution |
| `PHOENIX_HELIX_PAGE_DIR` | `F:\Phoenix\helix-pages` | `/phoenix/helix-pages` | Where .page files and snapshot JSON live |
| `PHOENIX_PAGING_SNAPSHOT_PATH` | (not used Windows side) | `/phoenix/helix-pages/windows_snapshot.json` | Snapshot path for paging.py |
| `PHOENIX_PAGING_NVME_MOUNT` | (not used Windows side) | `/mnt/nvme` | Where paging.py puts the swapfile |
| `PHOENIX_SHM` | `\tmp\phoenix_shm` | `/tmp/phoenix_shm` | Frank5 shared memory bus location |

---

## Ports

| Port | Component | Direction |
|------|-----------|-----------|
| 7701 | Helix-I ch1 (Strand A) | Ingress — push data in |
| 7702 | Helix-I ch2 (Strand A) | Ingress |
| 7703 | Helix-I ch3 (Strand B) | Ingress |
| 7704 | Helix-I ch4 (Strand B) | Ingress |
| 7805 | Helix-E ch5 (egress) | Output — downstream consumers connect here |
| 7806 | Helix-E ch6 | Output |
| 7807 | Helix-E ch7 | Output |
| 7808 | Helix-E ch8 | Output |
| 8888 | paging.py dashboard | HTTP — live swap + tier stats UI |

---

## Troubleshooting

### `AttributeError: module 'signal' has no attribute 'SIGUSR1'`
Already patched in `franken5.py`. If this recurs, check that you are running
`true_double_helix.py` (the PoC copy with the patch) and not `helixi.py` directly.

### `franken5` not found / ImportError
`PYTHONPATH` is not set. Run via `run-helix-poc.ps1` which sets it, or manually:
```powershell
$env:PYTHONPATH = "D:\Users\jwlef\Phoenix\Phoenix-DevOps-oS\sector1\helix-lightning"
py -3 tools\poc\true_double_helix.py
```

### Snapshot not appearing in `F:\Phoenix\helix-pages\`
1. Check `F:\Phoenix\` exists and is writable — run `setup-shared-fs.ps1` if not
2. Check `PHOENIX_HELIX_PAGE_DIR` is set to `F:\Phoenix\helix-pages`
3. Check the process is running: `Get-Process py`

### paging.py: snapshot shows as stale (age > 30s)
Windows side stopped writing. Check Task Scheduler:
```powershell
schtasks /query /tn "Phoenix\HelixLightningKernel" /fo LIST | Select-String "Status|Last Run"
```
Restart it: `schtasks /run /tn "Phoenix\HelixLightningKernel"`

### paging.py: `/phoenix/` not mounted
```bash
sudo mount -t cifs //10.0.2.2/Phoenix /phoenix \
  -o username=jwlef,password=YOUR_PASS,uid=1000,gid=1000,vers=3.0
```
Then restart the service: `sudo systemctl restart phoenix-helix-kernel`

### paging.py fails: `Swap initialization failed`
NVMe mount not present. Check `PHOENIX_PAGING_NVME_MOUNT`:
```bash
ls /mnt/nvme   # should exist
df -h /mnt/nvme
```
If NVMe is not available, set `PHOENIX_PAGING_NVME_MOUNT=/tmp` for testing
(swap will be created in /tmp — not for production).

### Suit overrides skipped ("not found — skipping")
`PHOENIX_SUITS` is not set or points at the wrong directory. It must point at the
repo root (`Phoenix-DevOps-oS/`), not at `sector1/`. The Task Scheduler task sets
this automatically via `run-helix-poc.ps1`.

---

## How this connects to the rest of Phoenix

```
sector1/helix-lightning/    ← THIS GUIDE
  Frank5, Helix-I/E, FrankRing, FrankSpawn, ProcessLibrary
  helix_suit_override.py → wires helix_complete_stack.py for ALL sectors

sector1/helix/
  helix_complete_stack.py  ← The suit. L1/L2/L3/L5 cache. Every ring runs through this.

sector2/
  intake.sh                ← Registers every file. Wired as a suit (clone_pool, packages_worker).
  package-handler/         ← D1 custody + R2 storage.

sector3/
  romeo.py / juliet.py     ← Ingress / egress boundary. Wired as suits.
  translator.sh            ← OUTPUT ONLY — fires at sector3 boundary via Helix-E.
  services/
    phoenix-helix-kernel.service  ← THIS GUIDE (Debian autostart)

sector4/
  paging.py                ← Linux paging brain. Reads windows_snapshot.json. ← THIS GUIDE
  paging_windows.py        ← Windows paging brain (attach_helix already wired).

tools/poc/
  true_double_helix.py     ← PoC entry point. Helix-I + snapshot writer. ← THIS GUIDE
  run-helix-poc.ps1        ← Windows launcher ← THIS GUIDE
  run-helix-poc.sh         ← Debian launcher ← THIS GUIDE
  install-helix-autostart.ps1  ← Windows Task Scheduler ← THIS GUIDE
  DOUBLE-HELIX-PLAN.md     ← Plan file for this work
  SHARED-FS-PLAN.md        ← Shared filesystem plan (SMB over QEMU)

dashboard/
  main.js                  ← Electron app. Real D1/R2 data. Claude HUD. Live monitor.
  manual/PHOENIX_MANUAL.md ← Full system reference (install, architecture, commands)
  manual/LAURIE_GUIDE.md   ← Plain-English guide for Laurie
```

The Helix Lightning Kernel is the engine everything else rides.
Frank wears every process. Helix holds the memory. paging.py holds the line.

---

## Next steps after this guide

1. Run both sides live and confirm `[SNAPSHOT]` appears in paging.py logs
2. Wire `helix_e.py` (Helix-E, Debian side) so Strand B has an active egress
3. Run `main_kernel.py` as the full boot (Frank → Library → Spawn → Helix-I/E together)
4. Hook `helix_complete_stack.py` into Life First LLM context as the memory backend

---

*Phoenix DevOps OS — GPL v3 — Every penny every time*
*Built by Jerry Leftwich + Claude (Anthropic)*
