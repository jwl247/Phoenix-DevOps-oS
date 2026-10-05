# Phoenix server baseline (`phoenix-harden.sh`): compliance notes

The baseline for every Debian box: pbmIII (applied 2026-10-05, harden-1.0.1), then the AWS lighthouse and the
Compaq. It is versioned (`/etc/phoenix/harden.VERSION`), self-healing (a `phoenix-harden-heal.timer` runs every 15
minutes and restores drift from known-good copies), and audited (journal tag `phoenix-harden`, plus auditd).

| Control | NIST SP 800-171 r2 | SOC 2 | FAR 52.204-21 | How | Evidence (pbmIII, 2026-10-05) |
|---|---|---|---|---|---|
| Boundary / least-functionality firewall | 3.13.1, 3.13.6 | CC6.6 | (b)(1)(x) | nftables default **drop**. Only these are allowed: loopback, established, ICMP essentials, DHCP, Nebula UDP 4242, the mesh interface (Nebula's group firewall decides there), and SSH only from the home LAN as break-glass | Applied with a 120 s auto-rollback, then confirmed. Mesh SSH, LAN SSH, internet and mesh↔AWS all verified before confirming |
| Remote access | 3.1.12, 3.1.13 | CC6.1 | (b)(1)(i) | SSH keys only, no root login, MaxAuthTries 3, 30 s grace, no X11/agent forwarding. Admin over the encrypted mesh | `phoenix-harden check` → clean |
| Least functionality | 3.4.6, 3.4.7 | CC6.8 | — | cups, cups-browsed, bluetooth, avahi-daemon and ModemManager disabled and masked on servers | All inactive |
| Kernel / network hardening | 3.13.x, 3.4.2 | CC6.8 | — | rp_filter, no redirects or source routing, syncookies, kptr/dmesg restrict, no unprivileged BPF, ptrace scope, protected links | Each sysctl value checked live by `drift()` |
| Audit logging | 3.3.1, 3.3.2 | CC7.2 | — | auditd watches identity files, sudoers, sshd config, `/etc/nebula`, the firewall, `/etc/phoenix` and logins. Heal actions logged | auditd active; journal entries for each heal |
| Configuration baseline + change control | 3.4.1, 3.4.2, 3.4.3 | CC8.1 | — | Known-good copies of every managed file. Drift is detected and restored every 15 min, with versioned records | Drift test: SSH passwords turned back on → detected → healed → clean |
| Flaw remediation | 3.14.1 | CC7.1 | (b)(1)(xii) | Unattended security upgrades | Enabled |

Open:
- Root password: replace the install default with a random one stored in the vault.
- Interactive SSH via a Windows Hello passkey (ecdsa-sk). Automation keeps a separate key, which should also be restricted to mesh source addresses.
- Apply the same baseline to the AWS lighthouse (with no LAN break-glass; the cloud firewall plus the mesh cover it) and to the Compaq.
- Lesson recorded: `cmd | grep -q` under `set -o pipefail` gives false alarms (SIGPIPE). Capture output first.
