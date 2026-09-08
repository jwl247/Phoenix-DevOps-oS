# Phoenix Office
**UnitedSys — United Systems | jwl247**
**Part of:** Phoenix DevOps OS (Sector 2 — Entourage apps)
**Status:** Specification frozen 2026-09-05 — Phase 1 (core document engine) built and tested, 21/21 passing

---

## What This Is

Not a word processor. Not Google Docs, not Microsoft Office. Office is a
self-sovereign document format with an AI copilot bound to it for life —
designed to remove the "convert this to that" tax that defines every
existing office suite. CLAUDE.md's one-line description going in was:
*"dual browser pane document, no convert no translate."* This document is
the real spec underneath that line, worked out 2026-09-05.

The core bet: a document should carry its own truth wherever it goes,
the way a Phoenix file already carries its own identity via the
[TAV address system](../../../CLAUDE.md) (SHA3-512 → base58, header/footer
QR). Office extends that idea from "this file is authentically this file"
to "this file's content, history, and rules of authorship travel with it,
with no central database required to trust it."

---

## Product principles (Jerry, 2026-09-07) — the bar every feature is held to

**EASY for the user, even when it's hard for us.** The complexity lives in
Phoenix, never in the person's face.

- **No 1000-page manual.** If a feature needs a manual, it's wrong. The
  screen tells you what to do.
- **A button for every process.** Not a menu of options to reason about —
  one obvious button per thing you'd want to do, in the state where it
  makes sense.
- **No "convert." No "save."** Conversion is invisible process-following
  (Module 4). **Saving is automatic** — the document is always persisted;
  there is no Save button to forget to press.
- **The clone pool carries the load.** Office doesn't manage files, Phoenix
  does. Concretely:
  - Every Office document is **auto-intaked into the clone pool** — hex
    identity, custody, R2. So "it's saved" means "the pool has it,"
    versioned and recoverable, with zero user action.
  - **Reference other documents by naming them.** "I need to reference
    these 3 documents" → tell Phoenix which → *poof*, those 3 are in your
    working directory, pulled from the pool. Use them, then **delete them
    freely** — the pool is the source of truth, not your workdir. (This is
    `usys clone` / the pull-down worker, wired into Office's UI.)
  - **New document = pick a template**, not "type your field names." The
    templates (work order, invoice, inspection, change order) live in the
    pool; picking one drops its field set in.

**Office is the hook; Phoenix is the reason it can be this easy.** "People
want PBM Office — so you have to have Phoenix." Every place we can make an
instance genuinely easy, Phoenix underneath is what makes that possible.
The two sell together.

---

## Decided

### The dual pane
Left pane: the user's own input/editing. Right pane: Claude's live
recommendations and suggested additions as they write — not a second
person's cursor (this is not real-time multiplayer co-editing), and not a
raw/rendered split of the same content. It's a standing AI copilot pane,
same spirit as ScriptForge's Fix Panel but for document content/structure
instead of code lint.

### The Worker
"The worker" is Claude's own tool, bound to one specific document for its
whole life — not a generic backend API, and not a Durable-Object-style
real-time sync layer (there's no second live user to sync with; see Dual
pane above). Its job:
- Dynamically import whatever processing capability the current task
  needs, on demand, rather than the document format dictating up front
  what's possible. Concretely (per Jerry, 2026-09-05): **Frank imports
  LibreOffice's own modules** on demand — GPL, open source, already
  handles the real breadth of document/spreadsheet/presentation format
  interop, so the Worker isn't reinventing format conversion from
  scratch. **Helix** sits underneath as the fast memory layer those
  imported modules run against. This means real document processing is a
  Phoenix-native capability — **the author side genuinely needs Phoenix
  running** (Frank + Helix + LibreOffice available to import) for this to
  work, unlike the counterparty/notification side, which deliberately
  doesn't require Phoenix at all (see Notification delivery, below).
- Convert formats **automatically** as the user's process changes (e.g.
  drafting text → needs a table → needs a chart) — the user never runs a
  manual "convert" or "save as" command. This is the literal meaning of
  "no convert no translate": conversion still happens, but it's invisible
  process-following, not a user-facing verb.
