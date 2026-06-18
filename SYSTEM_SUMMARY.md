# Phoenix DevOps OS — System Summary & Command Reference
# Updated: 2026-06-18 | Jerry Leftwich (@jwl247) | GPL v3
# =============================================================================

## Architecture — Four Sectors

```
Sector 1  Boot / Kernel          frank3, helix, phoenix_auth, concierge
Sector 2  Intake / Package       intake.sh, config_centralizer, propagator, ring0, all apps
Sector 3  Comms / Networking     romeo, juliet, dbl_juliet, quadengine, translator, WireGuard
Sector 4  Core Engine / Vault    Frank, Helix, breach_coms, clonepool, security stack
```

**On disk (WSL dev):**
```
~/phoenix-devops/
  sector1/    kernels/ helix/ auth/ concierge/
  sector2/    package-handler/ frank/ ring0/ propagator/ config_centralizer.py
              desktop/ glossary/ review-platform/ manual/ documents-worker/
  sector3/    translator/ romeo_juliet/ quadengine/ services/ wireguard/ bridge/
  sector4/    intake/ vault/ helix/ frank/ security/ telemetry/
  helix_lightning_kernel/     (submodule — private)
  phoenix_universal_kernel/   (submodule)
  lifefirst_modules/          (submodule)
  deploy/     setup_*.sh scripts
  scripts/    sync.sh
  bin/        lol
  tools/      conflict_map.py

~/Phoenix/                    clonepool/  bin/  cards/  logs/
~/CoPES/                      src/  intake/  (legacy — being consolidated)
```

**Nodes:**
```
WSL           10.77.0.2   ~/phoenix-devops/    dev machine
phoenix-ext   10.77.0.3   ~/phoenix-devops/    production (Dell Inspiron, 192.168.1.133)
Windows       10.77.0.1                        WireGuard hub
```

---

## Environment Variables

| Variable            | Value                                           |
|---------------------|-------------------------------------------------|
| PHOENIX_HOME        | /home/jwlef/Phoenix                            |
| PHOENIX_INSTALL_DIR | /home/jwlef/phoenix-devops                     |
| PHOENIX_CLONEPOOL   | /home/jwlef/Phoenix/clonepool                  |
| PHOENIX_BIN         | /home/jwlef/Phoenix/bin                        |
| PHOENIX_CARDS       | /home/jwlef/Phoenix/cards                      |
| PHOENIX_AUTH        | (in ~/.phoenix_env — do not hardcode)           |
| PHOENIX_WORKER_URL  | https://packages-worker.phoenix-jwl.workers.dev |
| PHOENIX_SECTOR1-4   | /home/jwlef/phoenix-devops/sector1-4           |
| CLONEPOOL_DIR       | /home/jwlef/Phoenix/clonepool                  |

```bash
source ~/.phoenix_env    # always first
```

---

## TAV Address System

```
hex_id    = filename.encode().hex()       → clonepool directory name
b58       = base58(hex_id[:8 bytes])      → short address  e.g. HdeWh8aY7bG
Header QR = USYS:<b58>:HEADER             → written BEFORE hash  (state: white/grey/black)
SHA3-512 hash on copy
Footer QR = USYS:<b58>:FOOTER:<sha3>      → written AFTER hash   (tier: T1/T2/T3/T4)
```

Never swap Header/Footer. Load-bearing rule.

---

## Commands by System

### Bootstrap / Install (cold machine)
```bash
curl -fsSL https://get.authenticcoder.com | bash
# fallback:
curl -fsSL https://packages-worker.phoenix-jwl.workers.dev/get | bash
# manual (with submodules):
git clone --recurse-submodules git@github.com:jwl247/Phoenix-DevOps-oS.git phoenix-devops
cd phoenix-devops && bash bootstrap.sh
```

### Global Sync (WSL → GitHub → phoenix-ext)
```bash
bash ~/phoenix-devops/scripts/sync.sh              # full sync + kernel restart on ext
bash ~/phoenix-devops/scripts/sync.sh --push       # WSL → GitHub only
bash ~/phoenix-devops/scripts/sync.sh --pull       # GitHub → phoenix-ext only (+ restart)
bash ~/phoenix-devops/scripts/sync.sh --no-restart # sync without restarting kernel
```

### Status Check
```bash
bash ~/phoenix-devops/status.sh    # 8-check health report — paste to Claude at session start
```

