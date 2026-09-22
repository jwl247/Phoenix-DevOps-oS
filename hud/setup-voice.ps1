<#
.SYNOPSIS
    One-shot setup for HUD voice (Milestone 3) — downloads the local Whisper
    STT model and Piper TTS binary/voice, verifies Piper actually runs, then
    optionally builds the HUD.

.DESCRIPTION
    Automates the manual steps in hud/VOICE_SETUP.md. Idempotent — safe to
    re-run; already-installed files are left alone. Respects the same
    PHOENIX_WHISPER_MODEL_PATH / PHOENIX_PIPER_DIR / PHOENIX_PIPER_VOICE
    overrides VoiceSetup.cs reads from ~/.phoenix/phoenix.env, so this script
    and the running HUD never disagree about where to look.

.PARAMETER Build
    Also run `dotnet build` on hud/Hud.csproj after the models are in place.

.PARAMETER Launch
    Also launch Hud.exe after a successful build (implies -Build).

.EXAMPLE
    ./setup-voice.ps1
    ./setup-voice.ps1 -Build -Launch
#>
param(
    [switch]$Build,
    [switch]$Launch
)

$ErrorActionPreference = 'Stop'
if ($Launch) { $Build = $true }

function Read-PhoenixEnvOverride([string]$Key, [string]$Default) {
    $envFile = Join-Path $HOME '.phoenix\phoenix.env'
    if (Test-Path $envFile) {
        foreach ($line in Get-Content $envFile) {
            $line = $line.Trim()
            if ($line.Length -eq 0 -or $line.StartsWith('#')) { continue }
            $eq = $line.IndexOf('=')
            if ($eq -lt 1) { continue }
            $k = $line.Substring(0, $eq).Trim()
            $v = $line.Substring($eq + 1).Trim().Trim('"', "'")
            if ($k -eq $Key) { return $v }
        }
    }
    return $Default
}

$whisperModelPath = Read-PhoenixEnvOverride 'PHOENIX_WHISPER_MODEL_PATH' 'E:\Phoenix\voice-models\whisper\ggml-base.en.bin'
$piperDir          = Read-PhoenixEnvOverride 'PHOENIX_PIPER_DIR' 'E:\Phoenix\voice-models\piper'
$piperVoiceFile    = Read-PhoenixEnvOverride 'PHOENIX_PIPER_VOICE' 'en_US-lessac-medium.onnx'
$piperVoiceStem    = [IO.Path]::GetFileNameWithoutExtension($piperVoiceFile)

Write-Host "=== Phoenix HUD voice setup ===" -ForegroundColor Cyan
Write-Host "Whisper model : $whisperModelPath"
Write-Host "Piper dir     : $piperDir"
Write-Host "Piper voice   : $piperVoiceFile"
Write-Host ""

# --- 1. Whisper STT model --------------------------------------------------
$whisperDir = Split-Path $whisperModelPath -Parent
New-Item -ItemType Directory -Force -Path $whisperDir | Out-Null

if (Test-Path $whisperModelPath) {
    Write-Host "[whisper] already present, skipping download." -ForegroundColor DarkGray
} else {
    Write-Host "[whisper] downloading ggml-base.en.bin (~140MB)..." -ForegroundColor Yellow
    $whisperUrl = 'https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin'
    Invoke-WebRequest -Uri $whisperUrl -OutFile $whisperModelPath
    Write-Host "[whisper] done: $((Get-Item $whisperModelPath).Length / 1MB) MB" -ForegroundColor Green
}

# --- 2. Piper binary ---------------------------------------------------------
New-Item -ItemType Directory -Force -Path $piperDir | Out-Null
$piperExe = Join-Path $piperDir 'piper.exe'

