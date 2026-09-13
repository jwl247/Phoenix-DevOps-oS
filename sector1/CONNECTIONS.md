# sector1 — Boot, kernel, auth, security

Written 2026-09-12. Verify against current code before trusting a specific line number.

## What it is
Sector 1 of the 4-sector architecture (see repo root `CLAUDE.md`): boot/kernel, auth,
and the security (guardian/honeypot) layer. Contains several genuinely distinct
sub-projects, not duplicates of each other:
- `auth/phoenix_auth.py` — hardware-fingerprint auth (replaces Google auth).
- `concierge/` — `concierge.c`, `bridge.py`, `linux_concierge.py`.
- `helix/` — a Python Helix stack variant (`helix_complete_package.py`, `helix_slim.py`, etc).
- `helix-lightning/` — the **Ball permission system** project: `franken5.py` (Frank5 core
  conductor), `frank_ring.py`, `frank_spawn.py`, `main_kernel.py`, `process_library.py`,
  `test_ball_permissions.py`. Distinct from `kernel/` below — not a duplicate.
- `kernel/` — the canonical boot loader: `main_kernel.py:boot()`, `llm_engine.py`,
  `phoenix_core.py`, `phoenix_status_server.py`, `file_tree_service.py`.
- `kernels/` — C kernel slots: `frank3_slot_a.c`, `frank3_slot_b.c`, `Makefile`.
- `security/` — the CoPES guardian/honeypot moving-target-defense system.
- `grub/` — a second, own-rooted USys-like implementation (`usys.sh`, `phoenix_dev_db.sql`,
  `README_usys.md`). **Unconfirmed whether this is live or legacy** — ask Jerry before
  assuming either.
- `saddle_block.sh` — fstab template for the physical `breach_coms1-4` drives.

## Dependencies
No package.json/requirements.txt here — pure Python 3 + C. `sector1/kernels/Makefile`
builds the C kernel slots.

## Commands / entry points
- `python -m security.test_guardians` (run from inside `sector1/`) — 20/20 passing per
  CLAUDE.md, tests the guardian/honeypot system.
- `make` in `sector1/kernels/` — builds frank3 kernel slots.
- `sector1/kernel/main_kernel.py:boot()` — the actual boot entry point, called by higher
  layers (not run standalone in normal operation).

## Connects to / connected from
- `sector1/kernel/main_kernel.py:boot()` → `sector1/security/copes_runtime.boot(...)`
  (arms the guardians).
- `sector1/auth/phoenix_auth.py:authenticate()` → `sector1/security/`'s
  `_guardian("auth_failure"/"auth_success", ...)`.
- `sector1/helix-lightning/*.py` files reference `sector1` in their own path-setup comments
  (relative `sys.path` insertion) — self-contained, not called from other sectors directly
  as of this writing.

## Known issues (verified, not guessed)
- `sector1/helix-lightning/` contains an accidental dev-VM dotfile dump (`.bash_history`,
  `.bashrc`, `.gitconfig`, `.ssh/`, etc.) — known since 2026-08-21, deliberately left
  untracked rather than deleted (per CLAUDE.md session log). Don't "clean" this without
  checking it's not load-bearing.
- `sector1/security/` guardians Gamma and Delta have no live feeders yet (need a file/net
  watcher and a vault-write hook) — the wiring exists, the triggers don't.
- `sector1/grub/`'s relationship to the canonical `scripts/usys.ps1` is undocumented —
  flag for Jerry, don't assume it's dead code and don't assume it's load-bearing either.
