# Pipeline internals — raw notes for mapping later

Jerry (2026-10-06): "document everything you have, I want to map our pipeline later."
Facts below were verified by running them on 2026-10-06, not copied from older docs.

## Mesh (Phoenix Mesh = Nebula 1.11.2, 10.42.0.0/16, UDP 4242)
| Node | Mesh IP | Role | Self-heal (own timers) | Healed BY peers |
|---|---|---|---|---|
| pbmii (Windows, travels) | 10.42.0.1 | Jerry's PC | task "Phoenix Mesh Heal" | **nobody** (no peer agent on Windows) |
| pbmiii (Debian, HP i5-2400, 15 GB) | 10.42.0.10 | relay, home server, LAN 192.168.1.192 | mesh-heal 5 min, harden + shares 15 min | awslh, pbmii |
| awslh (AWS Lightsail) | 10.42.0.2 | only lighthouse + relay | mesh-heal 5 min, harden 15 min | pbmiii, pbmii |
| compaq | 10.42.0.11 (planned) | home server | — | **not on the mesh yet** |

Peer healing chain: `sector3/mesh/phoenix_buddy.py` (timer every 5 min on each box) →
SSH as `phoenix-peer` → forced command `peer_agent.sh` (verbs: status / heal / export mesh /
restore mesh <hash>). Restore requires hash + ssh-keygen signature + `nebula -test`. Logs:
Linux `journalctl -t phoenix-buddy` / `-t phoenix-peer-agent`; PBMII `F:\Phoenix\mesh\buddy.log`.
Proven 10/6 (d8a5f53): smbd stop, nebula stop, corrupted config, tampered config refused.

Break-glass: `sector3/mesh/pbmiii-recover.sh` at III's console (tested 10/6, 6/6 OK).

### Gaps to "global" (not built — Jerry's call)
1. PBMII is never healed by a peer (would need an inbound agent on the Windows PC).
2. One lighthouse (awslh). If it's down, existing tunnels hold but new ones can't form.
3. A dead VM/box can't be revived by a peer (only services); awslh revive needs the AWS API.
4. Compaq not joined.

## Hardening (`scripts/hardening/phoenix-harden.sh`, 1.0.3)
sshd drop-in, sysctl drop-in, auditd rules, nftables (table inet phoenix), services off.
Known-good copies in /etc/phoenix/*.known-good; `heal` restores from them.
Bug fixed 10/6: the sysctl drop-in was `90-`, and Debian's `/usr/lib/sysctl.d/99-protect-links.conf`
loaded after it (fs.protected_fifos=1), so the drift came back on every heal on pbmIII and awslh.
Now `zz-phoenix-harden.conf`.

## Shares (`scripts/shares/phoenix-shares.sh`, 1.1.0) — pbmIII → PBMII drive letters
SMB3, encryption + signing required, bound to the mesh IP only, user `a`.
| PBMII | Share | pbmIII path | Disk |
|---|---|---|---|
| P: | pbmIII | /srv/pbmiii (rw) | 238 GB SSD (OS) |
| O: | pbmIII-old | /mnt/pbmiii-old (ro) | 1 TB Seagate, previous install, UUID 9d35bab9 |
| H: | helix-egress | /mnt/helix-egress (rw) | 700 GB Toshiba, LABEL helix-egress |

## AI layer on the boxes
- PBMII: Ollama (llama3 in C:\Users\jwlef\.ollama\models; OLLAMA_MODELS env points at an empty
  E: folder → breaks on restart, see backlog). Genie kernel running, no restart-on-boot.
- pbmIII: `ollama` binary at /usr/local/bin, service inactive, no models checked.
- OpenJarvis: parked (see backlog).

## Intake snag
`scripts/hsf-intake.sh` can't answer intake.sh's "same name, moved — version it?" prompt (it reads
the TTY, not the pipe), so `sector3/mesh/pbmiii-recover.sh` is committed but NOT intaked.
