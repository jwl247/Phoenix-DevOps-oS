# Phoenix PoC — How To

These are the proof-of-concept demos: **import once, run anywhere.** No installer,
no wizard, no WSL, no Microsoft. Phoenix intakes a binary or OS image once, gives
it a hex ID, and runs it from the clonepool forever after.

This folder holds the **suite templates** (manifests + launcher scripts) that ship
with the repo. A suite template is not runnable by itself — `usys run` reads suites
out of your local **clonepool** (`~/Phoenix/clonepool` by default), not out of the
repo. So the one-time setup below clones each template into your clonepool and
drops in the real binary/image, and after that `usys run <name>` just works.

---

## What's here

| File | Type | What it does |
|---|---|---|
| `run-debian.ps1` | launcher | Demo 1 — boots Debian 12 via `usys run debian` |
| `run-ubuntu.ps1` | launcher | Demo 2 (pro) — boots Ubuntu 24.04 via `usys run ubuntu`, `-Hyperv` for Act 2 |
| `debian.suite.json` | suite manifest | Debian 12 (Bookworm) cloud image, QEMU runtime |
| `ubuntu.suite.json` | suite manifest | Ubuntu 24.04.2 LTS (Noble) cloud image, QEMU runtime |
| `qemu-system.suite.json` | suite manifest | QEMU binary itself — the VM engine both distros run on |
| `hello-phoenix.suite.json` | suite manifest | Python script demo — same hex ID on every OS |
| `yt-dlp.suite.json` | suite manifest | yt-dlp binary — single-file, no-install download tool |

> The launcher scripts assume they live two directories under the repo root
> (`tools/poc/run-debian.ps1`), because they walk up two `Split-Path -Parent`
> hops to find `scripts/usys.ps1`. Run them from this location — don't copy
> them somewhere shallower or they'll resolve the wrong repo root.

---

## Prerequisites

