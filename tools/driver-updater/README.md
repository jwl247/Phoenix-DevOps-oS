# driver-updater

A driver updater that doesn't act like the intrusive ones (Driver Booster, DriverEasy,
etc.). Those pull from scraped third-party driver databases, bundle ads/toolbars/telemetry,
and auto-install unsigned installers with fake "critical" match confidence.

This one only talks to Microsoft's own signed driver catalog (the same one Windows Update
itself uses) via [PSWindowsUpdate](https://www.powershellgallery.com/packages/PSWindowsUpdate)
— an open-source PowerShell module, no bundled software, no telemetry beyond what Windows
Update already does. Nothing installs without you confirming it.

## What it does

**Part 1 — Windows Update's own driver catalog:**
1. Registers the "Microsoft Update" service if it isn't already (needed for driver-category
   updates — plain Windows Update doesn't include them).
2. Scans for driver updates Microsoft has vetted and signed for your exact hardware.
3. Prints what it found — title, KB, size.
4. Asks before installing anything.

**Part 2 — everything WU doesn't cover** (a Logitech mouse, a USB audio interface, RGB/gaming
gear — WU rarely carries these vendors at all):
1. Flags devices Windows genuinely can't drive at all (a real Device Manager error/missing-driver
   status), identified by vendor where possible.
2. Separately lists present hardware matched against a small known-vendor table (USB/PCI vendor
   ID → vendor name + their official driver/support page) — things that likely already work fine
   on Windows' generic driver, but where the vendor's own software adds real features (DPI/macros,
   RGB, mic EQ/noise suppression, multi-channel audio routing).

Vendor identification is via USB-IF/PCI-SIG vendor IDs pulled straight off the hardware — no
network lookup, no telemetry. The table in the script (`$VendorIdMap`) currently covers Logitech,
Razer, SteelSeries, Corsair, HyperX/Kingston, Creative, Focusrite, C-Media, Elgato, Cooler Master,
Astro, ROCCAT, ASUS, plus the major chipset/GPU vendors (NVIDIA/AMD/Intel/Realtek/VIA/Broadcom/
Qualcomm Atheros). Unrecognized vendor IDs print as a hex ID so you can look them up yourself —
add more to the table as you hit them, it's just a hashtable.

## What it deliberately does NOT do

- No third-party driver downloads from anywhere but Microsoft's WU catalog.
- No scraping "driver databases" or fuzzy/confidence-scored hardware-ID guessing.
- No bundled toolbars, ads, or "upgrade to Pro" nags.
- No silent background install — always reports first.
- Vendor pages in Part 2 are links only — nothing is fetched or auto-installed from them.

## Usage

```powershell
# Run from an elevated PowerShell
cd tools/driver-updater

# Scan and report only, install nothing
./driver-updater.ps1 -WhatIfOnly

# Scan, show current driver inventory too, then ask before installing
./driver-updater.ps1 -ListCurrent

# Scan and install everything found without per-run prompt
./driver-updater.ps1 -InstallAll

# WU driver updates only, skip the vendor-ID device scan
./driver-updater.ps1 -SkipVendorScan
```

Requires: Windows, PowerShell (5.1+ or 7+), admin elevation, internet access. First run
installs `PSWindowsUpdate` from the PowerShell Gallery if it isn't already present
(`-Scope CurrentUser`, no admin-wide install).
