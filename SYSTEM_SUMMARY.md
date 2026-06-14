# Phoenix DevOps OS — System Summary & Command Reference
# Generated: 2026-06-12 | Jerry Leftwich (@jwl247) | GPL v3
# =============================================================================

## Architecture — Four Sectors

```
Sector 1  Boot / Kernel          frank3, helix, phoenix_auth, concierge
Sector 2  Intake / Package       intake.sh, intake.py, config_centralizer, propagator, ring0
Sector 3  Comms / Networking     romeo, juliet, dbl_juliet, quadengine, translator
Sector 4  Core Engine / Vault    Frank, Helix, breach_coms, clonepool, process library
```

**On disk (WSL dev):**
```
~/projects/phoenix-devops/
  sector1/    kernels/ helix/ auth/ concierge/
  sector2/    package-handler/ frank/ ring0/ propagator/ config_centralizer.py
  sector3/    translator/ romeo_juliet/ quadengine/ services/
  sector4/    intake/ vault/ helix/ frank/
~/projects/Helix_lightning_kernel/   process_library.py  frank_ring.py
~/projects/Phoenix_Universal_Kernel/ main_kernel.py  phoenix_kernel/core.py
~/projects/CoPES/                    src/  bin/  intake/
~/projects/unitedsys/                core/  db/
~/projects/lifefirst_modules/        Life First backend (PHP/MySQL)
~/Phoenix/                           clonepool/  bin/  cards/  logs/
```

---

## TAV Address System

```
hex_id    = filename.encode().hex()       → clonepool directory name
b58       = base58(hex_id[:8 bytes])      → short address  e.g. HdeWh8aY7bG
Header QR = USYS:<b58>:HEADER             → written BEFORE hash
SHA3-512 hash on copy
Footer QR = USYS:<b58>:FOOTER:<sha3>      → written AFTER hash
```

Never swap Header/Footer. Architecture rule. Load-bearing.

---

## Commands

### Environment
```bash
source ~/.phoenix_env            # ALWAYS FIRST
```

### Intake (push file into system)
```bash
python3 ~/projects/unitedsys/core/intake.py <file>   # Python — full D1 sync
intake <file>                    # shell intake
intake <file.py.lol>             # .lol suffix stripped automatically
intake clone <file>              # pull latest from clonepool → $PWD
intake clone <dir>               # pull latest directory snapshot → $PWD
intake clone <dir> v2            # pull specific version
intake prune                     # evict versions older than 3 days
intake status                    # clonepool health
intake backend <pkg> <be> <ver>  # register a backend-installed package
```

### lol — the Phoenix command wrapper
```bash
lol file.py.lol                  # pull file by NAME from clonepool → $PWD
lol file.py.lolHdeWh8aY7bG       # pull file by B58 ADDRESS → $PWD
lol file.py.lolHEX636f6e...      # pull file by RAW HEX → $PWD
lol file.py.lol --intake         # push file INTO clonepool
lol name.lol --pkg               # intake a package by name
lol ~/dir.lol                    # intake a whole directory

# Install/update lol
python3 ~/projects/CoPES/bin/lol
```

### config_centralizer (Sector 2 / Ring 0 / SYSTEM)
```bash
# Scan default sector paths (sector1-4 + ~/Phoenix)
python3 ~/projects/phoenix-devops/sector2/config_centralizer.py

# Scan specific path
python3 ~/projects/phoenix-devops/sector2/config_centralizer.py /path/to/scan

# Cards written to: ~/Phoenix/cards/<hex>.card
# Finds: .conf .env .yaml .yml .json .toml .ini
# Skips: clonepool node_modules .git __pycache__ cards logs intake
```

### Universal Kernel (Sector 1 — ports 7701-7704)
```bash
# Start (source env first — AUTH gate requires PHOENIX_AUTH)
source ~/.phoenix_env
python3 ~/projects/Phoenix_Universal_Kernel/main_kernel.py

# Wire format — AUTH header required on every connection
# Line 1: AUTH <PHOENIX_AUTH token>
# Line 2: <command to execute>
# Example via netcat:
printf "AUTH 0bfadb4c...\nls -la\n" | nc localhost 7701
```

### D1 / Cloudflare Worker
```
Worker:   https://packages-worker.phoenix-jwl.workers.dev
DB:       phoenix_dev_db  (27958687-4349-47ed-8b6a-dbc4ab29730f)
Auth:     Authorization: Bearer $PHOENIX_AUTH

POST /clonepool   { hex_id, name, b58, pool_path, sidecar_path, state }
POST /custody     { hex_id, name, qr_top, qr_bottom, state, action, actor }
POST /glossary    { hex, name, b58, description, state, size, pool_path }
```

### Glossary (human-readable clonepool index)
```python
from core.glossary import init_glossary, amend, list_entries, check_evictions
# 3-day amend window before eviction
amend(hex_id="636f6e66...", description="Updated description")
```

---

## Environment Variables

| Variable | Value |
|---|---|
| PHOENIX_HOME | /home/jwlef/Phoenix |
| PHOENIX_AUTH | 0bfadb4c9579359ad41f355ae634b533bac04b3ef49f99fff76c43d1ec8f17c2 |
| CLONEPOOL_DIR | /home/jwlef/Phoenix/clonepool |
| PHOENIX_WORKER_URL | https://packages-worker.phoenix-jwl.workers.dev |
| PHOENIX_SECTOR1 | /home/jwlef/projects/phoenix-devops/sector1 |
| PHOENIX_SECTOR2 | /home/jwlef/projects/phoenix-devops/sector2 |
| PHOENIX_SECTOR3 | /home/jwlef/projects/phoenix-devops/sector3 |
| PHOENIX_SECTOR4 | /home/jwlef/projects/phoenix-devops/sector4 |
| PHOENIX_CARDS | /home/jwlef/Phoenix/cards |

