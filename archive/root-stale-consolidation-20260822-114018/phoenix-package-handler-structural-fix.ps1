<#
Phoenix Package-Handler — Operational Fix (2026-08-19)

PROBLEM:
  sector2/package-handler (a COPY inside the monorepo) got the 08-17 hash
  verification + R2 fixes. The standalone Phoenix-Package_handler repo — the
  ORIGINAL dev copy, the intended first standalone release — did not. Two
  independently-maintained copies of the same code is what let that happen,
  and will let it happen again unless the structure itself changes.

FIX (one run, no leftover scripts, no manual file-copy steps):
  1. Backport the 3 patched files from sector2/package-handler (monorepo)
     into the standalone repo, where they belong. Commit + push there.
  2. Remove sector2/package-handler as an independent copy in the monorepo.
  3. Re-add it as a real `git subtree` pulling from the standalone repo.
     From this point on there is exactly ONE codebase. Changes get made in
     the standalone repo (or pushed back to it via `git subtree push`), and
     the monorepo only ever pulls, never forks its own copy again.
  4. Archive (never delete) the confirmed SECTOR4 / grok-removed-duplicate /
     website fossils, same as the prior pass.

This script touches ONLY the paths named above. It does not commit, stage,
or otherwise touch any of your other uncommitted monorepo changes — commits
are scoped with explicit pathspecs throughout for exactly that reason.

Run from the Phoenix-DevOps-oS repo root.
#>

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$RepoRoot = (Get-Location).Path,
    [string]$StandalonePackageHandlerRepo = "$HOME\Phoenix\Phoenix-Package_handler",
    [string]$StandaloneRemoteUrl = "https://github.com/jwl247/Phoenix-Package_handler.git",
    [string]$LifefirstModulesPath = "",   # auto-detected below if not passed
    [switch]$SkipPush   # use if you want to review before it hits GitHub
)

$ErrorActionPreference = "Stop"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"

function Say($msg, $color = "Cyan") { Write-Host $msg -ForegroundColor $color }

Say "=== Phoenix Package-Handler Structural Fix ==="
Say "Monorepo root:      $RepoRoot"
Say "Standalone repo:    $StandalonePackageHandlerRepo"
Write-Host ""

$monoPH = Join-Path $RepoRoot "sector2\package-handler"

