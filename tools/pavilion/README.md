# tools/pavilion — lining out the Debian box

The Pavilion (i5, 16 GB, Debian 13.7 "trixie" Cinnamon) is the planned home for the
Debian VM workload, Helix/Frank, and a local LLM. These two scripts check the install,
bring up SSH, and set up key-based SSH in both directions with Windows.

## Order

1. **On the Pavilion** (local terminal, internet cable plugged into it):
   ```bash
   sudo bash pavilion-setup.sh
   ```
   It checks Debian 13 + network/DNS, fixes the live installer's leftover `cdrom:` apt
   source, repairs/upgrades packages, and reports disk, NTP, missing firmware and failed
   units. It then installs `openssh-server` with a hardened drop-in (checked by `sshd -t`
   before restart), adds a LAN-only `ufw` rule, and creates this box's key for SSH into
   Windows. At the end it prints the IP and host-key fingerprints.
2. **On Windows** (PS7; elevate it if you want `-AllowReverse`):
   ```powershell
   pwsh -File tools\pavilion\connect-from-windows.ps1 -HostName <ip> -User <debian-user> -AllowReverse
   ```
   Makes `~/.ssh/phoenix_pavilion_ed25519`, authorizes it on the Pavilion (asks for the
   password once), adds `Host pavilion`, and checks that key-only login works. `-AllowReverse` also turns on the Windows
   OpenSSH Server and authorizes the Pavilion's key (through `administrators_authorized_keys` with
   the required ACL). It also writes `Host <this-pc>` into the Pavilion's `~/.ssh/config`.
3. **Back on the Pavilion:** `sudo bash pavilion-setup.sh --harden` turns off password SSH.
   It won't run unless a key is already authorized, so it can't lock you out.

Both scripts are safe to re-run. Neither touches `/etc/udev/rules.d`, `/etc/modprobe.d`, or any
drive state (CLAUDE.md AI Safety Rules).

## Claude Code on the Pavilion

```bash
curl -fsSL https://claude.ai/install.sh | bash   # native installer → ~/.local/bin/claude
claude                                           # log in with the Claude.ai subscription
```
