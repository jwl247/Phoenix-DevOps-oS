# Phoenix Office — Modules 3–6 Build Plan
**UnitedSys — United Systems | jwl247**
**Part of:** Phoenix DevOps OS (Sector 2 — Entourage apps)
**Status:** Draft 2026-09-07 — for review. Builds on `DESIGN.md` (spec frozen 2026-09-05) and Phase 1 + Phase 2 Modules 1–2 (done, 27/27 passing).

---

## Ownership & role

Office **stays part of Phoenix DevOps OS, GPL v3** — it is not spun out to the
PBM companies. Jerry, 2026-09-07: *"the project is most likely going to stay
with us just utilized and tested in the companies."*

So the companies are the **proving ground**, not the owner:

| Entity | Relationship to Office |
|---|---|
| **Phoenix DevOps LLC** | owns and maintains Office (this repo, GPL v3) |
| **PBM Enterprises** (Jerry — steel buildings) | real work orders, field inspection forms, change orders, material receipts → the tamper-evident-record use case Office was designed for, exercised for real |
| **PBM Consulting** (Laurie) | **proofs the concept** — validates the whole thing works through real deliverables. **Exists only as a plan right now**, not operating. Laurie owns the whole PBM structure so it can qualify for the federal small-business set-asides she's eligible for (woman-owned / HUBZone / economically disadvantaged / disabled). That certification path is real work with its own timeline — the software must not outrun or distort it. |

**Jerry, 2026-09-07, on scope and pace:**
> *"it needs everything working no demo. consulting will proof the concept —
> not hurry it or sway the path too much."*

Three hard constraints from that:
1. **All four modules, fully working. No demo, no stub, no "good enough for
   now"** — CLAUDE.md rule 10 ("No demos. Real code only.") applies in full.
   Nothing below is optional or deferrable-past-shipping. The build *order*
   can be sequenced for sane engineering; the *scope* is all of it.
2. **Consulting proofs the concept** — i.e. real use is the acceptance test.
   A module isn't done when its unit tests pass, it's done when a real PBM
   document has gone through it end to end.
3. **Consulting does not set the timeline or the architecture.** Commercial
   interest validates the direction; it does not get to rush the build or
   bend `DESIGN.md`. Build it right.

---

## Module 3 — Notification transport (`notify.js` → real send)

**Status 2026-09-07: BUILT — code complete, 36/36 tests, `wrangler deploy
--dry-run` clean. Pending: Jerry's live deploy (Cloudflare secrets + Resend
key) + one real end-to-end SMS test.** Files: `notify-worker/index.js`,
`notify-worker/wrangler.jsonc`, `notify-worker/README.md`,
`lib/tamper-guard.js`, `notify.js` `workerTransport()`, `schema.sql`
`office_notifications`. Runbook in `notify-worker/README.md`.

**Transport reality (found while building):** "Cloudflare Email Workers" as
written in DESIGN.md is *not* a free arbitrary-recipient send path —
`send_email` only reaches verified addresses, and MailChannels ended its
free Workers offering in 2024. Working transport is **Resend** (one `fetch`,
free tier, swappable — `sendNotice()` is the only provider-aware spot). The
`send_email` binding path is still coded for the issuer-copy case. AWS SES
was rejected (single-cloud-vendor lock-in, against CLAUDE.md).

**Cron granularity:** Cloudflare minimum is 1 minute, so the escalation loop
is 60s not Module 6's 30s — the one deviation, noted in code + README.

**Original build spec (as designed):**
1. **New worker `office-notify-worker`** (`sector2/apps/office/notify-worker/`).
   Own worker, own route — *not* folded into `packages-worker` or
   `phoenix-clonepool-r2` (same standing call as the R2 worker split, per
   Jerry). Cloudflare Email Workers for outbound (stays inside the existing
   Cloudflare stack — no new SMTP credential).
   - `POST /notify` — body = the `buildAlterationNotice()` output. Auth:
     `PHOENIX_AUTH` bearer, same as the other two workers; add `GET /whoami`
     for the same drift-check the others have.
   - Sends to `notice.to` (carrier SMS-gateway address or plain email — the
     resolution already happens in `notify.js`).
   - Logs each send to a D1 table `office_notifications` (append-only:
     `doc_hex`, `to`, `via`, `attempt_field`, `sent_at`, `escalation_level`,
     `acknowledged_at`). This is the audit trail that an alteration was
     attempted *and* that the counterparty was told.
