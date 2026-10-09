#Requires -Version 7.2
# =============================================================================
# genie.ps1 — Phoenix Genie: the Phoenix Universal Kernel, living in PS7.
# Phoenix DevOps OS | jwl247 | GPL v3
#
# Dot-source from the PS7 profile:   . F:\Phoenix\Phoenix-DevOps-oS\sector1\kernel\genie\genie.ps1
# Then:  genie up | down | restart | status | log | doctor | find <term> | clone <name|hex> | profile
#
# What it does
#   up       boots sector1\kernel\main_kernel.py (Frank5 -> closet -> FrankSpawn ->
#            Helix-I 7701-7704 -> Helix-E 7805-7808 -> CoPES guardians -> LLM engine ->
#            FileTree -> status server :8765) as a hidden background process.
#   clone    OUT from the clonepool: D1 row (hash baseline) + R2 bytes via
#            packages-worker, SHA3-512 checked BEFORE the file is written. A file
#            whose bytes don't match custody never lands.
#
# Rules it keeps
#   - Clone = OUT, intake = IN. Genie never writes to R2/D1.
#   - No translation on clone (translator.sh is output-only, Helix-E's job).
#   - PHOENIX_AUTH / CF Access secrets are read from the environment only, sent
#     as headers only, never printed, never put on a command line or in a URL.
#   - Port fix: Helix-I owns 7701-7704; FileTree/status-server default to
#     7703/7704 and collide (bind fails, found 2026-10-03 boot test). Genie
#     launches the kernel with PHOENIX_TREE_PORT=7713 / PHOENIX_CLONE_PORT=7714
#     unless you set them yourself. No Python edited.
# =============================================================================

# StrictMode is set INSIDE `genie` (below), not here: this file is dot-sourced
# from the PS7 profile, and a script-scope Set-StrictMode would switch it on for
# the user's whole session and break other tools (usys pull/.lol, 2026-10-07
# audit CMDWALK-F01/F02, S1-F44).

# ── Locations ────────────────────────────────────────────────────────────────
# This file lives at <repo>\sector1\kernel\genie\genie.ps1
$script:GenieRepo      = if ($env:PHOENIX_ROOT -and (Test-Path (Join-Path $env:PHOENIX_ROOT 'sector1/kernel/main_kernel.py'))) {
                             (Resolve-Path $env:PHOENIX_ROOT).Path
                         } else {
                             (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
                         }
$script:GenieKernelDir = Join-Path $script:GenieRepo 'sector1/kernel'
$script:GenieEntry     = Join-Path $script:GenieKernelDir 'main_kernel.py'
$script:GenieHome      = if ($env:PHOENIX_GENIE_HOME) { $env:PHOENIX_GENIE_HOME } else { Join-Path $HOME '.phoenix/genie' }
$script:GeniePidFile   = Join-Path $script:GenieHome 'kernel.pid'
$script:GenieLog       = Join-Path $script:GenieHome 'kernel.log'
$script:GenieCloset    = Join-Path $script:GenieHome 'closet'
$script:GenieWorker    = if ($env:PHOENIX_WORKER_URL) { $env:PHOENIX_WORKER_URL.TrimEnd('/') } else { 'https://packages-worker.phoenix-jwl.workers.dev' }
$script:GenieStatusPort = if ($env:PHOENIX_STATUS_PORT) { [int]$env:PHOENIX_STATUS_PORT } else { 8765 }
$script:GenieIsWindows = $IsWindows
$script:GenieCtlPort  = if ($env:PHOENIX_GENIE_PORT) { [int]$env:PHOENIX_GENIE_PORT } else { 8766 }
$script:GenieTokenFile = Join-Path $script:GenieHome 'control.token'

# ── Output helpers ───────────────────────────────────────────────────────────
function G-Ok   ([string]$m) { Write-Host "  [genie] $m" -ForegroundColor Green }
function G-Info ([string]$m) { Write-Host "  [genie] $m" -ForegroundColor Cyan }
function G-Warn ([string]$m) { Write-Host "  [genie] $m" -ForegroundColor Yellow }
# every G-Err is a real failure: lol/usys turn it into exit 1 (refused/no answer/not found used to exit 0; 2026-10-09)
function G-Err  ([string]$m) { $global:GenieFailed = $true; Write-Host "  [genie] $m" -ForegroundColor Red }

# ── Python discovery ─────────────────────────────────────────────────────────
function Get-GeniePython {
    if ($env:PHOENIX_PYTHON -and (Test-Path $env:PHOENIX_PYTHON)) { return (Resolve-Path $env:PHOENIX_PYTHON).Path }
    foreach ($name in 'python', 'python3') {
        foreach ($c in @(Get-Command $name -CommandType Application -ErrorAction SilentlyContinue)) {
            # The WindowsApps "python.exe" is the Store installer stub, not Python.
            if ($c.Source -notmatch '\\WindowsApps\\') { return $c.Source }
        }
    }
    if ($script:GenieIsWindows) {
        $py = Get-Command py -CommandType Application -ErrorAction SilentlyContinue
        if ($py) {
            $exe = (& $py.Source -3 -c 'import sys; print(sys.executable)' 2>$null)
            if ($LASTEXITCODE -eq 0 -and $exe -and (Test-Path $exe)) { return $exe.Trim() }
        }
    }
    return $null
}

# ── Kernel process state ─────────────────────────────────────────────────────
function Test-GenieHealth {
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:$($script:GenieStatusPort)/health" -TimeoutSec 2 -ErrorAction Stop
        return [bool]$r.ok
    } catch { return $false }
}

function Get-GenieProc {
    if (-not (Test-Path $script:GeniePidFile)) { return $null }
    $pidText = (Get-Content $script:GeniePidFile -Raw -ErrorAction SilentlyContinue)
    if (-not $pidText) { return $null }
    $p = Get-Process -Id ([int]$pidText.Trim()) -ErrorAction SilentlyContinue
    # A recycled PID belonging to something else is not our kernel.
    if ($p -and $p.ProcessName -match '^(cmd|python|python3|py|sh)') { return $p }
    return $null
}

