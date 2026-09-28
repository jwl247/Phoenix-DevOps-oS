# Helix as a drive on the Precision (userspace VM, i7) — plan

> **STATUS (2026-09-28): shelved behind the Helix-team / game-gate work (Jerry's order of 2026-09-28). What it needs from the code already exists: `helix_boot.sh` HELIX_B_DEV / HELIX_B_MB=auto / HELIX_MOUNT=none and `install_helix_boot.sh HELIX_PROFILE=drive`. Still open: manifest-driven hostfwd/drives in usys.ps1, LIO unit, Windows iSCSI scripts. Note from the 9/28 exploration: `-snapshot` applies to every QEMU drive unless `-Persist`, and slirp caps iSCSI throughput at ~100–300 MB/s.**
> **STATUS (Jerry, 2026-09-27): KEEP THIS PLAN FOR LATER.** Next instead: "put Helix in front as a memory manager and see how it goes" (scope to be confirmed with Jerry). Immediate small task: format the wrong-package external drive G: ("SSD 3.0", vendor replacing it), NTFS, empty drive. Save this plan to `docs/plans/helix-drive-plan.md` when out of plan mode.

## Context
Jerry (2026-09-27): "put Helix in front of a drive, basically making her the drive — no coded paths or channels — using the i7", "via Debian import", "point her at it, both strands in her control, we can always change it later". Speed is the standing goal (the game is coming).

Measured today:
- **Drives:** only C: (WD NVMe, 0.14 ms random read) is an SSD. D:, E: and F: are 5400 rpm USB HDDs (5–9 ms, SMART-confirmed). F: is exFAT.
- **The new "SSD 3.0" (G:)** is almost certainly counterfeit: ITE `048D:1234` placeholder ID, 25 MB/s read, 7 MB/s write, basic USBSTOR driver. It can't be Strand B. Jerry to return it or capacity-test it.
- **Compaq verdict so far:** Helix gives 37x on repeated sequential reads (127 → 4,716 MB/s from RAM). Writes and cold random reads tie. dbench is -7% (write-through bookkeeping).

Design (the Compaq's proven shape, on the i7):
**slow big origin → Strand B on the internal NVMe → Strand A in RAM (8 GB)**, all block-level `dm-helix`, exported to Windows as one disk.

## Architecture
```
Windows apps → H: (NTFS "HELIX") → Microsoft iSCSI initiator → 127.0.0.1:3260
   → QEMU (WHPX, i7, 4 vCPU, ~10 GB) Debian 13 VM → LIO iSCSI target (block)
   → /dev/mapper/helix  (dm-helix: Strand A = RAM, auto; Strand B = NVMe image, auto; Dandelion)
   → origin: /dev/vdb = the drive she's pointed at
```
Point her at the drive; nothing else is hardcoded:
- **The one setting:** `HELIX_ORIGIN` = whatever disk the VM is given as the origin. v1 is a large raw image on D: (no drive handover, nothing at risk). Later it's a whole physical drive (e.g. the 20 TB) passed to the VM, with the same setting.
- **Her two strands:** `HELIX_RAM=auto` and Strand B `auto`, sized by her from what she's given. Strand B = a raw image file on C: (NVMe) handed to the VM as a second virtio disk.
- **VM description:** lives in the suite manifest (the Phoenix way). `usys.ps1` gains manifest-driven `hostfwd` and extra `drives` instead of the hardcoded ssh-only forward at `scripts/usys.ps1:1566`.

## Steps
0. **Security first:** scrub the old plaintext Windows password from the deployed `F:\Phoenix\clonepool\debian\seed\user-data`. The repo copy was cleaned 9/25; this copy is still served to every VM boot. The password is already rotated, but the copy must go anyway.
1. **Prereqs on Windows (need Jerry at the desk):**
   - enable the *Windows Hypervisor Platform* feature (admin prompt + one reboot; BIOS VT-x is already on);
   - install QEMU (winget);
   - set the MSiSCSI service to Automatic.
2. **Debian import:** Debian 13 genericcloud qcow2 → intake into the clone pool (Frank's import method) → a new suite `helix-drive` with its own `.suite.json` (RAM, vCPUs, disks, hostfwd 2222→22 and 3260→3260, WHPX). The old Debian 12 suite stays untouched. Switch the image to the standard `linux-image-amd64` kernel, which has the LIO target and dm modules the cloud kernel may lack.
3. **usys.ps1:** read `hostfwd` and `drives` from the manifest (keep today's ssh forward as the default). Suites without the keys behave exactly as now. Add tests to `scripts/usys-suite-gate.Tests.ps1`-style Pester tests.
4. **Helix in the VM:** `git archive` the repo to `/opt/phoenix` (same as the Compaq/pbm3), then run `install_helix_boot.sh`. `/etc/default/helix` holds only `HELIX_ORIGIN=/dev/vdb`, `HELIX_RAM=auto`, Strand B = `/dev/vdc` (block device, auto size; small `helix_boot.sh` change so Strand B can be a device, not only a loop image), and no mount (Windows owns the filesystem). Build `helix.ko` against the VM kernel. `dm_helix.c` was proven on 6.12 and Debian 13 ships 6.12, which is why the VM is Debian 13.
5. **Export:** `targetcli` makes a block backstore `/dev/mapper/helix`, one LUN, an ACL for the Windows initiator IQN, and CHAP. Put it in a systemd unit ordered after `helix.service`.
6. **Windows side:** `New-IscsiTargetPortal 127.0.0.1`, `Connect-IscsiTarget -IsPersistent`, initialize GPT, NTFS, label `HELIX`, letter H:. Written as a script `tools/helix-drive/connect.ps1`, idempotent.
7. **Startup and shutdown:**
   - a logon task `PhoenixHelixDrive` boots the VM headless, waits for 3260, and connects iSCSI;
   - a stop script disconnects iSCSI (flushes NTFS) before stopping the VM;
   - the Console gets a "Helix drive" service line, and `hands` gets a status tool.
8. **Docs + intake:** `docs/helix/HELIX_DRIVE.md`, CONNECTIONS, BENCHMARKS, session log. Intake every file.

## Safety
- **Nothing on D:, E: or F: is repartitioned or taken offline in v1.** The origin is an image *file* on D:, and Strand B is an image *file* on C:.
- dm-helix is write-through: a write reaches the origin before it's acknowledged. Killing the VM loses cache, never data. NTFS on H: recovers from its journal.
- No udev, modprobe, blacklist or readonly changes on the host (AI Safety Rules). The breach_coms drives are untouched.
- If the VM is down, H: is offline. Only data we put on H: is affected.

## Verification
- **Speed:** the same random/sequential latency tests used today (cache bypassed) on H: vs D: (raw HDD) vs C:.
  - Cold first pass.
  - Warm repeat (expect RAM-speed reads).
  - A working set bigger than 8 GB (Strand B from NVMe).
  - Record in `docs/helix/BENCHMARKS.md`.
- **Integrity:**
  1. Copy a 20 GB mixed set to H: and hash it.
  2. Hard-kill the VM mid-write, restart, reconnect.
  3. Hash again: nothing already acknowledged may be lost.
- **Reboot:** H: comes back by itself at logon.
- **Tests:**
  - Pester tests for the manifest-driven hostfwd/drives;
  - `helix_test` + `dm_helix_test.sh` inside the VM;
  - the kernel log is clean.

## Needs Jerry
- At the desk for step 1: enable the Hypervisor Platform (admin prompt + reboot) and approve the QEMU install.
- Origin v1 size on D: (default 500 GB of its 1,413 GB free).
- The counterfeit G: drive: return it, or capacity-test it (H2testw) first.
