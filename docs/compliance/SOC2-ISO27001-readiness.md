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
| CC1 | Control Environment | Governance, roles, accountability, **competence** | **Documented 2026-09-23** — [shared/governance-policy.md](./shared/governance-policy.md) (roles/accountability) + [shared/personnel-competency-report.md](./shared/personnel-competency-report.md) (the competence component specifically — Jerry's 28-year construction background, Laurie's training role). |
| CC2 | Communication and Information | Internal + external security-responsibility communication | **Partial.** Internal (CLAUDE.md, memory system, and now the governance policy) is genuinely strong. External is still a real gap — no public security policy/statement exists (e.g. a `security.txt` or a security page a customer could actually read). Not built in this pass — lower priority until there's an actual hosted-tier customer to publish it for. |
| CC3 | Risk Assessment | Identify/analyze/respond to risk | **Documented 2026-09-23** — [shared/risk-assessment-schedule.md](./shared/risk-assessment-schedule.md), wrapping a real cadence around the existing `project_security_gap_plan` substance. |
| CC4 | Monitoring Activities | Ongoing control evaluation, remediation | **Strong** — the dated remediation trail (`docs/history/SESSION-LOG.md` + git history, rewritten 2026-09-25 so pre-rewrite hashes no longer resolve; the dated entries are the record) and, since 2026-09-25, the daily pentest rounds in `pentest/` are exactly this in practice. |
| CC5 | Control Activities | Selecting/deploying controls | **Strong** — `Ball` permissions, Cloudflare Access, `isAuthorized()`. |
| CC6 | Logical and Physical Access | Provisioning, auth, segmentation, physical access, disposal | **Strong** — directly reuses the FAR doc's #1/#2/#6/#7/#8/#9/#11 evidence. |
| CC7 | System Operations | Vulnerability detection, monitoring, IR, recovery | **Improved, corrected 2026-09-29.** Recovery/backup: GitHub mirrors of all repos, a full `wbadmin` system image and `F:\Vault` backups are real. **Round-2 audit 2026-09-28 (XCUT-F15/F16):** the 4-day tier rotation previously credited here is wired but manual-only and has never been scheduled or run, and per-version R2 bytes had never been uploaded as of that audit (history is a D1 ledger only) — neither is credited for CC7.5 / ISO A.8.13 until verified live. Incident response is now [shared/incident-response-plan.md](./shared/incident-response-plan.md) with a real worked example. Daily internal pentest + functionality rounds run since 2026-09-25 per `pentest/PROTOCOL.md` (FAIL, 0/3 as of 2026-09-28); automated vulnerability scanning beyond that is still a gap. **2026-10-01:** `mesh_ip()` in `sector3/hlk/hlk.py` corrected — mesh node addressing was broken for Tailscale transport; rewritten Tailscale-first (`100.x.x.x`) with WireGuard fallback. System operations monitoring for mesh communications now correctly identifies nodes across both transports. |
| CC8 | Change Management | Authorize/design/test/approve changes | **Partial.** Git history + intake versioning is real, strong change tracking — but no formal change-approval step, since one person currently approves their own changes. Unchanged; a real second approver isn't possible until there's a second person with the standing to be one. **2026-10-01 drift audit:** `HX_ZLEVEL` in `sector1/helix/helix_complete_stack.py` detected as drifted from the authoritative kernel constant (`dm_helix.c`: level=5 → code had level=6). Drift detected and corrected within the same session. Demonstrates that change management catch processes are working; the correction is logged in `docs/history/SESSION-LOG.md`. |
| CC9 | Risk Mitigation | Business disruption planning, vendor risk management | **Strong on vendor risk** — vendor independence is Phoenix's literal founding design principle (the Firebase incident, `translator.sh`'s 9 backends, swappable email transport). **Gap on business disruption planning** — backups exist, but no written, tested BCP/DR plan. Not built in this pass — a real BCP/DR document is its own substantial piece of work, flagged for a future session rather than rushed here. **2026-10-01:** Hardcoded vendor model string in `sector3/hlk/hlk.py` H.L.K API tier removed — a live vendor dependency embedded in code that could silently fail if the vendor changes model naming or deprecates it. Replaced with required `HLK_API_MODEL` env var; raises `RuntimeError` if unset. Vendor risk mitigation applied at the code level, not just the architectural level. |

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
| **Technological** (A.8) | 34 | Encryption, access control, monitoring, config management, secure deletion, data masking, DLP, activity monitoring, web filtering, secure coding | **Mixed.** Strong: access control, monitoring, configuration management (the versioning system), secure deletion (Media Sanitization Procedure). Real, unbuilt gaps: no data masking, no DLP tooling, no web filtering. Secure coding is practiced (CLAUDE.md's own security-conscious rules — no leaked secrets, input validation at boundaries) but not written as a formal standard an auditor could point to. **2026-10-01 config management:** `HX_ZLEVEL` drift (level=6 vs authoritative level=5) corrected — concrete evidence of A.8 config monitoring finding and correcting a deviation from the documented baseline. `mesh_ip()` addressing corrected for Tailscale transport — monitoring coverage extended to reflect current network topology. Vendor model hardcoding removed from H.L.K — dependency risk reduced per A.8 secure coding and supply-chain risk principles. |

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
than rushed), and the pen test (internal rounds running daily, FAIL 0/3 as of 2026-09-28; outside test after 3 consecutive passes). Those are the honest remaining
items, not more documents to write for their own sake.
