# Sector 1 — Kernels / Hardware / Boot Layer

> **⚠️ Design-intent doc, not verified current — see `docs/README.md`'s status banner.** For
> what's actually live in Sector 1 today, use `sector1/CONNECTIONS.md` (dated, verified against
> real code) and root `CLAUDE.md`.

Path: `/etc/`

First sector in the corridor. In this design `auto_config_installer.py` fired on first boot and generated configs for downstream services — that file is not in this repo today (neither the live tree nor `archive/`).

## Files — where they actually are (verified 2026-09-28)

| File named in this design | Today |
|------|------|
| `auto_config_installer.py`, `doublehelix2storage.py`, `ai_paging_linux.py` | not in this repo (neither the live tree nor `archive/`); the live paging daemon is `sector4/paging.py` |
| `frankenhelix.py` | `sector2/ring0/frankenhelix.py` |
| `frank_helix.py` | `sector2/frank/frank_helix.py` |
| `phoenix_auth.py` | `sector1/auth/phoenix_auth.py` (SHA3-512 + BLAKE2b hardware fingerprint) |

What Sector 1 actually contains today (`auth/`, `concierge/`, `helix/`, `helix-lightning/`, `kernel/`, `kernels/`, `security/`, `grub/`, `saddle_block.sh`) is inventoried in `sector1/CONNECTIONS.md`.



## Systemd Units

Unit files live in `sector3/services/` (not deployed on the build target — see `docs/README.md`'s banner):

```
phoenix-log-setup.service      does NOT exist (install-units.sh still tries to enable it — S34OPS-F03)
phoenix-auto-config.service    exists in sector3/services/
phoenix-frankenhelix.service   exists in sector3/services/
phoenix-frank-helix.service    exists in sector3/services/
```

## ZMQ Ports

- `5557` — ZMQ router / Frank sideload bridge
- `5558` — doc worker push socket
