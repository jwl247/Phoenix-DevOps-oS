# phoenix-commands-sheet.ps1 — the permanent "Phoenix Commands.txt" on Jerry's Desktop.
# Phoenix DevOps OS | jwl247 | GPL v3
# Jerry 2026-10-07 night: "I need a permanent file on the desktop, aliases and commands."
# 2026-10-09: rebuilt from THE COMMAND CARD ($script:LolCard in usys.ps1) — the same table `lol help`,
# the Console and Jarvis read — not from docs\COMMANDS.md (hand-written, drifted: five names for one job,
# no highlight system, Tailscale, undeployed wares). Jerry: "it isn't exactly clear".
#
# Dot-sourced by usys.ps1 in every PS7 window: it rebuilds the Desktop file only when usys.ps1 (the card),
# the aliases or this file is newer than it (a cheap timestamp check). Deleting it just brings it back.
#   phoenix-commands          rebuild it now and open it
#   phoenix-commands -NoOpen  rebuild only

$script:PhxCmdRepo = if ($env:PHOENIX_ROOT -and (Test-Path (Join-Path $env:PHOENIX_ROOT 'scripts\usys.ps1'))) { $env:PHOENIX_ROOT } else { Split-Path $PSScriptRoot -Parent }

function Get-PhoenixCommandsSheetPath {
    Join-Path ([Environment]::GetFolderPath('Desktop')) 'Phoenix Commands.txt'   # wherever Windows says the Desktop is
}

function Update-PhoenixCommandsSheet([switch]$Force) {
    if (-not $script:LolCard) { return }                       # the card lives in usys.ps1
    $out = Get-PhoenixCommandsSheetPath
    $src = @((Join-Path $script:PhxCmdRepo 'scripts\usys.ps1'), (Join-Path $script:PhxCmdRepo 'scripts\phoenix-aliases.ps1'), $PSCommandPath) |
        Where-Object { Test-Path $_ }
    if (-not $Force -and (Test-Path $out)) {
        $built = (Get-Item $out).LastWriteTime
        if (-not ($src | Where-Object { (Get-Item $_).LastWriteTime -gt $built })) { return $out }
    }
    $w = ($script:LolCard | ForEach-Object { $_.Syntax.Length } | Measure-Object -Maximum).Maximum
    $words = foreach ($c in $script:LolCard) {
        $h = if ($c.Highlight) { 'H' } else { ' ' }
        $p = if ($c.Proven) { 'proven ' + $c.Proven.Substring(5) } else { 'not walked yet' }
        '  {0} {1}  {2}' -f $h, $c.Syntax.PadRight($w), $c.What
        '    {0}  e.g.  {1}    ({2})' -f ''.PadRight($w), $c.Example, $p
    }
    $old = ($script:LolCard | Where-Object { $_.Old } | ForEach-Object { "{0} = {1}" -f $_.Old, $_.Word }) -join '  ·  '
    $aliases = Get-Content (Join-Path $script:PhxCmdRepo 'scripts\phoenix-aliases.ps1') -TotalCount 40 |
        Where-Object { $_ -match '^#\s{3}\S' } | ForEach-Object { '  ' + $_.TrimStart('#').Trim() }
    $card = @"
PHOENIX COMMANDS
Built $(Get-Date -Format 'yyyy-MM-dd HH:mm') from the command card in the code (scripts\usys.ps1). Do not edit: it rebuilds itself.

HOW TO
  Type the word bare in PowerShell 7, from any folder.  In cmd or Git Bash:  lol <word>
  H = highlight a file on screen (Windows Terminal copies it), then type the word.
      It says what it picked, uses it once, and clears it.   intake.  = the folder you are in.
  lol help <word>  = that word in full.

THE WORDS
$($words -join "`r`n")

OLD NAMES (still work, never needed)
  $old

ALIASES (scripts\phoenix-aliases.ps1)
$($aliases -join "`r`n")

HUD (tray icon = the Phoenix bird)
  click = the Console;  right-click = Run..., Suit look-up..., Ask Jarvis..., Screenshot for Claude, Hide the eye
  Right Ctrl = talk;  say "open the dock" / "close the dock"

RESTORE (the restoration disc; F:\Phoenix\Phoenix-DevOps-oS)
  python sector3\restore\phoenix_manifest.py check `$HOME\.phoenix\manifests\phoenix-manifest-pbmii.json    what differs from known-good
  python sector3\restore\phoenix_restore.py plan  `$HOME\.phoenix\manifests\phoenix-manifest-pbmii.json    what it would put back
"@
    try {
        [IO.File]::WriteAllText($out, $card, [Text.UTF8Encoding]::new($true))
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
