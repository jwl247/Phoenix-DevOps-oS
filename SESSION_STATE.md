# Phoenix Session State
# Updated: 2026-08-22
# READ THIS AT THE START OF NEXT SESSION

## WHERE WE ARE

Dashboard is real end to end. Clonepool integrity system is real end to end.
Whole repo intaked fresh tonight. This file was badly stale (last touched
2026-08-11, QEMU/PoC era) — everything below it in that old version was
already done and superseded; see CLAUDE.md's SESSION LOG for the full
narrative of every session since, this file only tracks current state.

- Dashboard Electron app — real D1/R2 data, PS7 shell, clonepool browser,
  screenshot analysis, live monitor, dedicated Claude "subscription" mode ✅
- R2 actually receiving bytes (was documented as canonical since June,
  never bound until 2026-08-22) ✅
- Content-hash integrity system (SHA3-512 + BLAKE2b baseline, checked at
  `intake clone` time, gates clone-to-workdir on mismatch) ✅
- QR generation (header/footer) live in the active bash intake.sh pipeline ✅
- PHOENIX_AUTH rotated and working — plain Windows user env var, matching
  Cloudflare secret, nothing hardcoded anywhere ✅
- Whole repo intaked as of tonight — 376 files, 93 new, 283 already-current ✅

## WHAT WAS BUILT THIS SESSION (2026-08-22)

See CLAUDE.md SESSION LOG (2026-08-22 entry) for the full narrative —
dashboard fixes, R2 wiring, QR restoration, PHOENIX_AUTH rotation, and the
integrity-verification system are all documented there in detail so it
isn't duplicated here.

## KNOWN LOOSE ENDS (not urgent, not forgotten)

- `dashboardDEP/` and other `*DEP`-suffixed dirs share filenames with live
  counterparts — intake.sh's hex_id is filename-only, so both land under
  the same hex bucket as separate versions rather than colliding
  destructively, but it's confusing. Consider excluding `*DEP` dirs from
  intake or renaming them off the collision path.
- Tonight's whole-repo intake was run as `intake .`, so its directory-level
  summary entry got hex `2e` / name `.` instead of `Phoenix-DevOps-oS`.
  Cosmetic only — every individual file underneath is correctly named.
- The integrity-verification gate only covers `intake clone` (both
  single-file and directory-snapshot forms) so far. `intake_file`'s own
  duplicate-detection path and true hot-swap don't check hashes yet.
- HUD visual translucency — scoped to visual-only, not yet implemented.
- 3 redundant PS7 buttons in the dashboard UI — not yet consolidated.

## NEXT STEPS IN ORDER

1. docs/ reconciliation — QUICK_START.md vs GETTING_STARTED.md vs root
   README.md look like they may overlap, not yet audited
2. MapTiler map panel in dashboard (Jerry paying, integrate as desktop panel)
3. Glossary dashboard UI panel (backend/API already confirmed working —
   see docs/GLOSSARY.md)
4. Shade UI + drawer filesystem (desktop transformation — real shell is
   now in place as a foundation piece)
5. Deploy phoenix-dashboard.service on Ubuntu 192.168.1.133
6. Start manual/phoenix_manual.md

## KEY FILES

| File | Purpose |
|------|---------|
| `CLAUDE.md` (repo root) | Full architecture reference + session log — read this first |
| `sector2/package-handler/intake.sh` | Intake pipeline — hex identity, hashing, QR, R2, D1, integrity gate |
| `sector2/package-handler/README.md` | Command reference + integrity verification docs |
| `sector3/workers/packages-worker/index.js` | Cloudflare Worker — D1 + R2 API |
| `scripts/usys.ps1` | Global command layer (PowerShell) |
| `dashboard/main.js` | Electron main process — D1/R2/Claude/Ollama wiring |

## WHY THIS EXISTS
Life First app for Laurie. Local LLM, no vendor, no subscription, no lock-in.
Phoenix is the infrastructure. Every process, every import, every run is in service of that.
People with less money deserve to run the same tools as everyone else.
Every penny every time.
