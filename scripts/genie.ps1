#Requires -Version 7.0
<#
.SYNOPSIS
    genie.ps1 — say what you want in plain words; the genie picks a tool from the
    library and runs it through the universal kernel.

.DESCRIPTION
    genie is the compaq up             plain English -> one tool from the library
    genie learn <name> "<what it does>" <command> [args...] [-Ask]
                                       add a tool to the library ("build a library")
    genie library                      list the tools it can use
    genie preload                      load the closet: pull + verify every tool's program now
    genie install                      load genie + radar in every PS7 window; teach it the Radar tools
    genie forget <name>                take a tool out of the library
    genie log                          what it was asked and what it did

    The local model (Ollama, llama3.2:3b by default) is only allowed to answer
    with a tool name from the library or "none", in a fixed JSON shape
    (constrained decoding, the trick that took small models from 1-3/6 to 6/6
    in H.L.K, sector3/hlk/hlk.py). With no model running, it falls back to
    matching words: a clear match on a read-only tool runs, anything else asks.

    A tool's command runs through the universal kernel (scripts/phx-kernel.ps1):
    if this machine doesn't have it, the kernel pulls it from the clone pool,
    checks it against D1 custody and asks once. Arguments the model fills in are
    passed as separate arguments, never pasted into a command line, and only
    tools in the library can run at all.

    Tiers (CLAUDE.md "the permission tiers"): auto = runs without asking (reading,
    checking); ask = shows what it's about to do and waits for your yes.

.NOTES
    UnitedSys — United Systems | jwl247 | GPL-3.0 | Sector 2 (consumer side of the clone pool)
    Library: ~/.phoenix/genie/library.json   Log: ~/.phoenix/genie/log.jsonl
#>

$global:PhxGenie = @{
    Home  = Join-Path $HOME '.phoenix/genie'
    Model = if ($env:PHX_GENIE_MODEL) { $env:PHX_GENIE_MODEL } else { 'llama3.2:3b' }
    Url   = if ($env:PHX_GENIE_OLLAMA) { $env:PHX_GENIE_OLLAMA } else { 'http://127.0.0.1:11434' }
}
$global:PhxGenie.Library = Join-Path $global:PhxGenie.Home 'library.json'
$global:PhxGenie.ScriptDir = $PSScriptRoot
$global:PhxGenie.Log     = Join-Path $global:PhxGenie.Home 'log.jsonl'

# Tools every genie starts with: they only read and report, so they run without asking.
$global:PhxGenieSeed = [ordered]@{
    'kernel-status' = @{ says = "show the universal kernel's status: pool, keys, what's approved"; command = 'bingo'; argv = @('status'); tier = 'auto' }
    'kernel-list'   = @{ says = 'list the programs this machine has pulled from the clone pool';     command = 'bingo'; argv = @('list');   tier = 'auto' }
    'kernel-log'    = @{ says = 'show what the kernel pulled, approved and ran recently';            command = 'bingo'; argv = @('log');    tier = 'auto' }
}

# ── library ─────────────────────────────────────────────────────────────────
function global:Get-PhxGenieLibrary {
    $lib = [ordered]@{}
    foreach ($k in $global:PhxGenieSeed.Keys) { $lib[$k] = $global:PhxGenieSeed[$k] }
    try {
        $mine = Get-Content -LiteralPath $global:PhxGenie.Library -Raw -ErrorAction Stop | ConvertFrom-Json -AsHashtable
        foreach ($k in $mine.Keys) { $lib[$k] = $mine[$k] }
    } catch { }
    return $lib
}

function global:Save-PhxGenieLibrary([hashtable]$Mine) {
    New-Item -ItemType Directory -Path $global:PhxGenie.Home -Force | Out-Null
    $tmp = "$($global:PhxGenie.Library).tmp"
    $Mine | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $tmp -Encoding utf8
    Move-Item -LiteralPath $tmp -Destination $global:PhxGenie.Library -Force
}

function global:Get-PhxGenieMine {
    try { $m = Get-Content -LiteralPath $global:PhxGenie.Library -Raw -ErrorAction Stop | ConvertFrom-Json -AsHashtable; if ($m) { return $m } } catch { }
    return @{}
}