if (Test-Path $piperExe) {
    Write-Host "[piper] binary already present, skipping download." -ForegroundColor DarkGray
} else {
    Write-Host "[piper] looking up latest Windows release..." -ForegroundColor Yellow
    $release = Invoke-RestMethod -Uri 'https://api.github.com/repos/rhasspy/piper/releases/latest' -Headers @{ 'User-Agent' = 'phoenix-hud-setup' }
    $asset = $release.assets | Where-Object { $_.name -match 'windows' } | Select-Object -First 1
    if (-not $asset) { throw "[piper] no Windows asset found in release $($release.tag_name)" }

    $zipPath = Join-Path $piperDir $asset.name
    Write-Host "[piper] downloading $($asset.name) ($([math]::Round($asset.size/1MB,1)) MB)..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zipPath

    $extractDir = Join-Path $piperDir '_extract'
    Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force

    # The release zip wraps everything in a top-level piper/ folder — flatten it.
    $inner = Join-Path $extractDir 'piper'
    $source = if (Test-Path $inner) { $inner } else { $extractDir }
    Get-ChildItem $source | Move-Item -Destination $piperDir -Force

    Remove-Item $extractDir -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item $zipPath -Force
    Write-Host "[piper] binary installed." -ForegroundColor Green
}

# --- 3. Piper voice model ----------------------------------------------------
$voiceOnnx = Join-Path $piperDir $piperVoiceFile
$voiceJson = "$voiceOnnx.json"

if ((Test-Path $voiceOnnx) -and (Test-Path $voiceJson)) {
    Write-Host "[piper-voice] '$piperVoiceStem' already present, skipping download." -ForegroundColor DarkGray
} else {
    # rhasspy/piper-voices lays voices out as en/en_US/<name>/<quality>/en_US-<name>-<quality>.onnx[.json]
    # Parse en_US-lessac-medium -> lessac / medium (works for the standard en_US-*-* naming scheme).
    if ($piperVoiceStem -notmatch '^en_US-([a-z0-9_]+)-([a-z]+)$') {
        throw "[piper-voice] can't infer the piper-voices path from '$piperVoiceStem' — download it manually, see hud/VOICE_SETUP.md"
    }
    $name = $Matches[1]
    $quality = $Matches[2]
    $base = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/$name/$quality"

    Write-Host "[piper-voice] downloading '$piperVoiceStem'..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri "$base/$piperVoiceStem.onnx" -OutFile $voiceOnnx
    Invoke-WebRequest -Uri "$base/$piperVoiceStem.onnx.json" -OutFile $voiceJson
    Write-Host "[piper-voice] done: $([math]::Round((Get-Item $voiceOnnx).Length/1MB,1)) MB" -ForegroundColor Green
}

# --- 4. Sanity-check Piper actually runs ------------------------------------
Write-Host "[piper] smoke-testing TTS..." -ForegroundColor Yellow
$testWav = Join-Path $piperDir '_setup_test.wav'
Push-Location $piperDir
try {
    "Phoenix HUD voice setup complete." | & .\piper.exe --model $piperVoiceFile --output_file $testWav 2>&1 | Out-Null
    if (-not (Test-Path $testWav)) { throw "[piper] smoke test produced no output file" }
    Write-Host "[piper] smoke test OK ($((Get-Item $testWav).Length) bytes)." -ForegroundColor Green
} finally {
    Remove-Item $testWav -Force -ErrorAction SilentlyContinue
    Pop-Location
}

Write-Host ""
Write-Host "=== Voice models ready ===" -ForegroundColor Cyan
Write-Host "  Whisper : $whisperModelPath"
Write-Host "  Piper   : $piperExe + $voiceOnnx"
Write-Host "  Hotkey  : Right Ctrl (override with PHOENIX_VOICE_HOTKEY in ~/.phoenix/phoenix.env)"

# --- 5. Optional build + launch ---------------------------------------------
if ($Build) {
    Write-Host ""
    Write-Host "=== Building HUD ===" -ForegroundColor Cyan
    $hudDir = Split-Path $PSCommandPath -Parent
    Push-Location $hudDir
    try {
        dotnet build
        if ($LASTEXITCODE -ne 0) { throw "dotnet build failed (exit $LASTEXITCODE)" }
    } finally {
        Pop-Location
    }
}

if ($Launch) {
    $exeDir = Join-Path (Split-Path $PSCommandPath -Parent) 'bin\Debug\net9.0-windows'
    $exe = Join-Path $exeDir 'Hud.exe'
    if (-not (Test-Path $exe)) { throw "Hud.exe not found at $exe after build" }
    Write-Host ""
    Write-Host "=== Launching Hud.exe ===" -ForegroundColor Cyan
    Start-Process -FilePath $exe -WorkingDirectory $exeDir
    Write-Host "Hold Right Ctrl, speak, release. Watch the scanner bar and listen for the reply." -ForegroundColor Green
}
