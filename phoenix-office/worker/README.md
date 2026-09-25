# phoenix-office-worker

The backend for the standalone Phoenix Office product. Cloned from
`sector2/apps/office/notify-worker/` (2026-09-22), extended with document
storage, and pointed at its own everything — own worker name, own D1
database, own R2 bucket, own auth secret. Deploying this never touches
Phoenix's own `office-notify-worker`, `packages-worker`, or `phoenix_dev_db`.

## Why a separate worker instead of reusing Phoenix's

Two reasons, both load-bearing:

1. **Documents aren't code.** Phoenix's clone pool (`sector2/package-handler`)
   identifies files by `to_hex(basename)` — the filename — with 4-day tier
   rotation/eviction tuned for a fast local dev cache. That's wrong for a
   legal record: two different customers' `invoice.json` would collide, and
   a signed work order is not something you want evicted. This worker's
   `/documents/:hex` route is keyed by the document's *own* content-identity
   hash instead (already computed by `lib/file-format.js`'s
   `documentIdentityHash`) — collision is a non-issue by construction, and
   there's no eviction at all.
2. **This product ships to people who don't run Phoenix.** Giving every
   install Phoenix's own `PHOENIX_AUTH`/Cloudflare Access service token
   would mean anyone who decompiled the app got write access to Phoenix's
   entire clone pool, not just their own documents. This worker has its own
   `OFFICE_AUTH` secret, generated fresh, trusted by nothing else.

## Deploy (first time)

```
wrangler login
wrangler d1 create phoenix_office_db
# paste the returned database_id into wrangler.jsonc's d1_databases[0].database_id
wrangler d1 execute phoenix_office_db --file=schema.sql --remote
wrangler r2 bucket create phoenix-office-documents
wrangler secret put OFFICE_AUTH        # generate fresh, e.g. `openssl rand -hex 32`
wrangler secret put RESEND_API_KEY     # resend.com, free tier 100/day
wrangler deploy
```

## Routes

Same notify/ack/author routes as `office-notify-worker` (see that worker's
README for the escalation/transport design — unchanged here), plus:

- `PUT /documents/:hex` (Bearer `OFFICE_AUTH`) — store a signed `.office`
  file's raw bytes in R2 under `hex`. Best-effort custody row into
  `office_documents` if the body parses as a real document envelope; the R2
  write is what actually matters — the D1 row is a reference, not the
  source of truth (same principle as the rest of Office's design).
  **Write-once (2026-09-25):** re-PUT of identical bytes is a no-op
  (`already:true`); different bytes under an existing hex get **409**.
- Ack links: `GET /ack/:token` only shows a confirm page; the button's
  `POST /ack/:token` records the acknowledgement (link-preview bots GET every
  URL). Escalation backs off per level and stops after 12 sends. `HEAD
  /runtime/:name` now needs the bearer too.
- `GET /documents/:hex` (Bearer `OFFICE_AUTH`) — fetch the bytes back.
- `GET /documents` (Bearer `OFFICE_AUTH`) — browse recent documents, newest
  first. `?limit=30&state=SIGNED` to narrow. Powers the app's "Browse sealed
  documents" pull-in feature.
- `GET /documents/:hex/history` (Bearer `OFFICE_AUTH`) — the full
  `supersedes_hex` chain (original + every change order), oldest first.
  Empty array (not an error) if the hex was never sealed.
- `POST /documents/:hex/legal-hold` (Bearer `OFFICE_AUTH`, body `{by, reason}`)
  — place a legal hold on a sealed document. 404 if the hex was never
  sealed (nothing to hold). `reason` doubles as the legal matter/case
  reference, modeled on Microsoft 365's eDiscovery hold.
- `POST /documents/:hex/legal-hold/release` (Bearer, body `{by, reason?}`)
  — release it.
- `GET /documents/:hex/legal-hold` (Bearer) — the full place/release audit
  trail for one document (`office_legal_holds`), not just current status.
- `GET /legal-holds` (Bearer) — every document currently on hold, for a
  real discovery/subpoena response. Sealed documents already have no
  delete/purge path at all, so a hold's actual job here is the compliance
  flag + audit trail + this report, not blocking a deletion that was never
  possible in the first place.
- `GET /runtime/:name` (Bearer `OFFICE_AUTH`) — fetch a shared runtime asset
  from the `OFFICE_RUNTIME` bucket (e.g. the portable LibreOffice zip). Name
  must match `^[a-zA-Z0-9._-]+$` — no slashes, so it can't address anything
  outside a flat namespace.
- `HEAD /runtime/:name` (no auth) — size/existence check without downloading.

**Uploading a runtime asset** happens out-of-band, not through this worker
(no PUT route for `/runtime/` — these are large, infrequent, admin-only
uploads): `wrangler r2 object put phoenix-office-runtime/<name> --file=<path>
--remote`.

## Live state (2026-09-22)

Deployed. `phoenix_office_db` (3 tables), `phoenix-office-documents`,
`phoenix-office-runtime` (holds `libreoffice-portable-win64.zip`, ~300MB) all
live and bound. `OFFICE_AUTH` set. `RESEND_API_KEY` **not yet set** —
`/health` will show `transport: NONE` until it is; everything else works,
notifications just won't send.

## Live test

```
curl https://phoenix-office-worker.phoenix-jwl.workers.dev/health
# -> { "status": "ok", "worker": "phoenix-office-worker", "db_bound": true, "r2_bound": true, ... }
```

Then run the app (`npm start` in `phoenix-office/`), sign a document, and
confirm `office:sign`'s `sealed.ok` comes back `true` — the document is now
in R2 under its own hash, retrievable from any machine with the same
`OFFICE_AUTH`.