function global:Write-PhxGenieLog([hashtable]$Entry) {
    try {
        New-Item -ItemType Directory -Path $global:PhxGenie.Home -Force | Out-Null
        $Entry['ts'] = [DateTime]::UtcNow.ToString('o'); $Entry['host'] = [Environment]::MachineName
        Add-Content -LiteralPath $global:PhxGenie.Log -Value ($Entry | ConvertTo-Json -Compress -Depth 5) -Encoding utf8
    } catch { }
}

# ── deciding ────────────────────────────────────────────────────────────────
# One seam for the model call, so the tests can stand in for Ollama.
$global:PhxGenieModelCall = {
    param([hashtable]$Body)
    $uri = $global:PhxGenie.Url.TrimEnd('/') + '/api/chat'
    $r = Invoke-RestMethod -Uri $uri -Method Post -ContentType 'application/json' -TimeoutSec 300 `
            -Body ($Body | ConvertTo-Json -Depth 12 -Compress) -ErrorAction Stop
    return [string]$r.message.content
}

function global:Get-PhxGenieRules([System.Collections.IDictionary]$Lib) {
    $lines = foreach ($k in $Lib.Keys) {
        $t = $Lib[$k]; $holes = @(([regex]::Matches(($t.argv -join ' '), '\{(\w+)\}')) | ForEach-Object { $_.Groups[1].Value } | Select-Object -Unique)
        "- ${k}: $($t.says)" + $(if ($holes) { " (args: $($holes -join ', '))" } else { '' })
    }
    @"
You are the Phoenix genie. Pick the ONE tool below that does what the person asked, or "none"
if no tool fits. Never invent a tool. Fill "args" only with values the person actually said.
"say" is one short, plain sentence to the person about what you'll do (or why nothing fits).
Tools:
$($lines -join "`n")
"@
}

# -> @{ say; tool (name or $null); args = hashtable; how = 'model'|'words' }
function global:Resolve-PhxGenieAsk([string]$Ask, [System.Collections.IDictionary]$Lib) {
    $names = @($Lib.Keys)
    $shape = @{ type = 'object'; required = @('say', 'tool', 'args')
                properties = @{ say = @{ type = 'string' }; tool = @{ type = 'string'; enum = @($names + 'none') }; args = @{ type = 'object' } } }
    $body = @{ model = $global:PhxGenie.Model; stream = $false; format = $shape; keep_alive = -1; options = @{ temperature = 0 }
               messages = @(@{ role = 'system'; content = (Get-PhxGenieRules $Lib) }, @{ role = 'user'; content = $Ask }) }
    try {
        $d = (& $global:PhxGenieModelCall $body) | ConvertFrom-Json -AsHashtable
        $tool = [string]$d.tool
        return @{ say = [string]$d.say; tool = $(if ($tool -and $tool -ne 'none' -and $Lib.Contains($tool)) { $tool } else { $null })
                  args = $(if ($d.args -is [System.Collections.IDictionary]) { $d.args } else { @{} }); how = 'model' }
    } catch { }
    # No model: match the person's words against each tool's name + description.
    $words = @($Ask.ToLowerInvariant() -split '[^a-z0-9]+' | Where-Object { $_.Length -ge 3 })
    $scored = foreach ($k in $names) {
        $hay = ($k + ' ' + $Lib[$k].says).ToLowerInvariant()
        [pscustomobject]@{ Name = $k; Score = @($words | Where-Object { $hay.Contains($_) }).Count }
    }
    $best = @($scored | Sort-Object Score -Descending)
    if ($best.Count -and $best[0].Score -gt 0 -and ($best.Count -eq 1 -or $best[0].Score -gt $best[1].Score)) {
        return @{ say = "No model is running here, so I matched your words: $($best[0].Name)."; tool = $best[0].Name; args = @{}; how = 'words' }
    }
    return @{ say = "No model is running here and I couldn't tell which tool you meant. Try: genie library"; tool = $null; args = @{}; how = 'words' }
}

