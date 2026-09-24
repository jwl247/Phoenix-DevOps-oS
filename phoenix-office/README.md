# Phoenix Office

Tamper-evident work orders, invoices, inspections, and change orders. Fields
lock the instant they're filled. Once signed, a document is permanently
immutable — any later edit to the file on disk is detected and the
counterparty is notified automatically, repeatedly, until they acknowledge.

**This is a standalone product. It does not require Phoenix DevOps OS to be
installed.** Run it, sign in with your machine's own hardware identity (or
Windows/Google sign-in), pick a template, and go.

## Relationship to Phoenix DevOps OS

This folder is a **sister**, cloned out of `sector2/apps/office/` on
2026-09-22 — not a rename, not a repointed copy. Phoenix's own dashboard,
`packages-worker`, `office-notify-worker`, and `phoenix_dev_db` are
completely unaffected by anything here; nothing in this folder calls
`intake.sh` or shares Phoenix's auth token. See `worker/README.md` for why
that split matters (short version: a legal document needs a different
identity/storage model than a source-code file, and an external product
can't ship with Phoenix's own internal credentials baked in).

The document engine itself — `lib/document.js`, `lib/file-format.js`,
`lib/notify.js`, `lib/identity.js`, `lib/tamper-guard.js` — is a
byte-identical copy. Those libraries never had any Phoenix-pipeline coupling
in the first place (a document's identity is its own content hash, not a
filename), so nothing needed to change to make them portable. The 53-test
suite that already existed for them passes here unmodified.

## Run it

```
npm install
npm start
```

## Structure

```
main.js           Electron main process — window, IPC handlers, local autosave
preload.js         sandboxed renderer bridge
index.html          the app itself — dual-pane UI
lib/                 document engine — document.js/file-format.js/notify.js/
                     identity.js/tamper-guard.js are byte-identical clones of
                     sector2/apps/office/lib/; libreoffice.js + document-html.js
                     are new, standalone-only (PDF export)
templates/           work-order / invoice / inspection / change-order / blank
worker/              this product's own Cloudflare Worker — see worker/README.md
test/test.js         the 53-test engine suite (unchanged from Office)
```

## What's different from the Phoenix dashboard's Office button

- **Its own backend.** `worker/` is a separate Cloudflare Worker with its
  own D1 database, R2 bucket, and auth secret — not Phoenix's shared
  `phoenix_dev_db`/`PHOENIX_AUTH`.
- **Documents are content-addressed, not filename-addressed.** Signing a
  document PUTs it to the worker keyed by its own identity hash, never by
  filename — so two different people's `invoice.json` can never collide,
  and there's no 4-day tiering/eviction (these are permanent records).
