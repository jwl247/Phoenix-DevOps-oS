<#
.SYNOPSIS
    Clean driver updater — Windows Update's signed catalog, plus honest vendor pointers
    for hardware WU doesn't cover.

.DESCRIPTION
    No third-party driver database, no bundled toolbar/telemetry, no unsigned installers.

    Part 1 scans Windows Update's own signed driver catalog (via the Microsoft Update
    service) and installs only on explicit confirmation.

    Part 2 covers what WU misses — WU doesn't carry most peripheral vendors' latest
    (a Logitech mouse, a USB audio interface, RGB/gaming gear, etc.). This identifies
    present hardware by its USB/PCI vendor ID against a small known-vendor table and
    points you at that vendor's own official driver/support page. Nothing is scraped
    or auto-downloaded from those pages — you click through and grab it yourself.

    It also flags devices Windows genuinely can't drive at all (a real Device Manager
    error/missing-driver status), separately from "this works but the vendor's own
    software probably adds more" (macros, RGB, mic EQ, DPI, etc.).

.PARAMETER InstallAll
    Skip the confirmation prompt and install all found WU driver updates.

.PARAMETER WhatIfOnly
    Scan and report only. Never installs, even if you'd otherwise be prompted.

.PARAMETER ListCurrent
    Also print currently installed driver versions/dates for every PnP device.

.PARAMETER SkipVendorScan
    Skip Part 2 (vendor-ID identification for non-WU hardware). WU scan only.

.EXAMPLE
    ./driver-updater.ps1
    Full scan: WU driver updates + problem devices + vendor pointers. Asks before installing.

.EXAMPLE
    ./driver-updater.ps1 -WhatIfOnly
    Report everything, install nothing.
#>

[CmdletBinding()]
param(
    [switch]$InstallAll,
    [switch]$WhatIfOnly,
    [switch]$ListCurrent,
    [switch]$SkipVendorScan
)

$ErrorActionPreference = 'Stop'
$MS_UPDATE_SERVICE_ID = '7971f918-a847-4430-9279-4a52d1efe18d'

# --- Known USB/PCI vendor IDs -> vendor name + official driver/support page. ---
# Static reference data (USB-IF / PCI-SIG assigned IDs). Not fetched live, so it can go
# stale, but these are official vendor pages with low churn. Extend the table as needed —
# it's the only thing to touch to recognize more hardware.
$script:VendorIdMap = @{
    # USB VID (peripherals — mice, keyboards, audio interfaces, headsets, capture gear)
    '046D' = @{ Name = 'Logitech';                  Url = 'https://www.logitech.com/en-us/software/g-hub.html' }
    '1532' = @{ Name = 'Razer';                     Url = 'https://www.razer.com/synapse-3' }
    '1038' = @{ Name = 'SteelSeries';                Url = 'https://steelseries.com/gg' }
    '1B1C' = @{ Name = 'Corsair';                    Url = 'https://www.corsair.com/us/en/downloads' }
    '0951' = @{ Name = 'Kingston / HyperX';          Url = 'https://www.hyperxgaming.com/en/downloads' }
    '041E' = @{ Name = 'Creative Labs';              Url = 'https://support.creative.com/Downloads/' }
    '1235' = @{ Name = 'Focusrite';                  Url = 'https://focusrite.com/en/downloads' }
    '0D8C' = @{ Name = 'C-Media (audio chipset)';    Url = 'https://www.cmedia.com.tw/zh-cn/Support/Driver-Download' }
    '0FD9' = @{ Name = 'Elgato';                     Url = 'https://help.elgato.com/hc/en-us/categories/360002469877' }
    '2516' = @{ Name = 'Cooler Master';               Url = 'https://www.coolermaster.com/en-global/support/downloads/' }
    '3554' = @{ Name = 'Astro Gaming';               Url = 'https://www.astrogaming.com/en-us/software/astro-command-center.html' }
    '045E' = @{ Name = 'Microsoft (peripherals)';    Url = 'https://www.microsoft.com/accessories/en-us/downloads' }
    '0B05' = @{ Name = 'ASUS';                       Url = 'https://www.asus.com/support/' }
    '1E7D' = @{ Name = 'ROCCAT';                     Url = 'https://www.roccat.org/en-US/Home/Support/' }

    # PCI VEN (chipset, GPU, onboard audio/network)
    '10DE' = @{ Name = 'NVIDIA';                     Url = 'https://www.nvidia.com/en-us/drivers/' }
    '1002' = @{ Name = 'AMD';                        Url = 'https://www.amd.com/en/support' }
    '8086' = @{ Name = 'Intel';                      Url = 'https://www.intel.com/content/www/us/en/support/detect.html' }
    '10EC' = @{ Name = 'Realtek';                    Url = 'https://www.realtek.com/en/downloads' }
    '1106' = @{ Name = 'VIA Technologies';           Url = 'https://www.viatech.com/en/support/drivers/' }
    '14E4' = @{ Name = 'Broadcom';                   Url = 'https://www.broadcom.com/support/download-search' }
    '168C' = @{ Name = 'Qualcomm Atheros';           Url = 'https://www.qualcomm.com/support' }
}