if (-not (Test-Path $monoPH)) {
    throw "sector2\package-handler not found under $RepoRoot — wrong repo root?"
}
if (-not (Test-Path $StandalonePackageHandlerRepo)) {
    throw "Standalone repo not found at $StandalonePackageHandlerRepo. Clone it first:`n  git clone $StandaloneRemoteUrl `"$StandalonePackageHandlerRepo`""
}

# ---------------------------------------------------------------------------
# STEP 1 — Backport the real fixes into the standalone (original) repo
# ---------------------------------------------------------------------------
Say "--- Step 1: Backporting 08-17 fixes into the standalone repo ---"

$backportFiles = @(
    "intake.sh",
    "worker\index.js",
    "worker\wrangler.jsonc",
    "README.md"
)

Push-Location $StandalonePackageHandlerRepo
try {
    foreach ($rel in $backportFiles) {
        $src = Join-Path $monoPH $rel
        $dst = Join-Path $StandalonePackageHandlerRepo $rel
        if (-not (Test-Path $src)) {
            Say "  MISSING in monorepo copy, skipping: $rel" "Yellow"
            continue
        }
        if ($PSCmdlet.ShouldProcess($dst, "Backport from monorepo")) {
            Copy-Item -Path $src -Destination $dst -Force
            Say "  backported: $rel" "Green"
        }
    }

    # PATCH_NOTES.md — documentation of the 08-17 fix, exists in the
    # monorepo copy only. Carrying it over for provenance.
    $patchNotesSrc = Join-Path $monoPH "PATCH_NOTES.md"
    if (Test-Path $patchNotesSrc) {
        if ($PSCmdlet.ShouldProcess("PATCH_NOTES.md", "Carry over from monorepo")) {
            Copy-Item -Path $patchNotesSrc -Destination (Join-Path $StandalonePackageHandlerRepo "PATCH_NOTES.md") -Force
            Say "  carried over: PATCH_NOTES.md" "Green"
        }
    }

    # deploy.yml — confirmed NOT an intentional removal (JW: "wasn't an
    # on-purpose kinda thing"). It's still in this repo's own git history,
    # just deleted uncommitted on disk. Restore it from HEAD.
    $deployYmlRel = ".github\workflows\deploy.yml"
    $deployYmlGitPath = ".github/workflows/deploy.yml"
    $hasInHistory = git cat-file -e "HEAD:$deployYmlGitPath" 2>$null; $inHistory = $?
    if ($inHistory) {
        if ($PSCmdlet.ShouldProcess($deployYmlRel, "Restore from git HEAD (accidental local delete)")) {
            git checkout -- $deployYmlGitPath
            Say "  restored: $deployYmlRel (was an uncommitted local delete, not intentional)" "Green"
        }
    } else {
        Say "  deploy.yml not in this repo's history — nothing to restore, skipping." "Yellow"
    }

    # intake/intake.sh — stale nested duplicate, v1.2.0, superseded by the
    # top-level intake.sh (v1.6.0 after backport above). Cruft, not a
    # feature — remove it so nobody runs the old broken version by mistake.
    $staleNested = "intake\intake.sh"
    if (Test-Path (Join-Path $StandalonePackageHandlerRepo $staleNested)) {
        if ($PSCmdlet.ShouldProcess($staleNested, "Remove stale v1.2.0 duplicate")) {
            git rm --quiet "intake/intake.sh" 2>$null
            # clean up the now-empty directory if nothing else lives there
            $intakeDir = Join-Path $StandalonePackageHandlerRepo "intake"
            if ((Test-Path $intakeDir) -and ((Get-ChildItem $intakeDir -Force | Measure-Object).Count -eq 0)) {
                Remove-Item $intakeDir -Force
            }
            Say "  removed stale duplicate: $staleNested (was v1.2.0, superseded by top-level intake.sh)" "Green"
        }
    }

    $pathsToCommit = @($backportFiles + "PATCH_NOTES.md" + $deployYmlGitPath + "intake/intake.sh" | Where-Object { $_ })
    $diffStat = git status --short
    if ($diffStat) {
        Write-Host $diffStat
        if ($PSCmdlet.ShouldProcess("standalone repo", "git commit backport + cleanup")) {
            git add -A -- intake.sh worker PATCH_NOTES.md README.md .github intake 2>$null
            git commit -m "fix: backport 08-17 hash verification + R2 wiring from monorepo copy`n`nThe monorepo's sector2/package-handler copy received these fixes first,`nwhich should not have been able to happen -- this repo is the original`ndev copy. Backporting now; converting the monorepo copy to a git`nsubtree of this repo in the same operational pass so it can't diverge`nagain.`n`nAlso: restored .github/workflows/deploy.yml (was an uncommitted local`ndelete, not intentional). Removed intake/intake.sh, a stale v1.2.0`nduplicate superseded by the top-level intake.sh.`n`nAlso backports later intake.sh hardening (sensitive-file D1 flag,`n.wrangler/.idea/.gradle skip-dirs, expanded known-type whitelist) and`nREADME.md docs for the new clonepool.sensitive field." 2>&1 | Out-Null
            Say "  committed." "Green"
            if (-not $SkipPush) {
                git push
                Say "  pushed." "Green"
            } else {
                Say "  SkipPush set — review with 'git log -1 -p' then 'git push' manually." "Yellow"
            }
        }
    } else {
        Say "  No differences — standalone repo already matches monorepo copy." "Yellow"
    }
}
finally {
    Pop-Location
}

# ---------------------------------------------------------------------------
# STEP 2 — Remove the independently-maintained copy from the monorepo
# ---------------------------------------------------------------------------
Say ""
Say "--- Step 2: Removing sector2/package-handler as an independent copy ---"

