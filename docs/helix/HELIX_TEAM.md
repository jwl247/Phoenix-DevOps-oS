# The Helix team — what runs with her, and how it is kept running

Written 2026-09-28 (Jerry: "helix should have files in her presence when she is
in operation"). Verify against the code; every claim here has a check in
`tools/helix-team/verify-team.sh`.

## Members

| Member | Code | Runs as | Talks to |
|---|---|---|---|
| **Helix** (kernel, the Dandelion, temperature tiers, double strand) | `sector1/kernels/dm_helix.c`, `helix_kmod.c`, Frank3 slots, `libhelix/` | `helix.service` → `helix_boot.sh` (settings `/etc/default/helix`) | origin disk, Strand B, `/dev/helix_intent`, `/proc/helix` |
| **Paging manager** | `sector4/paging.py` | `phoenix-paging.service` | her kernel counters through libhelix (`PHOENIX_PAGING_HELIX=kernel`); dashboard on 127.0.0.1:8888 only |
| **Memory manager / VRAM** (userspace double Helix, same rules as the kernel) | `sector1/helix/helix_vram.py` hosted by `sector1/helix/helix_vramd.py` | `helix-vram.service` (settings `/etc/default/helix-vram`) | `/run/phoenix/helix-vram.sock` (0660, group `phoenix`); linked to the kernel Dandelion through libhelix |
| **Translator, memory side** | `sector1/helix/helix_translator.py` (`HelixTranslator`) | a library: `HelixTranslator(helix_backend_from_daemon())` | the vram socket (`.memory` malloc/free/read/write, `.fs` read_file/write_file) |
| **Translator, boundary** | `sector3/translator/translator.sh` | no service; fires on OUTPUT only (rule 2) | called by Helix-E / Juliet at the sector-3 boundary |
| **Guardian** (ring guardian) | `sector4/guardian/integrated_guardian.py` | `helix-guardian.service` (state `/var/lib/phoenix/guardian`) | scans `sector3/services`, `/etc/systemd/system`, `/etc/default` for port/path conflicts; heartbeat every cycle |
| **Temperature tier eviction** | inside `dm_helix.c` and mirrored in `helix_vram.py` (BLAZING→FROZEN; raw → zlib-5 → Strand B) | part of Helix | reported in `/proc/helix` and the vram `stat` op |

## Install / deploy

From a checkout on the Precision (or any box that can ssh to the target):

```bash
tools/helix-team/deploy-compaq.sh pbm-compaq        # ships git HEAD to /opt/phoenix, installs, verifies, pulls the ledger back
```

What it runs on the box: `tools/helix-team/install-team.sh` → `sector1/kernels/install_helix_boot.sh`
(builds `helix.ko`, `libhelix.so`, writes `/etc/default/helix` once) + the two new units. It never runs
`sector3/services/install-units.sh` (legacy units with dead paths; that script now skips any unit whose
program is not on the box). Nothing touches udev, modprobe.d, drives, or readonly state.

## Verify

```bash
sudo /opt/phoenix/tools/helix-team/verify-team.sh
```

16 checks, each written to `/opt/phoenix/verification/<date>/team-*.log` and `summary.json`; the deploy
script copies them into the repo's `verification/<date>/` prefixed with the host name. Checks: the four
services active; `dmsetup` shows the double strand (7-field table) and `/proc/helix` answers; modules
loaded; no Helix errors in dmesg; paging is fed by the kernel and its dashboard is on loopback only;
the vram socket is 0660, a client round-trip works and `kernel_linked` is true; the translator runs on
the daemon; the guardian heartbeat is younger than 15 minutes and it reports no unfriendly conflicts;
`translator.sh deps` runs.

## Settings

- `/etc/default/helix` — `HELIX_ORIGIN`, `HELIX_RAM`, `HELIX_B_IMG` or `HELIX_B_DEV` (+ `HELIX_B_MB=auto`), `HELIX_MOUNT` (`none` when she is exported as a block device). `HELIX_PROFILE=drive install_helix_boot.sh` writes the VM/iSCSI profile.
- `/etc/default/helix-vram` — tier sizes (defaults: her real config, 256/1024/3072 MiB + 8 GiB Strand B), Strand B directory, socket path.
- `/etc/default/helix-guardian` — optional overrides of `PHOENIX_GUARDIAN_SCAN_DIRS` / `PHOENIX_GUARDIAN_INTERVAL`.

## Using the memory manager from any local process

```python
import sys; sys.path.insert(0, "/opt/phoenix/sector1/helix")
from helix_vramd import HelixVramClient
with HelixVramClient() as c:          # /run/phoenix/helix-vram.sock, needs group phoenix
    c.alloc("session:42", {"who": "laurie"})
    c.read("session:42")
    c.stat()["dandelion"]             # heat, state, compression, kernel_linked
```

`python3 /opt/phoenix/sector1/helix/helix_vramd.py status` prints the same from the shell.

## Tests (run anywhere, no kernel needed)

```bash
HELIX_VRAM_NO_KERNEL=1 python3 sector1/helix/test_helix_vram.py     # the library, 11 tests
HELIX_VRAM_NO_KERNEL=1 python3 sector1/helix/test_helix_vramd.py    # the service + translator, 10 tests
python3 sector4/guardian/test_guardian.py                           # the guardian, 7 tests
```

All three are in `scripts/verify.sh`, so every push runs them.

## Not built (say so)

- The guardian's threat scoring / mesh voting code paths (`load_shared_intel`, `auto_block_list`) are
  carried over from the ring version but nothing feeds them yet; today the guardian's real job is the
  conflict scan and the heartbeat.
- The paging manager and the vram daemon each link to the kernel; they do not yet talk to each other.
