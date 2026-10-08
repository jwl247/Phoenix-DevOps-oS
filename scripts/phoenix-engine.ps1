# phoenix-engine.ps1 — Jarvis's alternate engine on PBMII, inside a "virtual processor".
# Phoenix DevOps OS | jwl247 | GPL v3
# Jerry 2026-10-08: "build a virtual processor and tie my cores to that, giving me some breathing room
# if bad shit starts happening".
#
# The virtual processor is a Windows Job Object: the OS itself (not the engine) enforces
#   - a HARD CPU cap (default 30% of the whole machine - it can never take more)
#   - which logical cores it may run on (default 8-11 of 12)
#   - a memory ceiling (default 4 GB) and below-normal priority
# so Jerry's own work always has room. `engine stop` is the kill switch.
#
#   engine start [-CpuPercent 30] [-Cores 0xF00] [-MemGB 4]
#   engine stop
#   engine status
#
# The engine itself: llama.cpp llama-server (E:\Phoenix\llm-engine\llama-b11149, sha256-checked,
# in the pool), Jarvis's model, LOCAL ONLY (127.0.0.1:8080), engine key required, no web UI, no MCP
# proxy, and a Windows Firewall rule blocking ALL its outbound traffic (no phoning home).

$script:EngineExe   = 'E:\Phoenix\llm-engine\llama-b11149\llama-server.exe'
$script:EngineModel = 'E:\models\llama3.2-3b\llama3.2-3b-q4km.gguf'
$script:EngineKey   = Join-Path $HOME '.phoenix\llm\engine.key'
$script:EngineHome  = Join-Path $HOME '.phoenix\llm'
$script:EnginePid   = Join-Path $script:EngineHome 'engine.pid'

if (-not ('Phx.JobBox' -as [type])) {
Add-Type -Namespace Phx -Name JobBox -MemberDefinition @'
[StructLayout(LayoutKind.Sequential)] public struct CPU_RATE { public uint ControlFlags; public uint CpuRate; }
[StructLayout(LayoutKind.Sequential)] public struct BASIC_LIMIT { public long PerProcessUserTimeLimit; public long PerJobUserTimeLimit; public uint LimitFlags; public UIntPtr MinimumWorkingSetSize; public UIntPtr MaximumWorkingSetSize; public uint ActiveProcessLimit; public UIntPtr Affinity; public uint PriorityClass; public uint SchedulingClass; }
[StructLayout(LayoutKind.Sequential)] public struct IO_COUNTERS { public ulong a, b, c, d, e, f; }
[StructLayout(LayoutKind.Sequential)] public struct EXT_LIMIT { public BASIC_LIMIT Basic; public IO_COUNTERS Io; public UIntPtr ProcessMemoryLimit; public UIntPtr JobMemoryLimit; public UIntPtr PeakProcessMemoryUsed; public UIntPtr PeakJobMemoryUsed; }
[DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] public static extern IntPtr CreateJobObject(IntPtr a, string name);
[DllImport("kernel32.dll", SetLastError=true)] public static extern bool SetInformationJobObject(IntPtr job, int cls, ref CPU_RATE info, int len);
[DllImport("kernel32.dll", SetLastError=true)] public static extern bool SetInformationJobObject(IntPtr job, int cls, ref EXT_LIMIT info, int len);
[DllImport("kernel32.dll", SetLastError=true)] public static extern bool AssignProcessToJobObject(IntPtr job, IntPtr proc);
'@
}

function Get-PhoenixEngineProcess {
    if (-not (Test-Path $script:EnginePid)) { return $null }
    $id = [int](Get-Content $script:EnginePid -Raw)
    $p = Get-Process -Id $id -ErrorAction SilentlyContinue
    if ($p -and $p.Path -eq $script:EngineExe) { return $p }
    return $null
}

