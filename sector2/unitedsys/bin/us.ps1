# us.ps1 — Windows entry point for the UnitedSys CLI (mirror of bin/us).
# UnitedSys — United Systems | jwl247 | GPL-3.0
#
# Runs `python -m core.us` with unitedsys/ on PYTHONPATH (no cd, so relative
# arguments like `us intake-dir .\dir` resolve against the caller's folder).
# Python is found by actually running --version: the Microsoft Store
# "python"/"python3" aliases resolve on PATH but only open a Store prompt.
# PHOENIX_PYTHON overrides the search. Was a 0-byte file before 2026-09-29
# (audit S2CORE-F20).

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

function Find-UsPython {
    if ($env:PHOENIX_PYTHON) { return $env:PHOENIX_PYTHON }
    foreach ($name in 'python', 'python3', 'py') {
        $cmd = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $cmd) { continue }
        try {
            $ver = & $cmd.Source --version 2>&1
            if ($LASTEXITCODE -eq 0 -and "$ver" -match '^Python 3\.') { return $cmd.Source }
        } catch { continue }
    }
    return $null
}

$py = Find-UsPython
if (-not $py) {
    Write-Error 'us: no working Python 3 found (install Python 3.11+ or set PHOENIX_PYTHON)'
    exit 1
}

$sep = [IO.Path]::PathSeparator
$env:PYTHONPATH = if ($env:PYTHONPATH) { "$root$sep$env:PYTHONPATH" } else { $root }
& $py -m core.us @args
exit $LASTEXITCODE
