# genie.Tests.ps1 — the genie's decisions, with a stand-in for the local model.
#   pwsh -NoProfile -File scripts/genie.Tests.ps1
# Standalone (no Pester), same style as phx-kernel.Tests.ps1. No network, no Ollama:
# the one model seam ($global:PhxGenieModelCall) is replaced. Nothing outside a temp folder.

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'genie.ps1')
$ErrorActionPreference = 'Continue'
$WarningPreference = 'SilentlyContinue'

$root = Join-Path ([IO.Path]::GetTempPath()) ("genie_" + [guid]::NewGuid().ToString('N').Substring(0, 8))
$global:PhxGenie.Home = $root
$global:PhxGenie.Library = Join-Path $root 'library.json'
$global:PhxGenie.Log = Join-Path $root 'log.jsonl'

$p = 0; $f = 0
function ok($cond, $msg) { if ($cond) { $script:p++; Write-Host "  ok   $msg" } else { $script:f++; Write-Host "  FAIL $msg" -ForegroundColor Red } }

# A harmless tool to run: records exactly the arguments it was given.
$global:ran = [System.Collections.Generic.List[object]]::new()
function global:phx-test-echo { $global:ran.Add(@($args)) ; "echo: $($args -join '|')" }

# The stand-in model: answers whatever the test sets, records what it was sent.
$global:reply = $null; $global:sent = $null; $global:modelDown = $false
$global:PhxGenieModelCall = { param($Body) $global:sent = $Body; if ($global:modelDown) { throw 'connection refused' }; return ($global:reply | ConvertTo-Json -Compress -Depth 5) }
$global:answer = 'y'; $global:asked = 0
function global:Read-Host { param($Prompt) $global:asked++; return $global:answer }
function Reset { $global:ran.Clear(); $global:asked = 0; $global:modelDown = $false; $global:answer = 'y' }

genie learn say-hi "say hello to someone by name" phx-test-echo hello '{who}' | Out-Null
genie learn wipe-cache "clear the download cache" phx-test-echo wipe -Ask | Out-Null

# ── 1. the model's answer is fenced in ─────────────────────────────────────
Reset; $global:reply = @{ say = 'Saying hi.'; tool = 'say-hi'; args = @{ who = 'Laurie' } }
genie say hi to laurie | Out-Null
$enum = $global:sent.format.properties.tool.enum
ok ($enum -contains 'say-hi' -and $enum -contains 'none' -and $enum -contains 'kernel-status') 'the model may only answer with a library tool or none'
ok ($global:sent.options.temperature -eq 0 -and $global:sent.model -eq 'llama3.2:3b') 'temperature 0, local llama3.2:3b by default'
ok ($global:ran.Count -eq 1 -and ($global:ran[0] -join '|') -eq 'hello|Laurie' -and $global:asked -eq 0) 'auto tool ran with the filled-in argument, no question'

Reset; $global:reply = @{ say = 'Deleting everything.'; tool = 'rm-rf'; args = @{} }
genie delete everything | Out-Null
ok ($global:ran.Count -eq 0) 'a tool the model made up is never run'

# ── 2. ask tier waits for a yes ────────────────────────────────────────────
Reset; $global:reply = @{ say = 'Clearing the cache.'; tool = 'wipe-cache'; args = @{} }; $global:answer = 'n'
genie clear the cache | Out-Null
ok ($global:asked -eq 1 -and $global:ran.Count -eq 0) 'ask tool + "n": asked, nothing ran'
Reset; $global:reply = @{ say = 'Clearing the cache.'; tool = 'wipe-cache'; args = @{} }
genie clear the cache | Out-Null
ok ($global:asked -eq 1 -and $global:ran.Count -eq 1) 'ask tool + "y": ran once'

# ── 3. missing detail, injection ───────────────────────────────────────────
Reset; $global:reply = @{ say = 'Saying hi.'; tool = 'say-hi'; args = @{} }
genie say hi | Out-Null
ok ($global:ran.Count -eq 0) 'a tool whose {hole} the person never filled does not run'
Reset; $global:reply = @{ say = 'Saying hi.'; tool = 'say-hi'; args = @{ who = 'x; Remove-Item C:\ -Recurse' } }
genie say hi | Out-Null
ok ($global:ran.Count -eq 1 -and $global:ran[0].Count -eq 2 -and $global:ran[0][1] -eq 'x; Remove-Item C:\ -Recurse') 'an argument stays one literal argument (no command injection)'

# ── 4. no model running ────────────────────────────────────────────────────
Reset; $global:modelDown = $true
genie please clear the download cache | Out-Null
ok ($global:asked -eq 1 -and $global:ran.Count -eq 1) 'no model: matched words to wipe-cache and asked first'
Reset; $global:modelDown = $true; $global:answer = 'y'
genie kernel | Out-Null
ok ($global:ran.Count -eq 0 -and $global:asked -eq 0) 'no model + a word that fits several tools: does nothing, says so'
Reset; $global:modelDown = $true
genie learn read-note "read the note on the desktop" phx-test-echo note | Out-Null
genie read the note | Out-Null
ok ($global:asked -eq 0 -and @($global:ran | Where-Object { $_[0] -eq 'note' }).Count -eq 1) 'no model + a clear match on a read-only tool: it just runs, no question'

# ── 5. building the library ────────────────────────────────────────────────
$lib = Get-PhxGenieLibrary
ok ($lib.Contains('say-hi') -and $lib['wipe-cache'].tier -eq 'ask' -and $lib['say-hi'].tier -eq 'auto') 'learned tools persist with their tier'
ok (($lib['say-hi'].argv -join ' ') -eq 'hello {who}') 'learned tool keeps its {hole}'
genie forget say-hi | Out-Null
ok (-not (Get-PhxGenieLibrary).Contains('say-hi') -and (Get-PhxGenieLibrary).Contains('kernel-status')) 'forget removes a learned tool; built-ins stay'
$listing = (genie library) -join "`n"
ok ($listing -match 'kernel-status' -and $listing -match 'wipe-cache') 'genie library lists built-in and learned tools'

# ── 6. the log answers "what did you just do" ──────────────────────────────
$log = @(Get-Content -LiteralPath $global:PhxGenie.Log | ForEach-Object { $_ | ConvertFrom-Json })
ok (@($log | Where-Object outcome -eq 'ran').Count -ge 4 -and @($log | Where-Object outcome -eq 'declined').Count -ge 1) 'every ask is logged: what was asked, which tool, what happened'
ok (@($log | Where-Object { $_.run -eq 'phx-test-echo hello x; Remove-Item C:\ -Recurse' }).Count -eq 1) 'the log shows the exact command that ran'

Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "`n$p passing, $f failing"
exit ([int]($f -gt 0))