function Start-GenieKernel {
    if (Test-GenieHealth) { G-Info "kernel already up — http://127.0.0.1:$($script:GenieStatusPort)"; return $true }
    if (-not (Test-Path $script:GenieEntry)) { G-Err "kernel entry not found: $($script:GenieEntry)"; return $false }
    $python = Get-GeniePython
    if (-not $python) { G-Err 'no Python found (set PHOENIX_PYTHON to python.exe)'; return $false }

    New-Item -ItemType Directory -Force -Path $script:GenieHome | Out-Null
    $stamp = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Add-Content -Path $script:GenieLog -Value "`n===== genie up $stamp  python=$python =====" -Encoding utf8

    $kernelEnv = [ordered]@{ PYTHONUNBUFFERED = '1'; PYTHONIOENCODING = 'utf-8' }   # guardian log lines carry emoji
    if (-not $env:PHOENIX_TREE_PORT)  { $kernelEnv['PHOENIX_TREE_PORT']  = '7713' }
    if (-not $env:PHOENIX_CLONE_PORT) { $kernelEnv['PHOENIX_CLONE_PORT'] = '7714' }

    if ($script:GenieIsWindows) {
        # ShellExecute (Start-Process, no redirection), window hidden: the kernel inherits NO handles.
        # CreateProcess with inheritance handed it every handle its caller held, so anything that read
        # `usys start` output (a Console button, a script) waited for the kernel to exit (2026-10-08).
        # cmd owns the >> redirect so the kernel never blocks on a full pipe.
        $saved = @{}
        foreach ($k in $kernelEnv.Keys) { $saved[$k] = [Environment]::GetEnvironmentVariable($k); [Environment]::SetEnvironmentVariable($k, $kernelEnv[$k]) }
        try {
            $proc = Start-Process -FilePath (Join-Path $env:SystemRoot 'System32\cmd.exe') -WindowStyle Hidden -PassThru `
                        -WorkingDirectory $script:GenieKernelDir `
                        -ArgumentList "/d /s /c `"`"$python`" -u `"$($script:GenieEntry)`" >> `"$($script:GenieLog)`" 2>&1`""
        } finally {
            foreach ($k in $saved.Keys) { [Environment]::SetEnvironmentVariable($k, $saved[$k]) }
        }
    } else {
        $psi = [System.Diagnostics.ProcessStartInfo]::new()
        $psi.UseShellExecute  = $false
        $psi.CreateNoWindow   = $true
        $psi.WorkingDirectory = $script:GenieKernelDir
        $psi.FileName = '/bin/sh'
        $psi.ArgumentList.Add('-c')
        $psi.ArgumentList.Add('exec "$0" -u "$1" >> "$2" 2>&1')
        $psi.ArgumentList.Add($python)
        $psi.ArgumentList.Add($script:GenieEntry)
        $psi.ArgumentList.Add($script:GenieLog)
        foreach ($k in $kernelEnv.Keys) { $psi.Environment[$k] = $kernelEnv[$k] }
        $proc = [System.Diagnostics.Process]::Start($psi)
    }
    Set-Content -Path $script:GeniePidFile -Value $proc.Id -Encoding ascii

    $deadline = (Get-Date).AddSeconds(20)
    while ((Get-Date) -lt $deadline) {
        if (Test-GenieHealth) {
            G-Ok "kernel OPERATIONAL  pid $($proc.Id)  status http://127.0.0.1:$($script:GenieStatusPort)"
            return $true
        }
        if ($proc.HasExited) { break }
        Start-Sleep -Milliseconds 250
    }
    G-Err "kernel did not come up (exit: $(if ($proc.HasExited) { $proc.ExitCode } else { 'still running, no /health' })). Last log lines:"
    Get-Content $script:GenieLog -Tail 15 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
    return $false
}

function Stop-GenieKernel {
    $p = Get-GenieProc
    if (-not $p) {
        if (Test-GenieHealth) { G-Warn "a kernel is answering on :$($script:GenieStatusPort) but Genie didn't start it — not touching it"; return }
        G-Info 'kernel not running'
        Remove-Item $script:GeniePidFile -ErrorAction SilentlyContinue
        return
    }
    if ($script:GenieIsWindows) {
        # cmd -> python: kill the tree, not just cmd.
        & (Join-Path $env:SystemRoot 'System32\taskkill.exe') /T /F /PID $p.Id *> $null
    } else {
        Stop-Process -Id $p.Id -ErrorAction SilentlyContinue   # SIGTERM; FrankSpawn has a handler
        if (-not $p.WaitForExit(5000)) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
    }
    Remove-Item $script:GeniePidFile -ErrorAction SilentlyContinue
    G-Ok "kernel stopped (pid $($p.Id))"
}

function Show-GenieStatus {
    $p  = Get-GenieProc
    $up = Test-GenieHealth
    Write-Host ''
    Write-Host '  PHOENIX GENIE' -ForegroundColor Magenta
    Write-Host ("  kernel   : {0}" -f $(if ($up) { 'OPERATIONAL' } else { 'down' })) -ForegroundColor $(if ($up) { 'Green' } else { 'Red' })
    Write-Host ("  pid      : {0}" -f $(if ($p) { $p.Id } else { '-' }))
    Write-Host ("  repo     : {0}" -f $script:GenieRepo)
    Write-Host ("  log      : {0}" -f $script:GenieLog)
    if ($up) {
        $ports = 7701..7704 + 7805..7808 + @($script:GenieStatusPort)
        $listening = @()
        if ($script:GenieIsWindows) {
            $listening = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
                           Where-Object LocalPort -in $ports | Select-Object -ExpandProperty LocalPort -Unique)
        } else {
            foreach ($pt in $ports) {
                try { $c = [System.Net.Sockets.TcpClient]::new(); $c.Connect('127.0.0.1', $pt); $c.Dispose(); $listening += $pt } catch {}
            }
        }
        $fmt = { param($r) ($r | ForEach-Object { if ($listening -contains $_) { "$_" } else { "$_(x)" } }) -join ' ' }
        Write-Host ("  helix-i  : {0}" -f (& $fmt (7701..7704)))
        Write-Host ("  helix-e  : {0}" -f (& $fmt (7805..7808)))
        try {
            $k = Invoke-GenieControl GET '/kernel' $null
            Write-Host ("  uptime   : {0}s  python {1}" -f $k.uptime_s, $k.python)
            Write-Host ("  closet   : {0} suits ({1} imported{2})" -f $k.library.suit_count, @($k.library.imported).Count,
                        $(if (@($k.library.imported).Count) { ': ' + (@($k.library.imported) -join ', ') } else { '' }))
            if ($k.library.PSObject.Properties['refused'] -and @($k.library.refused).Count) {
                G-Err ("refused at boot (file changed since custody check): {0} — genie import it again" -f (@($k.library.refused) -join ', '))
            }
            foreach ($side in 'helix_i', 'helix_e') {
                $h = $k.$side
                if ($h -and $h.PSObject.Properties['channels']) {
                    $ch = @($h.channels.PSObject.Properties | ForEach-Object { "ch$($_.Name)=$($_.Value.state)" }) -join ' '
                    Write-Host ("  {0,-8} : v{1}  {2}" -f $side.Replace('_', '-'), $h.version, $ch)
                }
            }
            if ($k.PSObject.Properties['helix'] -and $k.helix) {
                $h = $k.helix; $d = $h.dandelion
                Write-Host ("  helix    : dandelion {0}  heat {1}  load {2}  compression {3}{4}" -f $d.state, $d.heat, $d.load, $d.compression,
                            $(if ($d.kernel_linked) { '  (kernel-linked)' } else { '' })) -ForegroundColor $(switch ($d.state) { 'surging' { 'Red' } 'hot' { 'Yellow' } default { 'Green' } })
                Write-Host ("             L1+L2 raw {0:N1}/{1:N0} MB  L3 zlib-5 {2:N1}/{3:N0} MB  Strand B {4:N1}/{5:N0} MB  blocks {9}  saved {6:N1} MB  hit {7:N1}%  refused {8}" -f `
                            $h.hot_usage_mb, $h.raw_budget_mb, $h.warm_usage_mb, $h.z_budget_mb, $h.cold_usage_mb, $h.strand_b_budget_mb, $h.bytes_saved_mb, $h.hit_rate, $h.refused, $h.total_blocks)
            } else { G-Warn 'helix    : userspace Helix not running in the kernel (genie log)' }
            if ($k.PSObject.Properties['paging'] -and $k.paging) {
                $p = $k.paging
                Write-Host ("  paging   : pressure {0}  (ram {1}, commit {2})  doppelgangers {3}  Strand B budget {4} MB (base {5}, disk ceiling {6})" -f `
                            $p.pressure, $p.ram, $p.commit, @($p.doppelgangers).Count, $p.strand_b_budget_mb, $p.strand_b_base_mb, $p.strand_b_ceiling_mb)
                if ($p.strand_b_ceiling_mb -lt $p.strand_b_base_mb) {
                    G-Warn ("Strand B's disk can't hold even her base ({0} MB) — point HELIX_VRAM_STRAND_B at a bigger, fast drive" -f $p.strand_b_base_mb)
                }
                foreach ($dd in @($p.decisions) | Select-Object -Last 3) { Write-Host "             $($dd.ts) $($dd.action): $($dd.why)" -ForegroundColor DarkGray }
            }
        } catch { G-Warn "live kernel view unavailable: $($_.Exception.Message)" }
    }
    Write-Host ''
}

# ── Kernel control socket (genie_control.py, loopback + per-boot token) ─────
# ── Send a stage to a suit and wait for its answer ──────────────────────────
# Helix-I door (7700+ch) takes the stage in; the answer comes out of the
# matching Helix-E door (7804+ch). Listen FIRST, then send, so the answer
# can't slip out before anyone is listening. The stage must be a JSON object
# with "suit": "<name>" — only Genie-imported suits answer those.
# HELIX_SOCKET_TOKEN (from the environment) is the gate handshake when set.
function Split-GenieJsonStream([string]$buf) {
    $out = [System.Collections.Generic.List[string]]::new(); $depth = 0; $start = -1; $inStr = $false; $esc = $false
    for ($i = 0; $i -lt $buf.Length; $i++) {
        $c = $buf[$i]
        if ($inStr) { if ($esc) { $esc = $false } elseif ($c -eq '\') { $esc = $true } elseif ($c -eq '"') { $inStr = $false }; continue }
        if ($c -eq '"') { $inStr = $true }
        elseif ($c -eq '{') { if ($depth -eq 0) { $start = $i }; $depth++ }
        elseif ($c -eq '}' -and $depth -gt 0) { $depth--; if ($depth -eq 0) { $out.Add($buf.Substring($start, $i - $start + 1)); $start = -1 } }
    }
    $rest = if ($depth -gt 0 -and $start -ge 0) { $buf.Substring($start) } else { '' }
    return , @($out.ToArray(), $rest)
}

function Send-GenieStage([string]$Suit, [string]$Json, [int]$Channel = 1, [int]$Wait = 120, [string]$HostName = '127.0.0.1') {
    if (-not $Suit) { throw 'usage: genie send <suit> [''{"key": "value"}''] [-Channel 1-4] [-Wait sec]' }
    $stage = if ($Json) { try { $Json | ConvertFrom-Json -AsHashtable } catch { throw "the stage is not valid JSON: $($_.Exception.Message)" } } else { @{} }
    if ($stage -isnot [hashtable]) { throw 'the stage must be a JSON object: {"key": "value"}' }
    $stage['suit'] = $Suit
    $bytes = [Text.Encoding]::UTF8.GetBytes(($stage | ConvertTo-Json -Compress -Depth 20))
    $tok = if ($env:HELIX_SOCKET_TOKEN) { [Text.Encoding]::ASCII.GetBytes("HXT $($env:HELIX_SOCKET_TOKEN.Trim())`n") } else { $null }

    $ear = [Net.Sockets.TcpClient]::new()
    try {
        $ear.Connect($HostName, 7804 + $Channel)
        $es = $ear.GetStream(); if ($tok) { $es.Write($tok, 0, $tok.Length) }
        Start-Sleep -Milliseconds 150                      # let Helix-E admit us before the stage lands
        $mouth = [Net.Sockets.TcpClient]::new()
        try {
            $mouth.Connect($HostName, 7700 + $Channel)
            $ms = $mouth.GetStream(); if ($tok) { $ms.Write($tok, 0, $tok.Length) }
            $ms.Write($bytes, 0, $bytes.Length); $ms.Flush()
        } finally { $mouth.Close() }
        G-Info "sent to $Suit (Helix-I ch$Channel) — waiting up to $Wait s on Helix-E ch$Channel"
        $buf = ''; $chunk = [byte[]]::new(65536); $deadline = (Get-Date).AddSeconds($Wait)
        while ((Get-Date) -lt $deadline) {
            $task = $es.ReadAsync($chunk, 0, $chunk.Length)
            if (-not $task.Wait([int][Math]::Max(1, ($deadline - (Get-Date)).TotalMilliseconds))) { break }
            if ($task.Result -le 0) { throw 'Helix-E closed the stream (gate token wrong?)' }
            $buf += [Text.Encoding]::UTF8.GetString($chunk, 0, $task.Result)
            $msgs, $buf = Split-GenieJsonStream $buf
            foreach ($m in $msgs) {
                $o = try { $m | ConvertFrom-Json } catch { $null }
                if ($o -and $o.PSObject.Properties['suit'] -and $o.suit -eq $Suit) { return $o }
            }
        }
        throw "no answer from '$Suit' within $Wait s — is it imported (genie closet)? does its reply carry `"suit`": `"$Suit`"? see genie log"
    } finally { $ear.Close() }
}

function Invoke-GenieControl([string]$Method, [string]$Path, $Body) {
    if (-not (Test-Path $script:GenieTokenFile)) { throw 'kernel control socket is not up (no control.token) — genie restart' }
    $tok = (Get-Content $script:GenieTokenFile -Raw).Trim()
    $p = @{ Uri = "http://127.0.0.1:$($script:GenieCtlPort)$Path"; Method = $Method; Headers = @{ 'X-Genie-Token' = $tok }
            TimeoutSec = 30; SkipHttpErrorCheck = $true; StatusCodeVariable = 'sc' }
    if ($null -ne $Body) { $p.Body = ($Body | ConvertTo-Json -Compress); $p.ContentType = 'application/json' }
    $r = Invoke-RestMethod @p
    if ($sc -ge 400) { throw "kernel refused (HTTP $sc): $($r.error)" }
    return $r
}

# ── Worker access (clone = OUT) ──────────────────────────────────────────────
function Get-GenieHeaders {
    if (-not $env:PHOENIX_AUTH) { throw 'PHOENIX_AUTH is not set in this shell.' }
    $h = @{ Authorization = "Bearer $($env:PHOENIX_AUTH)" }
    # packages-worker sits behind Cloudflare Access (usys-cli service token).
    if ($env:CF_ACCESS_CLIENT_ID -and $env:CF_ACCESS_CLIENT_SECRET) {
        $h['CF-Access-Client-Id']     = $env:CF_ACCESS_CLIENT_ID
        $h['CF-Access-Client-Secret'] = $env:CF_ACCESS_CLIENT_SECRET
    }
    return $h
}

function Invoke-GenieWorker([string]$PathAndQuery) {
    $r = Invoke-WebRequest -Uri ($script:GenieWorker + $PathAndQuery) -Headers (Get-GenieHeaders) `
             -SkipHttpErrorCheck -MaximumRedirection 0 -TimeoutSec 60 -ErrorAction Stop
    $ctype = [string]($r.Headers['Content-Type'] | Select-Object -First 1)
    if ($r.StatusCode -in 301, 302, 303, 307, 308 -or $ctype -match 'text/html') {
        throw "Cloudflare Access refused the request (HTTP $($r.StatusCode)) — check CF_ACCESS_CLIENT_ID / CF_ACCESS_CLIENT_SECRET."
    }
    if ($r.StatusCode -eq 401) { throw 'packages-worker said 401 unauthorized — PHOENIX_AUTH in this shell is wrong or stale.' }
    if ($r.StatusCode -ge 500) { throw "packages-worker error HTTP $($r.StatusCode)" }
    return $r
}

function Get-GenieSha3([byte[]]$Bytes) {
    if ([System.Security.Cryptography.SHA3_512]::IsSupported) {
        return ([System.Convert]::ToHexString([System.Security.Cryptography.SHA3_512]::HashData($Bytes))).ToLowerInvariant()
    }
    # Older Windows builds lack SHA3 in CNG — fall back to Python's hashlib.
    $python = Get-GeniePython
    if (-not $python) { throw 'SHA3-512 unavailable (no OS support, no Python).' }
    $tmp = [System.IO.Path]::GetTempFileName()
    try {
        [System.IO.File]::WriteAllBytes($tmp, $Bytes)
        $h = & $python -c 'import hashlib,sys; print(hashlib.sha3_512(open(sys.argv[1],"rb").read()).hexdigest())' $tmp
        if ($LASTEXITCODE -ne 0) { throw 'python sha3 failed' }
        return $h.Trim().ToLowerInvariant()
    } finally { Remove-Item $tmp -ErrorAction SilentlyContinue }
}

function Get-GenieBash {
    if ($env:PHOENIX_BASH -and (Test-Path $env:PHOENIX_BASH)) { return $env:PHOENIX_BASH }
    foreach ($c in @("$env:ProgramFiles\Git\bin\bash.exe", "${env:ProgramFiles(x86)}\Git\bin\bash.exe")) {
        if ($c -and (Test-Path $c)) { return $c }
    }
    $b = Get-Command bash -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($b) { return $b.Source }
    return $null
}

function ConvertTo-GenieBashPath([string]$p) {
    # E:\x\y or E:/x/y -> /e/x/y for Git Bash; Linux paths pass through.
    if ($p -match '^([A-Za-z]):[\\/](.*)$') { return '/' + $Matches[1].ToLowerInvariant() + '/' + ($Matches[2] -replace '\\', '/') }
    return $p
}

function Invoke-GenieIntakeLocal([string]$Path, [ValidateSet('entertainment', 'system')][string]$Class = 'entertainment') {
    # IN: the same Sector 2 pipeline as `intake <file>`, run unattended. With no stdin,
    # intake takes its safe defaults: a sensitive file is refused, an identical file
    # keeps the version already in the pool, a different file with the same name is
    # refused. Afterwards custody must hold THESE bytes, or nothing is loaded.
    $full = (Resolve-Path -LiteralPath $Path).Path
    if ($full -match '\.py$') {
        # The package handler makes the suit correct first (suit_build.py: answers the kernel, never
        # silent, a script never runs at load, class stamped inside the hashed bytes), and the BUILT
        # suit is what goes in. Same parent-folder name, so the pool identity stays the same (2026-10-09).
        if ($Class -eq 'system') {
            # System suits run inside the kernel: only a person at a real terminal says yes (CLAUDE.md
            # safety rule 10 — never a pipe, a flag alone, a default, an agent or Jarvis).
            if ([Console]::IsInputRedirected -or -not [Environment]::UserInteractive) { throw 'a SYSTEM suit needs a yes typed at a terminal; nothing was taken in' }
            if ((Read-Host "  $([System.IO.Path]::GetFileName($full)) will run INSIDE the kernel. Type SYSTEM to agree") -cne 'SYSTEM') { throw 'not agreed; nothing was taken in' }
        }
        $python = Get-GeniePython
        if (-not $python) { throw 'no Python found to build the suit (set PHOENIX_PYTHON)' }
        $builder = Join-Path $script:GenieRepo 'sector2/package-handler/suit_build.py'
        $parentLeaf = Split-Path (Split-Path $full -Parent) -Leaf
        $built = Join-Path ([System.IO.Path]::GetTempPath()) "phoenix-suit-build\$parentLeaf\$([System.IO.Path]::GetFileName($full))"
        $msg = @(& $python -I $builder $full $built --class $Class 2>&1 | ForEach-Object { "$_" })
        if ($LASTEXITCODE -ne 0) { throw (($msg -join ' ') -replace '^suit_build: ', '') }
        G-Info ($msg -join ' ')
        $full = $built
    }
    $bash = Get-GenieBash
    if (-not $bash) { throw 'bash not found (Windows: install Git for Windows, or set PHOENIX_BASH)' }
    $intakeSh = Join-Path $script:GenieRepo 'sector2/package-handler/intake.sh'
    if (-not (Test-Path $intakeSh)) { throw "intake.sh not found: $intakeSh" }
    $prevPool = $env:CLONEPOOL_DIR
    if ($env:CLONEPOOL_DIR) { $env:CLONEPOOL_DIR = ConvertTo-GenieBashPath $env:CLONEPOOL_DIR }
    try {
        $out = @($null | & $bash (ConvertTo-GenieBashPath $intakeSh) (ConvertTo-GenieBashPath $full) 2>&1 | ForEach-Object { "$_" })
    } finally { $env:CLONEPOOL_DIR = $prevPool }
    $out | Where-Object { $_ -match '\[intake:' } | ForEach-Object { G-Info $_.Trim() }
    $name = [System.IO.Path]::GetFileName($full)
    # Intake may give the file a longer identity (folder/name) when another file holds
    # the bare name; it prints the hex it chose. Look the row up by that, never by name.
    $idLine = $out | Where-Object { $_ -match '\[intake:ID\] (.+) hex ([0-9a-f]+)\s*$' } | Select-Object -First 1
    $key = if ($idLine -and $idLine -match '\[intake:ID\] (.+) hex ([0-9a-f]+)\s*$') { $Matches[2] } else { $name }
    $row = Resolve-GenieRow $key
    $mine = Get-GenieSha3 ([System.IO.File]::ReadAllBytes($full))
    $theirs = if ($row.PSObject.Properties['hash_sha3']) { ([string]$row.hash_sha3).ToLowerInvariant() } else { '' }
    if ($mine -ne $theirs) {
        $why = ($out | Where-Object { $_ -match '\[intake:(CANCEL|STOP|ERROR|FAIL)' } | Select-Object -First 1)
        throw ("the pool's $name is not this file, so nothing was loaded." +
               $(if ($why) { " intake said: $($why.Trim())" } else { " Run: intake $Path   to see why." }))
    }
    if ($Class -eq 'system') {
        # The person typed SYSTEM above: these exact bytes may run inside the kernel. The kernel
        # trusts a system header only when its SHA3 is on this list (genie_control.py, the wall).
        $listPath = Join-Path $script:GenieHome 'system_suits.json'
        $list = @{}
        if (Test-Path $listPath) { (Get-Content $listPath -Raw | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $list[$_.Name] = $_.Value } }
        $list[$mine] = [ordered]@{ name = $name; agreed_at = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'); by = $env:USERNAME }
        $list | ConvertTo-Json -Depth 3 | Set-Content -Path $listPath -Encoding utf8
        G-Info "$name is on the system list (this exact SHA3 only; any change needs a new yes)"
    }
    return $row.hex_id
}

function Resolve-GenieRow([string]$Id) {
    # Exact hex_id wins; a bare name must match exactly one row (no silent guessing).
    # A hex goes straight to its row: /search is a D1 LIKE, and D1 refuses patterns over
    # 50 bytes ("LIKE or GLOB pattern too complex"), so every folder/name hex 500s there.
    if ($Id -match '^[0-9a-f]{8,}$' -and $Id.Length % 2 -eq 0) {
        $r = Invoke-GenieWorker "/clonepool/$([uri]::EscapeDataString($Id))?meta=true"
        if ($r.StatusCode -eq 200) {
            $m = $r.Content | ConvertFrom-Json
            if ($m.PSObject.Properties['hex_id'] -and $m.hex_id -eq $Id) { return $m }
        }
    }
    $q = [uri]::EscapeDataString($Id)
    $s = (Invoke-GenieWorker "/search?q=$q").Content | ConvertFrom-Json
    $hits = @($s.clonepool | Where-Object { $_.hex_id -eq $Id -or $_.name -eq $Id })
    $exactHex = @($hits | Where-Object hex_id -eq $Id)
    if ($exactHex.Count -eq 1) { $hits = $exactHex }
    if ($hits.Count -eq 0) {
        $near = @($s.clonepool | Select-Object -First 8 | ForEach-Object { $_.name })
        throw ("'$Id' not in the clonepool." + $(if ($near) { ' Did you mean: ' + ($near -join ', ') } else { '' }))
    }
    if ($hits.Count -gt 1) {
        throw ("'$Id' matches $($hits.Count) rows — clone by hex_id: " + (($hits | ForEach-Object { "$($_.hex_id) ($($_.tier))" }) -join ', '))
    }
    $hex = $hits[0].hex_id
    return (Invoke-GenieWorker "/clonepool/$([uri]::EscapeDataString($hex))?meta=true").Content | ConvertFrom-Json
}

function Invoke-GenieClone([string]$Id, [string]$To, [switch]$Force) {
    $row = Resolve-GenieRow $Id
    $r = Invoke-GenieWorker "/clonepool/$([uri]::EscapeDataString($row.hex_id))"
    if ($r.StatusCode -ne 200) { throw "worker returned HTTP $($r.StatusCode) for $($row.name)" }
    $ctype = [string]($r.Headers['Content-Type'] | Select-Object -First 1)
    # The worker falls back to the D1 row as JSON when R2 has no object.
    if ($ctype -notmatch 'octet-stream') { throw "$($row.name): no bytes in R2 (worker returned catalog metadata only). Re-intake it from the machine that has it." }

    $bytes = [byte[]]$r.Content
    $sha3  = Get-GenieSha3 $bytes
    $want  = if ($row.PSObject.Properties['hash_sha3'] -and $row.hash_sha3) { ([string]$row.hash_sha3).ToLowerInvariant() } else { $null }
    if ($want -and $sha3 -ne $want) {
        throw "$($row.name): SHA3-512 MISMATCH — R2 bytes do not match custody. Not written.`n    custody $($want.Substring(0,16))…  got $($sha3.Substring(0,16))…"
    }
    if (-not $want -and -not $Force) {
        throw "$($row.name): D1 has no SHA3 baseline, so the bytes can't be verified. Not written. Use -Force to accept unverified bytes."
    }

    $destDir = if ($To) { $To } else { $script:GenieCloset }
    New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    # A name can carry folders (kernel/main_kernel.py: another file holds the bare name); on disk it is the file name.
    $dest = Join-Path $destDir (Split-Path ([string]$row.name) -Leaf)
    $part = "$dest.genie-part"
    [System.IO.File]::WriteAllBytes($part, $bytes)
    Move-Item -LiteralPath $part -Destination $dest -Force       # atomic swap, never a half file
    $state = if ($want) { 'verified' } else { 'UNVERIFIED (-Force)' }
    $info = [pscustomobject]@{ Name = $row.name; Sha3 = $sha3; Verified = [bool]$want; Path = $dest }
    G-Ok ("cloned {0}  v{1}  {2:N1} KB  sha3 {3}  -> {4}" -f $row.name, ([string]$row.version).TrimStart('v'), ($bytes.Length / 1KB), $state, $dest)
    return $info
}

# ── Custody audit: rows with no SHA3 baseline (read-only) ───────────────────
# For every clonepool row missing hash_sha3: pull its R2 bytes, hash them, and
# look for local copies (its pool_path + same-named files in the repo). Two
# independent copies that agree are the only safe baseline, so the generated
# script only re-intakes a file when a local copy is byte-identical to R2, or
# when R2 has no bytes and a local copy exists. Everything else is listed for
# Jerry to decide. Genie writes nothing to R2 or D1 — intake does, when run.
function ConvertTo-GenieLocalPath([string]$p) {
    if (-not $p) { return $null }
    if (-not $IsWindows) {                # a Windows drive path (/e/... or E:/...) means nothing on Linux
        if ($p -match '^/[a-zA-Z]/' -or $p -match '^[A-Za-z]:[\\/]') { return $null }
        return $p
    }
    if ($p -match '^/([a-zA-Z])/(.*)$')  { return "$($Matches[1].ToUpper()):\$($Matches[2] -replace '/', '\')" }
    if ($p -match '^[A-Za-z]:/')         { return ($p -replace '/', '\') }
    return $null                          # /home/... = old WSL/Linux pool, not on this disk
}

function Invoke-GenieCustodyAudit {
    # GET /clonepool returns 100 rows unless asked for more — the audit saw only the newest 100.
    $all = @(((Invoke-GenieWorker '/clonepool?limit=1000000').Content | ConvertFrom-Json).clonepool)
    $rows = @($all | Where-Object { -not ($_.PSObject.Properties['hash_sha3'] -and $_.hash_sha3) })
    G-Info "$($all.Count) clonepool rows, $($rows.Count) without a SHA3 baseline — checking each (read-only)"

    $skip = '[\\/](\.git|node_modules|__pycache__|\.venv|venv|dist|build|\.wrangler)[\\/]'   # both separators
    $repoFiles = @(Get-ChildItem -LiteralPath $script:GenieRepo -Recurse -File -ErrorAction SilentlyContinue |
                   Where-Object { $_.FullName -notmatch $skip })
    $byName = @{}
    foreach ($f in $repoFiles) { if (-not $byName.ContainsKey($f.Name)) { $byName[$f.Name] = @() }; $byName[$f.Name] += $f.FullName }

    $report = foreach ($r in $rows) {
        $rec = [ordered]@{ name = $r.name; hex_id = $r.hex_id; version = $(if ($r.PSObject.Properties['version']) { $r.version } else { '' }); verdict = ''; r2_sha3 = ''; local = ''; action = '' }
        $r2 = $null
        try {
            $resp = Invoke-GenieWorker "/clonepool/$([uri]::EscapeDataString($r.hex_id))"
            $ct = [string]($resp.Headers['Content-Type'] | Select-Object -First 1)
            if ($resp.StatusCode -eq 200 -and $ct -match 'octet-stream') { $r2 = [byte[]]$resp.Content }
        } catch { $rec.verdict = 'ERROR'; $rec.action = $_.Exception.Message; [pscustomobject]$rec; continue }
        $r2sha = if ($r2) { Get-GenieSha3 $r2 } else { $null }
        if ($r2sha) { $rec.r2_sha3 = $r2sha.Substring(0, 16) }

        $cands = @()
        $lp = ConvertTo-GenieLocalPath $(if ($r.PSObject.Properties['pool_path']) { $r.pool_path } else { $null })
        if ($lp -and (Test-Path -LiteralPath $lp -PathType Leaf)) { $cands += (Resolve-Path -LiteralPath $lp).Path }
        if ($byName.ContainsKey($r.name)) { $cands += $byName[$r.name] }
        $isDir = ($lp -and (Test-Path -LiteralPath $lp -PathType Container)) -or
                 (@($repoFiles | Where-Object { $_.Directory.Name -eq $r.name } | Select-Object -First 1).Count -gt 0 -and -not $byName.ContainsKey($r.name))

        $match = $null; $firstLocal = $null
        foreach ($c in ($cands | Select-Object -Unique)) {
            if (-not $firstLocal) { $firstLocal = $c }
            if ($r2sha -and ((Get-GenieSha3 ([System.IO.File]::ReadAllBytes($c))) -eq $r2sha)) { $match = $c; break }
        }
        if ($isDir -and -not $r2) {
            $rec.verdict = 'DIRECTORY'; $rec.action = 'directory snapshot — re-intake the folder to give it a manifest baseline'
        } elseif ($match) {
            $rec.verdict = 'MATCH'; $rec.local = $match; $rec.action = 're-intake: local copy is byte-identical to R2'
        } elseif ($r2 -and $firstLocal) {
            $rec.verdict = 'DIFFERS'; $rec.local = $firstLocal; $rec.action = 'local differs from R2 — re-intake makes a NEW version; R2 bytes stay unverified history'
        } elseif ($r2) {
            $rec.verdict = 'R2-ONLY'; $rec.action = 'no local copy — only way to baseline is to trust the R2 bytes as-is (your call)'
        } elseif ($firstLocal) {
            $rec.verdict = 'LOCAL-ONLY'; $rec.local = $firstLocal; $rec.action = 're-intake: R2 has no bytes, local copy exists'
        } else {
            $rec.verdict = 'LOST'; $rec.action = 'no R2 bytes, no local copy — catalog row only'
        }
        [pscustomobject]$rec
    }

    $stamp = (Get-Date).ToString('yyyyMMdd-HHmmss')
    New-Item -ItemType Directory -Force -Path $script:GenieHome | Out-Null
    $csv = Join-Path $script:GenieHome "custody-audit-$stamp.csv"
    $ps1 = Join-Path $script:GenieHome "custody-reintake-$stamp.ps1"
    $report | Export-Csv -LiteralPath $csv -NoTypeInformation -Encoding utf8

    $lines = @("# Generated by genie custody $stamp — review, then run in PS7.",
               "# Only files with a trustworthy source are active. Others are commented with the reason.", '')
    foreach ($x in $report) {
        $q = if ($x.local) { "'" + ($x.local -replace "'", "''") + "'" } else { '' }
        switch ($x.verdict) {
            'MATCH'      { $lines += "intake $q   # $($x.name): local == R2" }
            'LOCAL-ONLY' { $lines += "intake $q   # $($x.name): R2 had no bytes" }
            'DIFFERS'    { $lines += "# intake $q   # $($x.name): DIFFERS from R2 — becomes a new version; decide" }
            default      { $lines += "# $($x.name): $($x.verdict) — $($x.action)" }
        }
    }
    Set-Content -LiteralPath $ps1 -Value $lines -Encoding utf8

    Write-Host ''
    $report | Group-Object verdict | Sort-Object Count -Descending | ForEach-Object {
        Write-Host ("  {0,-11} {1,3}" -f $_.Name, $_.Count) -ForegroundColor $(switch ($_.Name) { 'MATCH' { 'Green' } 'LOCAL-ONLY' { 'Green' } 'LOST' { 'Red' } 'ERROR' { 'Red' } default { 'Yellow' } })
    }
    Write-Host ''
    G-Ok "report  : $csv"
    G-Ok "script  : $ps1   (review it, then:  & '$ps1')"
}

# ── Profile wiring ───────────────────────────────────────────────────────────
function Install-GenieProfile {
    $profilePath = $PROFILE.CurrentUserAllHosts
    $self = (Resolve-Path $PSCommandPath).Path
    $line = ". '$self'   # Phoenix Genie"
    if (-not (Test-Path $profilePath)) { New-Item -ItemType File -Force -Path $profilePath | Out-Null }
    $existing = Get-Content $profilePath -Raw -ErrorAction SilentlyContinue
    if ($existing -and $existing -match [regex]::Escape('# Phoenix Genie')) {
        G-Info "already in $profilePath"; return
    }
    Add-Content -Path $profilePath -Value "`n$line" -Encoding utf8
    G-Ok "added to $profilePath — every new PS7 window loads Genie and boots the kernel if it's down."
    G-Info 'Set $env:PHOENIX_GENIE_AUTOUP = "0" to load Genie without auto-booting.'
}

# ── The command ──────────────────────────────────────────────────────────────
function genie {
    [CmdletBinding()]
    param(
        [Parameter(Position = 0)]
        [ValidateSet('up', 'down', 'restart', 'status', 'log', 'doctor', 'find', 'clone', 'import', 'closet', 'send', 'custody', 'profile', 'help')]
        [string]$Command = 'status',
        [Parameter(Position = 1, ValueFromRemainingArguments)]
        [string[]]$Args2,
        [string]$To,
        [int]$Lines = 40,
        [switch]$Force,
        [ValidateRange(1, 4)][int]$Sector = 2,
        [ValidateSet('physics', 'network', 'ai', 'assets', 'system', 'user')][string]$Family = 'user',
        [ValidateSet('', 'PYTHON', 'SHELL', 'BINARY', 'NODE', 'POWER')][string]$Type = '',
        [string]$Name,
        [switch]$Write,
        [ValidateRange(1, 4)][int]$Channel = 1,
        [ValidateRange(1, 600)][int]$Wait = 120
    )
    Set-StrictMode -Version Latest   # this call and the helpers it runs only
    try {
        switch ($Command) {
            # a person's `down` leaves a marker so Buddy Heal (sector3/mesh/phoenix_buddy.py) does not
            # start the kernel again behind their back; `up` clears it (2026-10-09)
            'up'      { Remove-Item (Join-Path $script:GenieHome 'stopped-on-purpose') -ErrorAction SilentlyContinue; [void](Start-GenieKernel) }
            'down'    { Stop-GenieKernel; Set-Content -Path (Join-Path $script:GenieHome 'stopped-on-purpose') -Value (Get-Date).ToString('s') -Encoding utf8 }
            'restart' { Stop-GenieKernel; Start-Sleep -Milliseconds 500; [void](Start-GenieKernel) }
            'status'  { Show-GenieStatus }
            'log'     { if (Test-Path $script:GenieLog) { Get-Content $script:GenieLog -Tail $Lines } else { G-Info 'no log yet' } }
            'find'    {
                if (-not $Args2) { throw 'usage: genie find <term>' }
                $s = (Invoke-GenieWorker "/search?q=$([uri]::EscapeDataString($Args2 -join ' '))").Content | ConvertFrom-Json
                $rows = @($s.clonepool)
                if (-not $rows) { G-Info 'no matches'; break }
                $w = [Math]::Max(4, ($rows | ForEach-Object { ([string]$_.name).Length } | Measure-Object -Maximum).Maximum)
                Write-Host ("  {0}  {1,-4} {2,-3} {3,-8} {4}" -f 'name'.PadRight($w), 'ver', 'tier', 'state', 'hex_id') -ForegroundColor DarkCyan
                foreach ($x in $rows) {
                    $ver = if ($x.PSObject.Properties['version'] -and $x.version) { "v" + ([string]$x.version).TrimStart('v') } else { '' }
                    Write-Host ("  {0}  {1,-4} {2,-3} {3,-8} {4}" -f ([string]$x.name).PadRight($w), $ver, $x.tier, $x.state, $x.hex_id)
                }
            }
            'clone'   {
                if (-not $Args2) { throw 'usage: genie clone <name|hex_id> [...] [-To <dir>] [-Force]' }
                foreach ($id in $Args2) {
                    try { [void](Invoke-GenieClone -Id $id -To $To -Force:$Force) } catch { G-Err $_.Exception.Message }
                }
            }
            'import'  {
                # A suit has ONE step: import. A local file is intaked (custody, R2), then the
                # kernel LOADS it: pulled from R2 straight into RAM, SHA3-checked against custody,
                # never written to this disk. Then it runs once and its answer is printed.
                #   genie import .\my_suit.py ['{"stage": "json"}']      genie import my_suit.py
                if (-not $Args2) { throw 'usage: genie import <file|name|hex_id> [''{json stage}''] [-Sector 1-4] [-Family user] [-Type PYTHON] [-Name suit] [-Write]' }
                $stageJson = (@($Args2 | Where-Object { $_.TrimStart().StartsWith('{') }) -join ' ')
                $ids = @($Args2 | Where-Object { -not $_.TrimStart().StartsWith('{') })
                if ($Name -and $ids.Count -gt 1) { throw '-Name only works with a single import' }
                if (-not (Test-GenieHealth)) { G-Info 'kernel is down — starting it'; Start-GenieKernel }
                if (-not (Test-GenieHealth)) { throw 'kernel did not come up — see genie log' }
                foreach ($id in $ids) {
                    try {
                        if (Test-Path -LiteralPath $id -PathType Leaf) { $id = Invoke-GenieIntakeLocal $id }
                        $row = Resolve-GenieRow $id
                        $body = @{ hex = $row.hex_id; sector = $Sector; family = $Family; write = [bool]$Write }
                        if ($row.PSObject.Properties['hash_sha3'] -and $row.hash_sha3) { $body.sha3_512 = ([string]$row.hash_sha3).ToLowerInvariant() }
                        if ($Type) { $body.suit_type = $Type }
                        if ($Name) { $body.name = $Name } elseif ($row.name) { $body.name = (Split-Path ([string]$row.name) -Leaf) }   # the suit's name, without the pool's folder part
                        $r = Invoke-GenieControl POST '/suits' $body
                        if (-not $r.in_ram) { G-Warn "$($r.name) was written to the closet on disk, not loaded in RAM" }
                        G-Ok ("loaded: {0}  [{1}] sector {2} ring {3}  {4}  closet now {5} suits" -f $r.name, $r.suit_type, $r.sector, $r.ring_pos,
                              $(if ($r.in_ram) { 'R2 -> RAM, nothing on disk' } else { 'closet (disk)' }), $r.suits_in_closet)
                        $suitName = [System.IO.Path]::GetFileNameWithoutExtension([string]$r.name)
                        $ans = Send-GenieStage -Suit $suitName -Json $stageJson -Channel $Channel -Wait $Wait
                        $ans | ConvertTo-Json -Depth 10 | Write-Host
                        # the suit answered but the work failed: still a failure for whoever ran it (2026-10-09)
                        if ($ans -and $ans.PSObject.Properties['ok'] -and $ans.ok -eq $false) { $global:GenieFailed = $true }
                    } catch { G-Err "$id — $($_.Exception.Message)" }
                }
            }
            'send'    {
                if (-not (Test-GenieHealth)) { throw 'kernel is down — genie up first' }
                $r = Send-GenieStage -Suit $Args2[0] -Json (($Args2 | Select-Object -Skip 1) -join ' ') -Channel $Channel -Wait $Wait
                $r | ConvertTo-Json -Depth 10 | Write-Host
                # the suit answered but the work failed: still a failure for whoever ran it (2026-10-09)
                if ($r -and $r.PSObject.Properties['ok'] -and $r.ok -eq $false) { $global:GenieFailed = $true }
            }
            'closet'  {
                $c = Invoke-GenieControl GET '/closet' $null
                $names = @($c.suits.PSObject.Properties | Sort-Object { $_.Value.sector }, { $_.Value.ring_pos })
                $w = [Math]::Max(4, ($names | ForEach-Object { $_.Name.Length } | Measure-Object -Maximum).Maximum)
                Write-Host ("  {0}  sec ring  {1,-7} {2,-8} {3,-9} {4}" -f 'suit'.PadRight($w), 'type', 'family', 'preloaded', 'origin  runs in') -ForegroundColor DarkCyan
                foreach ($n in $names) {
                    $v = $n.Value
                    $where = if ($v.PSObject.Properties['where'] -and $v.where -eq 'playbox') { 'play box' } else { 'KERNEL' }
                    Write-Host ("  {0}  {1,-3} {2,-4}  {3,-7} {4,-8} {5,-9} {6,-7} {7}" -f $n.Name.PadRight($w), $v.sector, $v.ring_pos, $v.type, $v.family,
                                $(if ($v.preloaded) { 'yes' } else { '-' }), $(if ($v.imported) { 'genie' } else { 'core' }), $where) `
                               -ForegroundColor $(if ($v.imported) { 'Green' } else { 'Gray' })
                }
                Write-Host "  $($c.suit_count) suits" -ForegroundColor DarkCyan
                if ($c.PSObject.Properties['playbox']) {
                    $pb = $c.playbox
                    if ($pb.running) { Write-Host ("  play box: pid {0}, {1} MB / {2}% CPU cap, {3} s per run, restarts {4}" -f $pb.pid, $pb.mem_mb, $pb.cpu_pct, $pb.timeout_s, $pb.restarts) -ForegroundColor DarkCyan }
                    else { Write-Host '  play box: not running (starts with the first entertainment suit)' -ForegroundColor DarkCyan }
                }
            }
            'custody' { Invoke-GenieCustodyAudit }
            'doctor'  {
                $py = Get-GeniePython
                if ($py) { G-Ok "python   $py" } else { G-Err 'python   not found' }
                if (Test-Path $script:GenieEntry) { G-Ok "kernel   $($script:GenieEntry)" } else { G-Err "kernel   missing: $($script:GenieEntry)" }
                if ([System.Security.Cryptography.SHA3_512]::IsSupported) { G-Ok 'sha3     native' } else { G-Warn 'sha3     via Python fallback' }
                if ($env:PHOENIX_AUTH) { G-Ok 'auth     PHOENIX_AUTH set' } else { G-Err 'auth     PHOENIX_AUTH not set' }
                if ($env:CF_ACCESS_CLIENT_ID -and $env:CF_ACCESS_CLIENT_SECRET) { G-Ok 'access   CF Access token set' } else { G-Warn 'access   CF_ACCESS_CLIENT_ID/SECRET not set' }
                try {
                    $w = Invoke-GenieWorker '/whoami'
                    if ($w.StatusCode -eq 200) { G-Ok "worker   $($script:GenieWorker) — auth OK" }
                    else { G-Err "worker   HTTP $($w.StatusCode): $($w.Content)" }
                } catch { G-Err "worker   $($_.Exception.Message)" }
                if (Test-GenieHealth) { G-Ok "kernel   up on :$($script:GenieStatusPort)" } else { G-Warn 'kernel   down (genie up)' }
                try { [void](Invoke-GenieControl GET '/health' $null); G-Ok "control  :$($script:GenieCtlPort) token OK" }
                catch { G-Warn "control  $($_.Exception.Message)" }
            }
            'profile' { Install-GenieProfile }
            'help'    {
                @'
  genie up | down | restart        boot / stop the Phoenix Universal Kernel (background)
  genie status                     kernel state, Helix ports, /status
  genie log [-Lines N]             tail the kernel log
  genie doctor                     python, kernel, sha3, auth, worker, kernel health
  genie find <term>                search the clonepool (D1)
  genie clone <name|hex> [-To d]   pull from R2, SHA3-512 verified before write
  genie import <file|name> ['{json}']  THE one step for a suit: a local file is intaked, then
                                   loaded R2 -> RAM (SHA3-checked, never on disk) and run once
                                   [-Sector 1-4] [-Family user] [-Type PYTHON] [-Name s] [-Write]
  genie closet                     every suit in the live closet (green = imported by Genie)
  genie send <suit> ['{json}']      run an already-loaded suit again with a new stage [-Channel 1-4] [-Wait s]
  genie custody                    audit clonepool rows with no SHA3 baseline; writes a reviewed re-intake script
  genie profile                    load Genie (and auto-boot) in every PS7 window
'@ | Write-Host
            }
        }
    } catch {
        G-Err $_.Exception.Message
    }
}

# ── Auto-boot on profile load ────────────────────────────────────────────────
# Fast path: /health is a localhost call (refused instantly when down).
if ($MyInvocation.InvocationName -eq '.' -and $env:PHOENIX_GENIE_AUTOUP -ne '0') {
    if (-not (Test-GenieHealth)) { [void](Start-GenieKernel) }
}
