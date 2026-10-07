#Requires -Version 7.0
# ============================================================
# Phoenix Global Clone -- clone.ps1  (forwarder)
# USys -- United Systems | jwl247 -- GPL v3
#
# `clone` takes a file OUT of the clone pool: this runs bin\clone.cmd (Git Bash ->
# bin/clone), the one clone engine. Until 2026-10-07 this file defined the OLD
# `clone` = IN (intake), the opposite of every other `clone` (audit CMDWALK-F06,
# S34OPS-F41). To put something INTO the pool: `intake <file-or-folder>`.
# Normally not needed at all: install.ps1 puts clone on PATH.
# ============================================================

function global:clone {
    $cmd = Join-Path $PSScriptRoot '..\bin\clone.cmd'
    if (-not (Test-Path $cmd)) { Write-Error "[clone] bin\clone.cmd not found beside tools\"; return }
    & $cmd @args
}
