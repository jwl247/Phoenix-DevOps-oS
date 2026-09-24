# Risk Assessment Schedule

Shared across all four compliance documents — satisfies NIST 800-171's RA
family, SOC 2's CC3 (Risk Assessment), and ISO 27001:2022's risk-assessment
expectations under the Organizational theme.

The substance of risk assessment has already been happening in practice —
`project_security_gap_plan` memory is, functionally, a real risk register:
findings, severity reasoning, and deliberate accept/fix decisions (Gap 2's
closure is a textbook documented risk-acceptance decision). What was
missing wasn't the practice, it was a schedule wrapped around it and a
named place it's supposed to live. This document is that wrapper.

---

## Methodology

1. **Identify assets** — the clonepool/custody D1 tables already function
   as a real, granular asset inventory (every intaked file, hashed,
   versioned, tiered). Use this as the starting point rather than building
   a separate asset list from scratch.
2. **Identify threats** — architecture review (the security-gap-plan
   process already does this), dependency/CVE awareness, and the planned
   pen test once it runs.
3. **Assess likelihood and impact** — using the severity classification in
   `incident-response-plan.md` as the shared scale, so a "Medium" finding
   here means the same thing it means during an actual incident.
4. **Decide: fix, accept, or defer** — and document *why*, not just the
   decision. Gap 2's closure (2026-09-21) is the model: cipher and scope
   were picked, then the decision reversed with a stated reason (Gap 1
   already closed the real exposure; the fingerprint-key design had an
   undisclosed data-loss risk). That level of stated reasoning is the bar
   for every entry here, not just "accepted."
5. **Track remediation** — dated, committed, verifiable (the standing
   practice already followed for Gap 1).

## Cadence

- **Annual formal review**, aligned with the Governance Policy's review
  cycle.
- **Immediate ad hoc review triggers**: a new contract type (especially
  one that could introduce CUI), new personnel with system access, a
  major architecture change, or a newly discovered vulnerability —
  same trigger list as the Governance Policy, since these are genuinely
  the same events viewed from a risk lens.
- **The planned pen test** (Jerry's own stated next security checkpoint,
  per `project_security_gap_plan`) counts as a full ad hoc risk assessment
  when it runs — not a separate, additional obligation.
- **Monthly automated documentation review** (real, running, not aspirational
  — built 2026-09-23): a cloud routine
  ([trig_01TSaySpWwFCZM8i31pwZqxU](https://claude.ai/code/routines/trig_01TSaySpWwFCZM8i31pwZqxU),
  fires monthly on the 1st) reads every file under `docs/compliance/`,
  checks whether the annual review is due, scans git history since its
  last run for anything matching the ad hoc triggers above, and appends a
  dated finding to `docs/compliance/shared/ongoing-assessment-log.md` —
  committed directly, never overwritten. This does not replace the annual
  review or a real pen test; it closes the specific gap this document used
  to have, that nothing automated ever actually ran the "remember to check
  monthly" habit a human was previously relied on for.
- **Weekly local technical check** (also real, running): the cloud routine
  above has zero access to this machine, so it can never re-verify the
  live claims in `FAR-52.204-21-compliance.md` controls #13-15 (Windows
  Defender status). `scripts/compliance-local-check.ps1`, scheduled via
  Windows Task Scheduler (`Phoenix-ComplianceCheck`, Mondays 9:00 AM),
  re-runs `Get-MpComputerStatus` and flags drift with a visible alert —
  logs every run (pass or fail) to `~/.unitedsys/logs/compliance-check.jsonl`
  locally (not committed — machine telemetry, not project history).

## Current risk register

Pointer, not a duplicate: the live register is
`project_security_gap_plan` memory plus CLAUDE.md's SESSION LOG. As of
2026-09-23:

| Item | Status | Decision record |
|---|---|---|
| Gap 1 — open GET auth on packages-worker | Fixed, 2026-09-21 | `project_security_gap_plan` |
| Gap 2 — content encryption at rest | Closed by deliberate risk acceptance, 2026-09-21 | `project_security_gap_plan` |
| Standing integrity job (T3 #10) | Open, deferred | CLAUDE.md NEXT SESSION |
| Real pen test | Planned, not yet run | `project_security_gap_plan` |
| Filename-collision bug (`hex_id = to_hex(basename)`) | Known, deferred | CLAUDE.md NEXT SESSION |

## Next scheduled review

Annual, tied to the Governance Policy — first review due 2027-09-23 unless
an ad hoc trigger fires sooner.
