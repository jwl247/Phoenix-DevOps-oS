# PBMII handoff — 2026-10-03 (Phoenix Genie session, Cowork)

Everything below was built and sandbox-tested in the cloud session and written
straight into `F:\Phoenix\Phoenix-DevOps-oS`. **Nothing is committed to git.**
Windows-only paths (cmd launch, taskkill, GlobalMemoryStatusEx) have run on
PBMII only where noted. Run the steps in order; each says what you should see.

---

## What changed (all in the working tree)

| File | What |
|---|---|
| `sector1/kernel/genie/genie.ps1` | **New.** Phoenix Genie — the Universal Kernel in PS7: `up/down/restart/status/log/doctor/find/clone/import/closet/custody/profile`. Clone = OUT only, SHA3-512 custody check before any byte is written. **Live on PBMII** (doctor green, 8 Helix ports, real R2 clone verified, control socket OK). |
| `sector1/kernel/genie/genie_control.py` | **New.** Kernel control socket 127.0.0.1:8766, per-boot token, no browsers, hot-loads custody-verified suits from the Genie closet only, imports persist and are re-verified at boot. **Live on PBMII.** |
| `sector1/kernel/main_kernel.py` | Starts genie_control, the userspace Helix + paging manager, `phoenix_ctx` for suits, and the addressed-stage resolver (`{"suit": name}` → Genie-imported suits only). |
| `sector1/helix/helix_vram.py` | Her load source now works on Windows (`machine_memory()`); external pressure source; Strand B resize (never below base/what she holds). 11/11 tests pass. |
| `sector4/paging_helix.py` | **New.** Paging manager wired to Helix: load (RAM + commit charge) → her Dandelion; her eviction → Doppelgangers that grow/retire Strand B. |
| `sector1/helix-lightning/helix_gate.py` | **New.** Helix socket gate: `HELIX_SOCKET_TOKEN` handshake; non-loopback bind without a token is refused (fails closed to 127.0.0.1). |
| `sector1/helix-lightning/helixi.py`, `helixe.py` | Use the gate; Helix-I 4 MB per-connection cap; Helix-E handshakes off the accept loop. |
| `sector2/apps/lifefirst/suits/lifefirst_checkin.py` | **New.** Life First's first suit: validate → hash-chained log → store in Helix → reply via Ollama-local (honest `"ai": false` fallback). |
| `sector3/phone-node/phoenix_phone.py` | **New.** Phone client (Termux): `say/voice/where/listen/flush/doctor`, outbox when the brain is away. |
| `sector3/phone-node/phone-setup.sh` | **New.** One-time Termux setup (keys hidden → 0600 header file, client custody-checked from R2, Tailscale-only brain address, start at boot; `--with-kernel` = proot Debian + PS7). Not yet run on a phone. |
| `sector2/package-handler/intake.sh` | Hash step no longer silently blank: openssl → Python hashlib fallback → loud `NO CUSTODY HASH`. |
| `scripts/intake.ps1` | Fixed: after the first `intake`, every later call failed with "Invoke-IntakeFile is not recognized". |
| `sector1-4/CONNECTIONS.md` | Documented all of the above (Atlas dry run: 247 → 253 nodes). |

---

## Run order on PBMII

### 1. Load the new code
Open a **new** PS7 window (the profile loads Genie). Then:
```powershell
. F:\Phoenix\Phoenix-DevOps-oS\scripts\intake.ps1
genie restart
genie doctor
genie status
```
Expect: doctor all green incl. `control :8766 token OK`. Status has two new lines:
`helix : dandelion … load …` and `paging : pressure … (ram …, commit …)`.
**Check `ram` is not 0** — that's the first real run of the Windows memory reading.
If `genie status` warns Strand B's disk can't hold her base, set
`HELIX_VRAM_STRAND_B` to a folder on the fast 4 TB drive (user env var) and `genie restart`.

### 2. Finish Romeo/Juliet (singles + the pair)
```powershell
intake F:\Phoenix\Phoenix-DevOps-oS\sector3\romeo_juliet\juliet.py
intake F:\Phoenix\Phoenix-DevOps-oS\sector3\romeo_juliet\dbl_juliet.py
intake F:\Phoenix\Phoenix-DevOps-oS\sector3\romeo_juliet\
pip install pyzmq        # Romeo/Juliet can't run on PBMII without it
```
(Romeo already went in this morning — D1 ledger v2, correct hash.)

### 3. Intake today's new/changed files (so they're in custody + R2)
```powershell
$r = 'F:\Phoenix\Phoenix-DevOps-oS'
'sector1\kernel\genie\genie.ps1','sector1\kernel\genie\genie_control.py','sector1\kernel\main_kernel.py',
'sector1\helix\helix_vram.py','sector4\paging_helix.py','sector1\helix-lightning\helix_gate.py',
'sector1\helix-lightning\helixi.py','sector1\helix-lightning\helixe.py',
'sector2\apps\lifefirst\suits\lifefirst_checkin.py','sector3\phone-node\phoenix_phone.py',
'sector3\phone-node\phone-setup.sh','sector2\package-handler\intake.sh','scripts\intake.ps1' |
  ForEach-Object { intake (Join-Path $r $_) }
```
Note: `main_kernel.py` exists in two folders and intake keys by file name — this
updates the clonepool's `main_kernel.py` (the Universal Kernel one), which is right.

