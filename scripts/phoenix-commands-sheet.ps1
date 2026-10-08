# phoenix-commands-sheet.ps1 — the permanent "Phoenix Commands.txt" on Jerry's Desktop.
# Phoenix DevOps OS | jwl247 | GPL v3
# Jerry 2026-10-07 night: "I need a permanent file on the desktop, aliases and commands."
#
# Built FROM the repo, never by hand, so it can't drift:
#   1. QUICK CARD  — every alias, read from the header of scripts\phoenix-aliases.ps1, plus the everyday commands
#   2. FULL LIST   — docs\COMMANDS.md as it is in the repo
# Loaded by usys.ps1 in every PS7 window: it rebuilds the Desktop file only when one of its sources is newer
# than the file (a cheap timestamp check), so it costs nothing when nothing changed.
#   phoenix-commands          rebuild it now and open it
#   phoenix-commands -NoOpen  rebuild only

$script:PhxCmdRepo = if ($env:PHOENIX_ROOT -and (Test-Path (Join-Path $env:PHOENIX_ROOT 'docs\COMMANDS.md'))) { $env:PHOENIX_ROOT } else { Split-Path $PSScriptRoot -Parent }

function Get-PhoenixCommandsSheetPath {
    $desk = [Environment]::GetFolderPath('Desktop')            # OneDrive Desktop when OneDrive owns it
    Join-Path $desk 'Phoenix Commands.txt'
}

function Update-PhoenixCommandsSheet([switch]$Force) {
    $out = Get-PhoenixCommandsSheetPath
    $src = @((Join-Path $script:PhxCmdRepo 'docs\COMMANDS.md'), (Join-Path $script:PhxCmdRepo 'scripts\phoenix-aliases.ps1'), $PSCommandPath) |
        Where-Object { Test-Path $_ }
    if (-not $Force -and (Test-Path $out)) {
        $built = (Get-Item $out).LastWriteTime
        if (-not ($src | Where-Object { (Get-Item $_).LastWriteTime -gt $built })) { return $out }
    }
    $aliases = Get-Content (Join-Path $script:PhxCmdRepo 'scripts\phoenix-aliases.ps1') -TotalCount 40 |
        Where-Object { $_ -match '^#\s{3}\S' } | ForEach-Object { '  ' + $_.TrimStart('#').Trim() }
    $card = @"
PHOENIX COMMANDS  (built $(Get-Date -Format 'yyyy-MM-dd HH:mm') from the repo - do not edit, it rebuilds itself)
Where: PBMII, PowerShell 7 (PS7), any folder unless it says otherwise.
=====================================================================================================

QUICK CARD - ALIASES (scripts\phoenix-aliases.ps1)
$($aliases -join "`r`n")
  g              go to the path you highlighted on screen (Windows Terminal copy-on-select)
  px <path>      the same path, slash-insensitive, on Windows and Linux

QUICK CARD - EVERYDAY
  intake <file|folder>        put it IN the clone pool (custody, versions, R2)
  clone <name> [vN] [folder]  take it OUT of the pool (latest or version N)
  pool <text>                 search the pool
  genie import <name|file>    run a suit (pool -> RAM -> run);  genie closet / genie status / genie restart
  usys help                   everything usys can do
  rotate-key                  rotate PHOENIX_AUTH everywhere (Jerry only, typed ROTATE)
  security status             the file sensor; security lock-hud / unlock-hud
  ssh pbm-compaq   (= pb3)    the Compaq;  aws1 = the awslh lighthouse
  phoenix-commands            rebuild this file now and open it

QUICK CARD - GIT BASH (repo folder: cd /f/Phoenix/Phoenix-DevOps-oS)
  bash scripts/hsf-intake.sh <paths...>           unattended intake
  bash scripts/pool-bundles.sh [sector1..4|system] the repo section of the pool
  python scripts/heal_check.py --box pbmiii       healing check, reads only

HUD (tray icon = the Phoenix bird)
  click = the Console;  right-click = Run..., Suit look-up..., Ask Jarvis..., Screenshot for Claude, Hide the eye
  Right Ctrl = talk;  say "open the dock" / "close the dock"

=====================================================================================================
FULL LIST (docs\COMMANDS.md)
=====================================================================================================

"@
    $full = Get-Content (Join-Path $script:PhxCmdRepo 'docs\COMMANDS.md') -Raw -Encoding utf8
    try {
        [IO.File]::WriteAllText($out, $card + $full, [Text.UTF8Encoding]::new($true))
    } catch { Write-Host "  phoenix-commands: couldn't write $out ($($_.Exception.Message))" -ForegroundColor Yellow }
    return $out
}

function global:phoenix-commands([switch]$NoOpen) {
    $f = Update-PhoenixCommandsSheet -Force
    Write-Host "  $f" -ForegroundColor DarkCyan
    if (-not $NoOpen) { Start-Process notepad.exe -ArgumentList "`"$f`"" }
}

# Every PS7 window: rebuild only if something changed (silent, fast).
try { [void](Update-PhoenixCommandsSheet) } catch { }
