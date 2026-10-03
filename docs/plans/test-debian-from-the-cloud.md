# THE TEST — "Debian from the cloud"

Jerry, 2026-10-03: "did the debian PoC go with the cloud instance to pull down — if not, we
need to put it in there. Call that the test."

**It did not.** The road-test plane (jerry.leftwich1 account: D1 `phoenix-roadtest`, worker
`phoenix-roadtest`) holds 102 entries — Phoenix's scripts, the Ollama bundle, llama3.2:3b, test
blobs. Its only Debian-related entry is `harden_debian_box.sh`. The Debian PoC lives only in our
own pool. This test puts it in the cloud plane and proves a worker box can pull it down cold,
verified, and boot it — "Phoenix brings the OS" (the manifest's own words), for real.

## What exists today (read live 2026-10-03)

Our pool (`phoenix_dev_db` + R2 `phoenix-clonepool`, jw.leftwich1 account):

| File | Size | D1 | R2 | State |
|---|---|---|---|---|
| `debian-12-genericcloud-amd64.qcow2` | 1,608,908,800 | v1, SHA3, 2026-09-30 | current + `versions/3ed934977661e991` | good |
| `usys-suite-qemu-system.tar` | 1,259,008,000 | v1, SHA3, 2026-09-30 | current + version key | **Windows QEMU** (`qemu-system-x86_64.exe`) — won't run on the Compaq |
| `debian.suite.json` | D1 says 1,143 | v1, 2026-08-21, SHA3 `435702be…` | 2,180 bytes (2026-09-21) | **D1 ≠ R2 ≠ repo** (repo 2,140, `24c0e298…`) — a verified pull is refused |
| `qemu-system.suite.json` | D1 723 | v1, 2026-08-21, `8346376e…` | 723 | repo 701, `40532902…` — stale record |
| `user-data` (cloud-init) | D1 2,696 | v1, 2026-09-25 | — | repo 2,626 — check |
| `meta-data` (cloud-init) | — | **not in the pool** | — | repo `tools/poc/debian-seed/meta-data` (62 bytes) |
| `run-debian.ps1`, `start-debian-persist.ps1` | small | v1 | present | Windows launchers |

The genericcloud image has **no password login**: it needs the NoCloud seed (user-data +
meta-data) or there's no way in. `usys run debian` serves the seed over loopback HTTP
(`python -m http.server 8000`, QEMU user-net reaches it as 10.0.2.2) — the same works on Linux.

## Step 1 — make the pool consistent (on the Precision, Jerry's machine)

Re-intake the current files so D1 = R2 = repo (`scripts/hsf-intake.sh`):
`tools/poc/debian.suite.json`, `tools/poc/qemu-system.suite.json`,
`tools/poc/debian-seed/user-data`, `tools/poc/debian-seed/meta-data`.
Pass: for each, D1 `hash_sha3` == SHA3 of the R2 bytes == SHA3 of the repo file.
Note the known collision bug (`hex_id = to_hex(basename)`): `user-data`/`meta-data` are generic
names — check nothing else in the pool already owns those hex ids before intaking.

## Step 2 — a QEMU that runs on Linux

The pooled QEMU is Windows-only. Pick one, Jerry's call (vendor/self-contained rule):
- **A (fast, honest first pass):** the box's own `qemu-system-x86` from Ubuntu's archive.
  Record that the VM runtime came from apt, not the pool.
- **B (the real "Phoenix brings the machine"):** a Linux QEMU suite in the pool —
  `qemu-system-x86_64` + its shared libraries + firmware (`bios-256k.bin`, `kvmvm`/pc-bios dir)
  bundled as `usys-suite-qemu-system-linux.tar`, SHA3'd, with `qemu-system-linux.suite.json`.
  Build it from the Debian/Ubuntu packages, prove it runs on a box that has never had QEMU.
Do A today, B after. KVM: check `/dev/kvm` on the Compaq; without it QEMU runs (TCG) but slow —
record which.

## Step 3 — seed the cloud plane

From the Precision (its uplink is far better than the Compaq's 20–26 Mbit/s), intake into the
**road-test plane** (its `PHOENIX_WORKER_URL` + per-plane `PHOENIX_AUTH`, from the vault, keys
in a 0600 file per A2-N1): the qcow2 (multipart, ~1.6 GB), `debian.suite.json`, `user-data`,
`meta-data` (+ the Linux QEMU suite once B exists). Pass: the plane's D1 rows carry the same SHA3
as our pool's.

## Step 4 — the test itself, on pbm-compaq (cold)

Fresh working dir, no local copy of anything. Time every step.
1. Pull `debian.suite.json`, `user-data`, `meta-data`, the qcow2 from the plane — through the
   ingress Helix path the road test built (`helix@ingress`, warm_write) — each SHA3 checked
   against the plane's D1 before it's kept (`intake clone`, or the universal kernel's pull).
2. Serve the seed on 127.0.0.1:8000; boot headless:
   `qemu-system-x86_64 [-enable-kvm] -m 2048 -smp 3 -drive file=<copy-on-write overlay of the qcow2>,if=virtio
   -netdev user,id=n,hostfwd=tcp:127.0.0.1:2222-:22 -device virtio-net,netdev=n -nographic
   -smbios type=1,serial=ds=nocloud-net;s=http://10.0.2.2:8000/`
   Use a qcow2 **overlay** (`qemu-img create -f qcow2 -b <pulled> -F qcow2 overlay.qcow2`) so the
   pulled, verified image is never modified.
3. `ssh -p 2222 phoenix@127.0.0.1 'uname -a; cat /etc/debian_version; df -h /'` — the
   "used briefly" part. Then `sudo poweroff`.
4. Run it again: the second start must not re-download (local copy hash-matches) — time it.

**Pass:** all four files byte-identical to custody, Debian boots, the command runs, second start
reuses the verified copy. **Record:** pull MB/s, verify time, boot-to-SSH seconds (KVM or TCG),
second-start time, plus anything refused and why. Results → `docs/plans/compaq-road-test-plan.md`
results section + SESSION-LOG.

**Fail is information, not a reason to hand-copy:** if a pull is refused, the custody record or
the bytes are wrong — fix the record by re-intaking, never by skipping the check.

## Safety (CLAUDE.md AI SAFETY RULES)

The VM uses user-mode networking and a file-backed overlay only: no bridges, no host disks
passed through, nothing in `/etc/modprobe.d` or `/etc/udev/rules.d`, no breach_coms drives
touched. Ask Jerry before installing packages (Step 2A) and before any service restart.
