# NIST SP 800-171 / CMMC Level 2 Readiness

**This tier only applies if PBM Consulting Service ever handles Controlled
Unclassified Information (CUI)**, not merely Federal Contract Information
(FCI). FCI alone stays at the FAR 52.204-21 baseline —
see [FAR-52.204-21-compliance.md](./FAR-52.204-21-compliance.md). This
document is informational/roadmap, not a build list — per Jerry (2026-09-23),
shown now so the shape of the work is known before it's a deadline, not
committed to being built before there's a real reason.

CMMC Level 2 assessments in 2026 are still conducted against **NIST 800-171
Revision 2** (110 controls, 14 families) — the DoD locked assessments to
Rev 2 via a class deviation even though NIST published Rev 3 (97 controls,
3 new families) in May 2024. This scorecard uses Rev 2's 14 families, since
that's what an actual assessment would use right now.

Source: [scrut.io CMMC controls hub](https://www.scrut.io/hub/cmmc/controls), fetched 2026-09-23.

---

## Family-level scorecard

| Family | Covers | Status |
|---|---|---|
| **AC** — Access Control | User/system access permissions | **Strong** — same evidence as FAR controls #1/#2/#6 (Cloudflare Access, `isAuthorized()`, `Ball` least-privilege permissions). Full 110-control granularity (session termination policy, remote-access monitoring, wireless restrictions) not individually verified. |
| **AT** — Awareness and Training | Personnel trained on security responsibilities | **Documented 2026-09-23** — [shared/security-training-record.md](./shared/security-training-record.md), seeded with 4 real entries from this same compliance pass, not placeholder boilerplate. Still needs a live annual review cycle to prove it's a practice, not a one-time document. |
| **AU** — Audit and Accountability | System logs, traceable to specific users | **Strong** — D1 append-only custody ledger, Cloudflare Access logs, git-committed remediation history. Genuinely above typical small-business baseline. |
| **CM** — Configuration Management | Documented baseline configs, change control | **Partial, strengthened.** The intake/versioning system tracks every file change with more rigor than most (content-hash, tier rotation, full history). [shared/governance-policy.md](./shared/governance-policy.md) now covers the policy-ownership side; a formal change-approval *process* (distinct from good tracking) is still just one person approving their own changes. |
| **IA** — Identification and Authentication | Verify identity before granting access | **Strong** — same evidence as FAR #5/#6 (hex identity, hardware fingerprint, Cloudflare Access). |
| **IR** — Incident Response | Detect, analyze, contain, recover from incidents | **Documented 2026-09-23** — [shared/incident-response-plan.md](./shared/incident-response-plan.md), with a real worked example (Gap 1's actual fix) rather than a hypothetical. Notification-timeline specifics still need to be confirmed against an actual contract's clauses if this is ever invoked for real. |
| **MA** — Maintenance | Authorized repair/upgrade while protecting CUI | **Partial.** `driver-updater.ps1`, Windows Update discipline, the intake pipeline's own maintenance are solid in practice; no written maintenance policy. |
| **MP** — Media Protection | Handling, storage, transport, disposal of CUI media | **Partial.** The Media Sanitization Procedure (FAR #7, above) covers disposal. CUI-specific marking (labeling which media contains CUI, controlling it in transport) isn't built — a real, CUI-specific gap beyond what FCI required. |
| **PS** — Personnel Security | Trustworthy personnel, enforced on hire/transfer/termination | **Partial, corrected 2026-09-23.** Previously marked "can't build until non-owner personnel exist" — wrong assumption. [shared/personnel-competency-report.md](./shared/personnel-competency-report.md) documents the owners' own field competency (Jerry's construction background, Laurie's training role), which is real personnel-security substance today. Screening/onboarding/offboarding *process* still genuinely waits on the first non-owner hire. |
| **PE** — Physical Protection | Physical environment security | **Meets** — reuses the [Physical Access Policy](./FAR-52.204-21-compliance.md#physical-access-policy) written for FAR #8/#9 directly; same facts apply. |
| **RA** — Risk Assessment | Periodic, documented risk identification | **Documented 2026-09-23** — [shared/risk-assessment-schedule.md](./shared/risk-assessment-schedule.md) wraps a real cadence around the substance that already existed (`project_security_gap_plan`). First scheduled review: 2027-09-23. |
| **CA** — Security Assessment | Verify controls are implemented and working as intended | **Not yet done.** This is exactly what the planned pen test (Jerry's own stated next checkpoint, see security-gap memory) would satisfy — hasn't run yet. The risk-assessment schedule above now explicitly counts that pen test as satisfying this the day it runs. |
| **SC** — System and Communications Protection | Boundary/communications monitoring and control | **Strong** — same evidence as FAR #10/#11 (Cloudflare Access boundary, `translator.sh` OUTPUT ONLY, Network Segmentation doc). |
| **SI** — System and Information Integrity | Flaw identification/correction, malicious content protection | **Strong** — same evidence as FAR #12–15 (content-hash integrity verification, Windows Defender verified live, dated remediation trail). |

---

## Honest summary

**Already well-positioned (5 of 14):** AC, AU, IA, SC, SI — these lean on
architecture Phoenix already has for reasons unrelated to compliance
(the custody chain, the boundary rules, the identity system), which happens
to line up well with what NIST 800-171 asks for.

**Documented 2026-09-23 (3 of 14):** AT, IR, RA — the shared docs in
`docs/compliance/shared/` closed these. Written, not yet proven by a live
review cycle — that's the honest distinction between "documented" and
"strong."

**Solid in practice, not fully formalized (3 of 14):** CM, MA, MP — real
technical/procedural substance exists; CM now has a governance-policy
anchor, MA and MP still need dedicated write-ups if this ever matters for
real.

**Real, unbuilt gap (1 of 14):** CA — the pen test, planned but not run.
PS moved from "unbuilt gap" to "Partial" once the owners' own competency
documentation was recognized as real substance, not a placeholder.

**Bottom line:** the paperwork layer (AT/IR/RA/PS) that used to be the
biggest gap is now closed or substantially addressed. What's left — MA/MP
formalization and CA (the pen test) — is a small remaining lift, not a
structural gap. Revisit CUI-specific work only once it's actually on the
table for a specific contract, same "real findings over speculation"
posture as the pen test.
