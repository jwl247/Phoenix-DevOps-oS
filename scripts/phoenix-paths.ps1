# phoenix-paths.ps1 — slash-insensitive paths for every Phoenix command (PS7 side).
# Phoenix DevOps OS | jwl247 | GPL v3
#
# Jerry 2026-10-07: "make a wrapper that makes all our system slash insensitive, seeing how we are
# Windows and Linux". One rule, three copies that must agree (tested together):
#   scripts/phoenix-paths.ps1   PS7      (this file; loaded by usys.ps1)
#   bin/phoenix-paths.sh        bash     (Git Bash + Linux; sourced by bin/intake, bin/clone)
#   scripts/phoenix_paths.py    Python
# Accepts F:\x  F:/x  /f/x (Git Bash)  /mnt/f/x (WSL-style)  ~/x  ~\x  .\x  ./x  `quoted`  "quoted".
# Only arguments that LOOK like a path are touched: URLs (https://...), flags (-x, --x) and words pass through.
#   ConvertTo-PhoenixPath '/f/Phoenix/x'    -> F:\Phoenix\x
#   px notepad /f/Phoenix/Phoenix-DevOps-oS/CLAUDE.md     run ANY program with its path arguments fixed

function ConvertTo-PhoenixPath([string]$Text) {
    if ($null -eq $Text) { return $null }
    $t = ($Text -split "`r?`n" | Where-Object { $_.Trim() } | Select-Object -First 1)
    if (-not $t) { return $t }
    $t = $t.Trim().Trim('`', '"', "'").Trim()
    if ($t -match '^[a-zA-Z][a-zA-Z0-9+.-]+://') { return $t }              # a URL, not a path
    $t = $t -replace '^file:///?', ''
    if ($t -match '^/mnt/([a-zA-Z])(/.*)?$') { $t = "$($Matches[1]):$($Matches[2])" }
    elseif ($t -match '^/([a-zA-Z])(/.*)$') { $t = "$($Matches[1]):$($Matches[2])" }   # /c alone is a flag, not a drive   # /f/Phoenix -> f:/Phoenix
    if ($t -match '^~([\\/].*)?$') { $t = $HOME + $Matches[1] }
    $t = $t -replace '/', '\'
    if ($t -match '^[a-z]:') { $t = $t.Substring(0, 1).ToUpper() + $t.Substring(1) }
    if ($t -match '^[A-Z]:$') { $t += '\' }
    return $t
}

function Test-PhoenixPathLike([string]$Arg) {
    if (-not $Arg -or $Arg -match '^-') { return $false }                   # flags stay flags
    if ($Arg -match '^[a-zA-Z][a-zA-Z0-9+.-]+://') { return $false }        # URLs stay URLs
    return $Arg -match '^([a-zA-Z]:[\\/]|[a-zA-Z]:$|/mnt/[a-zA-Z](/|$)|/[a-zA-Z]/|~[\\/]|\.{1,2}[\\/])' -or $Arg.Contains('\')
}

function Resolve-PhoenixArgs([string[]]$ArgList) {
    , [string[]]@($ArgList | ForEach-Object { if (Test-PhoenixPathLike $_) { ConvertTo-PhoenixPath $_ } else { $_ } })
}

function global:px {
    if ($args.Count -eq 0) { Write-Host '  px <command> [args...]   runs it with any path arguments made native (F:\, /f/, ~/ ...)'; return }
    $cmd = $args[0]
    $rest = if ($args.Count -gt 1) { Resolve-PhoenixArgs ([string[]]$args[1..($args.Count - 1)]) } else { @() }
    & $cmd @rest
}
