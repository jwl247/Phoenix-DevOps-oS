# Phoenix Session State
# Updated: 2026-09-04
# READ THIS AT THE START OF NEXT SESSION

## WHERE WE ARE

Dashboard: real terminal, CLAUDE hotline, unified working dir, HUD-mode
glass toggle, button generator + PoC buttons, Laurie's Guide (follows her
through a hunt, `PHOENIX_PROFILE=laurie` gated). Verified live 2026-09-04
after a week untouched — 22/23 automated checks passed, 0 console errors.
Still needs the HUD overlay retool and HELP CHAT/GUIDE folded into AI CHAT.

**Life First — DEPLOYED and verified live, 2026-09-04.** Booted the Debian
VM (note: `--share`/virtfs is broken on this machine's QEMU 11.1.0 build —
"no option group 'virtfs'" — boot with plain `-Persist`, no `--share`, and
move files over SSH/SFTP instead until a virtfs-capable QEMU build is
sorted), ran `install.sh` for real, found and fixed two real bugs in the
process (a FK column mismatch in secure_settings_schema.sql, and install.sh
not deploying laurie/*.php). End state, confirmed live:
- apache2 + mariadb + lifefirst-escalator.service all `active`
- `curl http://localhost/api.php?action=health` → real JSON, DB true, all
  5 modules installed
- `curl http://localhost/laurie/proxy.php?op=check_notifications` → real
  round-trip, browser path all the way to MySQL and back
- `/laurie/` → HTTP 200

**Known gap, not a bug:** no AI backend inside the VM yet (Ollama isn't
installed there, no CLAUDE_API_KEY set) — the AI-backed paths (today's
calendar summary) give a plain fallback message. The notification/
escalation half — the part that actually matters for the escalation tree —
works without either.

**Not yet done:** `cloudflared tunnel login` (cloudflared 2026.8.2 is
installed on the Windows host, not authenticated), the Life First MCP
connector auth (`/mcp` → claude.ai Life First App), and picking an AI
backend for the VM (install Ollama there, or set a real CLAUDE_API_KEY in
`/etc/lifefirst/lifefirst.env`).

The VM was left running at session end (10.0.2.15 inside, host SSH on
`localhost:2222`, phoenix/phoenix) — check `Get-Process qemu-system-x86_64`
before assuming it's down next session.

origin/main is at commit 155854a.

Clonepool integrity system is real end to end.
Shared filesystem is real end to end — proven live 2026-08-23.
SMB persistent mount proven live — fstab credentials= entry, umount/mount cycle confirmed.
Double Helix end-to-end smoke test: 5/5 Windows + 5/5 Debian — both strands proven 2026-08-24.
phoenix-helix-kernel.service deployed and running as systemd service — 2026-08-29.
FULL STACK RUNNING LIVE 2026-08-29:
  Windows: Frank5 + Helix-I ch1-4 + snapshot writer → F:\Phoenix\helix-pages\
  Debian:  paging.py AI v3.0, phoenix-helix-kernel.service enabled+running, [SNAPSHOT] loop confirmed
  Tier source: snapshot:/phoenix/helix-pages/windows_snapshot.json (not fallback)

- Dashboard Electron app — real D1/R2 data, PS7 shell, clonepool browser,
  screenshot analysis, live monitor, dedicated Claude "subscription" mode ✅
- R2 actually receiving bytes ✅
- Content-hash integrity system (SHA3-512 + BLAKE2b baseline) ✅
- QR generation (header/footer) live in the active bash intake.sh pipeline ✅
- PHOENIX_AUTH rotated and working ✅
- Whole repo intaked — 376 files ✅
- Debian running via QEMU — booted, SSH confirmed, phoenix user created ✅
- Windows ↔ Debian shared filesystem PROVEN LIVE ✅
  - Windows wrote test.txt → Debian read it
  - Debian wrote from-debian.txt → Windows read it
  - F:\Phoenix\ hosted on Windows, mounted at /phoenix inside Debian
  - Bridge: SMB over QEMU user-net (10.0.2.2), credentials file
  - No WSL. No virtfs. No Hyper-V. No install. Phoenix brought the OS.
- Double Helix PoC PROVEN LIVE end-to-end ✅
  - Windows: Frank5 booted, Helix-I ch1-4 listening, snapshot writing every 5s
  - Debian: paging.py reading snapshot, swapfile live, VP online, monitoring loop stable
  - Loop confirmed: [SNAPSHOT] L1/L2/L3/L5 lines in paging.py log every cycle
  - Shared FS bridge: F:\Phoenix\helix-pages\ ↔ /phoenix/helix-pages/ carrying live data
  - Windows autostart installed: Startup folder .cmd, starts at logon
- phoenix-helix-kernel.service DEPLOYED ✅
  - systemd service enabled, auto-restarts on failure
  - Service file: /etc/systemd/system/phoenix-helix-kernel.service
  - Swapfile: /var/swap/swapfile (200MB, pre-created manually — see boot sequence below)
  - SMB credentials: /etc/phoenix-cifs.creds (root:600)
  - fstab: credentials=/etc/phoenix-cifs.creds,vers=3.0

## WHAT WAS BUILT THIS SESSION (2026-08-29)

### Debian systemd service deployed
- Diagnosed SMB mount failure: cloud-init image boots with stale `guest` fstab entry
- Fixed: /etc/phoenix-cifs.creds created (username=jwlef, password=wtfover1A?, domain=)
- Fixed: fstab updated to credentials=/etc/phoenix-cifs.creds,vers=3.0,nofail,_netdev
- Fixed: swapfile — Linux blocks swapon on CIFS mount; pre-created 200MB at /var/swap/swapfile
- Deployed phoenix-helix-kernel.service with PHOENIX_PAGING_NVME_MOUNT=/phoenix/swap,
  PHOENIX_PAGING_INITIAL_SWAP_GB=1.0 — paging.py sees existing swap and skips init
- Service running: active(running), [SNAPSHOT] loop every 5s confirmed in journalctl
- D: drive was full (Steam/War Thunder) — removed Steam from D:, 109GB now free

## KNOWN ISSUES — MUST FIX NEXT SESSION

### cloud-init seed not updated
Every VM reboot wipes /etc/phoenix-cifs.creds and reverts fstab to `guest`.
The service will fail to start after reboot until the manual sequence below is run.
Fix: update `tools/poc/debian-seed/user-data` to bake in all three changes.

## MANUAL BOOT SEQUENCE (run after every VM reboot until seed is fixed)

```bash
# 1. Credentials + fstab
sudo bash -c "printf 'username=jwlef\npassword=wtfover1A?\ndomain=\n' > /etc/phoenix-cifs.creds"
sudo chmod 600 /etc/phoenix-cifs.creds
sudo sed -i '/10.0.2.2\/Phoenix/d' /etc/fstab
echo '//10.0.2.2/Phoenix  /phoenix  cifs  credentials=/etc/phoenix-cifs.creds,uid=1000,gid=1000,iocharset=utf8,vers=3.0,nofail,_netdev  0  0' | sudo tee -a /etc/fstab
sudo systemctl daemon-reload
sudo mount /phoenix

# 2. Pre-create swap (root disk is 2.8GB, ~92% full — only ~200MB available)
sudo mkdir -p /var/swap
sudo dd if=/dev/zero of=/var/swap/swapfile bs=1M count=200
sudo chmod 600 /var/swap/swapfile
sudo mkswap /var/swap/swapfile
sudo swapon /var/swap/swapfile

# 3. Start service
sudo systemctl start phoenix-helix-kernel
sudo journalctl -u phoenix-helix-kernel -f --no-pager
```

## NEXT STEPS IN ORDER

1. **Fix cloud-init seed** — `tools/poc/debian-seed/user-data` needs:
   - Pre-create 200MB swapfile at `/var/swap/swapfile` + swapon in runcmd
   - Write `/etc/phoenix-cifs.creds` (username=jwlef, password=wtfover1A?)
   - fstab entry with `credentials=/etc/phoenix-cifs.creds,vers=3.0` (not guest)
   - Copy + enable `phoenix-helix-kernel.service` via runcmd
   Without this, every VM reboot requires the manual sequence above.
2. **Add repo to share** — copy Phoenix-DevOps-oS into F:\Phoenix\ (nice to have).
3. **Glossary dashboard UI panel** — backend/API already confirmed working.
4. MapTiler map panel in dashboard.
5. Shade UI + drawer filesystem.
6. Deploy phoenix-dashboard.service on Ubuntu 192.168.1.133.
7. Start manual/phoenix_manual.md.

## KNOWN LOOSE ENDS (not urgent, not forgotten)

- `dashboardDEP/` and other `*DEP`-suffixed dirs share filenames with live
  counterparts — intake.sh's hex_id is filename-only, so both land under
  the same hex bucket as separate versions rather than colliding
  destructively, but it's confusing. Consider excluding `*DEP` dirs from
  intake or renaming them off the collision path.
- Tonight's whole-repo intake was run as `intake .`, so its directory-level
  summary entry got hex `2e` / name `.` instead of `Phoenix-DevOps-oS`.
  Cosmetic only — every individual file underneath is correctly named.
- The integrity-verification gate only covers `intake clone` (both
  single-file and directory-snapshot forms) so far. `intake_file`'s own
  duplicate-detection path and true hot-swap don't check hashes yet.
- HUD visual translucency — scoped to visual-only, not yet implemented.
- 3 redundant PS7 buttons in the dashboard UI — not yet consolidated.
- cloud-init seed `debian-seed/user-data` does not survive VM reboots —
  credentials/fstab/swap/service all need baking in (see NEXT STEPS #1).

## KEY FILES

| File | Purpose |
|------|---------|
| `CLAUDE.md` (repo root) | Full architecture reference + session log — read this first |
| `sector2/package-handler/intake.sh` | Intake pipeline — hex identity, hashing, QR, R2, D1, integrity gate |
| `sector2/package-handler/README.md` | Command reference + integrity verification docs |
| `sector3/workers/packages-worker/index.js` | Cloudflare Worker — D1 + R2 API |
| `scripts/usys.ps1` | Global command layer (PowerShell) |
| `dashboard/main.js` | Electron main process — D1/R2/Claude/Ollama wiring |
| `sector3/services/phoenix-helix-kernel.service` | Debian systemd service for paging brain |
| `tools/poc/debian-seed/user-data` | cloud-init seed — NEEDS UPDATE (see NEXT STEPS #1) |

## WHY THIS EXISTS
Life First app for Laurie. Local LLM, no vendor, no subscription, no lock-in.
Phoenix is the infrastructure. Every process, every import, every run is in service of that.
People with less money deserve to run the same tools as everyone else.
Every penny every time.
