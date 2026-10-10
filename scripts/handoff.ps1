# handoff.ps1 — the session handoff lives in the clone pool (R2), not the public repo (Jerry 2026-10-09).
# Phoenix DevOps OS | jwl247 | GPL v3
#
# CLAUDE.md carries ONE marker line (name + SHA3-512 prefix, nothing else):
#   <!-- handoff: HANDOFF-2026-10-09-day.md sha3:5092da9a5396fe32 -->
#
#   pwsh -NoProfile -File scripts\handoff.ps1 pull          # get it from the pool, check SHA3, print it
#   pwsh -NoProfile -File scripts\handoff.ps1 push <file>   # intake it, write the marker into CLAUDE.md
#
# `pull` is what the SessionStart hook runs: a bad hash or a failed get prints a loud STOP, never the text.
param([Parameter(Position = 0)][ValidateSet('pull', 'push')][string]$Verb = 'pull',
      [Parameter(Position = 1)][string]$File)

$ErrorActionPreference = 'Stop'
$repo   = Split-Path $PSScriptRoot -Parent
$claude = Join-Path $repo 'CLAUDE.md'
$home_  = Join-Path $env:USERPROFILE '.phoenix\handoff'
$marker = '<!-- handoff: (?<name>HANDOFF-[\w.-]+\.md) sha3:(?<sha>[0-9a-f]{16}) -->'

function Get-Sha3Prefix([string]$Path) {
    (& python -c "import hashlib,sys;print(hashlib.sha3_512(open(sys.argv[1],'rb').read()).hexdigest()[:16])" $Path).Trim()
}

function Invoke-Usys([string]$Word, [string[]]$Rest) {
    . (Join-Path $repo 'scripts\usys.ps1') 3>$null
    Invoke-UsysMain -Command $Word -Rest $Rest *>&1 | Out-String
}

if ($Verb -eq 'pull') {
    $m = [regex]::Match((Get-Content $claude -Raw), $marker)
    if (-not $m.Success) { "HANDOFF: no marker in CLAUDE.md - nothing pulled."; exit 0 }
    $name = $m.Groups['name'].Value; $want = $m.Groups['sha'].Value
    New-Item -ItemType Directory -Force $home_ | Out-Null
    $dst = Join-Path $home_ $name
    Remove-Item $dst -Force -ErrorAction SilentlyContinue
    Push-Location $home_
    try { $log = Invoke-Usys 'get' @($name) } finally { Pop-Location }
    if (-not (Test-Path $dst)) { "HANDOFF STOP: get $name failed - not pulled.`n$log"; exit 0 }
    $got = Get-Sha3Prefix $dst
    if ($got -ne $want) { "HANDOFF STOP: $name SHA3 $got does not match CLAUDE.md $want - not trusted, not shown."; exit 0 }
    "HANDOFF (from the clone pool, SHA3-512 $got... matches CLAUDE.md, copy at $dst):"
    ""
    Get-Content $dst -Raw
    exit 0
}

# push
if (-not $File -or -not (Test-Path $File)) { throw "usage: handoff.ps1 push <HANDOFF-....md>" }
$full = (Resolve-Path $File).Path
$name = Split-Path $full -Leaf
if ($name -notmatch '^HANDOFF-[\w.-]+\.md$') { throw "handoff file must be named HANDOFF-<date>-<part>.md" }
Push-Location (Split-Path $full -Parent)
try { $log = Invoke-Usys 'intake' @($name) } finally { Pop-Location }
$log
$sha  = Get-Sha3Prefix $full
$text = Get-Content $claude -Raw
$line = "<!-- handoff: $name sha3:$sha -->"
$text = if ([regex]::IsMatch($text, $marker)) { [regex]::Replace($text, $marker, $line) } else { $text.TrimEnd() + "`n$line`n" }
[IO.File]::WriteAllText($claude, $text, [Text.UTF8Encoding]::new($false))
"CLAUDE.md marker -> $line"