### Kernel (HLK — helix_lightning_kernel)
```bash
# WSL dev
bash ~/phoenix-devops/start_kernel.sh

# phoenix-ext (systemd)
sudo systemctl start phoenix-kernel
sudo systemctl stop phoenix-kernel
sudo systemctl restart phoenix-kernel
sudo systemctl status phoenix-kernel
journalctl -u phoenix-kernel -f          # live logs

# Wire protocol (AUTH required on every connection)
# Ports: HelixI 7701-7704 / HelixE 7805-7808
printf "AUTH $PHOENIX_AUTH\nls -la\n" | nc localhost 7701
```

### Intake / lol
```bash
intake <file>                    # push file → clonepool + D1
intake clone <file>              # pull latest → $PWD
intake clone <dir>               # pull directory snapshot → $PWD
intake clone <dir> v2            # pull specific version
intake prune                     # evict versions older than 3 days
intake status                    # clonepool health
intake backend <pkg> <be> <ver>  # register a backend-installed package

lol file.py.lol                  # pull by name from clonepool → $PWD
lol file.py.lolHdeWh8aY7bG       # pull by b58 address
lol file.py.lolHEX636f6e…        # pull by raw hex
lol file.py.lol --intake         # push into clonepool
lol name.lol --pkg               # intake a package
lol ~/dir.lol                    # intake a whole directory
```

### Frank (port 7347)
```bash
# Runs inside phoenix-kernel.service — not started separately
curl -s http://localhost:7347/health
curl -s -X POST http://localhost:7347/lifefirst \
  -H "Authorization: Bearer $PHOENIX_AUTH" \
  -d '{"message":"hello","user_id":"laurie"}'
```

### Helix
```bash
# Dual-strand (strand_a/strand_b) inside phoenix-kernel.service
# 300k+ ops/sec, zlib level 5, 4GB RAM
# Benchmark (pending on ext):
python3 ~/phoenix-devops/sector4/helix/helix.py --benchmark
```

### Vault Tiers (breach_coms drives — phoenix-ext)
```
breach_coms4  T1 PRIMARY    /mnt/g  (sdc1)   master vault — NEVER DELETE
breach_coms3  T2 SECONDARY  /mnt/f  (sdb1)   day-1 mirror
breach_coms2  T3 TERTIARY   /mnt/e  (sdc2)   day-2 mirror
breach_coms1  T4 TERTIARY   /mnt/d  (sda2)   day-3 mirror
clonepool     ~/Phoenix/clonepool             callable face of the vault
```

### Propagator (Sector 2)
```bash
python3 ~/phoenix-devops/sector2/propagator/propagator.py
bash ~/phoenix-devops/sector2/propagator/propcoms.sh
# dispatch config: sector2/propagator/dispatch.json
```

### config_centralizer (Sector 2 / Ring 0)
```bash
python3 ~/phoenix-devops/sector2/config_centralizer.py          # scan all sectors
python3 ~/phoenix-devops/sector2/config_centralizer.py /path    # specific path
# Output: ~/Phoenix/cards/<hex>.card
# Finds: .conf .env .yaml .yml .json .toml .ini
```

### WireGuard Mesh
```bash
# WSL — start / stop
sudo wg-quick up ~/phoenix-devops/sector3/wireguard/wg0-wsl.conf
sudo wg-quick down ~/phoenix-devops/sector3/wireguard/wg0-wsl.conf
sudo wg show wg0-wsl

# phoenix-ext (systemd)
sudo systemctl status wg-quick@wg0
sudo systemctl restart wg-quick@wg0

# Mesh IPs: Windows 10.77.0.1 | WSL 10.77.0.2 | phoenix-ext 10.77.0.3
ssh phx           # phoenix-ext via WireGuard
ssh phoenix-lan   # phoenix-ext via LAN
```

### D1 / packages-worker (Cloudflare)
```bash
# Health check
curl -s -H "Authorization: Bearer $PHOENIX_AUTH" \
  https://packages-worker.phoenix-jwl.workers.dev/health

# Wrangler deploy (from WSL)
cd ~/phoenix-devops/sector2/package-handler && npx wrangler deploy

# Endpoints:
POST /clonepool   { hex_id, name, b58, pool_path, sidecar_path, state }
POST /custody     { hex_id, name, qr_top, qr_bottom, state, action, actor }
POST /glossary    { hex, name, b58, description, state, size, pool_path }
GET  /health
GET  /get         → bootstrap.sh (browser gets install page)
```

