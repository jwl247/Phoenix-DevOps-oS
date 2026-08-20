# phoenix_partition.ps1
# Phoenix DevOps OS — Disk partitioning script
# Target: Disk 3 — Seagate BUP Slim 2TB (COPES drive)
# Run as Administrator in PS7
# jwl247 / United Systems / GPL v3
# =============================================================================
# LAYOUT:
#   P1   1GB     EFI/Boot          FAT32       PHOENIX-EFI
#   P2   50GB    Ubuntu root /     NTFS*       PHOENIX-ROOT
#   P3   20GB    Swap              NTFS*       PHOENIX-SWAP
#   P4   200GB   Helix T1 master   NTFS*       HELIX-T1
#   P5   200GB   Helix T2 mirror   NTFS*       HELIX-T2
#   P6   200GB   Helix T3 mirror   NTFS*       HELIX-T3
#   P7   200GB   Helix T4 mirror   NTFS*       HELIX-T4
#   P8   800GB   D1 mimic          NTFS*       PHOENIX-D1
#   P9   ~192GB  Distro cache      NTFS*       PHOENIX-DISTRO
#
# * Formatted NTFS now so Windows can see them.
#   Ubuntu installer / bootstrap.sh will reformat to ext4 at install time.
# =============================================================================

$DISK_NUMBER = 3
$CONFIRM = Read-Host "This will WIPE all data on Disk $DISK_NUMBER. Type WIPE to continue"
if ($CONFIRM -ne "WIPE") {
    Write-Host "Aborted." -ForegroundColor Yellow
    exit 1
}

Write-Host "`nPhoenix partitioning Disk $DISK_NUMBER..." -ForegroundColor Cyan

# ── Clear existing partitions ─────────────────────────────────────────────────
Write-Host "  Clearing disk..." -ForegroundColor Gray
Clear-Disk -Number $DISK_NUMBER -RemoveData -RemoveOEM -Confirm:$false
Initialize-Disk -Number $DISK_NUMBER -PartitionStyle GPT -Confirm:$false
Start-Sleep -Seconds 2

# ── Helper function ───────────────────────────────────────────────────────────
function New-PhoenixPartition {
    param(
        [int]$Disk,
        [int64]$SizeGB,
        [string]$Label,
        [string]$Letter,
        [bool]$IsLast = $false
    )
    Write-Host "  Creating $Label ($SizeGB GB)..." -ForegroundColor Gray

    if ($IsLast) {
        $part = New-Partition -DiskNumber $Disk -UseMaximumSize -AssignDriveLetter
    } else {
        $part = New-Partition -DiskNumber $Disk -Size ($SizeGB * 1GB) -AssignDriveLetter
    }

    Start-Sleep -Seconds 1

    Format-Volume -Partition $part -FileSystem NTFS -NewFileSystemLabel $Label `
        -Confirm:$false -Force | Out-Null

    Start-Sleep -Seconds 1
    return $part
}

# ── P1 — EFI/Boot (FAT32) ────────────────────────────────────────────────────
Write-Host "  Creating PHOENIX-EFI (1 GB)..." -ForegroundColor Gray
$p1 = New-Partition -DiskNumber $DISK_NUMBER -Size 1GB -AssignDriveLetter
Start-Sleep -Seconds 1
Format-Volume -Partition $p1 -FileSystem FAT32 -NewFileSystemLabel "PHOENIX-EFI" `
    -Confirm:$false -Force | Out-Null
Start-Sleep -Seconds 1
Write-Host "    ✓ PHOENIX-EFI" -ForegroundColor Green

# ── P2 — Ubuntu root ─────────────────────────────────────────────────────────
$p2 = New-PhoenixPartition -Disk $DISK_NUMBER -SizeGB 50  -Label "PHOENIX-ROOT"
Write-Host "    ✓ PHOENIX-ROOT" -ForegroundColor Green

# ── P3 — Swap ────────────────────────────────────────────────────────────────
$p3 = New-PhoenixPartition -Disk $DISK_NUMBER -SizeGB 20  -Label "PHOENIX-SWAP"
Write-Host "    ✓ PHOENIX-SWAP" -ForegroundColor Green

# ── P4 — Helix T1 master vault ───────────────────────────────────────────────
$p4 = New-PhoenixPartition -Disk $DISK_NUMBER -SizeGB 200 -Label "HELIX-T1"
Write-Host "    ✓ HELIX-T1 (master vault)" -ForegroundColor Green

# ── P5 — Helix T2 mirror ─────────────────────────────────────────────────────
$p5 = New-PhoenixPartition -Disk $DISK_NUMBER -SizeGB 200 -Label "HELIX-T2"
Write-Host "    ✓ HELIX-T2 (day-1 mirror)" -ForegroundColor Green

# ── P6 — Helix T3 mirror ─────────────────────────────────────────────────────
$p6 = New-PhoenixPartition -Disk $DISK_NUMBER -SizeGB 200 -Label "HELIX-T3"
Write-Host "    ✓ HELIX-T3 (day-2 mirror)" -ForegroundColor Green

# ── P7 — Helix T4 mirror ─────────────────────────────────────────────────────
$p7 = New-PhoenixPartition -Disk $DISK_NUMBER -SizeGB 200 -Label "HELIX-T4"
Write-Host "    ✓ HELIX-T4 (day-3 mirror)" -ForegroundColor Green

# ── P8 — D1 mimic ────────────────────────────────────────────────────────────
$p8 = New-PhoenixPartition -Disk $DISK_NUMBER -SizeGB 800 -Label "PHOENIX-D1"
Write-Host "    ✓ PHOENIX-D1 (local D1 mimic)" -ForegroundColor Green

# ── P9 — Distro cache (use remaining space) ──────────────────────────────────
Write-Host "  Creating PHOENIX-DISTRO (remaining space)..." -ForegroundColor Gray
$p9 = New-Partition -DiskNumber $DISK_NUMBER -UseMaximumSize -AssignDriveLetter
Start-Sleep -Seconds 1
Format-Volume -Partition $p9 -FileSystem NTFS -NewFileSystemLabel "PHOENIX-DISTRO" `
    -Confirm:$false -Force | Out-Null
Start-Sleep -Seconds 1
Write-Host "    ✓ PHOENIX-DISTRO (distro cache)" -ForegroundColor Green

# ── Summary ───────────────────────────────────────────────────────────────────
Write-Host "`nPhoenix partition layout complete:" -ForegroundColor Cyan
Write-Host "─────────────────────────────────────────────────" -ForegroundColor Gray
Get-Partition -DiskNumber $DISK_NUMBER | 
    Select-Object PartitionNumber, 
                  @{N="Size";E={"{0:N1} GB" -f ($_.Size/1GB)}},
                  DriveLetter,
                  @{N="Label";E={(Get-Volume -Partition $_ -ErrorAction SilentlyContinue).FileSystemLabel}} |
    Format-Table -AutoSize

Write-Host "Next step: run Ubuntu Server installer and point it at PHOENIX-ROOT" -ForegroundColor Yellow
Write-Host "           then run bootstrap.sh to initialize Helix + Frank + clone pool" -ForegroundColor Yellow
Write-Host "`nDone. Phoenix is partitioned. 🧬🔥`n" -ForegroundColor Cyan
