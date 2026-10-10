# install-security.ps1 — Phoenix file motion sensor on PBMII (Windows).
# Phoenix DevOps OS | jwl247 | GPL v3
# Run in PS7 from sector6\apps\security:  .\install-security.ps1
# Copies the suit to ~\.phoenix\security\bin, makes the baseline, registers a scheduled task
# (every 5 min, as you, no admin needed). The Genie suit is the same file: genie import security.py
$ErrorActionPreference = 'Stop'
$home_ = Join-Path $env:USERPROFILE '.phoenix\security'
$bin = Join-Path $home_ 'bin'
New-Item -ItemType Directory -Force $bin | Out-Null
Copy-Item (Join-Path $PSScriptRoot 'suits\security.py') $bin -Force
$py = (Get-Command python).Source
$sec = Join-Path $bin 'security.py'
if (-not (Test-Path (Join-Path $home_ 'state.json'))) { & $py $sec baseline | Out-Null }
$pyw = Join-Path (Split-Path $py) 'pythonw.exe'; if (-not (Test-Path $pyw)) { $pyw = $py }   # no console window popping up every 5 min
$act = New-ScheduledTaskAction -Execute $pyw -Argument "`"$sec`" scan" -WorkingDirectory $bin
$trg = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5)
$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
Register-ScheduledTask -TaskName 'Phoenix Security Scan' -Action $act -Trigger $trg -Settings $set -Force | Out-Null
& $py $sec status
