# Phoenix Security — file motion sensor

A motion camera on every directory of every mesh machine. It notices when anything changes,
records it in a tamper-evident log, flags the changes that matter, and tells you in plain English.

| Machine | Watches | Runs | Files (2026-10-06) | Full sweep |
|---|---|---|---|---|
| pbmIII | `/` (every disk mounted) | systemd timer, every 5 min, as root | 205,427 | 5.5 s |
| awslh | `/` | systemd timer, every 5 min, as root | 31,357 | 0.5 s |
| PBMII | every fixed drive (C:, D:, E:, F:) | scheduled task "Phoenix Security Scan", every 5 min | see below | see below |

## How it works
1. **Sweep:** metadata only (size, modified time, permissions, owner). Cheap enough for the whole disk.
2. **Motion:** compared with the last sweep → `added`, `removed`, `modified`, `permissions_changed`.
3. **Fingerprint:** only what moved gets a SHA3-512 hash (files over 256 MB: metadata only).
4. **Log:** every motion is appended to `motion.jsonl`. Each record carries the SHA3-512 of the
   record before it, so editing or deleting a line breaks the chain, and `verify` names the line.
5. **Alerts:** any permission/owner change anywhere, and any change at all under an alert path
   (ssh, sudoers, passwd/shadow, nebula, systemd units, cron, /boot, the vault, startup folders, the
   Genie closet, Jarvis's gate).
6. **Outbox:** at 5,000 records the log rolls into `outbox/motion-<time>.jsonl` (chain continues
   across segments), ready to go into Phoenix through intake.
7. **Summary:** local Ollama turns recent motion into five plain bullets. If Ollama isn't there, you
   get the raw alert list and it says so.

Left out on purpose: places that change every second by design (kernel pseudo-files, logs, caches,
temp, swap, Ollama model blobs). They're listed in each machine's `config.json` under `exclude`.

## Use it
| Where | Command |
|---|---|
| pbmIII / awslh (SSH) | `sudo phoenix-security status` · `scan` · `alerts 20` · `events 20` · `summary` · `verify` |
| PBMII (PS7) | `python $HOME\.phoenix\security\bin\security.py status` (same verbs) |
| PBMII Genie | `genie send security '{"action": "alerts"}'` (actions: status, scan, events, alerts, summary, verify) |

Exit codes for scripts: `scan` returns 3 when it raised alerts; `verify` returns 4 when the chain is broken.

## Files
| File | What |
|---|---|
| `suits/security.py` | the sensor: Genie suit and CLI in one file, standard-library Python only |
| `install-security.sh` | Linux: `/opt/phoenix-security`, `/usr/local/bin/phoenix-security`, timer, state in `/var/lib/phoenix-security` (0700) |
| `install-security.ps1` | Windows: `~\.phoenix\security`, scheduled task (pythonw, no window), baseline |

Change what's watched: edit `config.json` in the state folder (`watch`, `alert`, `exclude`, `cap`).

## Where it came from
Built 2026-10-06 from the design sketches in `metsec files/` (written in an earlier Claude session,
2026-10-04). Audit of each:

| Sketch | State found | What became of it |
|---|---|---|
| `sec` (= `motiondet cam`) | JavaScript outline; file counts, permissions and sizes were simulated (`Math.random`), hashing and backup were TODOs | Built for real here: sweep, motion types, permission check on every change, isolated hashing, snapshot cap → outbox |
| `sec2` | Outline of an AI analysis layer; the Ollama and Vosk calls were commented out | The useful part, Ollama reading recent motion and summarizing it for the owner, is `summary`. Audio analysis not built |
| `sec3` | Outline depending on two modules that never existed (`buffer-system`, `lockdown-module`) | Not carried over. Phoenix's response stays on our own machines: record, alert, block |
| `grounds-keeper (2).zip` | A Claude Platform agent definition | Not used (Jerry, 2026-10-06) |

## Compliance touch
NIST SP 800-53 SI-7 (integrity monitoring), AU-9/AU-10 (tamper-evident audit log), CM-3 (change
detection); SOC 2 CC7.2 (monitoring for anomalies).
