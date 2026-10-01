# phoenix-office — Phoenix Office (standalone sister product)

Written 2026-09-30 from the code in this folder. Verify against current code before trusting a specific line number.

## What it is
Laurie's business tool, shipped to people who do not run Phoenix at all. A desktop app
(Electron) for work orders, invoices, inspections, change orders, proposals, safety plans
and schedules. A field locks the moment it is filled; once a document is signed it is frozen,
and any later edit to the file is detected and the other party is notified until they
acknowledge. It also has Secretariat (an AI helper that acts only through a fixed tool list),
Legal Hold, and Project Assist (projects, phases, PMBOK checklist, bid factors). It has its own
Cloudflare Worker, own D1 database (`phoenix_office_db`), own R2 buckets and own token. It
shares nothing with Phoenix's packages-worker, `phoenix_dev_db` or `PHOENIX_AUTH`, and never
calls `intake.sh`. Signed documents are stored by their own content hash, never by filename.
- `main.js` — the Electron main process: splash then main window, every `office:*` IPC handler, local autosave, sealing signed documents to the worker, browse/pull/history, legal hold, saved jobs, Project Assist, PDF export, file conversion, the read-only Claude CLI "Suggestions" call, and the Secretariat agent session. Reads `PHOENIX_OFFICE_WORKER_URL`, `PHOENIX_OFFICE_AUTH`, `PHOENIX_OFFICE_GOOGLE_CLIENT_ID` / `_SECRET` from the environment at launch.
- `preload.js` — the narrow bridge between the page and `main.js`: only the allow-listed `office:*` channels get through (the page itself has no Node access).
- `index.html` — the whole app UI in one file: dual-pane document view, workspace pane (browse sealed documents, legal holds, saved jobs, projects), Secretariat pane with the KITT bar, signing consent, About page.
- `splash.html` — the branded start-up screen (shows `assets/phoenix-logo.png`).
- `brand.json` — optional letterhead for exported documents (business name, address, logo file). This copy is set to PBM Consulting Service; delete it and exports go out unbranded.
- `brand-logo.svg` — the letterhead logo that `brand.json` points at.
- `assets/phoenix-logo.png` — the phoenix bird art used by the splash screen and as the source for the app icon.
- `build/icon.png` — the 1024x1024 app icon (made from the bird art by `scripts/build-icon.js`); `build/icon.ico` is the Windows icon electron-builder uses.
- `package.json` — npm scripts (start, test, build-win/mac/linux) and the electron-builder installer settings (NSIS installer + portable exe on Windows, output to `dist/`).
- `package-lock.json` — exact versions of Electron and electron-builder.
- `.gitignore` — keeps `node_modules/`, `dist/` and exported PDFs out of git.
- `README.md` — the product's own explanation: how to run, configure and build it, and why it is a separate product from Phoenix.
- `lib/document.js` — the document engine: fill-once fields, the DRAFT → PENDING_REVIEW → SIGNED state machine, content hashes, integrity check, change orders. No network.
- `lib/file-format.js` — saves and loads a document as a `.office` file with header QR (before hashing) and footer QR (after signing), and computes the document's identity hash used as its storage key.
- `lib/hash.js` — SHA3-512 and BLAKE2b-512. Uses Node's own crypto when it has them; falls back to the copied-in noble-hashes code inside Electron, whose crypto lacks both.
- `lib/vendor/noble-hashes/` — a committed copy of @noble/hashes 1.7.1 (MIT, `LICENSE` inside), used by `lib/hash.js`. Not installed by npm on purpose.
- `lib/fingerprint.js` — the machine's hardware fingerprint (same double-hash recipe as Phoenix's `sector1/auth/phoenix_auth.py`, with Windows signals added); memoized so it is only gathered once.
- `lib/identity.js` — who the author is: hardware fingerprint, Windows account, or Google sign-in (device-code flow, no embedded browser), all resolved to one author id.
- `lib/notify.js` — builds the "this signed document was altered" message and works out who to send it to (email, or text through a phone carrier's email gateway); sends through the worker's `/notify` route.
- `lib/tamper-guard.js` — joins the two: checks a signed document and, only if it was altered, sends the notice through `lib/notify.js`.
- `lib/libreoffice.js` — PDF export and general file conversion by running LibreOffice headless. Uses an installed LibreOffice first; the download of a portable copy from the worker is switched off until its SHA-256 is pinned. Also the list of LibreOffice apps the user can launch.
- `lib/document-html.js` — turns a document into the plain printable HTML page LibreOffice converts to PDF (with letterhead and, for a schedule, the chart).
- `lib/brand.js` — reads `brand.json`; a missing or broken file just means no letterhead.
- `lib/schedule-gantt.js` — draws the Master schedule document's `phase_breakdown` field as a schedule chart (one row per trade, green / yellow / red), for both the live view and the PDF.
- `lib/project.js` — Project Assist objects: projects, the standard phase list (based on PMI/PMBOK), phase status. No network; the worker stores them.
- `lib/bid-factors.js` — the one ordered list of bid questions (size, setting, season, labor and so on) shared by the form and the Secretariat's `set_bid_factor` tool.
- `lib/phase-html.js` — turns a finished project phase, with its checklist decisions, into a printable page for PDF.
- `lib/ai-provider.js` — plain text answers for Secretariat, tried in this order: local Ollama, then an Anthropic API key, then the Claude CLI (developer machine only). No tool or file access is ever given to any of them.
- `lib/agent-tools.js` — Secretariat's fixed tool list and tiers. Base (runs at once): search, templates, new document, draft/fill field, export PDF, project tools, checklist search and rationale, print phase. Deviation (needs the user's Approve): hand to client, sign, advance phase, set checklist item, award project.
- `lib/agent-loop.js` — the Secretariat loop: the model must answer with one JSON tool call or a final answer; base tools run, deviation tools wait for the user's decision.
- `templates/blank.json` — empty template; the user names their own fields.
- `templates/work-order.json` — work order fields.
- `templates/invoice.json` — invoice fields.
- `templates/inspection.json` — field inspection fields.
- `templates/change-order.json` — change order fields (points back at the document it corrects).
- `templates/proposal.json` — proposal / bid fields for steel work.
- `templates/safety-plan.json` — site safety plan fields (OSHA 1926 references, fall protection, lift plan).
- `templates/schedule.json` — Master schedule fields; `phase_breakdown` feeds the schedule chart.
- `scripts/fix-electron.js` — runs after every `npm install` and repairs the Electron program if its own installer failed to unpack it.
- `scripts/build-icon.js` — one-off: crops the bird art into `build/icon.png` (run with Electron, not plain node).
- `test/test.js` — engine tests (document, file format, fingerprint, notify, tamper guard, identity, hash).
- `test/test-agent.js` — Secretariat and Project Assist tests (provider, tool list, loop, bid factors, project) with mocked models.
- `worker/index.js` — the product's Cloudflare Worker (`phoenix-office-worker`): `/health`, `/whoami`, `/notify` and `/ack/:token` (tamper notices, re-sent every minute by the cron until acknowledged, sent by email through Resend), `/author/*`, `/jobs`, `/runtime/:name`, `/documents` (write-once store by hash, browse, history chain, legal hold), `/legal-holds`, `/checklist-catalog`, `/projects/*` (phases, checklist items, decisions).
- `worker/wrangler.jsonc` — worker settings: D1 binding `OFFICE_DB` (`phoenix_office_db`), R2 `OFFICE_DOCS` (`phoenix-office-documents`) and `OFFICE_RUNTIME` (`phoenix-office-runtime`), one-minute cron; secrets `OFFICE_AUTH` and `RESEND_API_KEY` are set with wrangler, not in the file.
- `worker/schema.sql` — every D1 table: authors, documents, legal holds, notifications, jobs, projects, phases, checklist catalog, phase checklist items, checklist decisions. Safe to re-run.
- `worker/migrations/001-office-documents-project-columns.sql` — adds project_id / phase_id / doc_role to an older documents table; only for a database made before 2026-09-28 (the live one already has them).
- `worker/seed-checklist-catalog.sql` — the starting checklist catalog (OSHA steel erection and fall protection, Oklahoma licensing, PM practice), one set per phase plus "general". Safe to re-run.
- `worker/test.mjs` — worker tests with a fake D1 and R2, driving the real request handler.
- `worker/package.json` — marks the worker as an ES module.
- `worker/.gitignore` — keeps the 300 MB LibreOffice zip and wrangler's local folder out of git.
- `worker/README.md` — worker routes, first-time deploy steps, why it is separate from Phoenix's workers.

