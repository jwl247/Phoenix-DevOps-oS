# sector1/kernels — Helix in the Linux kernel

Pure-C kernel code for Helix, plus the userspace library her companions use
to talk to it. Linux only. Developed and load-tested on **pbm3** (Debian 13,
kernel 6.12, legacy BIOS). pbm3 is disposable test hardware: never load these
modules on a machine you can't afford to reboot.

## What's here

| File | Builds | What it is |
|---|---|---|
| `helix_kmod.c` + `dm_helix.c` | `helix.ko` | Helix core. `/dev/helix_intent` (plus the original name `/dev/helix_bridge`), `/proc/helix`, the Frank sideload registry, and **dm-helix**, an in-kernel block cache (device-mapper target `helix`). |
| `frank3_slot_a.c`, `frank3_slot_b.c` | `frank3_slot_{a,b}.ko` | Frank's kernel slots. They sideload into `helix.ko`, keep a 30 s heartbeat, and post pressure-band intents (60/75/88 %). |
| `helix.h` | — | The one ABI header, shared by kernel, `helix_test.c` and `libhelix`, so they can't drift apart. |
| `libhelix/libhelix.c`, `libhelix/helix.py` | `libhelix.so` | Userspace bridge library + Python binding: Jerry's original library, merged with the AgnosticLayer version. |
| `helix_test.c` | `helix_test` | Userspace test of every ioctl. |
| `dm_helix_test.sh` | — | dm-helix correctness + speed suite, run against a disk-image file only. |

## Build and run

A full kernel build took ~14 hours on this class of machine. This is an
out-of-tree module build against the running kernel's headers, and takes seconds.

```bash
sudo apt install linux-headers-$(uname -r) fio        # once
make                  # helix.ko + both Frank slots
make load             # modprobe dm_mod, insmod helix, sideload slots, show /proc/helix
make test             # userspace ioctl suite (root)
./dm_helix_test.sh    # dm-helix integrity + speed on ~/helixdm/origin.img
make unload
cd libhelix && cc -O2 -Wall -Wextra -fPIC -shared -o libhelix.so libhelix.c
```

Judge a build by `make`'s exit code plus a count of warning/error lines, never
by filtering output. Filtered output hid a real compile error on 2026-09-25,
and a stale, broken `.ko` got loaded.

## ioctl ABI (magic `'H'`)

Numbers 1–4 are Jerry's original libhelix ABI (`SECTOR4/heix/libhelix.c`) and
must not change. New calls take 5 and up.

| nr | Name | Payload |
|---|---|---|
| 1 | `REGISTER` | `char app_name[64]`. Registry capped at 256 apps, de-duplicated. |
| 2 | `DECLARE_HOT` | `char data_types[256]` |
| 3 | `DECLARE_COLD` | `char data_types[256]` |
| 4 | `MEM_SYNC` | `{u64 ptr; u64 size; s32 target_tier; u32 pad}` (24 bytes). Ledger only: `ptr` is never dereferenced. |
| 5 | `GET_STATS` | `struct helix_stats` (read) |

`read()` on the device pops one queued **intent** line: slot loads, pressure
bands, hot/cold declarations, mem_sync events, dm-helix up/down.

## dm-helix

> **Status: single-strand Helix, Dandelion restored (2026-09-25).** Every Helix
> has the Dandelion at her center. The double differs only by Strand B and the
> rungs (next). Design source: vault `OG_double_helix_complete.py` and CoPES
> `src/helix.py`. Her center had been coded out of every later copy.
>
> Dandelion: 64 lanes; OG heat (+load x 0.1, -0.05); compression factor
> max(0.3, 1 - load x 0.7), relaxing +0.1 per tick; states cold/hot/surging/cooling.
> She cools herself with data (freeing 5% of what she holds = -0.05 heat).
> Block temperatures FROZEN..BLAZING + next-access prediction; relief compresses
> cold blocks with zlib 5 and inflates them on read.
>
> Verified on pbm3: `HELIX_TEST_ONLY=8 ./dm_helix_test.sh` shows heat 0 -> 1.0
> (surging) under load, 1,450 blocks zlib-5 compressed, 3.5 MB cooled, back to
> cold at idle, 1,384 compressed-block reads inflated, 193 MB read back
> byte-identical, zfail 0. Full suite steps 1-7: 0 failures, warm hits 177,699
> IOPS / 4.9 us (vs 194,694 headless: the cost of her bookkeeping).
> Tuning open: relief ~50 blocks/s on this CPU; data cooling is weak under
> sustained load until Strand B.

```bash
LOOP=$(sudo losetup --direct-io=on --show -f disk.img)
sudo dmsetup create helix0 --table "0 $(sudo blockdev --getsz $LOOP) helix $LOOP 256"   # 256 MiB RAM
sudo dmsetup status helix0      # hits misses inserts evictions invalidations bypass cached_blocks
```

- 4 KiB blocks, LRU. Write-through: cached copies are dropped when a write is
  issued and again when it completes.
- A write-generation counter stops a read that raced a write from caching
  pre-write bytes.
- The cache is only ever a copy. Removing the target loses nothing.
- Not yet built: the compressed tier (zlib, Helix's format, level 5 per
  CLAUDE.md), the SSD tier, and write-back.

## Verified on pbm3 (2026-09-25)

- Userspace suite: all checks pass. Covers every ioctl, bad input, the app cap
  and the alias device.
- Sideload rules hold: a slot is refused without `helix.ko`, and `helix.ko`
  can't be unloaded while a slot is loaded.
- 3+ load/unload cycles; no oops, lockups or warnings in dmesg.
- dm-helix integrity:
  - randomized write/verify, then re-verify from cache
  - overwrite-no-stale and 4-job concurrent verify
  - whole-device sha256 equal to the raw device
  - ext4 checksums stable across remount; e2fsck clean
- dm-helix speed (4k random reads, direct I/O, 200 MiB region, pbm3's 2010
  Athlon II X2 + spinning disk): raw disk 535 IOPS / 1,858 us; Helix fully warm
  **194,694 IOPS / 4.4 us** (~364x). Half-warm runs show no measurable
  overhead on misses. `dm_helix_test.sh`: 0 failures.

## Safety

These modules run inside the kernel: a bug can hang the machine. Only load
them on test hardware. Test dm-helix on image files, never on a disk holding
data you need. Don't touch `/etc/udev` or `/etc/modprobe.d` (CLAUDE.md AI
SAFETY RULES); the devices stay root-only (0600) until Jerry decides otherwise.