function Assert-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Error "Run this from an elevated PowerShell (driver scans/installs need admin)."
        exit 1
    }
}

function Ensure-PSWindowsUpdate {
    if (-not (Get-Module -ListAvailable -Name PSWindowsUpdate)) {
        Write-Host "Installing PSWindowsUpdate (official PowerShell Gallery module — Microsoft's own WU/WUA wrapper, MIT-licensed, no telemetry beyond what WU itself already does)..." -ForegroundColor Cyan
        Install-Module -Name PSWindowsUpdate -Force -Scope CurrentUser -Repository PSGallery
    }
    Import-Module PSWindowsUpdate -ErrorAction Stop
}

function Ensure-MicrosoftUpdateService {
    # Driver updates only surface if "Microsoft Update" (not just base "Windows Update") is registered.
    $svc = Get-WUServiceManager | Where-Object { $_.ServiceID -eq $MS_UPDATE_SERVICE_ID }
    if (-not $svc) {
        Write-Host "Registering Microsoft Update service (required for driver-category updates)..." -ForegroundColor Cyan
        Add-WUServiceManager -MicrosoftUpdate -Confirm:$false | Out-Null
    }
}

function Show-CurrentDrivers {
    Write-Host "`nCurrently installed drivers (Win32_PnPSignedDriver):`n" -ForegroundColor Cyan
    Get-CimInstance Win32_PnPSignedDriver |
        Where-Object { $_.DeviceName } |
        Sort-Object DeviceClass, DeviceName |
        Format-Table DeviceName, DeviceClass, DriverVersion, DriverDate, Manufacturer -AutoSize |
        Out-String -Width 200 | Write-Host
}

function Get-WindowsUpdateDrivers {
    Write-Host "`nScanning Windows Update's signed driver catalog for this machine (can take a minute)...`n" -ForegroundColor Cyan
    @(Get-WindowsUpdate -MicrosoftUpdate -UpdateType Driver -ErrorAction SilentlyContinue)
}

function Install-FoundDrivers {
    param([switch]$Force)
    if (-not $Force) {
        $resp = Read-Host "`nInstall all listed driver updates now? [y/N]"
        if ($resp -notmatch '^[Yy]') {
            Write-Host "Nothing installed." -ForegroundColor DarkGray
            return
        }
    }
    Write-Host "`nInstalling via Windows Update..." -ForegroundColor Cyan
    Install-WindowsUpdate -MicrosoftUpdate -UpdateType Driver -AcceptAll -IgnoreReboot -Verbose
    Write-Host "`nDone. A reboot may be required for some drivers to fully take effect." -ForegroundColor Green
}

function Get-VendorFromDeviceId([string]$deviceId) {
    if ([string]::IsNullOrEmpty($deviceId)) { return $null }
    if ($deviceId -match '(?:VID|VEN)_([0-9A-Fa-f]{4})') {
        $id = $matches[1].ToUpper()
        if ($script:VendorIdMap.ContainsKey($id)) {
            return $script:VendorIdMap[$id]
        }
        return @{ Name = "Unrecognized vendor ID $id"; Url = $null }
    }
    return $null
}