### Desktop Apps (http://192.168.1.133/...)
```
/desktop/              Mixing board control surface
/desktop/mixer.php     12 service channel strips + VU meters + telemetry (polls every 8s)
/desktop/switches.php  Toggles + 4 dropdowns + 5 action buttons
/desktop/filetree.php  Filesystem browser, drag+drop group assignment, D1 forged docs
/glossary/             Clonepool index (135 entries, dark cockpit)
/review/               Peer review platform (immutable D1, 6 types, auto-promote at 2 votes)
/manual/               Operator Manual (14 sections, interactive)
/lifefirst/            Life First — Laurie's AI (Ollama primary → Claude fallback)

# Global Shell: backtick or F12 from anywhere in Desktop
# builtins: status / threat / services / frank / ollama / wg / mixer / switches / files / clear
# ask <question>  → Frank :7347 → Ollama → Claude fallback
# run <cmd>       → api/shell.php (proc_open, 30s timeout, blocklist, audit log)
```

### Ollama AI Stack (phoenix-ext)
```bash
ollama serve                     # start (or systemd)
ollama list                      # show pulled models
ollama pull phi3.5               # still pending
ollama run llama3.2:3b           # interactive

# Models:
# llama3.1    (4.9GB)  — Laurie / Life First DEDICATED — never shared
# llama3.2:3b (2.0GB)  — kernel / code fast path
# deepseek-r1:1.5b (1.1GB) — reasoning / chain of thought
# phi3.5      (pending) — chat / conversational

# Benchmark:
python3 ~/phoenix-devops/sector4/frank/frank_ollama_bridge.py --benchmark
# Result (Jun 16): llama3.2:3b warm=6.1 tok/s, avg=4.1 tok/s (CPU-only)
# Cold start ~60s — pre-warm via Frank PCS = next priority
```

### Security Stack (sector4/security/ — private submodule)
```bash
# 5 modules inside phoenix-kernel.service:
# FileMotionSensor, BufferEscalationSystem, LockdownDefenseSystem,
# SignalMirrorBouncer (amplificationFactor=1 LOCKED), Guardian
# Controlled from: /desktop/switches.php
# All events → D1 forensics tables
# Never push to public GitHub without Jerry's go-ahead
```

### Life First (Laurie's AI — http://192.168.1.133/lifefirst/)
```bash
# Deploy:
bash ~/phoenix-devops/lifefirst_modules/deploy_lifefirst.sh

# API:
curl -X POST http://192.168.1.133/lifefirst/api.php \
  -d '{"action":"chat","user_id":"laurie","message":"hello","token":"<PHOENIX_AUTH>"}'

# Escalation: Level 1(120s)→2(90s)→3(60s)→4(45s)→5(30s) → CALLS JERRY
# AI: llama3.1 primary → Claude API fallback
```

### Deploy Scripts
```bash
sudo bash ~/phoenix-devops/deploy/setup_phoenix_ext.sh    # Phase 1 prereqs + kernel service
bash ~/phoenix-devops/deploy/setup_desktop.sh
bash ~/phoenix-devops/deploy/setup_glossary.sh
bash ~/phoenix-devops/deploy/setup_review_platform.sh
bash ~/phoenix-devops/deploy/setup_manual.sh
bash ~/phoenix-devops/deploy/setup_ollama.sh
bash ~/phoenix-devops/deploy/setup_breach_coms.sh
bash ~/phoenix-devops/deploy/deploy.sh                    # translator.sh → systemd
```

---

## Clonepool Structure
```
~/Phoenix/clonepool/
  <hex_id>/
    v1_<filename>
    v2_<filename>
    <hex_id>.sidecar.json   # hex, b58, sha3, header_qr, footer_qr, state, frank_usable
```

---

## Session Protocol

```bash
# START
source ~/.phoenix_env
bash ~/phoenix-devops/status.sh

# SYNC NODES
bash ~/phoenix-devops/scripts/sync.sh

# INTAKE FILES
intake <file>

# END — update BUILD STATUS in CLAUDE.md, commit, sync
git -C ~/phoenix-devops add -p
git -C ~/phoenix-devops commit -m "session: <what changed>"
bash ~/phoenix-devops/scripts/sync.sh
```

---

## Critical Rules (never break)

1. Never delete from breach_coms4 (master vault)
2. Header QR BEFORE hash / Footer QR AFTER hash — never swap
3. translator.sh fires on OUTPUT ONLY — never on intake or clone
4. GPU blacklisted — never suggest GPU-dependent solutions
5. Universal Kernel requires AUTH header on every connection
6. Everything quadralingual until sector3 translator boundary
7. Security stack never pushed to public GitHub without Jerry's go-ahead
8. No demos. Real code only. Pro+ status before anything enters repo.
9. One repo. One OS. Everything in its sector.
10. Immutable: reviews, switches, custody chain
