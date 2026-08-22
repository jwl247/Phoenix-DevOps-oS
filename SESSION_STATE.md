# Phoenix Session State
# Updated: 2026-08-11
# READ THIS AT THE START OF NEXT SESSION

## WHERE WE ARE

Full PoC working. Auth unified. Tray app released. Ready for R2.

- `usys run debian` — Debian 12 boots on Windows, no WSL, no Hyper-V ✅
- QEMU in clonepool — zero system dependencies ✅
- `usys download` + `usys watch` — auto-intake on every download ✅
- `phoenix-tray.exe` — built, v0.1.0 released on GitHub ✅
- Silent auth — `usys init` runs once, wires `$PROFILE`, never asked again ✅
- `intake.py` uses `Authorization: Bearer` (the project HTTP auth standard) ✅
- Tray app reads auth from Windows registry — works when launched by double-click ✅

---

## WHAT WAS BUILT THIS SESSION

### tools/poc/hello-phoenix.py
Demo process. Pure Python stdlib. Prints OS, hostname, Python version, TAV address.
Runs identical on Windows and Linux. No external dependencies.
TAV address: G5SiUQJ4zXk
hex_id: 5a231ceba3b0c623a75c9bf88b0b620a...

### tools/poc/hello-phoenix.suite.json
Suite manifest for hello-phoenix. runtime: python, entry: hello-phoenix.py

### tools/poc/yt-dlp.exe + yt-dlp.suite.json
yt-dlp 2026.07.04 binary. Downloads video from YouTube and 1000+ sites.
The power demo — no install, runs from clone pool, downloads video to screen.
hex_id: 9553338972fef72a97594443...
Already intaked. Already in D1.

### phoenix-core/tools/intake.py (upgraded 0.2.0 → 0.3.0)
Now POSTs to /clonepool and /custody on packages-worker after every intake.
D1 sync confirmed working. Both PoC files are in D1 right now.
Fix applied: User-Agent header "Phoenix-Intake/0.3.0" required to pass Cloudflare 1010 block.

### scripts/usys.ps1 (new command: pull)
usys pull <name> — asks D1 for a suite record by name, stages it in the local clone pool.
Confirmed working: usys pull hello-phoenix.py → found in D1, staged, b58: G5SiUQJ4zXk

---

## DISTRO DEMO SEQUENCE (what to do next)

### Step 1 — Get QEMU binary (one time)
```powershell
# Download qemu-system-x86_64.exe from https://qemu.weilnetz.de/w64/
# Drop it into your qemu-system suite directory in the clonepool
# Then:
. .\scripts\usys.ps1
usys distro intake-qemu
```

### Step 2 — Get the disk images (one time)
```powershell
# Debian cloud image (~400MB, boots fast, no installer)
Invoke-WebRequest `
  "https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-genericcloud-amd64.qcow2" `
  -OutFile "tools\poc\debian-12.5-genericcloud-amd64.qcow2"

# Ubuntu cloud image (~650MB)
Invoke-WebRequest `
  "https://cloud-images.ubuntu.com/releases/24.04/release/ubuntu-24.04.2-server-cloudimg-amd64.img" `
  -OutFile "tools\poc\ubuntu-24.04.2-server-cloudimg-amd64.img"
```

### Step 3 — Intake the images into Phoenix
```powershell
python phoenix-core/tools/intake.py tools/poc/debian-12.5-genericcloud-amd64.qcow2
python phoenix-core/tools/intake.py tools/poc/ubuntu-24.04.2-server-cloudimg-amd64.img
```

### Step 4 — Clone the suite dirs into clonepool
```powershell
# The suite manifests live in tools/poc/ — copy whole dir into clonepool
# so usys run can find them
$pool = "$HOME\Phoenix\clonepool"
Copy-Item tools\poc\debian.suite.json  "$pool\debian\.suite.json"    -Force
Copy-Item tools\poc\ubuntu.suite.json  "$pool\ubuntu\.suite.json"    -Force
# Then copy the disk images into those dirs
Copy-Item "tools\poc\debian-12.5-genericcloud-amd64.qcow2"          "$pool\debian\" -Force
Copy-Item "tools\poc\ubuntu-24.04.2-server-cloudimg-amd64.img"      "$pool\ubuntu\" -Force
```

### Step 5 — Run the demo
```powershell
# Debian first
usys run debian

# Then Ubuntu — same command, different OS, mind blown
usys run ubuntu

# Or via demo scripts:
pwsh -NoProfile -ExecutionPolicy Bypass -File tools/poc/run-debian.ps1
pwsh -NoProfile -ExecutionPolicy Bypass -File tools/poc/run-ubuntu.ps1
```

---

## PREVIOUS DEMO SEQUENCE (hello-phoenix — already done)

### This machine (Windows) — already done
```powershell
# Intake (already done — records are in D1)
$env:PHOENIX_WORKER_URL = [Environment]::GetEnvironmentVariable('PHOENIX_WORKER_URL','User')
$env:PHOENIX_AUTH       = [Environment]::GetEnvironmentVariable('PHOENIX_AUTH','User')
python phoenix-core/tools/intake.py tools/poc/hello-phoenix.py
python phoenix-core/tools/intake.py tools/poc/yt-dlp.exe

# Run
pwsh -NoProfile -ExecutionPolicy Bypass -Command ". '.\scripts\usys.ps1'; usys run hello-phoenix"
pwsh -NoProfile -ExecutionPolicy Bypass -Command ". '.\scripts\usys.ps1'; usys run yt-dlp -- --version"
```

