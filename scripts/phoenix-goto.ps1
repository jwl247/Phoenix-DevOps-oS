# phoenix-goto.ps1 — `g`: highlight a path anywhere on screen, type g, you're there.
# Phoenix DevOps OS | jwl247 | GPL v3
#
# Jerry 2026-10-07: "highlight a path on your screen and it will go there".
# Windows Terminal "copy on select" puts the highlighted text on the clipboard; `g` reads it.
#   g             go to the path on the clipboard
#   g <path>      go to that path (same rules)
#   g -Open       also open it: a folder in Explorer, a file with its default app
# Understands what Claude and the tools print: F:\x\y, F:/x/y, /f/x/y (Git Bash), /mnt/f/x,
# ~\x or ~/x, `wrapped`, "quoted", a trailing :123 or :12:5 line number, a repo-relative
# sector2/x path (tried from the repo). A folder -> you're in it. A file -> you're in its
# folder and it's named. Nothing on the clipboard that exists -> says so, goes nowhere.

function ConvertTo-PhoenixPath([string]$Text) {
    $t = ($Text -split "`r?`n" | Where-Object { $_.Trim() } | Select-Object -First 1)
    if (-not $t) { return $null }
    $t = $t.Trim().Trim('`', '"', "'", '<', '>', '(', ')', '[', ']', ',', ';').Trim()
    $t = $t -replace '^file:///?', ''
    $t = $t -replace '(:\d+){1,2}$', ''                                   # file.py:123  /  file.py:12:5
    if ($t -match '^/mnt/([a-zA-Z])(/.*)?$') { $t = "$($Matches[1]):$($Matches[2])" }
    elseif ($t -match '^/([a-zA-Z])(/.*)?$') { $t = "$($Matches[1]):$($Matches[2])" }   # /f/Phoenix -> f:/Phoenix
    if ($t -match '^~([\\/].*)?$') { $t = $HOME + $Matches[1] }
    $t = $t -replace '/', '\'
    if ($t -match '^[a-z]:') { $t = $t.Substring(0, 1).ToUpper() + $t.Substring(1) }
    return $t
}

function Invoke-PhoenixGoto {
    [CmdletBinding()]
    param([Parameter(Position = 0)][string]$Path, [switch]$Open)
    $raw = if ($Path) { $Path } else { Get-Clipboard -Raw -ErrorAction SilentlyContinue }
    if (-not $raw) { Write-Host '  g: clipboard is empty - highlight a path first' -ForegroundColor Yellow; return }
    $p = ConvertTo-PhoenixPath $raw
    $cands = @($p)
    if ($p -and -not [IO.Path]::IsPathRooted($p)) {                       # repo-relative, as Claude prints them
        $repo = [Environment]::GetEnvironmentVariable('PHOENIX_ROOT', 'User')
        if ($repo) { $cands += (Join-Path $repo $p) }
    }
    $hit = $cands | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
    if (-not $hit) { Write-Host "  g: not found: $p" -ForegroundColor Yellow; return }
    $item = Get-Item -LiteralPath $hit -Force
    if ($item.PSIsContainer) {
        Set-Location -LiteralPath $item.FullName
        if ($Open) { Start-Process explorer.exe -ArgumentList "`"$($item.FullName)`"" }
    } else {
        Set-Location -LiteralPath $item.DirectoryName
        Write-Host "  file: $($item.Name)" -ForegroundColor Cyan
        if ($Open) { Invoke-Item -LiteralPath $item.FullName }
    }
}
Set-Alias -Name g -Value Invoke-PhoenixGoto -Scope Global -Force
