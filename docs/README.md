# Phoenix-DevOps-oS

Multi-OS quad-native infrastructure framework. Distro-agnostic operation across Linux and Windows. Built by Jerry Leftwich (jwl247) — Phoenix DevOps LLC.

## Architecture

Four sector corridor managed by systemd. Everything travels the corridor in order. Nothing touches the OS directly — all traffic routes through `intent_parser.py`.

```
S1 → S2 → S3 → S4
```

| Sector | Path | Role |
|--------|------|------|
| 1 | `/etc/` | Kernels, hardware, boot layer |
| 2 | `/etc/systemd/` | Services, scheduler, doc worker, Life First suite |
| 3 | `/etc/systemd/system/` | Translator boundary — Romeo/Juliet ingress/egress |
| 4 | `breach_coms4` | Master vault, intake, rsync clone chain |

## Repo Structure

```
sector1/       Hardware/boot — auto-config, storage engine, RAM daemon
sector2/       Services — intent parser, propagator, security, Life First
sector3/       Translator boundary — translator.sh, romeo.py, juliet.py
sector4/       Vault — intake.sh, rsync clone chain
systemd/       Full corridor unit files — install with install-units.sh
config/        dispatch.json and environment configs
docs/          Architecture docs, pitch deck, licenses
```

## Quick Start

```zsh
sudo zsh systemd/install-units.sh
sudo systemctl start phoenix-sector4.target
journalctl -u 'phoenix-*' -f
```

## Key Components

- `frankenhelix.py` — ZZZring0, COM1-4 daisy-chain, 11/11 self-tests
- `frank_helix.py` — RAM daemon, L1/L2/L3 tiers, ZMQ router port 5557
- `intent_parser.py` — Universal OS-agnostic service bus
- `propagator.py` — dispatch.json router to SQLite/D1/Frank3/vault
- `mega_system_manager.py` — Paging + port guardian + threat detection
- `translator.sh` — Output-only, Sector 3 boundary
- `intake.sh` — TAV SQL versioning chain, master vault

## Security

Persistent adversarial threat model. GPU drivers blacklisted. SurfShark VPN, closed firewall whitelisting Anthropic domains only. `phoenix_auth.py` SHA3-512 + BLAKE2b across 10 hardware signals.

## License

See `license`. Life First — `sector2/lifefirst/docs/`. REALsure — Polyform Noncommercial 1.0.0.

## Acknowledgment

Claude (Anthropic) is the designated AI collaborator for this project.