function Show-ProblemDevices {
    # ConfigManagerErrorCode 0 = working properly. 22 = manually disabled by the user, not a
    # problem. Anything else (28 = drivers not installed, 1/24/31/39/43 etc.) is a real,
    # Windows-reported "this device isn't fully working" status.
    Write-Host "`n--- Devices Windows can't fully drive ---`n" -ForegroundColor Cyan
    $problems = @(Get-CimInstance Win32_PnPEntity | Where-Object {
        $_.ConfigManagerErrorCode -ne 0 -and $_.ConfigManagerErrorCode -ne 22
    })
    if ($problems.Count -eq 0) {
        Write-Host "None — Windows reports every present device as configured OK." -ForegroundColor Green
        return
    }
    foreach ($d in $problems) {
        $vendor = Get-VendorFromDeviceId $d.DeviceID
        Write-Host ("- {0}  [error code {1}]" -f $d.Name, $d.ConfigManagerErrorCode) -ForegroundColor Yellow
        if ($vendor -and $vendor.Url) {
            Write-Host ("    Looks like {0} hardware — official drivers: {1}" -f $vendor.Name, $vendor.Url) -ForegroundColor DarkGray
        } elseif ($vendor) {
            Write-Host ("    {0} — no official link on file for this ID; search it on the vendor's own site." -f $vendor.Name) -ForegroundColor DarkGray
        }
    }
}

function Show-VendorSoftwareSuggestions {
    # These devices are usually already working fine on Windows' generic inbox driver
    # (HID for a mouse, USB Audio Class for a mic/interface) — this just points at where
    # the vendor's fuller driver/companion app lives (DPI/macros, RGB, mic EQ/noise
    # suppression), since Windows Update will never surface those on its own.
    Write-Host "`n--- Hardware from vendors that ship their own driver/companion app ---`n" -ForegroundColor Cyan
    $seen = @{}
    Get-CimInstance Win32_PnPEntity | ForEach-Object {
        $vendor = Get-VendorFromDeviceId $_.DeviceID
        if ($vendor -and $vendor.Url -and -not $seen.ContainsKey($vendor.Name)) {
            $seen[$vendor.Name] = @()
        }
        if ($vendor -and $vendor.Url) {
            $seen[$vendor.Name] += $_.Name
        }
    }
    if ($seen.Count -eq 0) {
        Write-Host "No recognized aftermarket peripheral/chipset vendors detected." -ForegroundColor DarkGray
        return
    }
    foreach ($name in $seen.Keys | Sort-Object) {
        $vendorUrl = $script:VendorIdMap.Values | Where-Object { $_.Name -eq $name } | Select-Object -First 1 -ExpandProperty Url
        Write-Host ("- {0}" -f $name)
        $seen[$name] | Select-Object -Unique | ForEach-Object { Write-Host ("    device: {0}" -f $_) -ForegroundColor DarkGray }
        Write-Host ("    {0}" -f $vendorUrl) -ForegroundColor DarkGray
    }
    Write-Host "`n(Nothing here is auto-downloaded — these are the vendors' own official pages, click through yourself.)" -ForegroundColor DarkGray
}

# ---------------------------------------------------------------------------

Assert-Admin
Ensure-PSWindowsUpdate
Ensure-MicrosoftUpdateService

if ($ListCurrent) {
    Show-CurrentDrivers
}

$driverUpdates = Get-WindowsUpdateDrivers

Write-Host "`n--- Windows Update driver catalog ---`n" -ForegroundColor Cyan
if ($driverUpdates.Count -eq 0) {
    Write-Host "No driver updates available on the Windows Update channel — everything WU knows about is current." -ForegroundColor Green
} else {
    Write-Host "Found $($driverUpdates.Count) driver update(s):`n" -ForegroundColor Yellow
    $i = 1
    foreach ($u in $driverUpdates) {
        Write-Host ("[{0}] {1}" -f $i, $u.Title)
        Write-Host ("     KB: {0}   Size: {1:N1} MB" -f $u.KB, ($u.Size / 1MB)) -ForegroundColor DarkGray
        $i++
    }
    if (-not $WhatIfOnly) {
        Install-FoundDrivers -Force:$InstallAll
    } else {
        Write-Host "`n(-WhatIfOnly set — report only, nothing installed.)" -ForegroundColor DarkGray
    }
}

Show-ProblemDevices

if (-not $SkipVendorScan) {
    Show-VendorSoftwareSuggestions
}
