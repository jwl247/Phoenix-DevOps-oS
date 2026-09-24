# SOC 2 / ISO 27001:2022 Readiness

**Different trigger than the federal-contracting docs in this folder.** FAR
52.204-21 and NIST 800-171 apply because of PBM's federal set-aside
ambitions. SOC 2 and ISO 27001 apply because of **phoenix-office's planned
hosted tier** (`$15-25/mo` per business, per `project_pbm_companies` memory)
— the moment Phoenix hosts another business's documents, "do you have
SOC 2?" becomes a real question a buyer asks, independent of any federal
contract. Informational/roadmap for now, same posture as the NIST doc,
pending Jerry's call on whether to start closing gaps immediately.

ISO 27001 note: the standard changed — current edition is **ISO 27001:2022**
(+ 2024 climate amendment), 93 Annex A controls across 4 themes. The
older, commonly-cited 2013 edition (114 controls, 14 domains) is superseded.
Sources: [SOC 2 TSC via Vanta](https://www.vanta.com/collection/soc-2/soc-2-trust-service-criteria), [ISO 27001:2022 via Scrut](https://www.scrut.io/hub/iso-27001/iso-27001-controls), both fetched 2026-09-23.

---

## SOC 2 — Security (CC1–CC9, mandatory for every SOC 2 report)

| # | Criterion | Covers | Status |
|---|---|---|---|
| CC1 | Control Environment | Governance, roles, accountability, **competence** | **Documented 2026-09-23** — [shared/governance-policy.md](./shared/governance-policy.md) (roles/accountability) + [shared/personnel-competency-report.md](./shared/personnel-competency-report.md) (the competence component specifically — Jerry's 25-year construction background, Laurie's training role). |
| CC2 | Communication and Information | Internal + external security-responsibility communication | **Partial.** Internal (CLAUDE.md, memory system, and now the governance policy) is genuinely strong. External is still a real gap — no public security policy/statement exists (e.g. a `security.txt` or a security page a customer could actually read). Not built in this pass — lower priority until there's an actual hosted-tier customer to publish it for. |
| CC3 | Risk Assessment | Identify/analyze/respond to risk | **Documented 2026-09-23** — [shared/risk-assessment-schedule.md](./shared/risk-assessment-schedule.md), wrapping a real cadence around the existing `project_security_gap_plan` substance. |
| CC4 | Monitoring Activities | Ongoing control evaluation, remediation | **Strong** — the dated, git-committed remediation trail is exactly this in practice. |
| CC5 | Control Activities | Selecting/deploying controls | **Strong** — `Ball` permissions, Cloudflare Access, `isAuthorized()`. |
| CC6 | Logical and Physical Access | Provisioning, auth, segmentation, physical access, disposal | **Strong** — directly reuses the FAR doc's #1/#2/#6/#7/#8/#9/#11 evidence. |
| CC7 | System Operations | Vulnerability detection, monitoring, IR, recovery | **Improved.** Recovery/backup remains a genuine strength (4-day tier rotation, GitHub mirrors of all repos, a full `wbadmin` system image, `F:\Vault` backups). Incident response is now [shared/incident-response-plan.md](./shared/incident-response-plan.md) with a real worked example. Formal, scheduled vulnerability scanning (distinct from the ad hoc audit-doc process) is still a genuine gap. |
| CC8 | Change Management | Authorize/design/test/approve changes | **Partial.** Git history + intake versioning is real, strong change tracking — but no formal change-approval step, since one person currently approves their own changes. Unchanged; a real second approver isn't possible until there's a second person with the standing to be one. |
| CC9 | Risk Mitigation | Business disruption planning, vendor risk management | **Strong on vendor risk** — vendor independence is Phoenix's literal founding design principle (the Firebase incident, `translator.sh`'s 9 backends, swappable email transport). **Gap on business disruption planning** — backups exist, but no written, tested BCP/DR plan. Not built in this pass — a real BCP/DR document is its own substantial piece of work, flagged for a future session rather than rushed here. |

**Optional TSC categories** (included only if a buyer requires them) — likely
relevant for phoenix-office's hosted tier specifically:
- **Confidentiality** — customer documents in R2/D1, directly relevant, not yet scoped
- **Availability** — SaaS uptime commitments, not yet scoped
- **Privacy** — if end-customer PII is ever stored, not yet scoped
- **Processing Integrity** — less likely to be asked for a document-hosting product, lower priority

---

## ISO 27001:2022 — Annex A (4 themes, 93 controls)

| Theme | Controls | Covers | Status |
|---|---|---|---|
| **Organizational** (A.5) | 37 | Policies, roles, threat intel, asset inventory, classification, cloud security, BCP | **Mixed, improved.** Asset inventory is a genuine strength — the entire custody/clonepool system *is* a real, granular asset inventory most companies this size don't have. [shared/governance-policy.md](./shared/governance-policy.md) now covers the written policy/roles gap. Remaining real gaps: no formal information-classification scheme beyond the `sensitive=1` flag, threat intelligence still ad hoc rather than a defined practice, no BCP document. |
| **People** (A.6) | 8 | Screening, employment terms, training, discipline | **Partial, corrected 2026-09-23** — [shared/personnel-competency-report.md](./shared/personnel-competency-report.md) documents the owners' own competency (Jerry's construction background, Laurie's training role, pending her specific credential details). Screening/employment-terms/discipline processes still genuinely wait on the first non-owner hire. |
| **Physical** (A.7) | 14 | Perimeter, entry access, surveillance, secure disposal | **Meets**, reusing the FAR doc's Physical Access Policy + Media Sanitization Procedure directly. No surveillance/CCTV system, which is appropriate at this scale, not a real gap. |
| **Technological** (A.8) | 34 | Encryption, access control, monitoring, config management, secure deletion, data masking, DLP, activity monitoring, web filtering, secure coding | **Mixed.** Strong: access control, monitoring, configuration management (the versioning system), secure deletion (Media Sanitization Procedure). Real, unbuilt gaps: no data masking, no DLP tooling, no web filtering. Secure coding is practiced (CLAUDE.md's own security-conscious rules — no leaked secrets, input validation at boundaries) but not written as a formal standard an auditor could point to. |

---

## Honest summary

Same shape as the NIST assessment: the controls that were already true
because of *how Phoenix was built for other reasons* (vendor independence,
the custody/audit chain, access control layering, backup discipline) score
strong. The paperwork layer — training records, risk-assessment cadence,
incident response plan, governance/policy document — that used to be the
consistent gap across FAR, NIST, SOC 2, and ISO 27001 alike is now closed,
via the four shared documents in `docs/compliance/shared/`, written once
and referenced from every framework rather than duplicated four times.

**What's still genuinely open, not paperwork-shaped:** external security
communication (CC2 — nothing to publish yet, no hosted-tier customer to
publish it for), formal change-approval process and a written BCP/DR plan
(CC8/CC9 — both real, both deferred as substantial standalone work rather
than rushed), and the actual pen test. Those are the honest remaining
items, not more documents to write for their own sake.
