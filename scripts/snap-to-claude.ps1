# snap-to-claude.ps1 — one click: screenshot of every screen, ready for Claude.
# Phoenix DevOps OS | jwl247 | GPL v3
#
# Jerry 2026-10-07: "an icon on my desktop that automatically sends you a screenshot".
# Saves to ~\.phoenix\screenshots\snap-<time>.png (+ latest.png), keeps the last 20, puts the
# picture on the clipboard. Then: Alt+V in Claude Code pastes it, or say "look" and Claude
# opens latest.png. Nothing leaves this PC (screens can show secrets).
#   snap-to-claude.ps1            make the shot
#   snap-to-claude.ps1 -Install   put the desktop icon in place
param([switch]$Install, [int]$Delay = 0, [switch]$Quiet)   # -Delay N: wait N s first (switch windows); -Quiet: no toast (/look)
$ErrorActionPreference = 'Stop'

if ($Install) {
    $desk = [Environment]::GetFolderPath('Desktop')
    $pwsh = (Get-Command pwsh).Source
    $lnk = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $desk 'Screenshot to Claude.lnk'))
    $lnk.TargetPath = $pwsh
    $lnk.Arguments = "-NoProfile -Sta -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    $lnk.WindowStyle = 7                                       # start minimized: no window in the shot
    $lnk.IconLocation = "$env:SystemRoot\System32\imageres.dll,68"
    $lnk.Description = 'Screenshot every screen for Claude (Alt+V to paste, or say look)'
    $lnk.Save()
    Write-Host "  desktop icon: $(Join-Path $desk 'Screenshot to Claude.lnk')"
    return
}

Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Start-Sleep -Milliseconds (350 + 1000 * [Math]::Max(0, [Math]::Min($Delay, 30)))   # let the click/menu close; -Delay for switching windows
$v = [System.Windows.Forms.SystemInformation]::VirtualScreen  # all monitors together
$bmp = New-Object System.Drawing.Bitmap $v.Width, $v.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($v.Left, $v.Top, 0, 0, $bmp.Size)
$g.Dispose()

$dir = Join-Path $HOME '.phoenix\screenshots'
New-Item -ItemType Directory -Force $dir | Out-Null
# Jerry 10/7: screens can show keys - only his Windows account may open these. No inherited rights,
# no Administrators/SYSTEM/Users entries; files made inside inherit the same. Re-applied every shot.
& icacls $dir /inheritance:r /grant:r "$($env:USERDOMAIN)\$($env:USERNAME):(OI)(CI)F" /Q | Out-Null
$file = Join-Path $dir ("snap-{0:yyyyMMdd-HHmmss}.png" -f (Get-Date))
$bmp.Save($file, [System.Drawing.Imaging.ImageFormat]::Png)
Copy-Item $file (Join-Path $dir 'latest.png') -Force
$onClip = $false
foreach ($try in 1..5) {                                       # another app can hold the clipboard for a moment
    try { [System.Windows.Forms.Clipboard]::SetImage($bmp); $onClip = $true; break } catch { Start-Sleep -Milliseconds 200 }
}
$bmp.Dispose()
Get-ChildItem $dir -Filter 'snap-*.png' | Sort-Object LastWriteTime -Descending | Select-Object -Skip 20 | Remove-Item -Force

if ($Quiet) { Write-Output $file; return }
$tip = New-Object System.Windows.Forms.NotifyIcon
$tip.Icon = [System.Drawing.SystemIcons]::Information
$tip.Visible = $true
$how = if ($onClip) { 'Alt+V in Claude Code to paste it, or just say "look".' } else { 'Saved (clipboard was busy): say "look" in Claude Code.' }
$tip.ShowBalloonTip(4000, 'Screenshot ready for Claude', $how, 'Info')
Start-Sleep -Seconds 4
$tip.Dispose()
