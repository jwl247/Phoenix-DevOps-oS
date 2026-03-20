# Sector 1 — Kernels / Hardware / Boot Layer

Path: `/etc/`

First sector in the corridor. `auto_config_installer.py` fires on first boot, profiles hardware, generates configs for all downstream services.

## Files

| File | Role |
|------|------|
| `auto_config_installer.py` | Bootstrap — detects OS, hardware, ports, systemd. Runs once via oneshot unit. |
| `frankenhelix.py` | ZZZring0 bidirectional listener. COM1-4 daisy-chain. Four Freewheeling instances watching breach_coms1-4. 11/11 self-tests. |
| `frank_helix.py` | RAM pressure daemon. L1/L2/L3 tiers at 60/75/88%. ZMQ router port 5557. Frank-to-Frank sideload bridge. |
| `doublehelix2storage.py` | Octahedron quad-engine storage. Vector/NoSQL/relational/time-series. DNA spiral layout. Feeds Frank3. |
| `ai_paging_linux.py` | RAM/swap daemon. Thermal protection 75/80C. LRU eviction. 64MB AI-mode pages. |
| `phoenix_auth.py` | SHA3-512 + BLAKE2b double hashing across 10 hardware signals. |

## Hardware Context

- ash CPU in PCIe slot
- 4-stage RAM
- SATA tap
- GPU drivers blacklisted
- Intel i915 display only

## Systemd Units

```
phoenix-log-setup.service      creates /var/log/phoenix
phoenix-auto-config.service    oneshot bootstrap, runs once
phoenix-frankenhelix.service   after auto-config
phoenix-frank-helix.service    after frankenhelix
```

## ZMQ Ports

- `5557` — ZMQ router / Frank sideload bridge
- `5558` — doc worker push socket
