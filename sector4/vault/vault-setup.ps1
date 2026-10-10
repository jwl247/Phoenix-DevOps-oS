<#
vault-setup.ps1 — Phoenix encrypted vault: bucket, worker, first push, proof
Phoenix DevOps OS | jwl247 | GPL v3

Run it in YOUR PowerShell window (it asks for the passphrase — it must be you typing):
  pwsh -File F:\Phoenix\Phoenix-DevOps-oS\sector4\vault\vault-setup.ps1
  pwsh -File F:\Phoenix\Phoenix-DevOps-oS\sector4\vault\vault-setup.ps1 -DryRun

Re-run any time the vault changes: it re-seals and uploads; the bucket/worker
steps skip themselves. Choose a passphrase of a few random words (16+
characters) and write it on paper somewhere that is NOT this PC.
#>
[CmdletBinding()]
param([switch] $DryRun)

$ErrorActionPreference = "Stop"
$Repo      = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$WorkerDir = Join-Path $PSScriptRoot "worker"
$Npx       = if (Get-Command npx.cmd -ErrorAction SilentlyContinue) { "npx.cmd" } else { "npx" }
$Url       = "https://phoenix-vault-worker.phoenix-jwl.workers.dev"

function Step($n, $t) { Write-Host "`n[$n/5] $t" -ForegroundColor Cyan }
function Ok($t)       { Write-Host "      OK  $t" -ForegroundColor Green }
function Fail($t)     { Write-Host "      FAILED  $t" -ForegroundColor Red; exit 1 }
function Run([string] $What, [scriptblock] $Cmd) {
    if ($DryRun) { Write-Host "      would run: $What" -ForegroundColor DarkGray; return "" }
    $out = & $Cmd 2>&1 | Out-String
    if ($LASTEXITCODE -ne 0) { Write-Host $out; Fail $What }
    return $out
}

if ($DryRun) { Write-Host "DRY RUN - nothing will be changed" -ForegroundColor Yellow }
python -c "import cryptography" 2>$null; if ($LASTEXITCODE -ne 0) { Fail "python 'cryptography' package missing" }

Step 1 "tests"
Push-Location $Repo
try {
    Run "python sector6/test_phoenix_vault.py" { python sector6/test_phoenix_vault.py } | Out-Null
    Run "node sector4/vault/worker/test/vault.test.mjs" { node sector4/vault/worker/test/vault.test.mjs } | Out-Null
    if (-not $DryRun) { Ok "vault tool + worker" }
} finally { Pop-Location }

Push-Location $WorkerDir
try {
    Step 2 "R2 bucket phoenix-vault"
    $list = Run "$Npx wrangler r2 bucket list" { & $Npx wrangler r2 bucket list }
    if ($DryRun) { Write-Host "      would create it if missing" -ForegroundColor DarkGray }
    elseif ($list -match "(?m)\bphoenix-vault\b") { Ok "already exists" }
    else { Run "create bucket" { & $Npx wrangler r2 bucket create phoenix-vault } | Out-Null; Ok "created" }

    Step 3 "deploy phoenix-vault-worker"
    $dep = Run "$Npx wrangler deploy" { & $Npx wrangler deploy }
    if (-not $DryRun) { Ok (($dep -split "`n" | Where-Object { $_ -match "Current Version ID" }) -join "").Trim() }
} finally { Pop-Location }

Step 4 "seal and upload the vault (you type the passphrase, twice)"
if ($DryRun) { Write-Host "      would run: python sector6/phoenix_vault.py push" -ForegroundColor DarkGray }
else {
    Push-Location $Repo
    try { python sector6/phoenix_vault.py push; if ($LASTEXITCODE -ne 0) { Fail "push" } } finally { Pop-Location }
    Ok "sealed, uploaded, fetch key registered"
}

Step 5 "prove it: pull the cloud copy back and compare (passphrase once more)"
if ($DryRun) { Write-Host "      would run: python sector6/phoenix_vault.py verify" -ForegroundColor DarkGray; exit 0 }
Start-Sleep -Seconds 3
Push-Location $Repo
try { python sector6/phoenix_vault.py --url $Url verify; if ($LASTEXITCODE -ne 0) { Fail "verify" } } finally { Pop-Location }
Ok "the cloud copy opens with your passphrase and matches the vault"

Write-Host "`nVault is live. On a new Debian box:" -ForegroundColor Green
Write-Host "  sudo apt install -y python3-cryptography curl"
Write-Host "  curl -fsSL $Url/pull.py -o phoenix_vault.py"
Write-Host "  sudo python3 phoenix_vault.py pull --keys PHOENIX_AUTH,PHOENIX_WORKER_URL"
