# phoenix-rotate.ps1 — `rotate-key`: rotate PHOENIX_AUTH everywhere in one command (PS7).
# Phoenix DevOps OS | jwl247 | GPL v3
#
#   rotate-key              rotate the key on every worker + this PC + the vault, then push the vault
#   rotate-key -SaveKey     same, and keep the vault passphrase for next time, encrypted under YOUR
#                           Windows account (DPAPI): only you, logged in as you, on this PC can open it
#   rotate-key -ForgetKey   delete the saved passphrase
#
# Loaded by the PS7 profile (scripts\usys.ps1 dot-sources it). Steps it runs:
#   1. sector2/package-handler/rotate-phoenix-auth.sh in Git Bash: new key -> packages-worker,
#      office-notify-worker, pbm-radar-worker (each verified) -> HKCU\Environment -> vault master
#   2. scripts/phoenix_vault.py push (the cloud copy boxes pull from)
#   3. this window picks up the new key; other windows need reopening
# The key is never printed. The passphrase never touches a command line.

$script:PhoenixVaultPassFile = Join-Path $HOME '.phoenix\vault-pass.dpapi.xml'

function Invoke-PhoenixRotate {
    [CmdletBinding()]
    param([switch]$SaveKey, [switch]$ForgetKey)

    if ($ForgetKey) {
        Remove-Item $script:PhoenixVaultPassFile -ErrorAction SilentlyContinue
        Write-Host '  rotate-key: saved vault passphrase deleted' -ForegroundColor Green
        return
    }
    $repo = [Environment]::GetEnvironmentVariable('PHOENIX_ROOT', 'User')
    if (-not $repo -or -not (Test-Path (Join-Path $repo 'sector2\package-handler\rotate-phoenix-auth.sh'))) {
        Write-Host '  rotate-key: PHOENIX_ROOT is not the repo' -ForegroundColor Red; return
    }
    $bash = @("$env:ProgramFiles\Git\bin\bash.exe", "${env:ProgramFiles(x86)}\Git\bin\bash.exe") | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
    if (-not $bash) { Write-Host '  rotate-key: Git Bash not found' -ForegroundColor Red; return }

    # 1. rotate (workers + registry + vault master); the script stops on any failed leg
    $sh = (Join-Path $repo 'sector2\package-handler\rotate-phoenix-auth.sh') -replace '\\', '/'
    & $bash -lc "exec bash `"$sh`""
    if ($LASTEXITCODE -ne 0) { Write-Host '  rotate-key: rotation stopped - see above; vault NOT pushed' -ForegroundColor Red; return }

    # 2. push the vault; passphrase from the DPAPI file if you saved one, else asked
    $pass = $null
    if (Test-Path $script:PhoenixVaultPassFile) {
        try { $pass = Import-Clixml $script:PhoenixVaultPassFile } catch { $pass = $null }
    }
    if (-not $pass) { $pass = Read-Host '  vault passphrase' -AsSecureString }
    if ($SaveKey) {
        New-Item -ItemType Directory -Force (Split-Path $script:PhoenixVaultPassFile) | Out-Null
        $pass | Export-Clixml $script:PhoenixVaultPassFile          # DPAPI: bound to this Windows user + PC
        icacls $script:PhoenixVaultPassFile /inheritance:r /grant:r "$($env:USERNAME):F" | Out-Null
        Write-Host '  rotate-key: passphrase saved under your Windows account (rotate-key -ForgetKey removes it)' -ForegroundColor Green
    }
    $env:PHOENIX_VAULT_PASSPHRASE = [Net.NetworkCredential]::new('', $pass).Password
    try {
        python (Join-Path $repo 'scripts\phoenix_vault.py') push
        $ok = ($LASTEXITCODE -eq 0)
    } finally { Remove-Item Env:PHOENIX_VAULT_PASSPHRASE -ErrorAction SilentlyContinue }
    if (-not $ok) { Write-Host '  rotate-key: vault push failed - workers + this PC already have the new key; rerun: python scripts\phoenix_vault.py push' -ForegroundColor Yellow; return }

    # 3. this window gets the new key now
    $env:PHOENIX_AUTH = [Environment]::GetEnvironmentVariable('PHOENIX_AUTH', 'User')
    Write-Host '  rotate-key: done - workers, this PC, vault master and the cloud vault all hold the new key. Reopen other windows.' -ForegroundColor Green
}
Set-Alias -Name rotate-key -Value Invoke-PhoenixRotate -Scope Global -Force
