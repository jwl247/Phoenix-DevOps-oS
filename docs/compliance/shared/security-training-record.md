# Security Awareness Training Record

Shared across all four compliance documents — satisfies NIST 800-171's AT
family, ISO 27001:2022's People (A.6) theme, and the implicit personnel
awareness expectation behind SOC 2's control environment.

For a single-operator business this is a log, not a program with a
curriculum vendor — real topics, dated, tied to real events where possible
rather than generic checkbox items. Add an entry here whenever a real
security-relevant lesson happens, not just on a fixed schedule (though an
annual minimum review still applies per the Governance Policy).

---

## Log

| Date | Topic | Trigger | Outcome |
|---|---|---|---|
| 2026-09-23 | Credential handling in AI-assisted terminal sessions | A real incident this session — an SSH password (`jwlef` / a real password) was typed directly into the Claude Code chat, which persists in conversation history/logs. | Corrective practice adopted: treat anything typed into an AI chat session as a real credential-exposure event, not a private terminal prompt. The assistant does not echo secrets back or reuse them elsewhere. Any credential typed into a chat this way should be treated as needing rotation if the transcript could ever leave a fully trusted channel. |
| 2026-09-23 | Physical access policy awareness | Written as part of the FAR 52.204-21 compliance pass. | Confirmed understanding: only Jerry and Laurie have physical access to Phoenix systems; any third-party physical work happens supervised or with FCI-bearing drives removed first. |
| 2026-09-23 | FCI/sensitive-data publishing policy | Written as part of the FAR 52.204-21 compliance pass — direct tension identified between CLAUDE.md's "open source by default" rule and federal contract data handling. | Confirmed understanding: Phoenix's own code stays open; any actual federal contract information must be flagged `sensitive=1`/FCI at intake and is never covered by the open-by-default rule. |
| 2026-09-23 | Media sanitization — SSD vs. HDD | Written as part of the FAR 52.204-21 compliance pass, after finding no sanitization standard had been applied to the 2026-09-20 drive reformat. | Confirmed understanding: `cipher /w` does not reliably sanitize SSDs due to wear-leveling; ATA Secure Erase / NVMe Format required for SSDs, single-pass overwrite acceptable for spinning `breach_coms` drives at FCI's confidentiality level, physical destruction for drives being retired outright. |

## Next scheduled review

Annual, alongside the Governance Policy review — see
`governance-policy.md`'s review cadence. Add real entries as they happen in
between; don't wait for the annual date if something real occurs.