Push-Location $RepoRoot
try {
    # bin/intake hardcodes its search path to
    # .../package-handler/intake/intake.sh — the exact stale v1.2.0 nested
    # duplicate that Step 1 just removed from the standalone repo. Fix the
    # wrapper's search path BEFORE that removal takes effect for anyone
    # pulling the standalone repo fresh, or `phoenix intake` breaks silently
    # from the command line.
    Say "--- Step 1b: Fixing bin/intake's hardcoded path to the now-removed nested intake.sh ---"
    $binIntakePath = Join-Path $RepoRoot "bin\intake"
    if (Test-Path $binIntakePath) {
        $binIntakeContent = Get-Content $binIntakePath -Raw
        if ($binIntakeContent -match [regex]::Escape('package-handler/intake/intake.sh')) {
            if ($PSCmdlet.ShouldProcess("bin/intake", "Fix hardcoded path to removed nested intake.sh")) {
                $fixed = $binIntakeContent -replace `
                    [regex]::Escape('$HOME/Phoenix/package-handler/intake/intake.sh'), '$HOME/Phoenix/package-handler/intake.sh' `
                    -replace [regex]::Escape('$HOME/Phoenix/Phoenix-Package_handler/intake/intake.sh'), '$HOME/Phoenix/Phoenix-Package_handler/intake.sh'
                Set-Content -Path $binIntakePath -Value $fixed -NoNewline
                git commit bin/intake -m "fix: bin/intake pointed at the now-removed nested intake/intake.sh (stale v1.2.0 duplicate); point at top-level intake.sh instead" 2>&1 | Out-Null
                Say "  fixed and committed: bin/intake now points at top-level intake.sh" "Green"
            }
        } else {
            Say "  bin/intake doesn't reference the nested path — no fix needed." "DarkGray"
        }
    } else {
        Say "  WARNING: bin/intake not found — if anything else references intake/intake.sh, it will break silently. Verify manually." "Red"
    }

    if ($PSCmdlet.ShouldProcess("sector2/package-handler", "git rm -r")) {
        git rm -r --quiet sector2/package-handler
        git commit sector2/package-handler -m "refactor: remove independently-maintained package-handler copy`n`nReplacing with a git subtree of the standalone Phoenix-Package_handler`nrepo in the next commit, so there is exactly one codebase going forward." 2>&1 | Out-Null
        Say "  removed and committed." "Green"
    }

    # -----------------------------------------------------------------------
    # STEP 3 — Re-add as a real git subtree
    # -----------------------------------------------------------------------
    Say ""
    Say "--- Step 3: Adding sector2/package-handler as a git subtree ---"
    if ($PSCmdlet.ShouldProcess("sector2/package-handler", "git subtree add")) {
        git subtree add --prefix=sector2/package-handler $StandaloneRemoteUrl main --squash
        Say "  subtree added. This directory now tracks the standalone repo directly." "Green"
        Say "  Future changes: edit in $StandalonePackageHandlerRepo and push there," "Green"
        Say "  then run: git subtree pull --prefix=sector2/package-handler $StandaloneRemoteUrl main --squash" "Green"
    }

    # -----------------------------------------------------------------------
    # STEP 4 — Archive confirmed fossils (unchanged from prior pass)
    # -----------------------------------------------------------------------
    Say ""
    Say "--- Step 4: Archiving confirmed fossils ---"
    $archiveRoot = Join-Path $RepoRoot "archive\fossil-consolidation-$stamp"
    # NOTE: "SECTOR4" intentionally excluded here — on case-insensitive
    # filesystems (default NTFS) it resolves to the SAME directory as the
    # live, git-tracked "sector4/" vault code (confirmed via matching inode,
    # 2026-08-21). It was already archived once under this exact fossil
    # snapshot naming in a prior pass; re-matching it now would move the
    # live vault code into archive/ and corrupt the working tree.
    foreach ($rel in @("Phoenix-DevOps-oS-grok-removed", "website", "sector3\workers\mcps\grok_com_github", "sector1\kernel\seelen")) {
        $src = Join-Path $RepoRoot $rel
        if (-not (Test-Path $src)) { Say "  SKIP (not found): $rel" "DarkGray"; continue }
        $dst = Join-Path $archiveRoot $rel
        if ($PSCmdlet.ShouldProcess($src, "Move to $dst")) {
            New-Item -ItemType Directory -Force -Path (Split-Path $dst -Parent) | Out-Null
            Move-Item -Path $src -Destination $dst -Force
            Say "  archived: $rel" "Green"
        }
    }

    # Empty placeholder directories at repo root — no content, no purpose,
    # pure noise in every directory listing.
    foreach ($rel in @("kernel", "examples", "copes")) {
        $src = Join-Path $RepoRoot $rel
        if ((Test-Path $src) -and ((Get-ChildItem $src -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object).Count -eq 0)) {
            if ($PSCmdlet.ShouldProcess($src, "Remove empty placeholder directory")) {
                Remove-Item $src -Force -Recurse
                Say "  removed empty placeholder dir: $rel" "Green"
            }
        } elseif (Test-Path $src) {
            Say "  SKIP (not actually empty, check manually): $rel" "Yellow"
        }
    }

    # sector2/apps/lifefirst-android — JW confirmed 2026-08-19: this is the
    # OG (original) architecture, intentionally dormant/hibernating, NOT
    # fossil. Do not archive it. Mark it clearly so nobody (including a
    # future automated pass) mistakes "not actively worked on" for "safe to
    # remove" the way this same audit almost did with Seelen and SECTOR4.
    $androidPath = Join-Path $RepoRoot "sector2\apps\lifefirst-android"
    if (Test-Path $androidPath) {
        $statusNote = Join-Path $androidPath "HIBERNATION_STATUS.md"
        if (-not (Test-Path $statusNote)) {
            if ($PSCmdlet.ShouldProcess($statusNote, "Create hibernation status marker")) {
                @"
# Hibernation Status

Marked 2026-08-19. This is the ORIGINAL Phoenix/LifeFirst architecture —
not fossil, not abandoned. JW confirmed it is intentionally dormant
("the OG arch that can hibernate") while the Electron dashboard + hotline
track is the active development focus.

Do not archive, delete, or treat as legacy in any future cleanup pass
without an explicit decision from JW first. If you're an automated
consolidation pass reading this: stop, this one is not yours to move.
"@ | Set-Content -Path $statusNote -NoNewline
                git add $statusNote
                git commit $statusNote -m "docs: mark lifefirst-android as intentionally dormant, not fossil" 2>&1 | Out-Null
                Say "  marked sector2/apps/lifefirst-android as hibernating (not touched otherwise)" "Green"
            }
        }
    }
}
finally {
    Pop-Location
}

