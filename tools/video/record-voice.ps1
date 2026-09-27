# record-voice.ps1 — record Jerry's voice from the V8S sound card for a video.
# UnitedSys — United Systems | jwl247 | GPL-3.0
#
# The phone records the picture, this records the sound (the V8S + a mic a
# hand's width away sounds far better than the phone's own mic). Clap once at
# the start; the edit lines the two up. Desktop shortcut: "Record voice".
# Press Q in the window to stop. Files: E:\Phoenix\video\raw\voice-<date-time>.wav
param([string]$Device = "Microphone (V8S)", [string]$OutDir = "E:\Phoenix\video\raw")

$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
$Host.UI.RawUI.WindowTitle = "Record voice (V8S)"
New-Item -ItemType Directory -Force $OutDir | Out-Null
$out = Join-Path $OutDir ("voice-{0}.wav" -f (Get-Date -Format "yyyyMMdd-HHmmss"))

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host "ffmpeg isn't installed (winget install Gyan.FFmpeg)." -ForegroundColor Red; Read-Host "Enter to close"; exit 1
}
$devices = & ffmpeg -hide_banner -list_devices true -f dshow -i dummy 2>&1 | Out-String
if ($devices -notmatch [regex]::Escape($Device)) {
    Write-Host "The V8S isn't plugged in (no '$Device' found). Plug in its USB cable and try again." -ForegroundColor Red
    Read-Host "Enter to close"; exit 1
}

Write-Host ""
Write-Host "  RECORDING your voice from the V8S." -ForegroundColor Green
Write-Host "  1. Start the phone camera recording too."
Write-Host "  2. Clap once so the edit can line them up."
Write-Host "  3. Press Q in this window when you're done."
Write-Host ""
& ffmpeg -hide_banner -loglevel error -stats -f dshow -i "audio=$Device" -c:a pcm_s16le $out
Write-Host ""
if (Test-Path $out) {
    $s = [math]::Round((Get-Item $out).Length / 1MB, 1)
    Write-Host "  Saved: $out ($s MB)" -ForegroundColor Green
} else {
    Write-Host "  Nothing was saved." -ForegroundColor Red
}
Read-Host "  Enter to close"
