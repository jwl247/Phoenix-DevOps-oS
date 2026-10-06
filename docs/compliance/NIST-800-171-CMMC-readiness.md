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
| **AU** — Audit and Accountability | System logs, traceable to specific users | **Strong** — D1 append-only custody ledger, Cloudflare Access logs, dated remediation history in `docs/history/SESSION-LOG.md` + git history (rewritten 2026-09-25 by `git filter-repo`; commit hashes cited before that date no longer resolve, so the dated entries are the record). Genuinely above typical small-business baseline. |
| **CM** — Configuration Management | Documented baseline configs, change control | **Partial (corrected 2026-09-29).** The intake/versioning system records every file change with a content hash at intake and a D1 `versions` ledger. **Round-2 audit 2026-09-28 (XCUT-F15/F16):** per-version bytes had never been uploaded to R2 as of that audit (history is a D1 ledger only; R2 holds latest), and T1→T4 tier rotation is wired but manual-only, never scheduled — neither is credited for 3.4.1/3.4.3 baselines or 3.8.9 backup until verified live. [shared/governance-policy.md](./shared/governance-policy.md) now covers the policy-ownership side; a formal change-approval *process* (distinct from good tracking) is still just one person approving their own changes. **2026-10-01 drift correction:** `HX_ZLEVEL` in `sector1/helix/helix_complete_stack.py` had drifted from the authoritative kernel constant (`dm_helix.c`: level=5) to level=6 — a config baseline deviation. Corrected same session. This is a concrete example of 3.4.1 baseline drift detection and timely correction. |
| **IA** — Identification and Authentication | Verify identity before granting access | **Strong** — same evidence as FAR #5/#6 (hex identity, hardware fingerprint, Cloudflare Access). |
| **IR** — Incident Response | Detect, analyze, contain, recover from incidents | **Documented 2026-09-23** — [shared/incident-response-plan.md](./shared/incident-response-plan.md), with a real worked example (Gap 1's actual fix) rather than a hypothetical. Notification-timeline specifics still need to be confirmed against an actual contract's clauses if this is ever invoked for real. |
| **MA** — Maintenance | Authorized repair/upgrade while protecting CUI | **Partial.** `driver-updater.ps1`, Windows Update discipline, the intake pipeline's own maintenance are solid in practice; no written maintenance policy. |
| **MP** — Media Protection | Handling, storage, transport, disposal of CUI media | **Partial.** The Media Sanitization Procedure (FAR #7, above) covers disposal. CUI-specific marking (labeling which media contains CUI, controlling it in transport) isn't built — a real, CUI-specific gap beyond what FCI required. |
| **PS** — Personnel Security | Trustworthy personnel, enforced on hire/transfer/termination | **Partial, corrected 2026-09-23.** Previously marked "can't build until non-owner personnel exist" — wrong assumption. [shared/personnel-competency-report.md](./shared/personnel-competency-report.md) documents the owners' own field competency (Jerry's construction background, Laurie's training role), which is real personnel-security substance today. Screening/onboarding/offboarding *process* still genuinely waits on the first non-owner hire. |
| **PE** — Physical Protection | Physical environment security | **Meets** — reuses the [Physical Access Policy](./FAR-52.204-21-compliance.md#physical-access-policy) written for FAR #8/#9 directly; same facts apply. |
| **RA** — Risk Assessment | Periodic, documented risk identification | **Documented 2026-09-23** — [shared/risk-assessment-schedule.md](./shared/risk-assessment-schedule.md) wraps a real cadence around the substance that already existed (`project_security_gap_plan`). First scheduled review: 2027-09-23. Internal pentest rounds (Rounds 1–2 run 2026-09-25, voided and re-run 2026-09-28, FAIL 0/3, ongoing daily — see CA below) count as ad hoc assessments. |
| **CA** — Security Assessment | Verify controls are implemented and working as intended | **Running, not passing (updated 2026-09-28).** Internal rounds per [pentest/PROTOCOL.md](./pentest/PROTOCOL.md): Rounds 1–2 run 2026-09-25, voided and re-run 2026-09-28, verdict FAIL, pass count 0/3, ongoing daily until 3 consecutive passes; the outside pen test follows that. Reports in [pentest/](./pentest/). |
| **SC** — System and Communications Protection | Boundary/communications monitoring and control | **Strong** — same evidence as FAR #10/#11 (Cloudflare Access boundary, `translator.sh` OUTPUT ONLY, Network Segmentation doc). |
| **SI** — System and Information Integrity | Flaw identification/correction, malicious content protection | **Strong** — same evidence as FAR #12–15 (content-hash integrity verification, Windows Defender verified live, dated remediation trail). **2026-10-01 drift audit:** Two additional SI-relevant corrections: (1) `mesh_ip()` in `sector3/hlk/hlk.py` was returning incorrect addresses for Tailscale nodes (`10.47.0.x` WireGuard range only), causing mesh communications to identify nodes incorrectly — rewritten Tailscale-first, corrects integrity of node identity in the mesh; (2) hardcoded vendor model string in H.L.K API tier removed — external API connections now require explicit, verified configuration (`HLK_API_MODEL` env var) rather than a static dependency that could silently route to a stale or unavailable endpoint. Both corrected same session per the dated remediation trail. |

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

**Real, open gap (1 of 14):** CA — internal pentest rounds are running daily (FAIL, 0/3 as of 2026-09-28); the outside pen test has not run.
PS moved from "unbuilt gap" to "Partial" once the owners' own competency
documentation was recognized as real substance, not a placeholder.

**Bottom line:** the paperwork layer (AT/IR/RA/PS) that used to be the
biggest gap is now closed or substantially addressed. What's left — MA/MP
formalization and CA (passing rounds, then the outside pen test) — is a small remaining lift, not a
structural gap. Revisit CUI-specific work only once it's actually on the
table for a specific contract, same "real findings over speculation"
posture as the pen test.
