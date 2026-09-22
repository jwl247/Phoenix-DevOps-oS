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
- **A restricted "Secretary" pane that can also compose.** UI label is
  "Secretary," not "Copilot" — deliberately, to avoid any confusion with
  Microsoft/GitHub Copilot; it's Claude-powered, zero Microsoft dependency
  (channel names `office:copilot`/`office:compose` are just internal wiring,
  unchanged for stability). Gives standing suggestions; `office:compose`
  drafts one field's value on request (a "✨" button next to any empty
  field) — the author reviews/edits before it's committed, since fields are
  still fill-once. Both run a read-only, no-tool `claude --print` call — no
  filesystem/tool access, since this app runs on other people's computers,
  not just Jerry's. Entirely optional: nothing else in the app depends on
  it, and it degrades to a clear "offline" message if `claude` isn't found.
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

## Status

Code-complete, 74 tests passing (53 engine + 21 worker). Deployed and
live-verified end to end on 2026-09-22: real sign→seal→fetch round-trip,
a real 2-link change-order history chain, browse+pull, a real AI-composed
field value, and a real LibreOffice-converted PDF (57KB, valid PDF 1.7).
Not yet packaged as an installer (`electron-builder` is wired in
`package.json` but unexercised). `RESEND_API_KEY` still needed for real
tamper-notification delivery — see `worker/README.md`.
