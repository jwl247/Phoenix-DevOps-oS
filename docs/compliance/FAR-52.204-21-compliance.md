# FAR 52.204-21 — Basic Safeguarding of Covered Contractor Information Systems

Baseline federal contracting security clause. Applies to any contractor (prime or
sub) whose information systems process, store, or transmit Federal Contract
Information (FCI) — triggers automatically the moment PBM Consulting Service
holds a federal contract, even without Controlled Unclassified Information
(CUI) in the picture. This document exists so that trigger doesn't arrive
before the answer does.

Goal, per Jerry (2026-09-23): every one of the 15 controls should be
genuinely above the regulatory floor, not just technically passing. This
document is the honest scorecard, updated as gaps close — not a claim made
once and left stale.

Source: [48 CFR § 52.204-21(b)(1)](https://www.law.cornell.edu/cfr/text/48/52.204-21), fetched 2026-09-23.

---

## Scorecard

| # | Control | Status | Evidence |
|---|---|---|---|
| 1 | Limit system access to authorized users/processes/devices | **Above standard** | Cloudflare Access (identity + service-token policies) + `isAuthorized()` on every route in `sector2/package-handler/worker/index.js` — two independent layers on the `packages-worker.phoenix-jwl.workers.dev` hostname. **Caveat (verified 2026-09-25):** the `get.authenticcoder.com` custom domain routes to the same worker *without* the Access layer — only the bearer-token check applies there (probe: unauthenticated `GET /glossary` → `401`, `GET /health` → `200`) |
| 2 | Limit access to permitted transactions/functions | **Above standard** | `sector1/security` / `franken5.py`'s `Ball` + `FAMILY_PERMISSIONS` — least-privilege by device family, explicit grant required for delete/translate/kernel |
| 3 | Verify/control external system connections | **Meets** | `translator.sh` OUTPUT ONLY boundary, sector3 romeo/juliet ingress/egress split — architecturally sound; romeo.py/juliet.py themselves are still Phase 5 (unbuilt) per CLAUDE.md, so the rule is enforced by convention today, not yet by code on that specific pair. **Updated 2026-10-01:** H.L.K mesh connections (`sector3/hlk/hlk.py`) require explicit `HLK_API_MODEL` env var for all external API calls — hardcoded vendor model string removed; external connections now require verified, explicit configuration before they can be established. |
| 4 | Control info posted on publicly accessible systems | **Fixed 2026-09-23** | See [FCI Publishing Policy](#fci-publishing-policy) below |
| 5 | Identify system users/processes/devices | **Above standard** | Hex identity + QR custody system (deterministic, per-file), `phoenix_auth.py` hardware fingerprint |
| 6 | Authenticate as a prerequisite to access | **Above standard** | Three independent layers: Cloudflare Access (edge) + `isAuthorized()` (app) + hardware fingerprint (machine) |
| 7 | Sanitize/destroy media before disposal/reuse | **Fixed 2026-09-23** | See [Media Sanitization Procedure](#media-sanitization-procedure) below |
| 8 | Limit physical access to authorized individuals | **Fixed 2026-09-23** | See [Physical Access Policy](#physical-access-policy) below |
| 9 | Escort visitors, log physical access, manage access devices | **Fixed 2026-09-23** | Covered in the same Physical Access Policy — no separate physical-access-device inventory exists because none is needed under the current single-operator premises model |
| 10 | Monitor/protect comms at external + internal boundaries | **Partial (re-scored 2026-10-07, XCUT-F39)**: the mesh boundary moved to Nebula and is not re-verified on live nodes; Cloudflare Access is off on packages-worker (XCUT-S16). Was "Above standard". | This is a first-class architectural concept in Phoenix already — `translator.sh` OUTPUT ONLY, sector3 boundary, Cloudflare Access gating every worker. **Corrected 2026-10-07 (Round 4 XCUT-F39):** Tailscale and WireGuard were removed 2026-10-05; the Phoenix Mesh is now Nebula `10.42.0.0/16` (`sector3/mesh/`, `docs/PIPELINE-INTERNALS.md`). The H.L.K mesh control is being moved to Nebula 2026-10-07 (S34OPS-F45: `mesh_ip()` in `sector3/hlk/hlk.py` reads 10.42.x as of commit `50e88f4`, not yet re-verified on the live nodes) — re-verify before credit; no credit is taken for it until then. Original 10-01 note, now historical: **Updated 2026-10-01:** H.L.K mesh boundary enforcement now covers Tailscale (`100.x.x.x`) in addition to the legacy WireGuard range (`10.47.0.x`). `mesh_ip()` in `sector3/hlk/hlk.py` rewritten Tailscale-first with WireGuard fallback — mesh communications at the node boundary are now correctly identified and monitored regardless of transport layer. |
| 11 | Segment publicly accessible components from internal network | **Fixed 2026-09-23** | See [Network Segmentation](#network-segmentation) below |
| 12 | Identify/report/correct flaws in a timely manner | **Partial (re-scored 2026-10-07, XCUT-F39)**: Round 4 = FAIL 0/3, fixes in progress (addenda 1-4). Was "Above standard". | Dated remediation trail — `project_security_gap_plan` memory, dated entries in `docs/history/SESSION-LOG.md` + git history (rewritten 2026-09-25 by `git filter-repo`; commit hashes cited before that date no longer resolve, so the dated log entries are the record), and the daily pentest rounds in `pentest/` since 2026-09-25. **2026-10-01 drift audit:** Three architecture drifts identified and corrected same session — (1) `HX_ZLEVEL` in `sector1/helix/helix_complete_stack.py` was `level=6`, corrected to `level=5` per `dm_helix.c` constant; (2) `mesh_ip()` in `sector3/hlk/hlk.py` was WireGuard-only, broken for Tailscale nodes [superseded 2026-10-07: both transports removed 10-05, mesh is Nebula 10.42.0.0/16, `mesh_ip()` moved to Nebula in `50e88f4` (S34OPS-F45), re-verify before credit] — rewritten Tailscale-first; (3) `HLK_API_MODEL` in `sector3/hlk/hlk.py` was hardcoded vendor model string — removed, now raises `RuntimeError` if env var not set. All three detected, documented, and corrected within same session. |
| 13 | Malicious code protection at appropriate locations | **Verified 2026-09-23** | Windows Defender: `AntivirusEnabled=True`, `RealTimeProtectionEnabled=True`, `BehaviorMonitorEnabled=True` — confirmed live via `Get-MpComputerStatus`, not assumed |
| 14 | Update malicious code protection mechanisms | **Verified 2026-09-23** | `AntivirusSignatureLastUpdated` / `AntispywareSignatureLastUpdated` both same-day at check time; scheduled signature update task present |
| 15 | Periodic + real-time scans of downloaded/opened/executed files | **Verified 2026-09-23** | `IoavProtectionEnabled=True` (on-access-via-download scanning), `OnAccessProtectionEnabled=True`, daily scheduled scan task confirmed `Ready` |

---

## FCI Publishing Policy

**The tension:** CLAUDE.md's standing rule is "Open source by default, share by
default, opt out not opt in" (Critical Rule #12). That rule is about
**Phoenix's own code and architecture** — the OS, the intake pipeline, the
apps. It was never meant to apply to a client's or contracting agency's data
that happens to pass through Phoenix's infrastructure, but nothing had said
so explicitly until now.

**Policy, effective 2026-09-23:**

1. Phoenix's own source code, architecture, and documentation remain open by
   default under GPL v3 — this does not change.
2. Any file, record, or document that constitutes Federal Contract
   Information (FCI) — anything received from, generated for, or about a
   federal contract or the agency awarding it — is **never** covered by the
   open-by-default rule. It is content passing through the system, not
   content of the system.
3. Mechanically: FCI-bearing files get `sensitive=1` at intake
   (`clonepool.sensitive`, already built), and `sensitive=1` content is
   excluded from any future public-facing glossary browsing, public repo
   sync, or default "share" behavior. The existing sensitive-file heuristic
   (`*auth*`/`*secret*`/`*password*`/`*credential*`/`*token*`) is a
   filename-pattern net, not a classification system — FCI needs to be
   flagged explicitly at intake time, by the person doing the intake, not
   inferred from the filename.
4. This policy applies the moment a federal contract exists — not
   retroactively to anything already public, since nothing FCI-bearing has
   ever been intaked.

**Not yet done:** `intake.sh` doesn't currently have an explicit `--fci` flag
distinct from the general sensitive-file heuristic. Build this when PBM's
first federal contract actually lands — no need to build the mechanism
before there's real FCI to flag.

---

## Media Sanitization Procedure

**The gap:** drives have been reformatted and repurposed before (E: →
"Claude Operational Zone", 2026-09-20) with no sanitization standard
applied — fine when nothing sensitive was ever on them, not fine as a
standing practice once FCI could be involved.

**Procedure, effective 2026-09-23**, aligned to NIST SP 800-88 guidance
(the standard FAR 52.204-21 implicitly points to):

1. **SSD/NVMe drives:** use the drive's own ATA Secure Erase or NVMe Format
   with Secure Erase command before reuse or disposal. `cipher /w` (Windows'
   built-in free-space wipe) is **not sufficient on SSDs** — wear-leveling
   means logical overwrite doesn't guarantee physical erasure. Note this
   explicitly since it's the tool most likely to be reached for by habit.
2. **Spinning HDDs (the `breach_coms` physical drives):** a single-pass
   full-disk overwrite (e.g. `dd if=/dev/zero` from the Debian VM, or a
   dedicated tool) is acceptable per NIST 800-88 for the confidentiality
   level FCI requires (not CUI — CUI would need cryptographic erase or
   physical destruction, a higher bar, not needed here yet).
3. **Drives that will never be reused** (retired hardware, drives being
   physically disposed of): physical destruction (drill through the
   platters, or a drive shredder service) rather than relying on a wipe
   that can't be independently verified after the fact.
4. **Before any `breach_coms` drive is reformatted, repurposed, or retired**,
   confirm nothing FCI-flagged (`sensitive=1` and explicitly marked FCI per
   the publishing policy above) exists on it. If it does, sanitize per (1)
   or (2) above **before** the reformat, not as an afterthought.
5. This procedure does not retroactively apply to the 2026-09-20 E: drive
   reformat — no FCI existed anywhere in Phoenix at that time.

---

## Physical Access Policy

Reality, written down rather than assumed:

1. Phoenix's systems (this Windows PC, the `breach_coms` physical drives,
   any attached storage) exist on premises where the only individuals with
   physical access are Jerry Leftwich and Laurie Leftwich. No third party
   has unescorted physical access to any system that processes or stores
   FCI.
2. Any physical maintenance, repair, or hardware work performed by a
   third party (e.g. a repair technician) happens either with Jerry present
   and supervising, or after any FCI-bearing drive has been removed from the
   machine being serviced.
3. No formal visitor log or badge system exists, and none is required under
   this model — the control (FAR 52.204-21(b)(1)(ix)) is satisfied by the
   fact that no unescorted visitor access to covered systems occurs at all,
   not by a logging mechanism monitoring visitors who were never given
   access in the first place.
4. This policy is revisited if the operating model changes — a shared
   office space, an employee, or a subcontractor with physical system access
   would all require a real update here, not a footnote.

---

## Network Segmentation

**What's actually publicly accessible (inventory re-verified 2026-09-28, round-2
audit XCUT-F20c):** only Cloudflare Workers — `packages-worker` (also on
`get.authenticcoder.com`, bearer-only there; Cloudflare Access is currently OFF on its workers.dev hostname too, XCUT-S16, 2026-10-07), `office-notify-worker`,
`phoenix-office-worker`, `pbm-leads-worker`, `pbm-radar-worker`, the
`pbm-consulting-website` static-assets worker (pbmconsultingservice.com),
`lifefirst-mcp`, `lifefirst-mustanswer`, `phoenix-mesh-worker` (the Phoenix Mesh
switchboard), `sacrifice-worker` (Sacrifice game state + map tiles; public reads by design, writes need `FRANK_TOKEN`; `/` 200 on 2026-10-07), `phoenix-vault-worker` (hands out the encrypted vault only to a caller holding the passphrase-derived fetch token; `/` 200 on 2026-10-07) — both added 2026-10-07 (XCUT-F39), and — when the tunnel is up — the `lifefirst` Cloudflare tunnel
publishing the Debian VM's Apache (down, 530, on 2026-09-28). `phoenix-clonepool-r2`
was deleted 2026-09-25 (404). Each worker is gated by Cloudflare Access (per Gap 1's
fix) or its own bearer-token auth; the static site and its `/radar` form are public by
design (Turnstile on the forms).

**What's never publicly accessible:** D1 databases and R2 buckets have no
public endpoint of their own — every read or write goes through a Worker,
which is the only thing with the binding. The physical machines (this PC,
the Debian VM, the `breach_coms` drives) have no open inbound port to the
public internet at all. **Exception (corrected 2026-10-07, XCUT-F39):** the `awslh` AWS Lightsail
box is the Nebula mesh lighthouse and relay and listens on a public IP on UDP 4242
(`docs/PIPELINE-INTERNALS.md`); everything else reaches each other over that mesh. `192.168.1.x` addresses are LAN-only, unreachable from outside the
router.

**This is already real segmentation, just never diagrammed:**

```
Internet
   │
   ▼
Cloudflare Access (identity + service-token gate)
   │
   ▼
Cloudflare Workers  ◄── the only publicly-addressable layer
   │
   ▼
D1 / R2  ◄── no public endpoint, only reachable via a Worker binding
   │
   ▼
Local machines (this PC, Debian VM, breach_coms drives)
   ◄── LAN-only, no public inbound port (except awslh, the Nebula lighthouse: public UDP 4242)
```

Satisfies FAR 52.204-21(b)(1)(xi) as written: publicly accessible components
(the Workers) are already logically and physically separated from internal
systems (the local machines and their storage) — the fix here was writing
it down, not building new isolation that didn't exist.

---

## Office — where FCI actually lives

Both Office variants (`sector2/apps/office`, the Entourage app, and
`phoenix-office/`, the standalone sister product) are the systems most
likely to actually hold FCI in practice — work orders, signed contract
documents, change orders, anything a federal contract generates on paper.
This section makes that connection explicit rather than leaving Office
covered only implicitly by the general scorecard above.

1. **Access control (#1, #2, #6):** Office's own author-identity system
   (`lib/identity.js` — fingerprint / Windows SID / Google OpenID, resolved
   to a canonical `author_id`) sits on top of the same Cloudflare Access +
   `isAuthorized()` layers already covering `office-notify-worker` and
   `phoenix-office-worker`. A document's fill/sign/seal lifecycle is
   already access-gated per step, not just at the API boundary.
2. **FCI marking (#4):** any document created in Office for actual federal
   contract work must be flagged `sensitive=1` / FCI at creation, per the
   FCI Publishing Policy above. Office's fields lock individually as
   filled and the document hash-locks permanently on signing — this is a
   natural point to also stamp the FCI flag, since signing is already the
   moment the document becomes immutable. **Not yet built**: neither Office
   variant currently prompts for or sets an FCI flag at sign time — this is
   the same "build it when a real contract exists" deferral as the general
   `--fci` intake flag above, just scoped to Office's own signing flow.
3. **Tamper-evidence IS the audit trail (#12):** Office's whole design
   premise — hash-lock on signing, `tamper-guard.js` alteration detection,
   append-only `office_notifications`/version-history tables — already
   produces exactly the kind of "identify and report flaws/tampering in a
   timely manner" evidence FAR 52.204-21(b)(1)(xii) asks for, just aimed at
   document integrity rather than infrastructure vulnerabilities. Worth
   citing directly if this ever comes up in a real compliance review.
4. **Sanitization (#7):** signed Office documents are seal-on-sign intaked
   into R2 (permanent, immutable per-content key) — the Media Sanitization
   Procedure above applies to the local disposable copy
   (`~/PhoenixOffice/<b58>.office.json`, explicitly called disposable once
   sealed per the 2026-09-07 build), not the R2-held sealed original. Worth
   confirming this distinction explicitly if a real contract's documents
   ever pass through here: "disposable" and "sanitization-exempt because
   it's disposable" are not automatically the same claim, and haven't been
   tested against that specific question yet.
5. **Closed 2026-09-23:** `RESEND_API_KEY` is now set on both notify
   workers — `office-notify-worker` and `phoenix-office-worker` `/health`
   both report `"transport":"resend"` (re-verified 2026-09-25), so tamper
   notifications actually deliver. (Previously a real functional gap in
   control #12's "timely" requirement.) `pbm-leads-worker` reported
   `"transport":"NONE"` until its Resend key was set 2026-09-27; live `/health`
   → `"transport":"resend"` (re-verified 2026-09-28). It carries no FCI.