- Auto-fill data that's contextually obvious during that change (exact
  sourcing — same document, Phoenix's D1/glossary, or elsewhere — is
  still open; see below).

### Self-sovereign truth
The document itself is the source of truth, not a D1 row. This is a
deliberate departure from how the rest of Phoenix works today — the clone
pool's D1 ledger is explicitly "chain of evidence for everything"
(CLAUDE.md) for every other artifact type. Office documents are the one
kind of Phoenix artifact where the *file itself*, not a central database,
is authoritative. D1 may still hold a custody/reference record (consistent
with the rest of Phoenix), but losing that record must never invalidate
the document's own truth.

### Immutability + authorship rules
Once a document is forged, it follows Phoenix's existing immutability
principle (CLAUDE.md rule: *"Immutable: reviews, switches, custody
chain"*) applied specifically to the document and its governance:
- Content: modify forward (new version), never delete/overwrite prior
  state — same shape as the clone pool's existing version retention.
- Rules of authorship/permissions on the document: settable and later
  *modifiable* by the OG (original) author only, but never removable —
  there must always be a governing rule in force. Rule changes are
  themselves append-only, same principle as content.

### The driving use case: tamper-evident records
Not primarily a creative-writing copilot. The concrete target (2026-09-05):
work orders, invoices, and filled forms that can't be quietly altered
after the fact by whoever filled them out — e.g. a mechanic editing a work
order to add a charge the customer never approved. Once finalized, the
content is locked permanently: **zero further edits to the original.** A
real-world correction (the customer did add a service) must exist as a
new, separately dated, visibly-linked document (a change order) — never
an edit to the original record. This reuses the exact integrity shape
already proven in the clone pool: `intake.sh` sets a SHA3-512 + BLAKE2b
hash baseline at intake time and re-verifies it at clone time, gating on
mismatch (`sector2/package-handler/README.md` § Integrity Verification).
Office applies the same pattern to "finalized" instead of "intaked."

**General principle worth naming (2026-09-05, Jerry):** to make anything
immutable, all it takes is a narrowed snapshot of it, held read-only. That's
literally what SIGNED is — a snapshot of the field set at the handoff
moment, hash-locked, never opened for writing again. Not specific to
Office; this is the same shape as `breach_coms4`'s "never delete" rule and
the clone pool's version retention, just named plainly. Worth reapplying
anywhere else in Phoenix something needs to become tamper-evident.

### Read+fill, not write — from the moment of forging, not just after signing
Refined 2026-09-05, per Jerry: immutability doesn't start at the end of
the document's life, it starts at the *field* level from the moment it's
forged. A field, once filled, can never be overwritten — not even by the
same author, not even while the document is still in DRAFT. Filling a
still-empty field is always allowed pre-signature; overwriting an
already-filled one is rejected exactly like an alteration attempt on a
signed document, just scoped to that one field. This means even a
work-in-progress document is already tamper-evident at the field level,
not just the finished one.

### Signing is a custody handoff, not a button
Resolves open question #4. The document moves through a real state
machine, "the ball" passing between two named parties:

```
DRAFT            → author fills fields (each fillable once — see above)
  → handed to client for review
PENDING_REVIEW   → client's turn to hold the ball (sign / reject / request changes)
  → client signs, handing it back to author
SIGNED           → hash baseline set over the full field set at this exact
                   moment. Fully immutable, period — no more fills, no
                   more edits, to any field, by anyone, ever. Any attempt
                   past this point is an alteration attempt, not a normal
                   edit or fill.
```

Signing triggers specifically on the **client's signature / handback**,
not on first save and not on a generic "finalize" action. This also
answers who the counterparty is for escalation purposes (open question
#7, partially): it's whoever last held the ball on the other side of the
final handoff — in the work-order example, the customer.

### Alteration attempts trigger a standalone notification — not Life First
Considered reusing Life First's Module 6 engine
(`sector2/apps/lifefirst/module_6_notification_ai.php`) directly, since
its escalation logic is genuinely generic (any `user_id`/`message`/
`type`/`priority`, 5-level/30-second `must_answer` escalation with
acknowledgment tracking already built and working). **Rejected 2026-09-05:
Office's counterparty can't be assumed to have Life First at all** — an
oil-change customer has no reason to be a Life First user, and the whole
point of this feature is protecting them, so it can't require them to
already be in Phoenix's ecosystem. Office needs its own delivery path,
independent of Life First's user table:
- Contact info (phone/email) captured directly on the document itself,
  not looked up via a Life First/Phoenix account.
- A standalone SMS/email send on any alteration attempt against a SIGNED
  document.
- Module 6's *shape* (repeat until acknowledged, escalating urgency) is
  still worth copying as a pattern — just not its implementation or its
  dependency on a Life First user existing.

### Authorship = pluggable identity, Phoenix's own always sovereign
Resolves open questions #1 and #2 together. Rather than porting
`phoenix_auth.py`'s Linux-only hardware-signal collection to Windows, each
platform uses whichever native identity it already has, all resolving to
one canonical `author_id` (D1-backed) that can carry multiple linked
credentials:
- **Phoenix hardware fingerprint** (`sector1/auth/phoenix_auth.py`'s
  existing SHA3-512 + BLAKE2b double hash) — the sovereign option, works
  standalone with zero vendor, zero account, zero network. Always
  available; this is the one that can never be required to route through
  anyone else.
- **Windows sign-in** — the OS account that already authenticated the
  person on that machine. No new sign-in flow needed on Windows.
- **Google sign-in** — for cross-machine convenience (a Google identity is
  inherently fleet-spanning without enrolling individual machines).
  **Explicitly approved by Jerry, 2026-09-05** — per CLAUDE.md's own rule,
  a Google/Microsoft dependency needs his explicit sign-off, given here as
  one interchangeable *option* alongside the other two, never the only
  path. Phoenix's own fingerprint must remain fully sufficient alone for
  anyone who wants zero vendor involvement.

Whichever identity verified the document at each custody-handoff step is
what gets recorded in its embedded history (see File format, below) —
this also naturally answers "one machine or a fleet": a Google or Windows
identity already spans a fleet by nature, while a bare Phoenix fingerprint
stays scoped to that one sovereign machine unless/until multiple
fingerprints are explicitly linked to the same `author_id`.

Only the OG author's verified identity (via any linked credential) can:
- Change the document's rules.
- Produce a **copy** that becomes its own new, independent source of
  truth (a fork). Anyone else can view/reference the original but cannot
  spin off their own authoritative version of it.

### Autofill scope
Same document first, Phoenix's own D1/glossary second. No outside/internet
lookups — the Worker stays self-contained, consistent with the rest of
Phoenix's self-sovereignty stance. Example: a repeat customer's name/phone
autofills from an earlier document or D1 if already known there; a part
price autofills from the glossary if cataloged; nothing gets pulled from
a general web lookup.

### Copy semantics
A non-author gets read/reference access only — can open and view the
document in Office, cannot produce a new independent-truth fork of it.
No plain-snapshot export in v1; that's a straightforward later addition
if it turns out to be needed, not a blocker to building the core.

### Notification delivery
Standalone, not Life First (see above). Carrier email-to-SMS gateways
(`number@vtext.com`-style) as the primary path, plain email as fallback
when no carrier is given. Outbound path: Cloudflare Email Workers, to stay
inside Phoenix's existing vendor (same stack as D1/R2), not a new SMTP
credential to manage.

---

## Build plan

**Phase 1 — core document engine — DONE, 2026-09-05:**
- `lib/fingerprint.js` — cross-platform author fingerprint, same
  SHA3-512+BLAKE2b double-hash algorithm as `phoenix_auth.py`. Verified
  live on this machine: all 9 Windows signals (machine GUID, BIOS serial,
  CPU ID, board serial, product UUID, MAC, OS build, RAM, CPU name)
  returned real hardware data, none "unavailable"; fingerprint is stable
  across repeated calls.
- `lib/document.js` — field-level read+fill state machine (DRAFT →
  PENDING_REVIEW → SIGNED), a field once filled can never be overwritten
  even pre-signature, hash baseline set over all fields at signing,
  tamper detection (`verifyIntegrity`) on any later mismatch, change
  orders that link to but never edit the original.
- `lib/notify.js` — carrier email-to-SMS gateway + plain-email fallback,
  alteration-notice construction, pluggable send transport.
- `test/test.js` — 21/21 passing, real assertions (not smoke tests):
  fingerprint stability + real-signal verification, every state
  transition and its illegal-transition guards, tamper detection against
  a directly-mutated field (the actual "mechanic edits the file on disk"
  scenario), notification targeting and payload correctness.
**Phase 2, Module 1 — embedded-truth file format — DONE, 2026-09-05:**
- `lib/file-format.js` — `.office` file save/load. Header QR is a stable
  per-document identity fixed at creation (doesn't drift as fields fill
  in); footer QR only exists once SIGNED and is the actual integrity
  proof, reusing `document.js`'s existing `contentHash`/`hashesMatch`.
  Base58 ported from `phoenix-core/tools/intake.py`'s `_base58()` —
  cross-verified byte-identical against a live Python run on 4 vectors
  including leading-zero-byte edge cases.
- `test/test.js` — 27/27 passing (6 new): base58 parity, header stability
  across fills, footer timing, full save→load round-trip, and the actual
  attack scenario — directly editing a signed `.office` file's saved
  bytes on disk, caught on load.

**Phase 2, Module 2 — D1 schema — DONE, 2026-09-05:**
- `schema.sql` — `office_authors` (pluggable credential→author_id
  mapping) and `office_documents` (custody/reference record, explicitly
  not the source of truth — the `.office` file remains authoritative even
  if this table is lost). Applied for real: `wrangler d1 execute
  phoenix_dev_db --file=schema.sql --remote`, both tables confirmed live
  via a follow-up query against `sqlite_master`.

**Phase 2, Module 3 — notification transport — CODE COMPLETE, 2026-09-07:**
- `notify-worker/` — `office-notify-worker`, standalone Cloudflare Worker.
  `POST /notify` (bearer `PHOENIX_AUTH`), `GET /ack/:token` (single-use,
  token is the auth), `GET /whoami`, `GET /health`. `scheduled()` cron
  (`* * * * *`) re-sends every unacknowledged notification, escalating the
  subject, level capped at 5. Zero deps. Survives with no Phoenix box up.
- `schema.sql` — `office_notifications` append-only audit table (the proof
  the attempt happened *and* the counterparty was told, repeatedly, until
  acknowledged).
- `lib/tamper-guard.js` — `checkAndAlert(doc, opts)`, the seam between
  `document.js` (pure detection) and `notify.js` (payloads) and the worker.
  Never throws; a failed notice can't corrupt the op that found the tamper.
- `notify.js` gained `workerTransport({ workerUrl, auth, docHex })`.
- 36/36 tests (test harness fixed to actually await async cases).
  `wrangler deploy --dry-run` clean.
- **Transport:** DESIGN.md's "Cloudflare Email Workers" isn't a real free
  arbitrary-recipient path (`send_email` = verified recipients only;
  MailChannels' free tier gone). Working transport is **Resend** (swappable,
  one `fetch`); `send_email` binding still coded for issuer copies; AWS SES
  rejected (vendor lock-in). Cron min is 60s, not Module 6's 30s.
- **Pending:** Jerry's live deploy (secrets + Resend key) + one real SMS
  round-trip. Runbook: `notify-worker/README.md`.

**Phase 2, Module 5 — pluggable author identity — CODE COMPLETE, 2026-09-07:**
- `lib/identity.js` — `resolveAuthor()` resolves the acting author to one
  canonical `author_id`. `fingerprint` (always works, zero network, never
  needs D1 — the sovereign anchor) / `windows` (the OS account SID) /
  `google` (an OpenID `sub` via the OAuth 2.0 device-authorization flow —
  no embedded browser). `author_id` is *derived* deterministically from a
  credential; D1's `office_authors` only *links* alternate credentials to
  an existing id, and nothing breaks if D1 is unreachable (degrades to
  `source: 'derived'`, never throws).
- `notify-worker/index.js` gained `GET /author/:type/:value` (lookup) and
  `POST /author/link` — the Office backend for `office_authors` (same D1,
  same auth). `lib/identity.js` `workerAuthStore()` binds to them, same
  pattern as `notify.js` `workerTransport()`.
- `document.js` **unchanged** — its handoffs already take an opaque
  identity string in `by`. Module 6 calls `resolveAuthor()` and passes
  `author_id` into `createDocument` / `fillField` / `sign`.
- Live-verified on the real machine: fingerprint → stable derived id;
  Windows SID (`S-1-5-21-…`) → stable derived id. 36 → **49 tests**.
  Google `sub` decode + device-flow poll covered with mocked fetch (real
  Google needs an OAuth client id; without one the google path is simply
  unavailable and fingerprint/windows still work).
- **Hardening noted:** full JWKS signature verification of the Google
  id_token (currently decode + aud/iss/exp check — sufficient since the
  token comes straight from Google's TLS endpoint in response to our own
  device_code).

**Phase 2, Module 6 — dual-pane UI — CODE COMPLETE, 2026-09-07:**
- `sector2/apps/office/index.html` — the app. Left pane: the document's
  fields (each goes read-only the instant it's filled — the lib enforces
  it, the UI reflects it), counterparty contact, state badge
  (DRAFT/PENDING REVIEW/SIGNED), and the custody-handoff buttons that
  change with state (Hand to client → Client signs / Send back → Verify
  integrity / New change order). Header + footer QR strings shown. Right
  pane: the Claude copilot — suggestions on the document as it's filled,
  auto-refreshed (debounced) on every change.
- `sector2/apps/office/preload.js` — narrow bridge, 12 allow-listed
  `office:*` channels, nothing else. Renderer stays sandboxed
  (contextIsolation on, nodeIntegration off).
- `dashboard/office-launcher.js` — opens the window with that preload;
  `office:*` IPC handlers call the libs in the main process; `office:copilot`
  routes through the dashboard's existing `_runClaudeCli` (subscription,
  no-tools). `dialog` for open/save.
- Wired into the dashboard: `require('./office-launcher').register(...)` in
  `main.js`, `launch-office` in `preload.js`'s allowlist, an **OFFICE**
  button in `button-generator.js`.
- `document.js` unchanged. Verified end-to-end (no Electron needed for the
  logic): whoami → new → fill → overwrite-blocked → hand → sign → QR →
  save/open round-trip → on-disk tamper → verify + notify → change order.
  **50 tests.** Channel names cross-checked identical across
  preload / launcher / html.
- **Not covered by automated tests** (needs a running Electron window): the
  actual render, the contextBridge, and a live copilot call — launch it
  from the dashboard's OFFICE button to exercise those.

**Module 7 — the EASY pass — DONE, 2026-09-07:** autosave (no Save button —
`~/PhoenixOffice/<b58>.office.json`, written on every change); auto-intake
of the *signed* document into the clone pool on sign ("sealed — the local
copy is disposable"); template picker for New (`templates/*.json` —
work-order / invoice / inspection / change-order / blank); reference-pull
("name documents → Phoenix clones them from the pool into a scratch drawer
→ delete freely"); Recent list + path-guarded one-click reopen. 50 → **51
tests.** Security note (separate Office DB): stay shared for now, the
`.office` file is the real security; split to a dedicated DB + token when a
federal contract or real customer data drives it — see `PLAN-modules-3-6.md`.

**Not yet done:** Module 4 (LibreOffice/Frank/Helix wiring — the invisible
format-following). Office is fully usable for the tamper-evident-record
purpose without it. Plan: `PLAN-modules-3-6.md`.

**Phase 2 — dual-pane UI:** the ScriptForge-style single-file HTML app,
wired into the dashboard the same way (own Electron window, sandboxed).
Left pane = form fields, right pane = Claude's live suggestions.

**Phase 3 — Google/Windows sign-in options, D1-backed author identity
table, Cloudflare Email Workers wiring for real delivery.**

Not attempting all three phases in one pass — Phase 1 gets built now,
for real, tested. Phases 2-3 come after Phase 1 is solid.
