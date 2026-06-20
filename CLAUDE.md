# Phoenix DevOps OS — Claude Session Guide

## Paste at session start
Run `bash ~/phoenix-devops/status.sh` and paste output to establish system state.

## Architecture
- **WSL (UnitedSystemsAO)** — primary dev machine, `~/phoenix-devops`
- **phoenix-ext (192.168.1.133)** — secondary machine, SSH via `phoenix-lan`
- **WireGuard mesh** — WSL: `wg0-wsl`, ext: `wg0` (10.77.0.3), full mesh via `ssh phx`
- **Cloudflare D1 worker** — `https://packages-worker.phoenix-jwl.workers.dev`

## Submodules
| Submodule | Repo | Notes |
|---|---|---|
| `helix_lightning_kernel` | `git@github.com:jwl247/Helix_lightning_kernel.git` | Contains legacy `HLK/` and `Phoenix-DevOps-oS/` dirs — plain folders, not submodules |
| `lifefirst_modules` | `git@github.com:jwl247/lifefirst_modules.git` | Private repo — SSH only, frank/suits integration |
| `phoenix_universal_kernel` | `git@github.com:jwl247/Phoenix_Universal_Kernel.git` | SSH only |

## Resolved Issues
- **2026-06-20** — Ext submodules uninitialized; fixed GitHub SSH key on ext, fixed `lifefirst_modules` URL from HTTPS to SSH, cleared legacy gitlinks (`HLK`, `Phoenix-DevOps-oS`) from `helix_lightning_kernel` index

## Next Session Priorities
1. Speed baseline + update CLAUDE.md
2. Pre-warm llama3.1 on boot
3. Wire `Cpt_conductor` into `phoenix_boot.sh`
4. Deploy to phoenix-ext and test on breach_coms drives