### 4. Life First suit into the live kernel + first real AI reply
```powershell
ollama list                      # need llama3.2:3b; if missing: ollama pull llama3.2:3b
genie import lifefirst_checkin.py
python -c "import socket,json,time;c=socket.create_connection(('127.0.0.1',7805));c.settimeout(40);time.sleep(.3);s=socket.create_connection(('127.0.0.1',7701));s.sendall(json.dumps({'suit':'lifefirst_checkin','who':'jerry','text':'first check-in from PBMII'}).encode());s.close();print(c.recv(65536).decode())"
python F:\Phoenix\Phoenix-DevOps-oS\sector2\apps\lifefirst\suits\lifefirst_checkin.py verify
genie status
```
Expect: a JSON reply with `"ai": true` (or `"ai": false` + the reason if Ollama
isn't running), `verify` → `"ok": true`, and `helix … blocks 1`.

### 5. Atlas
```powershell
cd F:\Phoenix\Phoenix-DevOps-oS\sector2\package-handler
node parse-connections.js
```
Expect: the worker rebuilds from the new bundle; **253 nodes**.

### 6. The 86 rows with no hash
```powershell
genie custody
```
Review the generated script in `~\.phoenix\genie\` before running it. Decide the
`DIFFERS` / `R2-ONLY` / `LOST` rows by hand.

### 7. Open the Helix sockets to the mesh (your call — security setting)
Only when the phone is ready. Generate a token, bind to PBMII's **Tailscale** address:
```powershell
$tok = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).ToLower()
$ts  = (tailscale ip -4)
[Environment]::SetEnvironmentVariable('HELIX_SOCKET_TOKEN', $tok, 'User')
[Environment]::SetEnvironmentVariable('HELIX_I_BIND', $ts, 'User')
[Environment]::SetEnvironmentVariable('HELIX_E_BIND', $ts, 'User')
```
New PS7 window → `genie restart`. Windows Firewall will need inbound rules for
TCP 7701 and 7805 **scoped to the Tailscale interface / 100.64.0.0/10 only** —
create them yourself in Windows Defender Firewall; don't open them to Private/Public.
Keep the token for the phone setup (step 8). Without the token the kernel refuses
the mesh bind and stays on loopback (logged CRITICAL) — that's by design.

### 8. Phone node
On the phone: Tailscale app (signed in to the Phoenix tailnet), Termux (F-Droid),
Termux:API app, Termux:Boot app (open it once). Get `phone-setup.sh` onto the phone
(Taildrop it from PBMII, or after `git push`: `curl -fsSLO https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/sector3/phone-node/phone-setup.sh`), then in Termux:
```bash
bash phone-setup.sh
lifefirst say "testing from my phone"
```
It asks for PHOENIX_AUTH + CF Access keys (hidden), PBMII's Tailscale address, the
token from step 7, and whose phone it is. It refuses a non-Tailscale address.

### 9. Commit
```powershell
cd F:\Phoenix\Phoenix-DevOps-oS
git status
git add sector1/kernel/genie sector1/kernel/main_kernel.py sector1/helix/helix_vram.py sector4/paging_helix.py `
        sector1/helix-lightning/helix_gate.py sector1/helix-lightning/helixi.py sector1/helix-lightning/helixe.py `
        sector2/apps/lifefirst/suits sector3/phone-node sector2/package-handler/intake.sh scripts/intake.ps1 `
        sector1/CONNECTIONS.md sector2/CONNECTIONS.md sector3/CONNECTIONS.md sector4/CONNECTIONS.md
git commit -m "Phoenix Genie: Universal Kernel in PS7, Helix+paging wired, gated Helix sockets, Life First check-in suit, phone node"
git push
```
`git status` will also show uncommitted 10/1–10/2 work from other sessions —
survey that separately (CLAUDE.md NEXT SESSION item 6).

---

## Decisions waiting on Jerry
- **Strand B location**: which drive letter is the 4 TB game drive (`HELIX_VRAM_STRAND_B`).
- **E: vs F: clonepool** (S2CORE-F41): romeo.py's intake landed on E: and labelled itself v1 while the D1 ledger correctly says v2.
- **Helix-E vs Juliet**: both claim to be THE output-translation boundary.
- **`paging_windows.py`**: retire it (pagefile changes need a reboot; superseded by `paging_helix.py`)?
- **Romeo/Juliet `~/.catalog` crash** on fresh machines — apply the one-line fix?
- **The 86 unhashed rows** — the `genie custody` review.

## Known issues found today (also in CONNECTIONS.md)
- FileTree/status server default to 7703/7704, colliding with Helix-I (Genie moves them to 7713/7714).
- `phoenix_status_server` `/status` reports Helix/Frank unavailable (reads DB files the kernel never writes); use `genie status`.
- Helix-I channel state stays `SIGNALED` after a stage (cosmetic).
- Helix-E broadcasts every ch5 result to every consumer; the phone filters by `who`. Fine for one family; per-user channels are needed before more people use it.
- intake prints `→` as `ΓåÆ` (Git Bash vs PS7 encoding) and a stray `5000` line.
- The `helix` core suit (and 8 others) point at a file with no `run()` (S1-F28) — unaddressed stages still do nothing.

## CLAUDE.md session protocol (for the PBMII session)
Update BUILD STATUS / NEXT SESSION, append the session entry to
`docs/history/SESSION-LOG.md`, run `parse-connections.js` (step 5), push.
Project doc with the design: `claude/phone-node-design.md` (Phoenix Genie project).
