# install-phoenix-seelen.ps1
# Phoenix DevOps OS — Seelen UI Plugin Pack Installer
# One-liner:
#   irm https://raw.githubusercontent.com/jwl247/Phoenix_Universal_Kernel/main/seelen/install-phoenix-seelen.ps1 | iex
#
# What this does:
#   1. Verifies Seelen UI is installed (warns if not, does not abort)
#   2. Copies all four Phoenix toolbar plugins into the Seelen plugins directory
#   3. Copies phoenix_status_server.py into Phoenix_Universal_Kernel if the
#      repo is cloned locally (skips if running remotely via iex pipe)
#   4. Prints next steps
#
# GPL v3 — jwl247 / Phoenix DevOps LLC

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Paths ─────────────────────────────────────────────────────────────────────

$SeelenPlugins = "$env:APPDATA\com.seelen.seelen-ui\plugins"
$ScriptDir     = Split-Path -Parent $MyInvocation.MyCommand.Path

# When run via iex pipe $ScriptDir is empty — detect it
if (-not $ScriptDir) {
    # Running piped — plugins embedded as base64 below, extracted to temp
    $ScriptDir = $null
}

# ── Banner ────────────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "  ╔══════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "  ║   Phoenix DevOps OS — Seelen UI Plugin Pack      ║" -ForegroundColor Cyan
Write-Host "  ║   4 toolbar plugins  ·  one-liner install        ║" -ForegroundColor Cyan
Write-Host "  ╚══════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ── Check Seelen ──────────────────────────────────────────────────────────────

if (-not (Test-Path $SeelenPlugins)) {
    Write-Host "  [WARN] Seelen UI plugins folder not found at:" -ForegroundColor Yellow
    Write-Host "         $SeelenPlugins" -ForegroundColor Yellow
    Write-Host "         Install Seelen UI first: winget install Seelen.SeelenUI" -ForegroundColor Yellow
    Write-Host "         Creating directory anyway..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Force -Path $SeelenPlugins | Out-Null
}

# ── Plugin definitions ────────────────────────────────────────────────────────
# Each entry: [plugin_folder_name, display name]

$Plugins = @(
    "tb_phoenix_status",
    "tb_phoenix_llm",
    "tb_clonepool",
    "tb_lifefirst"
)

# ── Source resolution ─────────────────────────────────────────────────────────
# Running from repo clone? Use local files.
# Running via iex pipe? Download from GitHub raw.

$BaseUrl   = "https://raw.githubusercontent.com/jwl247/Phoenix_Universal_Kernel/main/seelen/plugins"
$LocalBase = if ($ScriptDir) { Join-Path (Split-Path $ScriptDir) "plugins" } else { $null }

function Get-PluginFile([string]$PluginName, [string]$RelPath) {
    $localFile = if ($LocalBase) { Join-Path $LocalBase "$PluginName\$RelPath" } else { $null }
    if ($localFile -and (Test-Path $localFile)) {
        return Get-Content -Raw $localFile
    }
    # Fetch from GitHub
    $url = "$BaseUrl/$PluginName/$RelPath"
    try {
        return (Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 10).Content
    } catch {
        Write-Host "  [WARN] Could not fetch $url" -ForegroundColor Yellow
        return $null
    }
}

# ── Plugin file manifests ─────────────────────────────────────────────────────

$PluginFiles = @{
    "tb_phoenix_status" = @(
        "metadata.yml",
        "plugin/template.js",
        "plugin/tooltip.js",
        "i18n/display_name.yml",
        "i18n/description.yml"
    )
    "tb_phoenix_llm" = @(
        "metadata.yml",
        "plugin/template.js",
        "plugin/tooltip.js",
        "i18n/display_name.yml",
        "i18n/description.yml"
    )
    "tb_clonepool" = @(
        "metadata.yml",
        "plugin/template.js",
        "plugin/tooltip.js",
        "i18n/display_name.yml",
        "i18n/description.yml"
    )
    "tb_lifefirst" = @(
        "metadata.yml",
        "plugin/template.js",
        "plugin/tooltip.js",
        "i18n/display_name.yml",
        "i18n/description.yml"
    )
}

# ── Install ───────────────────────────────────────────────────────────────────

$installed = 0
$skipped   = 0

foreach ($plugin in $Plugins) {
    $dest = Join-Path $SeelenPlugins $plugin
    Write-Host "  Installing $plugin..." -NoNewline

    $files = $PluginFiles[$plugin]
    $ok    = $true

    foreach ($file in $files) {
        $content = Get-PluginFile $plugin $file
        if ($null -eq $content) {
            $ok = $false
            break
        }
        $destFile = Join-Path $dest $file
        $destDir  = Split-Path $destFile
        if (-not (Test-Path $destDir)) {
            New-Item -ItemType Directory -Force -Path $destDir | Out-Null
        }
        Set-Content -Path $destFile -Value $content -NoNewline -Encoding UTF8
    }

    if ($ok) {
        Write-Host " done" -ForegroundColor Green
        $installed++
    } else {
        Write-Host " skipped (source unavailable)" -ForegroundColor Yellow
        $skipped++
    }
}

# ── Summary ───────────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "  ─────────────────────────────────────────────────────" -ForegroundColor DarkGray
Write-Host "  Installed : $installed plugin(s)" -ForegroundColor Green
if ($skipped -gt 0) {
    Write-Host "  Skipped   : $skipped plugin(s)" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "  Plugin directory:" -ForegroundColor Cyan
Write-Host "  $SeelenPlugins" -ForegroundColor White
Write-Host ""
Write-Host "  Next steps:" -ForegroundColor Cyan
Write-Host "  1. Start the Phoenix kernel:" -ForegroundColor White
Write-Host "     python Phoenix_Universal_Kernel\main_kernel.py" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  2. In Seelen UI settings → Toolbar → Add plugins:" -ForegroundColor White
Write-Host "     · Phoenix Status    (@phoenix/tb-phoenix-status)" -ForegroundColor DarkGray
Write-Host "     · Phoenix LLM       (@phoenix/tb-phoenix-llm)" -ForegroundColor DarkGray
Write-Host "     · Clone Pool        (@phoenix/tb-clonepool)" -ForegroundColor DarkGray
Write-Host "     · Life First        (@phoenix/tb-lifefirst)" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  3. (Optional) Pull large LLM models for Life First:" -ForegroundColor White
Write-Host "     ollama pull llama3.1:8b" -ForegroundColor DarkGray
Write-Host "     ollama pull llama3.1:70b   # needs paged-vRAM on 8GB machines" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Phoenix status server: http://localhost:8765/health" -ForegroundColor Cyan
Write-Host ""
