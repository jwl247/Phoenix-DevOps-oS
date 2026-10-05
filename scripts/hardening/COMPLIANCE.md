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

## Shares (`scripts/shares/phoenix-shares.sh`): pbmIII, 2026-10-05, shares-1.0.1

| Control | NIST SP 800-171 r2 | SOC 2 | How | Evidence |
|---|---|---|---|---|
| Least privilege / access control | 3.1.1, 3.1.2, 3.1.5 | CC6.1, CC6.3 | One SMB user; Samba bound only to the mesh IP (`10.42.0.10:445`), `hosts allow 10.42.0.0/16`. Nebula only lets the `jerry` group reach servers | `ss -ltn` shows 10.42.0.10:445 + loopback only |
| Protect data in transit | 3.13.8 | CC6.7 | SMB3 with encryption **required** and mandatory signing, inside Nebula's encryption | `Get-SmbConnection` → 3.1.1, Encrypted True |
| Integrity of the old disk | 3.8.x, 3.4.6 | CC6.1 | The old install disk is mounted `ro,noexec,nosuid,nodev` and shared read-only | A write from `O:` is refused |
| Configuration + drift | 3.4.1–3.4.3 | CC8.1 | Known-good smb.conf, heal timer every 15 min. Drift includes "SMB exposed off-mesh" and "SMB not on the mesh" | `phoenix-shares check` → clean |
| Secrets handling | 3.13.10, 3.5.10 | CC6.1 | The SMB password is random and kept in the vault (`samba-pbmiii.env`). It reaches the box via a 0600 file, then shredded, never on argv. Stored on the PC in Windows Credential Manager | — |
| Audit | 3.3.1 | CC7.2 | auditd watches `/etc/samba/`; Samba auth audit at level 3 to the journal | — |
