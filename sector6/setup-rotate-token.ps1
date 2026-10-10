# setup-rotate-token.ps1 — put CF_ACCESS_ROTATE_TOKEN into the vault, safely, once.
# Phoenix DevOps OS | jwl247 | GPL v3
#
# Jerry 2026-10-07: "make it a script" (so nothing gets messed up).
# Run it yourself in a PowerShell 7 window:
#   & F:\Phoenix\Phoenix-DevOps-oS\sector6\setup-rotate-token.ps1
# What it does:
#   1. opens Cloudflare's API Tokens page and shows the exact 4 settings to pick
#   2. asks you to paste the token - typed hidden, never shown, never on a command line
#   3. proves it before saving: active, and it can see the usys-cli service token on the
#      jw.leftwich1 account. Wrong token -> nothing is written.
#   4. writes CF_ACCESS_ROTATE_TOKEN=... into phoenix-secrets.env (never the .template),
#      right under CF_ACCESS_CLIENT_SECRET; replaces an old line if there is one; backup first.
# ONLY JERRY: his Windows account, a real console, not Claude/Jarvis/a script (rule 10).
$ErrorActionPreference = 'Stop'
$OwnerSid = 'S-1-5-21-1896517873-2457859212-3872445003-1001'      # Jerry (jwlef) on PBMII - not a secret
$Vault = 'F:\Phoenix\Vault\secrets\phoenix-secrets.env'
$Account = 'ed936f2c71a0d788e39b8f44200df76d'                     # Jw.leftwich1@gmail.com's Account - not a secret

function Say($t, $c = 'Gray') { Write-Host "  $t" -ForegroundColor $c }

if ([Security.Principal.WindowsIdentity]::GetCurrent().User.Value -ne $OwnerSid) { Say 'refused - Jerry''s Windows account only' Red; return }
if ($env:CLAUDECODE -or $env:CLAUDE_CODE_ENTRYPOINT -or $Host.Name -ne 'ConsoleHost' -or [Console]::IsInputRedirected) {
    Say 'refused - run it yourself in a PowerShell 7 window (not from Claude, Jarvis or a script)' Red; return
}
if (-not (Test-Path $Vault)) { Say "vault file not found: $Vault (is F: the PHOENIX drive?)" Red; return }

Write-Host ''
Say 'STEP 1 - make the token (the page opens now, logged in as jw.leftwich1):' Cyan
Say 'Create Token -> Custom token "Get started", then set exactly:'
Say '  Token name ........ phoenix-access-rotate'
Say '  Permissions ....... Account | Access: Service Tokens | Edit     (ONE row only)'
Say '  Account Resources . Include | Jw.leftwich1@gmail.com''s Account'
Say '  -> Continue to summary -> Create Token -> Copy'
Start-Process 'https://dash.cloudflare.com/profile/api-tokens'
Write-Host ''
$sec = Read-Host '  STEP 2 - paste the token here (hidden), then Enter' -AsSecureString
$tok = [Net.NetworkCredential]::new('', $sec).Password.Trim()
if ($tok.Length -lt 30 -or $tok -match '\s') { Say 'that does not look like a Cloudflare token - nothing written' Red; return }

Say 'STEP 3 - checking it with Cloudflare before saving...' Cyan
$h = @{ Authorization = "Bearer $tok" }
try {
    $v = Invoke-RestMethod -Uri 'https://api.cloudflare.com/client/v4/user/tokens/verify' -Headers $h -TimeoutSec 20
    if ($v.result.status -ne 'active') { Say "token is $($v.result.status), not active - nothing written" Red; return }
    $list = Invoke-RestMethod -Uri "https://api.cloudflare.com/client/v4/accounts/$Account/access/service_tokens" -Headers $h -TimeoutSec 20
    if (-not ($list.result | Where-Object name -eq 'usys-cli')) { Say 'token works but cannot see usys-cli on jw.leftwich1 - wrong account picked? nothing written' Red; return }
} catch {
    Say "Cloudflare refused it ($($_.Exception.Response.StatusCode)) - check the permission row and the account; nothing written" Red; return
} finally { $h = $null }
Say 'token is active and can see usys-cli on jw.leftwich1' Green

Say 'STEP 4 - writing the vault line...' Cyan
$raw = [IO.File]::ReadAllText($Vault)
$nl = if ($raw.Contains("`r`n")) { "`r`n" } else { "`n" }
Copy-Item $Vault "$Vault.bak-$(Get-Date -Format yyyyMMdd-HHmmss)"
$lines = [Collections.Generic.List[string]]($raw -split "`r?`n")
$old = $lines.FindIndex({ param($l) $l.StartsWith('CF_ACCESS_ROTATE_TOKEN=') })
if ($old -ge 0) { $lines[$old] = "CF_ACCESS_ROTATE_TOKEN=$tok"; $how = 'replaced the old line' }
else {
    $at = $lines.FindIndex({ param($l) $l.StartsWith('CF_ACCESS_CLIENT_SECRET=') })
    if ($at -ge 0) { $lines.Insert($at + 1, "CF_ACCESS_ROTATE_TOKEN=$tok") } else { $lines.Add("CF_ACCESS_ROTATE_TOKEN=$tok") }
    $how = 'added under CF_ACCESS_CLIENT_SECRET'
}
[IO.File]::WriteAllText($Vault, ($lines -join $nl), [Text.UTF8Encoding]::new($false))
$tok = $null; $sec.Dispose()
Set-Clipboard -Value ' '                                         # the token doesn't stay on the clipboard
Say "vault: $how (backup beside it)" Green
Write-Host ''
Say 'Done. Tell Claude "token''s in". Rotate whenever you choose: rotate-key in a PS7 window.' Green
