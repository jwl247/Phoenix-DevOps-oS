# Ongoing Assessment Log

This file is appended to automatically by the monthly compliance-documentation
review routine (`docs/compliance/shared/risk-assessment-schedule.md`'s
"Monthly automated documentation review"). Entries are never overwritten or
deleted — each run adds one new dated entry below the last. This is a
monitoring log, not a compliance document itself: findings here that look
like they need a real document update are flagged for human review, not
applied automatically.

---

## 2026-10-01

**Annual review status:** Not due. First annual review of the
`docs/compliance/` folder (per `governance-policy.md` /
`risk-assessment-schedule.md`) is scheduled 2027-09-23. No ad hoc trigger
found below that would move that date up.

**Since boundary:** This is the first entry in this log, so the 35-day
default was used: `git log --since="2026-08-27"`. (In practice the repo's
actual commit history in that window only starts 2026-09-27 — 50 commits,
2026-09-27 through 2026-09-30.)

**Findings relevant to compliance posture:**

1. **Discovered-vulnerability trigger, already closed.** Round 2 pentest
   addendum 2 (2026-09-29, `docs/compliance/pentest/2026-09-28-round2-addendum-2.md`)
   found and fixed real issues on the `jerry.leftwich1` road-test account:
   an unauthenticated Cloudflare Access bypass policy reachable on a
   VNC app (A2-01), a Stripe **test** key and a road-test `PHOENIX_AUTH`
   bearer token both printed to a session transcript via a masking bug and
   `curl` argv exposure (A2-02/A2-03, both rotated), and a live,
   unauthenticated `workers.dev` worker plus dormant tunnels with valid
   old connector tokens that nobody had intentionally turned on (A2-04,
   now deleted/disabled). All listed as "Fixed — verified" in the report.
   Eight lower-severity findings remain open (A2-N1 through A2-N8, Medium
   down to Info) — the same list already referenced generically in the
   NIST/SOC2 docs' "Round-2 audit 2026-09-28" citations; no new entries
   beyond what the pentest report itself already tracks.
2. **Pen test program status unchanged.** No new Round 2 security-round
   run found since 2026-09-28 (still FAIL, 0/3 consecutive passes) — matches
   what `NIST-800-171-CMMC-readiness.md`, `SOC2-ISO27001-readiness.md`, and
   `risk-assessment-schedule.md` already state. No update needed to those
   docs on this point.
3. **Possible document-update candidate (not applied — human review
   needed):** `backfill-versions.py` and a `clone x vN` fix (commits
   `faa896b`, `7d98086`, `e2e5a6c`) appear to close the specific gap the
   NIST CM entry and SOC2 CC7 entry both cite by name — "per-version R2
   bytes had never been uploaded... neither is credited until verified
   live." CLAUDE.md's own 2026-09-30 session note says versioning was
   "verified live (411/414 retrievable)." If that verification holds up,
   `NIST-800-171-CMMC-readiness.md`'s CM row and
   `SOC2-ISO27001-readiness.md`'s CC7 row may be ready to move from
   "Partial"/caveated to a stronger status — flagging for Jerry/a real
   review pass rather than editing the scorecards from this routine.
4. **New external surface, scoped outside production (informational).**
   The Compaq road test stood up a second Cloudflare account's worker
   (`dataplane-up.sh`, `workers_dev: true`) and new tunnels/Helix instances
   on `pbm-compaq`, explicitly as a test plane. The road-test writeup and
   addendum 2 both confirm the production account (`packages-worker` etc.
   on `phoenix-jwl`) was verified unchanged at the end of the test. No
   change needed to `FAR-52.204-21-compliance.md`'s Network Segmentation
   inventory, which already scopes to the production account.
5. **Stripe billing (Radar, `pbm-radar-worker`) moved from unconfigured to
   live in test mode** (`fbc847a`, session log "Radar billing proven in
   test mode"). `pbm-radar-worker` was already in the FAR doc's worker
   inventory; going live with real (non-test) Stripe keys is listed as a
   pending NEXT SESSION item in CLAUDE.md ("`STRIPE_SECRET_KEY_LIVE` into
   the vault"), not yet done as of this review.
6. **No matches** for: new federal contract or CUI/PBM contract work, new
   personnel with system access (no hires/subcontractors mentioned in the
   session history), or the Debian VM being promoted past proof-of-concept
   status. No ad hoc review trigger from `governance-policy.md` /
   `risk-assessment-schedule.md` fired on those grounds.

**Net assessment:** No material changes found that require an immediate
annual-review-style update to the FAR/NIST/SOC2/ISO scorecards themselves,
beyond item 3 above (flagged for human review, not applied). The pentest
program's own addendum already captured and is tracking the
discovered-vulnerability-trigger events from this window.