- **Pull/browse is against this product's own store, not the clone pool.**
  "Browse sealed documents" lists what's been signed before (`GET
  /documents`); pulling one down (`office:reference`) writes it into a local
  scratch dir for reference or to keep working from. There's no reliance on
  Phoenix's clone pool anywhere in this path.
- **Version history is real, not just designed.** A change order's
  `supersedes_hex` chain is walkable end to end (`office:history` /
  `GET /documents/:hex/history`) — the original and every correction that
  followed it, in order, from either end of the chain.
- **A restricted "Secretariat" pane that can also compose.** UI label is
  "Secretariat," not "Copilot" — deliberately, to avoid any confusion with
  Microsoft/GitHub Copilot; it's Claude-powered, zero Microsoft dependency
  (channel names `office:copilot`/`office:compose` are just internal wiring,
  unchanged for stability). Gives standing suggestions; `office:compose`
  drafts one field's value on request (a "✨" button next to any empty
  field) — the author reviews/edits before it's committed, since fields are
  still fill-once. Both run a read-only, no-tool `claude --print` call — no
  filesystem/tool access, since this app runs on other people's computers,
  not just Jerry's. Entirely optional: nothing else in the app depends on
  it, and it degrades to a clear "offline" message if `claude` isn't found.
- **A tool-using Secretariat agent, additive to the pane above.** "Ask
  Secretariat" (new, next to the original Suggestions box, which is
  untouched) can actually act — start a document, draft/fill fields,
  search this product's own sealed documents, hand off, sign, export — not
  just suggest. It acts ONLY through a fixed, declared tool catalog
  (`lib/agent-tools.js`); the model is never given a shell or filesystem
  access. Two permission tiers: 'base' tools run immediately (search,
  draft, fill, export); 'deviation' tools (hand-off, sign — anything that
  leaves the local draft) show an inline confirm card with the exact
  tool+args and wait for an explicit Approve/Deny. Offline-first on
  purpose (`lib/ai-provider.js`): local Ollama is tried before any API
  key, since these are often confidential business records that shouldn't
  need to leave the machine by default; the restricted Claude CLI is a
  dev-only last resort (not installed on the machines this app ships to).
  A CSS-only "KITT bar" (`.kitt-bar`) shows idle/thinking/acting/confirm
  at a glance. Search results render into the same DB-backed workspace
  pane the "Browse sealed documents" button uses — one shared function,
  one source of truth, not a separate results list buried in chat.
  Code-complete and unit-tested (`test/test-agent.js`, 25 passing) as of
  2026-09-22 — **not yet live-tested against a running Ollama or a real
  multi-step document conversation.** See `project_phoenix_office_secretary_agent`
  in Claude's memory for the full build log.
- **Real PDF export, no Phoenix dependency.** `office:export-pdf` renders
  the document to HTML and shells a real LibreOffice headless conversion.
  "Library" pattern, not "universal kernel": it looks for an already-
  installed LibreOffice first; if none is found, it fetches this product's
  own portable copy from its own worker (`GET /runtime/libreoffice-portable-
  win64.zip`, ~300MB, one time, cached in `userData` after) and extracts it.
  Either way, conversion itself is a local subprocess call — never a
  dependency on Phoenix's kernel, Debian VM, or `phoenix-unoserver.service`
  being up. (Windows only for now — the runtime asset is a Windows portable
  build; other platforms need LibreOffice installed manually until a
  mac/Linux asset is uploaded too.)
- **General file conversion, not just Office's own documents.** The "Convert
  a file…" picker in the header moves ANY file into a different process's
  format — pdf/docx/odt/rtf/txt/html/xlsx/ods/csv/pptx/odp/png
  (`lib/libreoffice.js`'s `convertFile()`, `office:convert` IPC channel).
  Same local-first/R2-fallback resolution as PDF export. Live-verified: a
  real Word-compatible `.rtf` converted to both `.html` (what a design tool
  would import) and `.odt`, content intact in both.
- **Legal hold, 2026-09-23.** Modeled on Microsoft 365's eDiscovery hold: a
  sealed document can be flagged as under legal hold, tied to a matter/case
  reference, with a real append-only audit trail (`office_legal_holds` —
  who placed/released it, when, why) separate from the denormalized
  current-status flag on `office_documents`. A worth-knowing honest point:
  sealed documents were already permanent before this — nothing in the
  worker has ever had a delete/purge route — so a hold's real job is the
  compliance flag, audit trail, and discovery-response report
  (`GET /legal-holds`), not blocking a deletion path that doesn't exist.
  "⚖ Legal hold…" button on any signed document; "⚖ Legal holds" in the
  workspace pane lists everything currently held. Backend fully tested
  (8 new worker tests, 30/30 passing); needs the schema migration applied
  and the worker redeployed before it's live (see `worker/schema.sql`'s
  migration block).
- **eIDAS/ESIGN-hardened signing, 2026-09-23.** Sign and Legal-hold-place
  now require a **Google-verified identity**, not the fingerprint-based one
  used everywhere else — a hardware fingerprint identifies a *machine*, and
  eIDAS Article 26 (the EU's Advanced Electronic Signature standard, AdES)
  requires identifying the actual *signatory*. Device-code OAuth flow (no
  embedded browser — a short code shown in-app, entered at
  `google.com/device` in the user's own browser), wired end to end
  (`office:google-signin-start/poll/cancel`, `lib/identity.js`'s
  already-tested Google functions, never previously wired to any UI).
  Signing also now shows explicit ESIGN Act / UETA consent-and-intent
  language (conduct electronically + affirmative intent to sign,
  spelled out, not implied by a button click) before the existing
  hash-lock/tamper-guard fires — that lock already satisfies AdES's other
  three Article 26 requirements (uniquely linked, sole control, tamper-
  detectable), so this closes the one gap.
  **Real, permanent limitation, not a gap to close:** the EU's highest
  tier, QES (Qualified Electronic Signature — the only one with automatic
  legal parity with a handwritten signature across all 27 member states)
  *requires* a government-licensed EU Qualified Trust Service Provider and
  certified signature hardware. No self-sovereign system can ever reach
  QES; it's a hard regulatory wall, not an engineering one. AdES is the
  real, honest ceiling here, and AdES already has strong legal standing on
  its own.
  **Not yet done: requires a real Google Cloud OAuth client** — same class
  of external dependency as the still-pending `RESEND_API_KEY`. In Google
  Cloud Console, create an OAuth client ID with **Application type: "TVs
  and Limited Input devices"** — that's the specific type Google requires
  for the device-code flow (confirmed via Google's own docs 2026-09-23;
  "Desktop app" is the wrong type and won't support this grant). Set
  `PHOENIX_OFFICE_GOOGLE_CLIENT_ID` / `PHOENIX_OFFICE_GOOGLE_CLIENT_SECRET`
  from it before this can actually complete a sign-in — until then,
  Sign/Legal-hold will correctly report "Google sign-in is not configured"
  rather than silently failing.

## Status

Code-complete, 83 tests passing (53 engine + 30 Secretariat-agent). Deployed
and live-verified end to end: real sign→seal→fetch round-trip, a real
2-link change-order history chain, browse+pull, a real AI-composed field
value, and a real LibreOffice-converted PDF (57KB, valid PDF 1.7).

**Packaged as a real installer, 2026-09-23** — `electron-builder`'s config
was missing entirely (`electron` was even listed under `dependencies`
instead of `devDependencies`, which electron-builder correctly refuses to
build with). Fixed both; `npm run build-win` now produces a real NSIS
installer (`Phoenix Office Setup 1.0.0.exe`) and a portable exe
(`Phoenix Office 1.0.0.exe`), ~77MB each, verified to actually build (not
just configured). App icon (`build/icon.png`, 1024x1024) is a real center
crop of the phoenix bird art via a one-off script
(`scripts/build-icon.js`, uses Electron's own `nativeImage` — no external
image tool needed); electron-builder auto-generates `.ico`/`.icns` from it.
mac/Linux builds are configured (`dmg`/`AppImage`) but unexercised — only
tested on Windows so far.

**Restyled to match LibreOffice's actual visual language, 2026-09-23** —
was a near-black dev-dashboard theme (`#0a0c10` background, neon blue
accent); now a light office-suite theme matched against a real LibreOffice
26.8 (Colibre theme) screenshot: white/light-gray chrome, muted functional
accent colors instead of one hero color, the document panel rendered as a
white "page" on a gray canvas (echoing how LibreOffice itself renders a
page). The DRAFT/PENDING_REVIEW/SIGNED badge is now a subtly-tilted
bordered mark — a restrained nod to a physical document stamp, the one
deliberate visual flourish, everything else kept quiet. Live-verified by
launching the app and screenshotting it next to a real LibreOffice Writer
window — genuinely reads as belonging alongside it now.

`RESEND_API_KEY` still needed for real tamper-notification delivery — see
`worker/README.md`.