2. **Escalation loop** — copy Module 6's *shape* (`MAX_ESCALATION_LEVEL 5`,
   `ESCALATION_INTERVAL_SECONDS 30`, repeat-until-acknowledged), not its
   code or its Life First `users` dependency. Two options for the timer:
   - a Cloudflare **Cron Trigger** on `office-notify-worker` that re-scans
     `office_notifications` for unacknowledged rows and re-sends with a
     louder subject line, or
   - a `scheduled` handler — same idea, simpler. Pick the cron trigger;
     it survives with zero Phoenix machine running (the counterparty
     protection must not depend on the author's box being up).
3. **Acknowledgement** — the notice email/SMS carries a link
   (`office-notify-worker/ack/:token`); hitting it stamps `acknowledged_at`
   and stops escalation. No account needed — the token *is* the auth,
   single-use, per-notification.
4. **Wire `notifyAlterationAttempt()`** into `document.js`'s
   `verifyIntegrity()` failure path — right now tamper detection returns a
   result; it should also fire the notification (fire-and-forget, never
   blocking or throwing into the document op, which `notify.js` already
   guarantees).

**Done when:** someone edits a SIGNED `.office` file on disk for a real PBM
work order, and the customer's phone gets the SMS within a minute, and it
keeps re-sending until they tap the ack link.

**External-cost note:** Email Workers send volume is metered; internal
dogfood volume is trivially within free tier. Carrier SMS gateways are
free but deliverability is carrier-dependent — plain email is the reliable
fallback and should be the default ask on the document.

---

## Module 4 — Document worker (LibreOffice / Frank / Helix)

The heavy one, and the one that makes Office *Office* rather than a form
validator. This is "the Worker" from DESIGN.md — Claude's per-document tool
that follows the user's process and converts formats invisibly.

**Today:** nothing. `phoenix-unoserver.service` exists
(`sector3/services/`), dormant, nothing calls it. `unoserver` = the
LibreOffice UNO daemon; `unoconvert` talks to it.

**Build, in sub-steps (this module can ship partially):**

- **4a — unoserver reachable.** Deploy `phoenix-unoserver.service` on the
  Debian VM (the same box Life First runs on — it already has the
  systemd/target scaffolding). Confirm `unoconvert in.odt out.pdf` works
  against it over `localhost:2003`. Pure infra; no Office code yet.
- **4b — a `worker.js` in `sector2/apps/office/`** that:
  - takes `{ documentState, targetCapability }` and returns the document
    re-rendered into whatever form the current step needs (text → table →
    spreadsheet cell → chart), by shelling `unoconvert` / driving unoserver.
  - runs **on the author's machine / Phoenix box only** — DESIGN.md is
    explicit the author side needs Phoenix running (Frank + Helix +
    LibreOffice). The counterparty side (Module 3) stays Phoenix-free.
  - "Frank imports LibreOffice's modules on demand" = Frank's import method
    (`intake.sh` authority) registers the LibreOffice components Office
    needs as clone-pool entries, so the capability is versioned/custodied
    like everything else, not a hidden system dependency.
- **4c — Helix as the memory layer.** The imported modules run against
  Helix (the double-strand engine) as fast working memory rather than
  spilling to disk — DESIGN.md: *"Helix sits underneath as the fast memory
  layer those imported modules run against."* This is the piece that most
  depends on Helix actually being up (see `[[helix-paging-benchmark-session]]`
  / `[[phoenix-priority-queue]]` — Helix on Debian is itself an open item).
  **If Helix isn't ready, 4b still works** against plain tmpfs — 4c is an
  optimization, not a blocker.
- **4d — autofill.** `worker.js` gains a `resolveField(fieldName, context)`
  that checks: (1) same document, (2) Phoenix D1/glossary, in that order,
  no web. Repeat-customer name/phone from an earlier `office_documents`
  row; part price from the package-handler glossary.

**Done when:** a PBM Enterprises field tech drafts a work order that starts
as notes, needs a line-item table, needs a total — and never once runs a
"convert" or "save as," and the customer's name auto-fills because they're
a repeat.

**Sequencing:** 4a is a ~1-session infra task. 4b is the real work. 4c is a
genuine dependency on Helix-running-on-Debian (`[[phoenix-priority-queue]]`)
— not a reason to skip it, a reason to sequence Module 4 after that Helix
work lands, or to build 4b against tmpfs first and swap Helix in when it's
ready **without declaring Module 4 done until 4c is real**. 4d (autofill)
follows 4b. Module 4 does not depend on Modules 3/5/6.

---

## Module 5 — Pluggable sign-in (`office_authors` → real resolution)

**Status 2026-09-07: BUILT — code complete, 49/49 tests, worker dry-run
clean, live-verified on the real machine (fingerprint + Windows SID both
resolve to stable derived ids).**
- `lib/identity.js` — `resolveAuthor()`, `credentialFor()`, `windowsSid()`,
  `deriveAuthorId()` (deterministic/offline — the sovereign anchor),
  `linkCredential()`, `workerAuthStore()`, and the Google device-flow
  helpers (`googleDeviceCodeStart/Poll`, `googleSubFromIdToken`).
- `notify-worker/index.js` — `GET /author/:type/:value`, `POST /author/link`
  (the Office backend for `office_authors`).
- `document.js` untouched — Module 6 passes `resolveAuthor().author_id` in.
- **Pending:** a real Google OAuth client id (`console.cloud.google.com`,
  "TV & Limited Input" type) to exercise the google path live — optional,
  fingerprint + windows cover the internal case fully. JWKS signature
  verification of the id_token is a noted hardening step.

**Original build spec (as designed):**
1. **`lib/identity.js`** — `resolveAuthor({ preferred }) → { author_id,
   credential_type, credential_value }`. Order of attempt:
   - `fingerprint` — always works, zero network, `machineFingerprint()`.
     This is the only one that must never require the D1 table to exist.
   - `windows` — `whoami /user` → SID (already have `safePowerShell` in
     fingerprint.js). No new sign-in flow.
   - `google` — OAuth device-code flow (no embedded browser needed), stores
     the `sub` claim. Jerry pre-approved Google as *one option*, 2026-09-05.
2. **Credential linking** — `linkCredential(author_id, type, value)` writes
   `office_authors`; `UNIQUE(credential_type, credential_value)` already
   stops one credential attaching to two authors. First credential seen for
   a new person mints a fresh `author_id` (uuid); subsequent ones on the
   same machine/login offer to link.
3. **Where it's used** — every custody handoff in `document.js`
   (`fill` / `handToClient` / `sign`) records *which verified identity*
   did it, into the document's embedded history. That's already the schema
   shape; Module 5 just makes the identity real instead of a passed-in
   string.

**Done when:** Laurie signs a Consulting deliverable on her machine with
her Windows account, Jerry counter-signs on his with a Phoenix fingerprint,
and the `.office` file's history shows both, resolved to two stable
`author_id`s.

**External-cost note:** Google OAuth needs a registered app
(console.cloud.google.com) — free, but it's a Google dependency to set up.
Windows + fingerprint paths have zero external cost and cover the PBM
internal case completely; Google is only for later cross-org convenience.

---

## Module 6 — Dual-pane UI

**Status 2026-09-07: BUILT — code complete, 50 tests, all channel names
cross-checked, end-to-end lifecycle verified without Electron.**
- `sector2/apps/office/index.html` — left = fields (lock on fill) +
  counterparty + state badge + state-aware handoff buttons + QR strings;
  right = Claude copilot (debounced auto-refresh).
- `sector2/apps/office/preload.js` — 12 allow-listed `office:*` channels,
  sandboxed renderer.
- `dashboard/office-launcher.js` — window + `office:*` handlers (call the
  libs in main) + `office:copilot` via the dashboard's `_runClaudeCli`.
- Wired: `main.js` register line, `preload.js` `launch-office`,
  `button-generator.js` **OFFICE** button.
- **Pending:** launch it once from the dashboard to exercise the live
  render / contextBridge / copilot (can't unit-test a running window).

**Original build spec (as designed):**
1. **`sector2/apps/office/index.html`** — single-file app, same shape as
   ScriptForge. Left pane: the document's fields, rendered from
   `document.js` state — each field an input that goes read-only the
   instant it's filled (the field-level immutability is already enforced in
   the lib; the UI just reflects it). State badge (DRAFT / PENDING_REVIEW /
   SIGNED) and the custody-handoff buttons.
2. **Right pane: Claude copilot.** Standing suggestions as the user fills
   fields — "this looks like a work order, add a labor line?", "customer
   phone missing — needed for the tamper-notice path." Same spirit as
   ScriptForge's Fix Panel. Talks to the dashboard's existing Claude chain
   (subscription CLI path), *not* a new backend.
3. **`dashboard/office-launcher.js`** — copy `scriptforge-launcher.js`
   almost verbatim (`launch-office` IPC, own window). Register in `main.js`
   next to the other launchers. Add an `OFFICE` button via
   `button-generator.js` in the right-hand column.
4. **File open/save** — `.office` files via `lib/file-format.js`. Open a
   file → hydrate the panes. Save → `file-format.js` write. The Electron
   window *can* have Node for this (unlike ScriptForge, Office needs
   filesystem + the libs) — but keep the renderer sandboxed and do file IO
   over IPC to `main.js`, never `nodeIntegration` in the pane itself.

**Done when:** you can open Office from the dashboard, fill a work order,
hand it to a client, they sign, and the footer QR appears — all from the
UI, no CLI. And the copilot pane is genuinely wired (real Claude chain),
not a placeholder — "everything working, no demo."

**Depends on:** Modules 1–2 (done), and Module 5 for real identity on the
handoff buttons. Can be built in parallel with Module 4; the panes render
`document.js` state either way, and gain the auto-convert behavior when
Module 4's `worker.js` is in.

---

## Build order

All four ship. This is engineering sequence, not a scope cut — nothing here
is "phase 2 someday."

```
Module 3  (notify transport)   ── self-contained, no Helix/LibreOffice/UI
                                   dependency; it's the protection promise.
                                   Build first, end to end.
      │
Module 5  (identity resolver)  ── small, independent; needed before the
      │                            handoff buttons in Module 6 mean anything.
      │
Module 6  (dual-pane UI)       ── needs 1-2 (done) + 5; build in parallel
      │                            with Module 4, gains auto-convert when 4b lands.
      │
Module 4  (LibreOffice worker) ── 4a infra now; 4b the real engine; 4c holds
                                   until Helix-on-Debian is real, and Module 4
                                   is not "done" until 4c is. Heaviest, last
                                   to fully land — but required.
```

**Recommended first session:** Module 3 end to end (worker + escalation +
ack + wired into `verifyIntegrity`) — self-contained, it's the promise the
whole design is built to keep, zero upstream dependencies.

**Whole-thing "done":** a real PBM Enterprises work order authored in
Module 6's UI, format-followed by Module 4's worker, signed by an identity
Module 5 resolved, and — when someone later tampers with the file — the
customer notified by Module 3's escalation loop. That single end-to-end
run through all four is the acceptance test. Consulting confirms it against
their own real deliverables.

---

## External-cost gates (from DESIGN.md)

- **Security audit** and **legal e-signature review** — DESIGN.md gates
  these "before any real customer use."
- **The line to hold:** internal dogfooding (Enterprises' own field forms,
  Consulting tracking its own deliverables) does not need either gate.
  Both gates land before Office is the **system of record for a binding,
  legally-relied-upon record** — a signed work order Enterprises would
  invoke in a payment dispute, a Consulting SOW a client signs, and
  **anything touching a federal contract** (the set-aside positioning means
  government work is a real target — that raises the bar on both the
  security audit and the e-signature review, likely toward FISMA / NIST
  800-171 territory rather than just commercial e-sign law).
- **This is a reason "no hurry" is right:** shipping the software ahead of
  the compliance/certification path just means it sits waiting. Build it
  correct and complete; the gates run in parallel with the PBM plan, not
  after a rushed build.
- **Open question for Jerry:** does a signed steel-building work order
  between Enterprises and a private customer count as "binding" for the
  gate? It reads that way, which would pull the legal review in before
  Enterprises relies on Office for real customer work.

---

## Open questions

1. ~~**Debian VM vs Windows for the author-side worker (Module 4).**~~
   **Resolved (Jerry, 2026-09-07): "it won't matter because you're
   importing the process."** Frank's import method pulls in whatever
   LibreOffice components the task needs, on whatever box Phoenix is
   running — the worker doesn't care where unoserver lives, it imports the
   capability to wherever it's invoked. So Module 4b is written against
   "Frank imports the process," not "connect to a fixed unoserver host."
   4a (deploy `phoenix-unoserver.service`) still happens so there's a
   daemon to import against; it just isn't a hardcoded network dependency.
2. **Binding-contract gate timing** (above).
3. **Change-order UX** — DESIGN.md nails the data model (new dated
   document, `supersedes_hex`, never edits the original). Module 6 needs a
   real flow for "create a change order from this signed doc" — worth a
   quick sketch before building the UI.
4. **Google OAuth app registration** — do it now (unblocks Module 5c
   whenever), or defer until cross-org sign-in is actually needed? Windows
   + fingerprint cover 100% of the internal PBM case.
5. **Federal-contract target — does it change the design now, or just the
   gates?** If Office documents may end up as records on government work,
   NIST 800-171 / CMMC-style requirements (audit logging, access control,
   crypto module validation) could touch the architecture, not only the
   review step. Worth a read of what the set-aside categories actually
   require of a records system *before* Module 3/5 lock in their D1 tables
   and crypto choices — cheaper to know now than to retrofit. Not a blocker
   to starting Module 3, but flag it before that worker's schema is frozen.
