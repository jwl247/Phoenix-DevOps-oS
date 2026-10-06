#Requires -Version 7.2
# member-keys.test.ps1 — packages-worker 3.9.0 member keys, end to end, LOCAL ONLY.
# Phoenix DevOps OS | jwl247 | GPL v3
#
#   Where: PBMII, PowerShell 7, from the repo root:
#     cd F:\Phoenix\Phoenix-DevOps-oS
#     pwsh -NoProfile -File tentative-wares\package-handler-3.9.0\test\member-keys.test.ps1
#
# Cannot touch live data: wrangler runs with --local and its own --persist-to folder in
# a throwaway temp dir; the copied wrangler.jsonc has no remote flags; intake.sh gets a
# throwaway HOME, CLONEPOOL_DIR and PHOENIX_WORKER_URL=http://127.0.0.1:<port>.
# The D1 starts in the LIVE shape (3.8.x schema, no owner column, no api_keys) and the
# real migration runs on it — the same order the live deploy uses.
$ErrorActionPreference = 'Stop'
$repo   = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$ware   = Join-Path $repo 'tentative-wares/package-handler-3.9.0'
$port   = 8799
$base   = "http://127.0.0.1:$port"
$tmp    = Join-Path ([IO.Path]::GetTempPath()) ("pw390-" + [guid]::NewGuid().ToString('n').Substring(0, 8))
$owner  = 'owner-test-' + [guid]::NewGuid().ToString('n')
$pass = 0; $fail = 0
function Check([string]$what, [bool]$cond, [string]$detail = '') {
    if ($cond) { $script:pass++; Write-Host "  PASS  $what" -ForegroundColor Green }
    else       { $script:fail++; Write-Host "  FAIL  $what  $detail" -ForegroundColor Red }
}
function Call([string]$method, [string]$path, $key, $body = $null, [byte[]]$bytes = $null) {
    $h = @{}; if ($key) { $h.Authorization = "Bearer $key" }
    $p = @{ Method = $method; Uri = "$base$path"; Headers = $h; SkipHttpErrorCheck = $true; TimeoutSec = 30 }
    if ($null -ne $body)  { $p.Body = ($body | ConvertTo-Json -Compress); $p.ContentType = 'application/json' }
    if ($null -ne $bytes) { $p.Body = $bytes; $p.ContentType = 'application/octet-stream' }
    $r = Invoke-WebRequest @p
    $j = $null; try { $j = $r.Content | ConvertFrom-Json } catch {}
    [pscustomobject]@{ Code = [int]$r.StatusCode; Json = $j; Raw = $r.Content }
}
function HexOf([string]$s) { -join ([Text.Encoding]::UTF8.GetBytes($s) | ForEach-Object { $_.ToString('x2') }) }

