# Incident Response Plan

Shared across all four compliance documents — satisfies NIST 800-171's IR
family, SOC 2's CC7 (System Operations) incident-response expectation, and
ISO 27001:2022's incident management controls under the Organizational
theme.

Scaled to a single-operator business. This plan gets a real test the first
time it's actually invoked for something beyond the scale of what's already
happened (see the worked example below) — until then, treat it as the
written form of a process that's already been followed once in practice.

---

## Roles

- **Incident lead: Jerry Leftwich.** Sole point of accountability for
  detecting, triaging, containing, and resolving any security incident.
- **Escalation:** for anything beyond what Jerry can personally remediate
  (a real compromise requiring forensics, a legal/notification obligation
  beyond what's understood here), escalate to a contracted security
  professional or legal counsel — not yet named, since none has been
  needed. Name one before this plan is ever relied on for something with
  real legal exposure (a federal contract breach, specifically).

## Detection sources

- Cloudflare Access logs (who authenticated, when, from where)
- D1 custody append-only ledger (every intake/version/state change)
- Windows Defender real-time alerts
- Direct observation during development/audit work (this is how Gap 1 was
  actually found — a direct code-inspection pass, not automated alerting)
- Anomalous behavior noticed during normal use (the honeypot/guardian
  system in `sector1/security/`, once it has live feeders beyond auth
  events)

## Severity classification

| Level | Definition | Example |
|---|---|---|
| **Informational** | No real exposure, worth noting | A dependency has a known CVE with no exploitable path here |
| **Low** | Limited, contained exposure | A misconfigured permission on a non-sensitive route |
| **Medium** | Real exposure, no confirmed exploitation | The pre-fix state of Gap 1, if discovered before being exploited |
| **High** | Confirmed exposure or active exploitation | Evidence of unauthorized access actually occurring |
| **Critical** | Federal contract data (FCI/CUI) exposed, or system integrity compromised | Any scenario requiring formal notification under a federal contract |

## Response steps

1. **Contain** — stop the exposure first. For an open-auth-style issue like
   Gap 1, this means gating the route immediately, even before root cause
   is fully understood.
2. **Assess** — determine actual scope: what was exposed, for how long,
   whether real exploitation occurred (not just theoretical exposure).
3. **Remediate** — fix the root cause, not just the symptom. Gap 1's real
   fix required finding *two* layered causes (missing app-layer check +
   a leftover Cloudflare Access bypass policy) — stopping at the first
   cause found would have left the second one live.
4. **Document** — every incident gets a dated entry in CLAUDE.md's SESSION
   LOG and, for anything security-relevant, the `project_security_gap_plan`
   memory (or its successor). This is already the standing practice; this
   plan just names it as the formal incident record.
5. **Notify, if required** — for Medium severity or above involving actual
   federal contract data: FAR clauses generally require notifying the
   contracting officer; CUI incidents under a CMMC-scoped contract carry
   specific DoD reporting timelines (as short as 72 hours from discovery
   for some clauses) — confirm the exact clause-specific timeline against
   the actual contract if this is ever live, don't assume a number here.
6. **Post-incident review** — after remediation, a short retrospective:
   what let this happen, what would catch it faster next time, does this
   plan itself need updating. Gap 1's fix already did this in substance
   (the "not done / worth a look" notes in the security-gap memory) —
   formalize it as a required last step, not an optional afterthought.

## Worked example (real, not hypothetical)

Gap 1 (2026-09-21): every GET route on `packages-worker` had zero
authentication. Detected via direct code inspection (not automated
alerting — a real gap in detection sources, noted above). Contained and
remediated same session: app-layer `isAuthorized()` gate added to all 19
open routes, plus a leftover Cloudflare Access bypass policy from
2026-03-27 removed. Verified end-to-end (unauthenticated GET → 401,
authenticated `intake.sh status` → succeeds). Documented in CLAUDE.md's
SESSION LOG and `project_security_gap_plan` memory with commit references.
No notification was required (pre-contract, no FCI/CUI existed in the
system at the time). This is the template every future incident should
follow, whether or not this exact plan document existed when it happened.

## Next scheduled review

Tied to the Governance Policy's annual cadence, plus immediately upon the
first real incident this plan is invoked for after today.