---

## Clonepool Structure

```
~/Phoenix/clonepool/
  <hex_id>/
    v1_<filename>          # first intake
    v2_<filename>          # re-intaked
    <hex_id>.sidecar.json  # hex, b58, sha3, header_qr, footer_qr, state, frank_usable
```

---

## Vault Tiers

```
breach_coms4  T1 PRIMARY    /mnt/g   master vault — NEVER DELETE
breach_coms3  T2 SECONDARY  /mnt/f   day-1 mirror
breach_coms2  T3 TERTIARY   /mnt/e   day-2 mirror
breach_coms1  T4 TERTIARY   /mnt/d   day-3 mirror, 4-day window
clonepool     callable face of the vault
```

---

## Life First App — Command Reference

### Backend (Phoenix server — PHP/MySQL)
```
Base URL: http://<SERVER_IP>/lifefirst/api.php
Auth:     X-Phoenix-Token: <PHOENIX_AUTH>   OR   token field in JSON body

POST ?action=chat
  { "action":"chat", "user_id":"laurie", "message":"...", "token":"..." }
  → routes to correct AI module via intent detection

POST ?action=register_device
  { "action":"register_device", "user_id":"laurie", "fcm_token":"...", "token":"..." }
  → stores FCM token for push delivery

POST ?action=acknowledge_alarm
  { "action":"acknowledge_alarm", "alarm_id":"123", "user_id":"laurie", "token":"..." }
  → stops escalation chain

GET  ?action=health   → module health check
GET  ?action=test     → API alive check
```

### AI Provider (config.php)
```php
define('AI_PROVIDER', 'claude');   // or 'ollama'
// Claude: needs CLAUDE_API_KEY env var or set in config.php
// Ollama: needs `ollama serve` running locally, no GPU required
//   Install: curl -fsSL https://ollama.com/install.sh | sh
//   Pull:    ollama pull llama3.2
```

### Escalation chain (Module 6)
```
Level 1: 120s grace → Level 2 (volume up, faster vibration)
Level 2:  90s grace → Level 3
Level 3:  60s grace → Level 4
Level 4:  45s grace → Level 5
Level 5:  30s grace → CALLS JERRY (JERRY_PHONE in config.php)
```

---

## Files Changed / Created This Session (2026-06-12)

| File | Action | B58 |
|---|---|---|
| bootstrap.sh | fixed write_status() variable bug | — |
| intake.py | written from scratch | — |
| glossary.py | fixed b58 column missing | — |
| .phoenix_env | updated auth token + added SECTOR1-4 + CARDS | 8mX1TwQejh9 |
| config_centralizer.py | NEW — sector 2 ring 0 SYSTEM process | HdeWh8aY7bG |
| egress_helix | fixed jwwlef→jwlef typo, graceful venv activate | HxkJsCnb3U3 |
| CoPES/bin/lol | NEW — added .lolHEX and .lolB58 address pull | dRVM |
| phoenix_kernel/core.py | AUTH gate added (hmac.compare_digest) | 4mZ51LzJEC |
| config.php (lifefirst) | NEW — central Life First config | HdeWh8aY3sD |
| ai_provider.php | NEW — Claude + Ollama shared AI layer | — |
| module_2_api_router.php | added chat/register_device/acknowledge_alarm actions | — |
| module_3_schedule_ai.php | wired to ai_provider, removed hardcoded key | — |
| module_4_messenger_ai.php | wired to ai_provider, removed hardcoded key | — |
| module_5_ai_memory.php | wired to ai_provider, removed hardcoded key | — |
| module_6_notification_ai.php | wired to ai_provider, removed hardcoded key | — |
| PhoenixAiClient.kt | NEW — Android → Phoenix backend | ET4MZURMT5r |
| AlarmService.kt | NEW — relentless foreground alarm service | BwgwKxfUVqj |
| AlarmActivity.kt | NEW — full-screen lock screen alarm, no escape | — |
| TokenUploadWorker.kt | completed TODO — real HTTP to Phoenix | — |

---

## Session Protocol

```bash
# START
source ~/.phoenix_env
cat ~/projects/phoenix-devops/CLAUDE.md
python3 ~/projects/phoenix-devops/sector2/config_centralizer.py
intake status

# INTAKE EVERY NEW FILE
python3 ~/projects/unitedsys/core/intake.py <file>

# END
# intake modified files, update BUILD STATUS in phoenix-devops/CLAUDE.md
```

---

## Critical Rules (never break)

1. Never overwrite without Jerry's prior approval
2. Never delete from breach_coms4 (master vault)
3. Header QR BEFORE hash / Footer QR AFTER hash — never swap
4. translator.sh fires on OUTPUT ONLY — never on intake
5. GPU blacklisted — never suggest GPU-dependent solutions
6. Universal Kernel requires AUTH header on every connection
7. Everything quadralingual until sector 3 translator boundary
8. No demos. Real code only. Pro+ status before anything enters repo.
