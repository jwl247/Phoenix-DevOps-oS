# Keyboard + mouse across the boxes (KVM over the mesh)

Set up 2026-10-07 (Jerry: "I need my keyboard and mouse to work on all three computers"). One keyboard
and mouse on **PBMII** drive the **Compaq (pbmIII)** and, when it's on, the **HP (pbm3)**.

| Box | Role | Software | Where |
|---|---|---|---|
| PBMII (Windows) | server | Deskflow 1.27.0 portable (GPL; zip sha256 `8d19004c…`, matches the GitHub digest). Update check off. | `%LOCALAPPDATA%\Phoenix\deskflow\…\deskflow.exe`, started at logon (Startup shortcut "Phoenix KVM (Deskflow)"). Saved copy: `E:\Phoenix\imports\deskflow\` |
| pbmIII (Debian 12) | client, right of PBMII | `barrier` 2.4.0 (Debian archive), Barrier protocol | `~/.config/autostart/phoenix-kvm.desktop` → `barrierc --enable-crypto --name pbmiii --restart 10.42.0.1:24800` |
| pbm3 (Debian 13) | client, left of PBMII | not yet: power it on, then Deskflow's trixie .deb (Wayland via libei) or barrier | — |

**Security (best practice, Jerry's call):**
- **Mesh only.** The server binds 10.42.0.1. The Windows firewall rule "Phoenix Deskflow (mesh only)" allows TCP 24800 from 10.42.0.0/16 only. Nebula allows 24800 only from the `servers` group (`sector3/mesh/phoenix_net.py`, so self-heal keeps it).
- **Mutual TLS.** The Compaq trusts PBMII's certificate (`~/.local/share/barrier/SSL/Fingerprints/TrustedServers.txt`, sha256 `7742e3db…`). PBMII trusts the Compaq's own certificate (`~/.local/share/barrier/SSL/Barrier.pem`, RSA 2048, 0600, sha256 `07:6E:AB:46…2E:49:73:50`), approved by Jerry in the Deskflow window. `checkPeerFingerprints` stays on.
- **The Compaq runs Xorg, not Wayland.** GNOME 43 can't share input under Wayland. Changed in `/etc/gdm3/daemon.conf` (`WaylandEnable=false`); backup at `daemon.conf.pre-xorg-20261007`.

**If it stops working:** on pbmIII, `journalctl --user -n 30 | grep barrier`. On PBMII, `Get-NetTCPConnection -LocalPort 24800`.
- `timed out` = mesh/firewall: check the Nebula inbound rule for 24800.
- `certificate required` = the Compaq's Barrier.pem is missing.
- `fingerprint does not match` = PBMII's Deskflow certificate changed: re-trust it on the Compaq.