# Fill {holes} in the tool's argv from what was asked. -> string[] or $null (a hole left empty)
function global:Get-PhxGenieArgv([System.Collections.IDictionary]$Tool, [System.Collections.IDictionary]$ToolArgs) {
    $out = [System.Collections.Generic.List[string]]::new()
    foreach ($a in @($Tool.argv)) {
        $v = [string]$a
        foreach ($m in [regex]::Matches($v, '\{(\w+)\}')) {
            $x = $ToolArgs[$m.Groups[1].Value]
            if ($null -eq $x -or "$x".Trim() -eq '') { return $null }
            $v = $v.Replace($m.Value, "$x")
        }
        $out.Add($v)
    }
    return , $out.ToArray()
}

# ── doing ───────────────────────────────────────────────────────────────────
function global:Invoke-PhxGenieTool([string]$Name, [System.Collections.IDictionary]$Tool, [string[]]$Argv) {
    $cmd = Get-Command $Tool.command -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($cmd) { & $cmd @Argv; return }
    if (Get-Command Resolve-PhxKCommand -ErrorAction SilentlyContinue) {      # the kernel: pull, verify, ask once
        $hit = Resolve-PhxKCommand $Tool.command 'Runspace'
        if ($hit) { Invoke-PhxKCommand $hit $Argv; return }
    }
    Write-Warning "genie: '$($Tool.command)' isn't on this machine and the clone pool doesn't have it."
}

function global:Invoke-PhxGenie([string]$Ask) {
    $lib = Get-PhxGenieLibrary
    $d = Resolve-PhxGenieAsk $Ask $lib
    if ($d.say) { Write-Host "  genie: $($d.say)" -ForegroundColor Cyan }
    if (-not $d.tool) { Write-PhxGenieLog @{ ask = $Ask; how = $d.how; tool = $null; outcome = 'nothing fit' }; return }
    $tool = $lib[$d.tool]
    $argv = Get-PhxGenieArgv $tool $d.args
    if ($null -eq $argv) {
        Write-Host "  genie: $($d.tool) needs more detail than you gave (it uses: $(($tool.argv -join ' ')))." -ForegroundColor Yellow
        Write-PhxGenieLog @{ ask = $Ask; how = $d.how; tool = $d.tool; outcome = 'missing detail' }; return
    }
    $show = (@($tool.command) + $argv) -join ' '
    # Ask-tier tools always wait for a yes. Auto (read-only) tools just run, model or not:
    # without a model, Resolve-PhxGenieAsk only returns a tool on a clear word match.
    if ($tool.tier -ne 'auto') {
        if ((Read-Host "  Run '$show'? [y/N]") -notmatch '^[Yy]') { Write-PhxGenieLog @{ ask = $Ask; how = $d.how; tool = $d.tool; run = $show; outcome = 'declined' }; return }
    } else {
        Write-Host "  genie: running $show" -ForegroundColor DarkGray
    }
    Write-PhxGenieLog @{ ask = $Ask; how = $d.how; tool = $d.tool; run = $show; outcome = 'ran' }
    Invoke-PhxGenieTool $d.tool $tool $argv
}

