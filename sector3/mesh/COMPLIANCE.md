# Phoenix Mesh — compliance notes

Phoenix Mesh (Nebula, our own CA) replaced Tailscale and WireGuard on 2026-10-05. Below: what each
part does for the frameworks in `docs/compliance/` and how we checked it. When a box or a rule
changes, update this note.

| Control area | NIST SP 800-171 r2 | SOC 2 (TSC) | FAR 52.204-21 | How the mesh meets it | Evidence (2026-10-05) |
|---|---|---|---|---|---|
| Device identity | 3.5.1, 3.5.2 | CC6.1 | (b)(1)(v), (vi) | Every machine holds a certificate signed by our CA, naming its mesh IP and groups. No cert means no packets | `nebula-cert print` on each host cert; the handshake log shows `certName=pbmiii issuer=…` |
| Access by role | 3.1.1, 3.1.2, 3.1.5 | CC6.1, CC6.3 | (b)(1)(i), (ii) | Nebula's firewall drops by default and allows by group: servers accept from `jerry` and `servers`; RDP only from `jerry` | `firewall:` in each generated `config.yml` (inbound_action: drop) |
| Boundary protection | 3.13.1, 3.13.5 | CC6.6 | (b)(1)(x), (xi) | Nothing is exposed except Nebula's UDP port on the lighthouse; SSH and RDP live inside the mesh only. SSH on pbmIII is keys-only, no root login | `sshd -T` → passwordauthentication no, permitrootlogin no |
| Encryption in transit | 3.13.8, 3.13.11 | CC6.7 | — | All mesh traffic is Noise-protocol encrypted (Curve25519, AES-GCM) | Nebula default cipher; `boringcrypto=false` logged |
| Key management | 3.13.10 | CC6.1 | — | The CA key lives only in the vault (encrypted when pushed). Host certs last 1 year and are renewed by `phoenix_net.py renew`; the heal check warns 30 days ahead | `cert_days_left` = 364 days for all hosts |
| Baseline configuration | 3.4.1, 3.4.2 | CC8.1 | — | Configs come from `hosts.json` (git), never hand-edited. Each box stores a known-good copy and a version stamp (`git:<sha> config:<sha256>`) | `/etc/nebula/VERSION`, `C:\ProgramData\Nebula\VERSION` |
| Config change control / drift | 3.4.3 | CC8.1, CC7.1 | — | The heal check (every 5 minutes) restores the known-good config on drift and logs it | Tested: rogue edit restored on pbmIII and this PC |
| Availability / self-healing | — | A1.2, CC7.4 | — | systemd `Restart=always` + heal timer (Linux); service recovery actions + heal task (Windows) | Tested: service killed, restarted by heal on both |
| Audit trail | 3.3.1, 3.3.2 | CC7.2 | — | Every repair is logged: journal tag `phoenix-mesh-heal` (Linux), Application log source "Phoenix Mesh" (Windows) | Entries present for both tests above |
| Software provenance | 3.14.1 | CC7.1 | (b)(1)(xii) | Nebula comes from the official release, checksum-verified, then intaked into the clone pool. Boxes install from the pool, never the internet | SHASUM256 OK; clone pool v1 sidecars hash-match |
| Patching | 3.14.1 | CC7.1 | (b)(1)(xii) | Debian boxes run unattended security upgrades | `unattended-upgrades` enabled on pbmIII |

Open items:
- The vault's cloud copy predates the CA and host certs, so it needs a re-push (`phoenix_vault.py push`, JW's passphrase).
- The lighthouse is not yet on the home router: it needs a public address (port forward UDP 4242) for remote access.
- pbmIII's root password is still the install default. It gets a long random one, stored in the vault.

## Buddy healing (phoenix_buddy.py + peer_agent.sh, buddy-1.0.0 / peer-agent-1.0.0, 2026-10-06)
| Control | How |
|---|---|
| AC-6 least privilege | Peer key per box; `restrict`, `from=` mesh+home LAN, forced command = the agent; sudoers allows ONLY the agent. Verbs: status / heal / export mesh / restore mesh. Shell attempts refused (tested). |
| SI-7 integrity | Mesh configs signed at render (`ssh-keygen -Y`, key in vault only). Restore installs only if hash = requested version AND signature valid AND `nebula -test` passes. Tampered config refused (tested: "signature invalid", "hash mismatch"). |
| CP-10 recovery | Buddies keep the last 10 signed mesh versions of each peer; a box that lost its own known-good gets it back (tested: config + known-good corrupted on pbmIII, PBMII restored over LAN). |
| AU-2/AU-3 audit | Every agent call logged with caller address (journalctl -t phoenix-peer-agent); every buddy action logged (journalctl -t phoenix-buddy; PBMII F:\Phoenix\mesh\buddy.log). Logs on state change only. |
| SC-7 boundary | Mesh firewall: only tcp/22 added between groups servers <-> lighthouse for the agent. |
