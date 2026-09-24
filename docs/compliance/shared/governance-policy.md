# Information Security Governance Policy

Shared across all four compliance documents in `docs/compliance/` — written
once, referenced from each, rather than duplicated per-framework. Satisfies
FAR's implicit governance expectations, NIST 800-171's CM/RA program intent,
SOC 2's CC1 (Control Environment), and ISO 27001:2022's A.5 organizational
policy controls.

Scaled deliberately to reality: a single-operator business, not enterprise
boilerplate. This document gets revised the moment that reality changes —
a hire, a subcontractor, a co-owner taking on operational security duties.

---

## Scope

This policy governs the Phoenix DevOps OS infrastructure and any system
built on it (packages-worker, D1/R2, the `breach_coms` physical drives, the
Debian VM, this Windows PC) as used by PBM Consulting Service and PBM
Enterprises.

## Ownership and accountability

- **Jerry Leftwich** is the sole owner and operator of all Phoenix
  infrastructure and is solely accountable for security decisions,
  incident response, and this policy's maintenance.
- **Laurie Leftwich** holds a protected ownership share in the business
  outcome (per `project_pbm_companies` memory) but has no operational
  security responsibility under this policy. This is a deliberate
  structural fact, not an oversight — it's the actual shape of the
  business today.
- There is no board, no security committee, and no delegated security
  officer. Any framework document that expects one (some SOC 2/ISO 27001
  language assumes multi-person governance) should be read against this
  fact rather than assuming a structure that doesn't exist.

## Policy statements

1. **Vendor independence is a security control, not just an architecture
   preference.** Every material dependency on a single vendor is treated as
   a risk to be designed around — this is CLAUDE.md's founding rule (the
   Firebase incident), and it directly satisfies the "vendor risk
   management" intent behind SOC 2's CC9 and NIST/CMMC's supply-chain
   framing, even though it predates any compliance motivation.
2. **Open source by default, with an explicit carve-out.** Phoenix's own
   code stays open (GPL v3). Federal Contract Information, Controlled
   Unclassified Information, and any customer's confidential documents
   passing through the system are never covered by that default — see
   the FCI Publishing Policy in `FAR-52.204-21-compliance.md`.
3. **Access is least-privilege by default**, enforced through the `Ball`
   permission system, Cloudflare Access, and hardware-fingerprint
   authentication — not requested case-by-case.
4. **Every fix gets dated and recorded.** The existing practice of logging
   security fixes in CLAUDE.md's SESSION LOG and the `project_security_gap_plan`
   memory, with commit hashes, *is* this policy's audit-trail requirement
   — already proven in practice (Gap 1's fix, 2026-09-21), just formally
   named as the record of record here.
5. **AI-assisted sessions handling credentials require the same care as any
   other credential handling.** A real incident during this same session
   (a password typed directly into the chat transcript while walking
   through SSH access) is logged as the first entry in
   `security-training-record.md` — the corrective practice (don't echo
   secrets back, treat anything typed in chat as potentially exposed) is
   now written down rather than just handled once and forgotten.

## Review cadence

- **Minimum annual review** of this policy and the whole `docs/compliance/`
  folder.
- **Immediate review triggers**: PBM's first federal contract, PBM's first
  hire or subcontractor with system access, any contract that could
  introduce CUI, a discovered security incident, or a major architecture
  change (e.g. the Debian VM being promoted past PoC status).

## Version history

| Date | Change |
|---|---|
| 2026-09-23 | First version, written alongside the FAR/NIST/SOC2/ISO27001 scorecards |