### Second machine (morning) — exact sequence
```bash
git clone https://github.com/jwl247/Phoenix-DevOps-oS
cd Phoenix-DevOps-oS

export PHOENIX_WORKER_URL=https://packages-worker.phoenix-jwl.workers.dev
export PHOENIX_AUTH=<same token from this machine>
export CLONEPOOL_DIR=~/Phoenix/clonepool

# Intake on this machine (registers in D1 from THIS machine)
python3 phoenix-core/tools/intake.py tools/poc/hello-phoenix.py

# Run it — same hex ID, different OS, different hostname
python3 phoenix-core/tools/intake.py tools/poc/hello-phoenix.py
# OR if usys is wired:
# usys run hello-phoenix
```

### What the second machine output will prove
Same TAV address: G5SiUQJ4zXk
Different OS line: Linux
Different hostname
Same Frank record in D1

THAT is the demo. Import once. Run anywhere.

---

## NEW FILES THIS SESSION

| File | Purpose |
|------|---------|
| `tools/phoenix-tray.py` | System tray app — watches Downloads, runs suites, prompts intake |
| `tools/phoenix-tray.suite.json` | Suite manifest for tray app |
| `tools/poc/qemu-system.suite.json` | QEMU binary suite manifest |
| `tools/poc/debian.suite.json` | Debian 12 VM suite manifest |
| `tools/poc/ubuntu.suite.json` | Ubuntu 24.04 VM suite manifest |
| `tools/poc/run-debian.ps1` | Debian demo launcher |
| `tools/poc/run-ubuntu.ps1` | Ubuntu demo launcher |
| `scripts/usys.ps1` (updated) | Added: qemu runtime, `usys download`, `usys watch`, silent auth init |
| `phoenix-core/tools/intake.py` (updated) | Uses standard `Authorization: Bearer` auth, v0.3.0 |

---

## INFRASTRUCTURE STATUS

| Component | Status |
|-----------|--------|
| `intake.py` | ✅ Working — hashes, sidecar, catalog.db, clonepool, D1 sync |
| Auth header | ✅ Standardized — `Authorization: Bearer` everywhere |
| `usys init` | ✅ One-time setup — asks for token once, wires `$PROFILE`, silent forever after |
| D1 (packages-worker) | ✅ Live — `packages-worker.phoenix-jwl.workers.dev` |
| clonepool (local) | ✅ Working — `~/Phoenix/clonepool` |
| `usys run` | ✅ python, node, bash, powershell, binary, **qemu** runtimes |
| `usys pull` | ✅ Fetches suite record from D1 by name |
| `usys download` | ✅ Download + auto-intake in one command |
| `usys watch` | ✅ Background watcher on `~/Downloads` — prompt or auto-intake |
| `usys distro` | ✅ list / fetch-qemu / intake-qemu |
| QEMU in clonepool | ✅ `clonepool/qemu-system/` — no system install needed |
| Debian VM | ✅ Boots — `usys run debian --accel tcg` confirmed working |
| Ubuntu VM | ⏳ Suite ready — disk image not yet downloaded |
| `phoenix-tray.exe` | ✅ v0.1.0 released — `https://github.com/jwl247/Phoenix-DevOps-oS/releases/tag/v0.1.0` |
| R2 binary sync | ❌ NOT YET — **next session** |
| hello-phoenix in D1 | ✅ b58: `G5SiUQJ4zXk` |
| yt-dlp in D1 | ✅ hex: `9553338972fef72a...` |

---

## NEXT STEPS IN ORDER

1. **NEXT SESSION** — R2 binary sync
   - Add `PUT /r2/:hex_id` + `GET /r2/:hex_id` to `packages-worker/index.js` (~30 lines)
   - Add `r2_push()` to `intake.py` — streams file after D1 sync (~20 lines)
   - Extend `usys pull` to download binary from R2 into clonepool (~15 lines)
   - Small files first (exes, scripts) — multipart needed for Debian 330MB (later)
2. **SOON** — Test on Laurie's machine — `usys init` → token once → silent forever
3. **SOON** — LifeFirst MCP must-answer DO module
4. **FUTURE** — Ollama replacing Cloudflare AI binding
5. **FUTURE** — Ubuntu VM disk image + cloud-init seed ISO

---

## KEY FILES

| File | Purpose |
|------|---------|
| `tools/phoenix-tray.py` | Tray app source |
| `dist/phoenix-tray.exe` | Built exe (gitignored — rebuild with PyInstaller) |
| `phoenix-core/tools/intake.py` | Intake pipeline v0.3.0 |
| `scripts/usys.ps1` | Global command layer |
| `sector3/workers/packages-worker/index.js` | Cloudflare Worker — D1 API (needs R2 routes added) |
| `CLAUDE.md` (repo root) | Full architecture reference — read this first |

---

## LAURIE ONBOARDING (when ready)

```powershell
# 1. Clone repo
git clone https://github.com/jwl247/Phoenix-DevOps-oS
cd Phoenix-DevOps-oS

# 2. One-time init — asks for token once, wires profile, silent forever
pwsh -NoProfile -ExecutionPolicy Bypass -Command ". '.\scripts\usys.ps1'; usys init"

# 3. Open new terminal — usys + auth load automatically
usys status

# OR just send her phoenix-tray.exe from the GitHub release
# She double-clicks it — Phoenix is running, Downloads are watched
```

---

## WHY THIS EXISTS
Life First app for Laurie. Local LLM, no vendor, no subscription, no lock-in.
Phoenix is the infrastructure. Every process, every import, every run is in service of that.
People with less money deserve to run the same tools as everyone else.
Every penny every time.