function Start-PhoenixEngine {
    param([int]$CpuPercent = 30, [long]$Cores = 0xF00, [int]$MemGB = 4)
    if (Get-PhoenixEngineProcess) { Write-Host '  engine: already running (engine status)'; return }
    foreach ($f in $script:EngineExe, $script:EngineModel, $script:EngineKey) {
        if (-not (Test-Path $f)) { Write-Host "  engine: missing $f" -ForegroundColor Red; return }
    }
    New-Item -ItemType Directory -Force $script:EngineHome | Out-Null
    # No phoning home: Windows blocks every outbound connection this exe tries (not a switch in the engine).
    if (-not (Get-NetFirewallRule -DisplayName 'Phoenix LLM engine - block ALL outbound' -ErrorAction SilentlyContinue)) {
        try { New-NetFirewallRule -DisplayName 'Phoenix LLM engine - block ALL outbound' -Direction Outbound -Program $script:EngineExe -Action Block -Profile Any | Out-Null }
        catch { Write-Host "  engine: could not add the outbound block rule ($($_.Exception.Message)) - not starting" -ForegroundColor Red; return }
    }
    $args = @('--model', $script:EngineModel, '--alias', 'llama3.2:3b', '--host', '127.0.0.1', '--port', '8080',
              '--api-key-file', $script:EngineKey, '--ctx-size', '8192', '--threads', '4', '--no-webui', '--no-ui-mcp-proxy')
    $p = Start-Process $script:EngineExe -ArgumentList $args -WindowStyle Hidden -PassThru `
            -RedirectStandardError (Join-Path $script:EngineHome 'engine.log') -RedirectStandardOutput (Join-Path $script:EngineHome 'engine.out')

    # The virtual processor: one Job Object, limits set BEFORE the engine is put in it.
    $job = [Phx.JobBox]::CreateJobObject([IntPtr]::Zero, "PhoenixEngineBox-$($p.Id)")
    $cpu = New-Object Phx.JobBox+CPU_RATE
    $cpu.ControlFlags = 0x1 -bor 0x4          # ENABLE | HARD_CAP
    $cpu.CpuRate = [uint32]($CpuPercent * 100) # in 1/100ths of a percent of the whole machine
    $okCpu = [Phx.JobBox]::SetInformationJobObject($job, 15, [ref]$cpu, [Runtime.InteropServices.Marshal]::SizeOf($cpu))
    $ext = New-Object Phx.JobBox+EXT_LIMIT
    $ext.Basic.LimitFlags = 0x10 -bor 0x20 -bor 0x200   # AFFINITY | PRIORITY_CLASS | JOB_MEMORY
    $ext.Basic.Affinity = [UIntPtr][uint64]$Cores
    $ext.Basic.PriorityClass = 0x4000                   # BELOW_NORMAL
    $ext.JobMemoryLimit = [UIntPtr][uint64]([long]$MemGB * 1GB)
    $okExt = [Phx.JobBox]::SetInformationJobObject($job, 9, [ref]$ext, [Runtime.InteropServices.Marshal]::SizeOf($ext))
    $okAssign = [Phx.JobBox]::AssignProcessToJobObject($job, $p.Handle)
    if (-not ($okCpu -and $okExt -and $okAssign)) {
        Stop-Process -Id $p.Id -Force
        Write-Host "  engine: the virtual processor could not be built (cpu=$okCpu limits=$okExt assign=$okAssign) - engine stopped, nothing left running" -ForegroundColor Red
        return
    }
    # Belt and braces: the job's affinity/priority limits did not show on the process in the first test
    # (2026-10-08: affinity read 0xFFF, priority Normal), so set them on the process too and check.
    try { $p.ProcessorAffinity = [IntPtr]$Cores; $p.PriorityClass = 'BelowNormal' } catch {}
    $p.Refresh()
    if ([int64]$p.ProcessorAffinity -ne $Cores -or $p.PriorityClass -ne 'BelowNormal') {
        Stop-Process -Id $p.Id -Force
        Write-Host ("  engine: cores/priority would not stick (affinity 0x{0:X}, {1}) - engine stopped" -f [int64]$p.ProcessorAffinity, $p.PriorityClass) -ForegroundColor Red
        return
    }
    Set-Content $script:EnginePid $p.Id
    $up = $false
    foreach ($i in 1..60) { try { if ((Invoke-RestMethod http://127.0.0.1:8080/health -TimeoutSec 2).status -eq 'ok') { $up = $true; break } } catch {}; Start-Sleep 1 }
    if ($up) { Write-Host ("  engine: up - pid {0}, in its virtual processor: hard cap {1}% CPU, cores 0x{2:X}, {3} GB, below-normal" -f $p.Id, $CpuPercent, $Cores, $MemGB) -ForegroundColor Green }
    else { Write-Host "  engine: started (pid $($p.Id)) but never answered /health - see $($script:EngineHome)\engine.log" -ForegroundColor Red }
}

function Stop-PhoenixEngine {
    $p = Get-PhoenixEngineProcess
    if (-not $p) { Write-Host '  engine: not running'; return }
    Stop-Process -Id $p.Id -Force
    Remove-Item $script:EnginePid -ErrorAction SilentlyContinue
    Write-Host "  engine: stopped (pid $($p.Id))" -ForegroundColor Green
}

function Get-PhoenixEngineStatus {
    $p = Get-PhoenixEngineProcess
    if (-not $p) { Write-Host '  engine: not running'; return }
    $h = try { (Invoke-RestMethod http://127.0.0.1:8080/health -TimeoutSec 2).status } catch { 'no answer' }
    Write-Host ("  engine: pid {0}  health {1}  cpu {2:N0}s  mem {3:N0} MB  affinity 0x{4:X}  priority {5}" -f `
        $p.Id, $h, $p.TotalProcessorTime.TotalSeconds, ($p.WorkingSet64 / 1MB), [int64]$p.ProcessorAffinity, $p.PriorityClass)
}

function Invoke-PhoenixEngine {
    param([Parameter(Position = 0)][ValidateSet('start', 'stop', 'status')][string]$Verb = 'status',
          [int]$CpuPercent = 30, [long]$Cores = 0xF00, [int]$MemGB = 4)
    switch ($Verb) {
        'start'  { Start-PhoenixEngine -CpuPercent $CpuPercent -Cores $Cores -MemGB $MemGB }
        'stop'   { Stop-PhoenixEngine }
        'status' { Get-PhoenixEngineStatus }
    }
}
Set-Alias -Name engine -Value Invoke-PhoenixEngine -Scope Global -Force -ErrorAction SilentlyContinue