New-Item -ItemType Directory -Force -Path $tmp | Out-Null
$wk = Join-Path $tmp 'worker'; New-Item -ItemType Directory -Force -Path $wk | Out-Null
Copy-Item (Join-Path $ware 'worker/index.js') $wk
Copy-Item (Join-Path $repo 'sector2/package-handler/worker/atlas-parse.mjs') $wk   # index.js imports it
Copy-Item (Join-Path $repo 'sector2/package-handler/worker/wrangler.jsonc') $wk
Set-Content (Join-Path $wk '.dev.vars') "PHOENIX_AUTH=$owner" -NoNewline
$state = Join-Path $tmp 'state'
$npx = if ($IsWindows) { 'npx.cmd' } else { 'npx' }
$wv = Join-Path $repo 'sector2/package-handler/worker'   # wrangler lives here (no install)
$wr = @('--no-install', 'wrangler')
$wf = @('--config', (Join-Path $wk 'wrangler.jsonc'), '--persist-to', $state)
$dev = $null
try {
    Write-Host "== D1 in the live shape, then the real migration (local, $tmp)"
    Push-Location $wv
    & $npx @wr d1 execute phoenix_dev_db --local @wf --file (Join-Path $repo 'sector2/package-handler/worker/schema-d1.sql') *> (Join-Path $tmp 'schema.log')
    Check 'live-shape schema applied' ($LASTEXITCODE -eq 0) (Get-Content (Join-Path $tmp 'schema.log') -Tail 5 | Out-String)
    & $npx @wr d1 execute phoenix_dev_db --local @wf --file (Join-Path $ware 'worker/migrate-3.9.0-member-keys.sql') *> (Join-Path $tmp 'migrate.log')
    Check 'migration applied' ($LASTEXITCODE -eq 0) (Get-Content (Join-Path $tmp 'migrate.log') -Tail 5 | Out-String)
    # an owner row that already exists before 3.9.0 (owner NULL = the Phoenix owner)
    & $npx @wr d1 execute phoenix_dev_db --local @wf --command "INSERT INTO clonepool (hex_id,b58,name,state,tier,version,sensitive) VALUES ('$(HexOf 'owners_file.py')','x','owners_file.py','white',1,'v1',0),('$(HexOf 'secret_plan.txt')','y','secret_plan.txt','white',1,'v1',1)" *> $null
    Pop-Location

    Write-Host "== worker 3.9.0 on $base (local)"
    $dev = Start-Process -FilePath $npx -ArgumentList (@($wr) + @('dev', '--local', '--port', "$port", '--ip', '127.0.0.1') + $wf) `
           -WorkingDirectory $wk -PassThru -NoNewWindow -RedirectStandardOutput (Join-Path $tmp 'dev.log') -RedirectStandardError (Join-Path $tmp 'dev.err')
    $up = $false
    foreach ($i in 1..60) { try { if ((Call GET '/health' $null).Code -eq 200) { $up = $true; break } } catch {}; Start-Sleep -Milliseconds 500 }
    Check 'worker answers /health' $up
    if (-not $up) { throw 'worker never came up' }
    Check 'version is 3.9.0' ((Call GET '/health' $null).Json.version -eq '3.9.0')

    Write-Host '== keys (owner)'
    $k = Call POST '/keys' $owner @{ who = 'son' }
    Check 'owner issues a key' ($k.Code -eq 200 -and $k.Json.key -like 'phx_*')
    $son = $k.Json.key
    Check 'key shown once: duplicate refused' ((Call POST '/keys' $owner @{ who = 'son' }).Code -eq 409)
    Check 'bad name refused' ((Call POST '/keys' $owner @{ who = 'Owner' }).Code -eq 400)
    $ro = (Call POST '/keys' $owner @{ who = 'reader'; scopes = 'read' }).Json.key
    $list = Call GET '/keys' $owner
    Check 'list shows names, never keys' ($list.Code -eq 200 -and $list.Raw -notmatch 'phx_' -and $list.Json.count -eq 2)

    Write-Host '== son (member key)'
    $w = Call GET '/whoami' $son
    Check 'whoami = son' ($w.Json.who -eq 'son')
    $cp = Call GET '/clonepool' $son
    Check 'reads the pool' ($cp.Code -eq 200)
    Check 'sensitive rows hidden from his list' ($cp.Raw -notmatch 'secret_plan')
    Check 'sensitive record refused' ((Call GET "/clonepool/$(HexOf 'secret_plan.txt')" $son).Code -eq 403)
    Check 'cannot list keys' ((Call GET '/keys' $son).Code -eq 403)
    Check 'cannot issue keys' ((Call POST '/keys' $son @{ who = 'friend' }).Code -eq 403)
    Check 'cannot delete owner file' ((Call DELETE "/clonepool/$(HexOf 'owners_file.py')" $son).Code -eq 403)
    Check 'cannot overwrite owner bytes' ((Call PUT "/clonepool/$(HexOf 'owners_file.py')" $son -bytes ([byte[]](1,2,3))).Code -eq 403)
    Check 'may-write refuses owner name' ((Call GET "/may-write/$(HexOf 'owners_file.py')" $son).Code -eq 403)
    $hx = HexOf 'sons_first.py'
    Check 'may-write allows a new name' ((Call GET "/may-write/$hx" $son).Code -eq 200)
    Check 'read-only key cannot write' ((Call PUT "/clonepool/$hx" $ro -bytes ([byte[]](1))).Code -eq 403)

    Write-Host '== the real intake.sh, as son, into a throwaway pool'
    $bash = if ($IsWindows) { 'C:\Program Files\Git\bin\bash.exe' } else { '/bin/bash' }
    $h2 = Join-Path $tmp 'home'; $pool = Join-Path $tmp 'pool'; New-Item -ItemType Directory -Force $h2, $pool | Out-Null
    $f = Join-Path $tmp 'sons_first.py'; Set-Content $f "print('hello from son')`n" -NoNewline
    $f2 = Join-Path $tmp 'owners_file.py'; Set-Content $f2 "print('not yours')`n" -NoNewline
    $env:HOME = $h2; $env:CLONEPOOL_DIR = $pool; $env:PHOENIX_WORKER_URL = $base; $env:PHOENIX_AUTH = $son
    $env:CF_ACCESS_CLIENT_ID = ''; $env:CF_ACCESS_CLIENT_SECRET = ''
    $intake = Join-Path $ware 'intake.sh'
    $o1 = & $bash $intake ($f -replace '\\', '/') 2>&1 | Out-String
    $row = (Call GET "/clonepool/$hx`?meta=true" $owner).Json
    Check 'his new file goes in' ($o1 -match 'intake:OK') ($o1 | Select-Object -Last 1)
    Check 'row owner = son (set by the worker)' ($row.owner -eq 'son' -or $row.clonepool.owner -eq 'son') ($row | ConvertTo-Json -Compress -Depth 4)
    $o2 = & $bash $intake ($f2 -replace '\\', '/') 2>&1 | Out-String
    Check 'owner name refused with the reason' ($o2 -match 'REFUSED') ($o2)
    Check 'owner bytes untouched' ((Call GET "/clonepool/$(HexOf 'owners_file.py')?meta=true" $owner).Json.Raw -notmatch 'son')

    Write-Host '== his installer + genie-cloud, as he will use them (temp profile, no user env touched)'
    $k2 = (Call POST '/keys' $owner @{ who = 'son2' }).Json.key
    $gc = Join-Path $repo 'tentative-wares/genie-cloud'
    $ip = Join-Path $tmp 'inst'; $prof = Join-Path $ip 'profile.ps1'
    $inst = try { & (Join-Path $gc 'install-genie-cloud.ps1') -InstallDir (Join-Path $ip 'Phoenix') `
             -ProfilePath $prof -ConfigDir (Join-Path $ip 'cfg') -NoUserEnv `
             -Key (ConvertTo-SecureString $k2 -AsPlainText -Force) *>&1 | Out-String } catch { "THREW: $_" }   # a throw is a FAIL, not the end of the run
    Check 'installer finishes' ($inst -match 'Done\.') ($inst)
    Check 'installer never prints the key' ($inst -notmatch [regex]::Escape($k2))
    Check 'bad key refused, nothing saved' (((& { try { & (Join-Path $gc 'install-genie-cloud.ps1') -InstallDir (Join-Path $tmp 'x') -ProfilePath (Join-Path $tmp 'x/p.ps1') -ConfigDir (Join-Path $tmp 'x/c') -NoUserEnv -Key (ConvertTo-SecureString 'notakey' -AsPlainText -Force) } catch { $_.Exception.Message } }) *>&1 | Out-String) -match 'does not look like' -and -not (Test-Path (Join-Path $tmp 'x/c/genie.env')))
    $out = Join-Path $tmp 'cloned'
    $env:PHOENIX_AUTH = ''      # the profile must bring his key in by itself
    $g = & pwsh -NoProfile -Command ". '$prof'; genie doctor; genie find sons_first; genie clone sons_first.py -To '$out'" 2>&1 | Out-String
    Check 'new window: doctor signs in as son2' ($g -match 'son2') ($g)
    Check 'new window: find sees his brother''s file' ($g -match 'sons_first')
    Check 'clone writes SHA3-verified bytes' ((Test-Path (Join-Path $out 'sons_first.py')) -and ((Get-Content (Join-Path $out 'sons_first.py') -Raw) -eq (Get-Content $f -Raw))) ($g)
    $env:PHOENIX_AUTH = $son

    Write-Host '== revoke'
    Check 'owner revokes son' ((Call POST '/keys/son/revoke' $owner).Code -eq 200)
    Check 'his key stops at once (401)' ((Call GET '/whoami' $son).Code -eq 401)
    Check 'owner key still works' ((Call GET '/whoami' $owner).Json.who -eq 'owner')
}
finally {
    if ($dev -and -not $dev.HasExited) {
        if ($IsWindows) { & taskkill.exe /T /F /PID $dev.Id *> $null } else { Stop-Process -Id $dev.Id -Force }
    }
    foreach ($v in 'HOME', 'CLONEPOOL_DIR', 'PHOENIX_WORKER_URL', 'PHOENIX_AUTH', 'CF_ACCESS_CLIENT_ID', 'CF_ACCESS_CLIENT_SECRET') { Remove-Item "env:$v" -ErrorAction SilentlyContinue }
    Write-Host ''
    Write-Host ("  {0} passed, {1} failed   (scratch: {2})" -f $pass, $fail, $tmp) -ForegroundColor $(if ($fail) { 'Red' } else { 'Green' })
}
exit [int]($fail -gt 0)