## Dependencies
Node.js and npm; Electron 28 and electron-builder 24 (dev dependencies, installed by
`npm install`). No other npm packages: hashing is the committed noble-hashes copy. Optional at
run time: LibreOffice (PDF export and conversion; Windows only for now), Ollama on
`127.0.0.1:11434` or an Anthropic API key (Secretariat), a Google OAuth client of type "TVs and
Limited Input devices" (Sign and Legal hold). Worker: Cloudflare account, wrangler, D1 and two R2
buckets, a Resend key for real email delivery.

## Commands / entry points
- `cd phoenix-office && npm install` (also runs `scripts/fix-electron.js`).
- `npm start` — run the app.
- `npm test` — runs `node test/test.js` then `node test/test-agent.js`.
- `npm run build-win` — installer and portable exe into `phoenix-office/dist/`.
- `node phoenix-office/worker/test.mjs` — worker tests (47 passing on 2026-09-30).
- `cd phoenix-office/worker && wrangler deploy` — deploy the worker (first-time steps in `worker/README.md`).
- `wrangler d1 execute phoenix_office_db --file=schema.sql --remote` (from `worker/`) — create or update the tables.
- Health: `https://phoenix-office-worker.phoenix-jwl.workers.dev/health` (no token needed).

## Connects to / connected from
- `phoenix-office/index.html` → `phoenix-office/preload.js` (the page can only reach the app through these channels).
- `phoenix-office/preload.js` → `phoenix-office/main.js` (each channel is handled in the main process).
- `phoenix-office/main.js` → `phoenix-office/worker/index.js` (sealing, browse, pull, history, legal hold, saved jobs, author links and all of Project Assist go to this worker over HTTPS with the `PHOENIX_OFFICE_AUTH` token).
- `phoenix-office/lib/tamper-guard.js` → `phoenix-office/worker/index.js` (an altered signed document is reported to the worker's `/notify` route, through `lib/notify.js`).
- `phoenix-office/lib/libreoffice.js` → `phoenix-office/worker/index.js` (would fetch the portable LibreOffice zip from `/runtime/`; switched off until the SHA-256 is pinned).
- `phoenix-office/main.js` → `phoenix-office/lib/agent-loop.js` (runs the Secretariat session).
- `phoenix-office/lib/agent-loop.js` → `phoenix-office/lib/agent-tools.js` (the model can only name tools from this list; `main.js` hands the list to the loop).
- `phoenix-office/lib/agent-tools.js` → `phoenix-office/lib/bid-factors.js` (the `set_bid_factor` tool uses the same question list as the form).
- `phoenix-office/lib/agent-tools.js` → `phoenix-office/lib/schedule-gantt.js` (builds a schedule's trade breakdown from a project timeline).
- `phoenix-office/main.js` → `phoenix-office/lib/ai-provider.js` (Secretariat's text answers: Ollama, then API key, then Claude CLI).
- `phoenix-office/lib/ai-provider.js` → local Ollama (an HTTP call to Ollama on this machine, outside the repo).
- `phoenix-office/lib/document-html.js` → `phoenix-office/lib/brand.js` (letterhead on exported documents).
- `phoenix-office/lib/brand.js` → `phoenix-office/brand.json` (business name, address and logo file).
- `phoenix-office/lib/document-html.js` → `phoenix-office/lib/schedule-gantt.js` (the schedule chart in the PDF).
- `phoenix-office/lib/phase-html.js` → `phoenix-office/lib/document-html.js` (reuses the letterhead).
- `phoenix-office/lib/hash.js` → `phoenix-office/lib/vendor/noble-hashes/sha3.js` (fallback hashing inside Electron).
- `phoenix-office/lib/document.js` → `phoenix-office/lib/fingerprint.js` (default author when no identity is given).
- `phoenix-office/lib/fingerprint.js` → `sector1/auth/phoenix_auth.py` (same fingerprint recipe, copied; no code is called).
- `phoenix-office/lib/document.js` → `sector2/apps/office/lib/document.js` (cloned from Phoenix's internal Office on 2026-09-22; no code is called, and the two have since diverged).
- `phoenix-office/worker/index.js` → `sector2/apps/office/notify-worker/index.js` (cloned from it; the notify/ack/author routes have the same shape; no code is called).
- `phoenix-office/worker/seed-checklist-catalog.sql` → `phoenix-office/lib/project.js` (the catalog's phase ids must match the standard phase list).
- `phoenix-office/worker/schema.sql` → `phoenix-office/worker/index.js` (the tables the worker reads and writes).
- `phoenix-office/worker/test.mjs` → `phoenix-office/worker/index.js` (tests the real handler).
- `phoenix-office/worker/index.js` → Resend email service (tamper notices go out by email when `RESEND_API_KEY` is set; outside the repo).
- `hands/hands.py` → `phoenix-office/main.js` (the hands `open_app office` tool starts Electron in this folder).
- `portal/server.py` → `phoenix-office/worker/index.js` (the Phoenix Console checks the worker's `/health`).
- `scripts/usys.ps1` → `phoenix-office/worker/index.js` (`usys` status checks the worker's `/health`).

## Known issues (verified, not guessed)
- Tamper notices cannot reach anyone until `RESEND_API_KEY` is set on the worker; `/health`
  then shows `transport: NONE` (per `worker/README.md`; not re-checked live today).
- Sign and Legal hold need `PHOENIX_OFFICE_GOOGLE_CLIENT_ID` / `_SECRET`; without them they
  report "Google sign-in is not configured".
- The portable LibreOffice download is off: `RUNTIME_ASSET_SHA256` in `lib/libreoffice.js` is
  empty, so a machine without LibreOffice installed cannot export PDFs.
- PDF export / conversion is Windows-only; `lib/libreoffice.js` refuses other platforms.
- Secretariat's agent has passing unit tests but has not been tried live with a running Ollama
  and a real multi-step document conversation (README).
- Out-of-date wording in the docs, the code is right: the README and the `main.js` header
  say `lib/document.js` is byte-identical to `sector2/apps/office/lib/document.js` — it is not
  (this copy's `sign()` also stores a drawn signature image and email). The README's Structure
  section lists 5 templates; there are 8. `worker/README.md` lists `HEAD /runtime/:name` as
  "no auth" and says the database has 3 tables; the code requires the token and `schema.sql`
  has 10 tables. `worker/wrangler.jsonc` says the database id is "left blank on purpose", but it
  is filled in. README test counts (92; worker "30/30") are older than the current suites.