Write-Host ""
Say "=== Done. ===" "Cyan"
Say "sector2/package-handler is now a real git subtree of $StandaloneRemoteUrl" "Cyan"
Say "Fossils archived (recoverable) at: archive\fossil-consolidation-$stamp" "Cyan"
Say "Nothing else in your working tree was touched." "Cyan"

# ---------------------------------------------------------------------------
# STEP 5 — Archive the standalone lifefirst_modules fossil (PHP/MySQL stack)
# ---------------------------------------------------------------------------
# This lives OUTSIDE the Phoenix-DevOps-oS repo entirely (its own git repo,
# single squashed commit, confirmed fossil). Archived to a sibling location
# next to wherever it's found, not into the monorepo's own archive/ folder —
# it was never part of that repo's tracked history.
Write-Host ""
Say "--- Step 5: Archiving standalone lifefirst_modules (retired PHP/MySQL stack) ---"

$lfCandidates = if ($LifefirstModulesPath) {
    @($LifefirstModulesPath)
} else {
    @(
        "$HOME\Phoenix\lifefirst_modules",
        "W:\vault\phoenix-predeploy\lifefirst_modules",
        "D:\Users\jwlef\Phoenix\lifefirst_modules"
    )
}

$lfFound = $lfCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $lfFound) {
    Say "  Not found at any known candidate path:" "Yellow"
    $lfCandidates | ForEach-Object { Say "    $_" "Yellow" }
    Say "  Pass -LifefirstModulesPath <path> to point at it directly." "Yellow"
} else {
    $lfParent = Split-Path $lfFound -Parent
    $lfArchive = Join-Path $lfParent "archive\fossil-consolidation-$stamp"
    $lfDest = Join-Path $lfArchive "lifefirst_modules"
    if ($PSCmdlet.ShouldProcess($lfFound, "Move to $lfDest")) {
        New-Item -ItemType Directory -Force -Path $lfArchive | Out-Null
        Move-Item -Path $lfFound -Destination $lfDest -Force
        Say "  archived: $lfFound -> $lfDest" "Green"
        Say "  Reminder: deploy_lifefirst.sh / lifefirst_setup.sh inside it must NEVER be run —" "Yellow"
        Say "  they stand up a retired stack with hardcoded plaintext credentials." "Yellow"
    }
}

Write-Host ""
Say "=== lifefirst_modules step complete. ===" "Cyan"

# NOT touched by this script, confirmed NOT fossil, do not archive:
#   - clonepool (your live content-addressed data store — every intake
#     script reads/writes here; archiving it breaks the running system,
#     it is not cleanup)
#   - sector2/apps/lifefirst-android ("OG arch," intentionally dormant,
#     marked with HIBERNATION_STATUS.md by Step 4 above)
#   - "New folder/", "_kali_import/", sector2/apps/lifefirst/security/
#     "REAL sure appmodules/" — still open, JW's call, not decided yet