# sector1 — Boot, kernel, auth, security

Written 2026-09-12; refreshed 2026-09-29 against the 2026-09-28 Round 2 audit (S1 + CONN).
Verify against current code before trusting a specific line number.

## What it is
Sector 1 of the 4-sector architecture (see repo root `CLAUDE.md`): boot/kernel, auth,
Helix (userspace and kernel), and the security (guardian/honeypot) layer. Contains several
genuinely distinct sub-projects, not duplicates of each other:
- `auth/phoenix_auth.py` — hardware-fingerprint auth (replaces Google auth). Standalone CLI; nothing in the repo imports it.
- `concierge/` — `concierge.c`, `bridge.py`, `linux_concierge.py` (Windows↔Linux bridge; `bridge.py` does the real chunking + BLAKE2b, `concierge.c`'s chunk code is unused).
- `helix/` — userspace Helix. **Canonical:** `helix_vram.py` (HelixMemoryManager, double strand, zlib-5), `helix_translator.py` (quadralingual translator on the real manager), `test_helix_vram.py` (11 tests). Older stages kept alongside: `helix_complete_package.py`, `helix_complete_stack.py` (toy zlib-6 stacks), `helix_stack_stress_test.py`, `helix_slim.py` (needs `pyzmq`), `helix_fuse.py` (needs `fusepy`), `kernel/` (`helix_kernel.c` userspace bench + `helix_baseline.c`), `run/helix_run`, `conf/helix_mesh.conf`.
- `helix-lightning/` — the **Ball permission system** project: `franken5.py` (Frank5 core conductor), `frank_ring.py`, `frank_spawn.py`, `main_kernel.py`, `process_library.py`, `helixi.py` (Helix-I stage intake, 7701-7704), `helixe.py` (Helix-E egress, 7800+, calls `sector3/translator/translator.sh`), `helix_suit_override.py`, `test_ball_permissions.py` (20 tests), `THEMOMENT.txt`. Distinct from `kernel/` below — not a duplicate.
- `kernel/` — the canonical boot loader: `main_kernel.py:boot()` (imports helix-lightning + arms CoPES), `llm_engine.py`, `phoenix_status_server.py`, `file_tree_service.py`, `setup.sh` (PyInstaller build). `phoenix_core.py` and `phoenix_kernel/core.py` are legacy remote-shell kernels **not** used by `boot()`.
- `kernels/` — the Linux kernel Helix: `helix_kmod.c` + `dm_helix.c` → `helix.ko` (with `/proc/helix`, dm-helix target), `frank3_slot_a.c`/`frank3_slot_b.c` slot modules, `helix.h` (ioctl ABI), `libhelix/` (`libhelix.c` → `libhelix.so`, `helix.py` ctypes binding), `helix_test.c`, `Makefile`, `README.md`, and scripts `helix_boot.sh`, `install_helix_boot.sh`, `dm_helix_test.sh`, `helix_freedrive.sh`, `helix_phoronix.sh`, `helix_verdict_lean.sh` (Compaq-specific). Built/benchmarked on pbm3/pbm-compaq (see `docs/helix/BENCHMARKS.md`).
- `security/` — the CoPES guardian/honeypot moving-target-defense system: `copes_runtime.py`, `guardian_rotator.py`, `guardian_base.py`, four guardians (`guardian_alpha/beta/gamma/delta.py`), `honeypot.py` (off the live path), `test_guardians.py` (20 tests), plus `harden_debian_box.sh` (sshd key-only + nftables hardening for the Debian servers).
- `grub/` — Phoenix GRUB USB boot controller + PAM key auth (`grub/grub.cfg`, `scripts/`), and a second, own-rooted USys-like registry (`usys.sh`, `phoenix_dev_db.sql`, `README_usys.md`). **Unconfirmed whether the usys part is live or legacy** — ask Jerry before assuming either. The GRUB stack is known-unbootable (audit S1-F01/F02/F25/F26).
- `saddle_block.sh` — fstab template for the physical `breach_coms1-4` drives.

## Dependencies
No package.json/requirements.txt here, but not dependency-free:
- Python 3 stdlib for most files; optional/required extras: `pyzmq` (`helix/helix_slim.py` exits without it), `fusepy` (`helix/helix_fuse.py`), `base58` (optional in `kernel/file_tree_service.py`, falls back to hex).
- Linux kernel headers + gcc/make for `kernels/` (`Makefile` builds `helix.ko`, `frank3_slot_a.ko`, `frank3_slot_b.ko`; `libhelix/` builds `libhelix.so`). No `install`/`depmod` target — `modprobe` needs the `.ko`s copied by hand.
- `grub/` scripts need grub-mkimage/grub-install, parted, sqlite3 (usys.sh), root.

## Commands / entry points
- `python -m security.test_guardians` (run from inside `sector1/`) — 20/20.
- `python helix-lightning/test_ball_permissions.py` — 20/20.
- `python helix/test_helix_vram.py` — 11/11; `python helix/helix_translator.py` — self-test; `python helix/helix_stack_stress_test.py` — stress test.
- `make` in `sector1/kernels/` — builds `helix.ko` + frank3 slot modules (Linux only).
- `sector1/kernel/main_kernel.py:boot()` — the actual boot entry point.
- `bash grub/scripts/build_phoenix_usb.sh /dev/sdX`, `build_now.sh /dev/sdX` (typed YES), `gen_key.sh`, `install_phoenix_grub.sh` — root, erase devices; QEMU-only until the audit items are fixed.

## Connects to / connected from
- `sector1/kernel/main_kernel.py` → `sector1/helix-lightning/franken5.py` (sys.path import of Frank5, ProcessLibrary, Spawn, HelixI, HelixE).
- `sector1/kernel/main_kernel.py` → `sector1/security/copes_runtime.py` (`boot()` arms the guardians — in that process only).
- `sector1/helix-lightning/helix_suit_override.py` → `sector1/helix/helix_complete_stack.py` (9 core suits point here; it has no `run()`/`main()`, so they execute nothing — audit S1-F28).
- `sector1/helix-lightning/helixe.py` → `sector3/translator/translator.sh` (fallback when the deployed `/etc/systemd/system/translator/translator.sh` is absent; `TRANSLATOR_SH` overrides).
- `sector1/helix/helix_translator.py` → `sector1/helix/helix_vram.py` (real HelixMemoryManager; `use_kernel=True` → `sector1/kernels/libhelix/helix.py`).
- `sector4/paging.py` → `sector1/kernels/libhelix/helix.py` (kernel Dandelion signal on pbm-compaq).
- `sector3/services/helix.service` → `sector1/kernels/helix_boot.sh`.
- `sector1/auth/phoenix_auth.py` → `sector1/security/copes_runtime.py` (`_guardian("auth_failure"/"auth_success")` — but from its own process, so the event lands `disarmed`; see Known issues).
- `scripts/usys.ps1` → `sector1/security/copes_runtime.py` (`Send-UsysGuardianEvent` `suite_unrecognized` via a fresh `python -c` job — also lands `disarmed`).
- `sector1/helix-lightning/*.py` are otherwise self-contained — no other sector imports them.

## Known issues (verified, not guessed)
- **CoPES guardians are not reachable in deployment** (audit S1-F23): `copes_runtime` state is process-local and both feeders dispatch from other processes → `{"status": "disarmed"}`. Needs a cross-process ingress; open for Jerry. Gamma/Delta additionally have no feeders at all (no file/net watcher, no vault-write hook).
- 9 of Frank's 16 core suits point at `helix/helix_complete_stack.py`, which isn't wearable (S1-F28); `process_library.py` registers three app suits whose files don't exist and only searches deploy paths (S1-F32).
- `kernel/llm_engine.py` / `phoenix_status_server.py` default `LIFEFIRST_API` to the retired PHP fossil; `main_kernel.py`, `file_tree_service.py`, `llm_engine.py` look for a `sector1/CoPES/src` that doesn't exist (S1-F36). `phoenix_status_server` `/node`, `/tree` crash with NameError (S1-F07).
- GRUB stack (`grub/`) must not be installed on any machine as-is: key check never validates (F01), no-key branch locks every entry (F02), the RAM-load feature can't work (F25), `install_phoenix_grub.sh` installs to the host's `/boot` (F26).
- `helix-lightning/` no longer holds the old dev-VM dotfile dump (gone; `ls -a` shows only tracked files + `__pycache__`).
- `sector1/grub/`'s relationship to the canonical `scripts/usys.ps1` is undocumented — flag for Jerry, don't assume it's dead code and don't assume it's load-bearing either.