1. **PowerShell 7+** (`pwsh`) — `usys.ps1` requires it.
2. **Git Bash** installed (ships with Git for Windows) — used for bash intake pipelines.
3. **USys initialized once:**
   ```powershell
   . .\scripts\usys.ps1
   usys init
   ```
   This creates `~/.usys`, `~/Phoenix/clonepool`, `~/.catalog`, wires `usys` into
   your `$PROFILE`, and asks for `PHOENIX_WORKER_URL` / `PHOENIX_AUTH` (skip these
   if you're not syncing to D1 yet — local-only works fine).
4. Open a **new terminal** after `usys init` so the profile hook loads, or just
   re-dot-source `scripts\usys.ps1` in the current one.

---

## Quick start — Debian demo (Act 1, no setup beyond QEMU)

```powershell
# 1. Get QEMU (one-time — see "Setting up qemu-system" below)
# 2. Get the Debian cloud image (one-time — see "Setting up debian" below)
# 3. Run it
pwsh -NoProfile -ExecutionPolicy Bypass -File tools\poc\run-debian.ps1
```

That's Act 1: pure software emulation (`-accel tcg`), no hardware requirements,
boots anywhere. It runs in **snapshot mode** by default — writes go to a throwaway
overlay, the base image never changes.

---

## Setting up each suite

Suites run from the clonepool, not from `tools/poc/`. Clone the template in, then
drop the real payload (binary/image) alongside the manifest.

### 1. `qemu-system` (needed by both distros)

```powershell
usys clone tools\poc\qemu-system.suite.json -Category infrastructure
```

Then download QEMU for Windows x64 from https://qemu.weilnetz.de/w64/ and copy
`qemu-system-x86_64.exe` into:

```
~/Phoenix/clonepool/qemu-system/qemu-system-x86_64.exe
```

(`usys clone` on the `.suite.json` creates the suite folder — copy the exe in
after. `usys run` resolves QEMU from this suite automatically.)

### 2. `debian`

```powershell
usys clone tools\poc\debian.suite.json -Category distro
usys download https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-genericcloud-amd64.qcow2 -OutFile ~/Phoenix/clonepool/debian/debian-12.5-genericcloud-amd64.qcow2
```

Verify against `SHA512SUMS` linked in `debian.suite.json` metadata before trusting
the image.

### 3. `ubuntu`

```powershell
usys clone tools\poc\ubuntu.suite.json -Category distro
usys download https://cloud-images.ubuntu.com/releases/24.04/release/ubuntu-24.04.2-server-cloudimg-amd64.img -OutFile ~/Phoenix/clonepool/ubuntu/ubuntu-24.04.2-server-cloudimg-amd64.img
```

### 4. `hello-phoenix`

```powershell
usys clone tools\poc\hello-phoenix.suite.json -Category poc
```

Then add a `hello-phoenix.py` entry point into the cloned suite folder
(`~/Phoenix/clonepool/hello-phoenix/`) — this one's a script demo you write
yourself; the manifest just proves the hex ID travels with it across OSes.

### 5. `yt-dlp`

```powershell
usys clone tools\poc\yt-dlp.suite.json -Category poc
usys download https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe -OutFile ~/Phoenix/clonepool/yt-dlp/yt-dlp.exe
```

---

## Running

```powershell
usys run debian                    # Act 1 — TCG software emulation, always works
usys run debian --accel hyperv     # Act 2 — WHPX + Hyper-V enlightenments, near-native
usys run ubuntu
tools\poc\run-ubuntu.ps1 2         # same as --accel hyperv, via the launcher's Act 2 flag
usys run yt-dlp <video-url>
usys run hello-phoenix
```

Accelerator values: `auto` (default, Phoenix picks), `tcg` (software, universal),
`whpx` (Windows Hypervisor Platform), `hyperv` (WHPX + full HV enlightenments,
fastest on Windows), `kvm` (Linux/WSL).

Pass `-Persist` to write VM changes back to the image instead of discarding them
on exit (default is snapshot/ephemeral).

Check what's actually staged at any time:

```powershell
usys list-suites
usys status
```

---

## Shared filesystem — Windows ↔ Debian

Debian and Windows share the same directories on `F:\Phoenix\` — no sync, no
copy, no WSL. QEMU's virtio-9p passthrough bridges them. The PS7 wrappers
(`phx-import`, `phx-export`, `phx-sync`, `phx-ls`) are the only legal
operations against the shared area. The profile loads them on every terminal open.

### One-time setup (Windows side)

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File tools\poc\setup-shared-fs.ps1
```

This creates `F:\Phoenix\{Desktop,Documents,Downloads,Projects,Vault}`, stamps
each with a `_PHOENIX_DIR.txt` marker, prints the mount table, and wires the
profile. Safe to run more than once — nothing is overwritten destructively.

Or via usys after `usys init`:

```powershell
usys fs-init
```

### Running Debian with the shared FS

```powershell
usys run debian --share                       # Act 1 (TCG) + shared FS
usys run debian --accel hyperv --share        # Act 2 (near-native) + shared FS
```

Without `--share`: standard boot, unchanged. The shared directories are opt-in.

### Debian side (first boot with updated cloud-init seed)

On first boot after setup, cloud-init installs `plan9-fs-utils` and injects
fstab entries with `noauto,x-systemd.automount`. Each directory mounts
automatically on first access — a missing tag never stalls boot.

```bash
# Inside Debian — directories are live when booted with --share:
ls /phoenix/Desktop
ls /phoenix/Documents
ls /phoenix/Downloads
ls /phoenix/Projects
ls /phoenix/Vault
```

### PS7 wrappers — the enforcement layer

| Command | Direction | What it does |
|---------|-----------|--------------|
| `phx-import <path>` | shared FS → clonepool | Intakes a file from the shared area; gives it hex ID + D1 registration |
| `phx-export <name> <dir>` | clonepool → shared FS | Copies a pool item into a named shared directory |
| `phx-sync <dir>` | shared FS dir → clonepool | Imports every file in a shared dir not yet in the pool (idempotent) |
| `phx-ls [dir]` | read-only | Lists shared dirs and their pool registration status |

All four are also available as `usys fs-import`, `usys fs-export`,
`usys fs-sync`, `usys fs-ls`.

**Rule:** ALL operations against `F:\Phoenix\` go through these wrappers.
No raw path access. No bypass. The profile enforces this.

```powershell
# Examples
phx-ls                              # show all five dirs + pool status
phx-ls Desktop                     # show one dir
phx-import F:\Phoenix\Desktop\report.pdf    # intake a shared file
phx-sync Downloads                  # import everything new in Downloads\
phx-export my-script F:\Phoenix\Projects\  # copy pool item into Projects\
```

### Mount tag reference

| Windows path | virtio-9p tag | Debian path |
|---|---|---|
| `F:\Phoenix\Desktop` | `phoenix-desktop` | `/phoenix/Desktop` |
| `F:\Phoenix\Documents` | `phoenix-documents` | `/phoenix/Documents` |
| `F:\Phoenix\Downloads` | `phoenix-downloads` | `/phoenix/Downloads` |
| `F:\Phoenix\Projects` | `phoenix-projects` | `/phoenix/Projects` |
| `F:\Phoenix\Vault` | `phoenix-vault` | `/phoenix/Vault` |

The mount tag is the stable QEMU contract — the Windows host path can move
without touching Debian's `/etc/fstab`.

---

## Troubleshooting

- **`Suite not found: debian`** — the manifest hasn't been cloned into
  `~/Phoenix/clonepool` yet, or `CLONEPOOL_DIR` points somewhere else. Run
  `usys status` to see the resolved clonepool path.
- **`QEMU not found`** — `qemu-system-x86_64.exe` isn't in the `qemu-system`
  suite folder and isn't on `PATH`. See step 1 above.
- **`Entry point not found`** — the `.qcow2`/`.img`/`.exe` payload wasn't copied
  into the cloned suite folder next to `.suite.json`. The manifest's `entry`
  field names the exact filename it expects.
- **Slow boot on Windows** — you're on `tcg`. Enable Windows Hypervisor Platform
  (`Enable-WindowsOptionalFeature -Online -FeatureName HypervisorPlatform`) and
  rerun with `--accel hyperv`.

---

**USys — United Systems | jwl247 | GPL-3.0**