function global:genie {
    $words = @($args | ForEach-Object { "$_" })
    $first = if ($words.Count) { $words[0] } else { '' }
    switch ($first) {
        '' { Write-Host '  genie <what you want, in plain words>   ·   genie learn | library | preload | install | forget | log' }
        'library' {
            $lib = Get-PhxGenieLibrary
            foreach ($k in $lib.Keys) { '{0,-18} {1,-5} {2}' -f $k, $lib[$k].tier, $lib[$k].says }
        }
        'learn' {
            # genie learn <name> "<what it does>" <command> [argv...] [-Ask]
            $ask = $words -contains '-Ask'; $w = @($words | Where-Object { $_ -ne '-Ask' })
            if ($w.Count -lt 4 -or $w[1] -notmatch '^[a-z0-9][a-z0-9-]{1,40}$') {
                Write-Host '  genie learn <name> "<what it does>" <command> [args, {holes} for things you say] [-Ask]'
                Write-Host '  example: genie learn mesh-links "show the health of every mesh link" phoenix-net links'; return
            }
            $mine = Get-PhxGenieMine
            $mine[$w[1]] = @{ says = $w[2]; command = $w[3]; argv = @($w | Select-Object -Skip 4); tier = $(if ($ask) { 'ask' } else { 'auto' }) }
            Save-PhxGenieLibrary $mine
            Write-PhxGenieLog @{ learned = $w[1]; command = $w[3]; tier = $mine[$w[1]].tier }
            Write-Host "  genie: learned $($w[1]) ($($mine[$w[1]].tier))"
        }
        'forget' {
            $mine = Get-PhxGenieMine
            if ($words.Count -ge 2 -and $mine.ContainsKey($words[1])) { $mine.Remove($words[1]); Save-PhxGenieLibrary $mine; Write-Host "  genie: forgot $($words[1])" }
            else { Write-Host "  genie: '$($words[1])' isn't one you taught it (the built-in ones stay)" }
        }
        'preload' {
            # Load the closet first (the original H.L.K Process Library): every tool's
            # program pulled and verified now, so asking later fetches nothing.
            if (-not (Get-Command bingo -ErrorAction SilentlyContinue)) { Write-Host '  genie: the universal kernel (phx-kernel.ps1) is not loaded'; return }
            bingo preload
        }
        'install' {
            # Next to the profile, beside the kernel: genie + radar load in every PS7 window,
            # and the genie learns the Radar tools (read-only, so they run without asking).
            $dir = Split-Path $PROFILE.CurrentUserAllHosts
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
            $lines = @()
            foreach ($f in 'radar.ps1', 'genie.ps1') {
                $src = Join-Path $global:PhxGenie.ScriptDir $f
                if (-not (Test-Path -LiteralPath $src)) { continue }
                $dst = Join-Path $dir $f
                if ($src -ne $dst) { Copy-Item -LiteralPath $src -Destination $dst -Force }
                $lines += ". `"$dst`"   # Phoenix $($f -replace '\.ps1$','')"
            }
            $cur = if (Test-Path -LiteralPath $PROFILE.CurrentUserAllHosts) { Get-Content -LiteralPath $PROFILE.CurrentUserAllHosts -Raw } else { '' }
            foreach ($l in $lines) { if ($cur -notmatch [regex]::Escape($l)) { Add-Content -LiteralPath $PROFILE.CurrentUserAllHosts -Value $l } }
            $mine = Get-PhxGenieMine
            $teach = [ordered]@{
                'radar-new'     = @{ says = "show the new set-aside bids from this morning's Radar email"; command = 'radar'; argv = @('new'); tier = 'auto' }
                'radar-client'  = @{ says = 'show the last week of set-aside bids for one Radar client by name'; command = 'radar'; argv = @('week', '{client}'); tier = 'auto' }
                'radar-clients' = @{ says = 'list the Radar subscribers: who, NAICS codes, states, billing'; command = 'radar'; argv = @('clients'); tier = 'auto' }
                'radar-runs'    = @{ says = "check whether Radar's daily run went out and what it found"; command = 'radar'; argv = @('runs'); tier = 'auto' }
            }
            foreach ($k in $teach.Keys) { if (-not $mine.ContainsKey($k)) { $mine[$k] = $teach[$k] } }
            Save-PhxGenieLibrary $mine
            Write-Host "  installed next to your profile: $(($lines | ForEach-Object { ($_ -split '"')[1] }) -join ', ')"
            Write-Host '  the genie learned: radar-new, radar-client, radar-clients, radar-runs'
            Write-Host '  open a new PS7 window, then try:  genie any new bids this morning'
        }
        'log' { if (Test-Path -LiteralPath $global:PhxGenie.Log) { Get-Content -LiteralPath $global:PhxGenie.Log -Tail 20 } }
        default { Invoke-PhxGenie ($words -join ' ') }
    }
}

# Run as a script (how the kernel runs it after pulling it from the pool): genie.ps1 is the compaq up
if ($MyInvocation.InvocationName -ne '.') { genie @args }
