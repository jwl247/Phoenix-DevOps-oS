# office-notify-worker

Phoenix Office **Module 3** — the standalone alteration-attempt notification
path. When a SIGNED `.office` document is tampered with, the counterparty
(who has no Phoenix account and no Life First) gets notified, and keeps
being notified until they acknowledge.

Split out as its own worker on purpose: it must keep working with **zero
Phoenix machine running**, so the protection never depends on the author's
box. It does not touch `packages-worker` or `phoenix-clonepool-r2`.

---

## Routes

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET  | `/health` | none | worker + binding + active-transport status |
| GET  | `/whoami` | `Bearer PHOENIX_AUTH` | auth round-trip, no side effects (drift check) |
| POST | `/notify` | `Bearer PHOENIX_AUTH` | create + send a notification, start the escalation clock |
| GET  | `/ack/:token` | the token itself | counterparty acknowledges → escalation stops |

`POST /notify` body:

```json
{
  "doc_hex": "<file-format.js documentIdentityHash(doc)>",
  "notice":  { "to": "...", "via": "sms-gateway|email", "subject": "...", "body": "...", "doc_hash": {...}, "field": "total", "detected_at": "..." }
}
```

`notice` is exactly `notify.js` `buildAlterationNotice()` output. The Phoenix
side builds it (it has the carrier gateway table, the document); the worker
only sends, escalates, and logs. `lib/tamper-guard.js` `checkAndAlert()` is
the normal caller — it computes `doc_hex`, builds the notice, and POSTs here.

## Escalation

`scheduled()` runs on `* * * * *` (Cloudflare cron minimum is 1 minute —
DESIGN.md / Life First Module 6 specify 30s; **this is the one deviation**,
noted on purpose). Each run re-sends every unacknowledged notification whose
last send is >45s old, escalating the subject line (`REMINDER:` →
`SECOND REMINDER:` → `URGENT:` → `URGENT — PLEASE RESPOND:`), level capped at
5, then it keeps re-sending at level 5 until the ack link is hit.

Every send (initial and escalation) is one append-only row update in
`office_notifications` (`sector2/apps/office/schema.sql`) — the audit trail
that the attempt happened *and* the counterparty was told.

---

## Transport — read this

DESIGN.md said "Cloudflare Email Workers." That is not actually a free
arbitrary-recipient send path:

- **Cloudflare Email Routing `send_email` binding** only delivers to
  **verified** destination addresses — fine for a copy to the issuer,
  useless for reaching an arbitrary customer's phone/email.
- **MailChannels** (the old free Workers email path) ended its free
  Cloudflare offering in 2024.

So the working transport is **Resend** (`resend.com`, free tier 100/day /
3000/month, one `fetch` call, no SDK). It's a small dependency but a real
one, and the alternative is AWS SES — which is exactly the single-cloud-
vendor lock-in CLAUDE.md rejects. Resend does one thing (transactional
send) and is swappable: the worker's `sendNotice()` is the only place that
knows the provider.

The `send_email` binding path is still coded (`ISSUER_COPY` binding, hand-
rolled MIME, zero extra deps) for the verified-recipient / issuer-copy case.

---

## Deploy (needs Jerry's Cloudflare auth)

```bash
cd sector2/apps/office

# 1. schema — adds office_notifications to phoenix_dev_db
wrangler d1 execute phoenix_dev_db --file=schema.sql --remote

cd notify-worker

# 2. secrets
wrangler secret put PHOENIX_AUTH      # MUST match the value packages-worker / phoenix-clonepool-r2 use
wrangler secret put RESEND_API_KEY    # from resend.com — the working send transport
# optional:
# wrangler secret put NOTIFY_FROM     # e.g. "Phoenix Office <office@authenticcoder.com>" — domain must be verified in Resend

# 3. deploy (registers the worker AND the cron trigger)
wrangler deploy

# 4. verify
curl -s https://office-notify-worker.phoenix-jwl.workers.dev/health
curl -s -H "Authorization: Bearer $PHOENIX_AUTH" https://office-notify-worker.phoenix-jwl.workers.dev/whoami
```

`wrangler deploy --dry-run --outdir=/tmp/x` validates config + bundle
without deploying (already passing as of 2026-09-07).

## Live end-to-end test (Jerry)

1. Verify a sending domain in Resend (or use their `onboarding@resend.dev`
   sandbox to your own address).
2. In a Node REPL in `sector2/apps/office`:
   ```js
   const doc = require('./lib/document');
   const { checkAndAlert } = require('./lib/tamper-guard');
   let d = doc.createDocument({ fieldNames: ['total'], authorFingerprint: 'A',
     counterparty: { email: '<your email>' } });        // or { phone, carrier }
   d = doc.fillField(d, 'total', '150', 'A').document;
   d = doc.handToClient(d); d = doc.sign(d, 'C');
   d.fields.total = '999';                               // tamper
   await checkAndAlert(d, {
     notifyWorkerUrl: 'https://office-notify-worker.phoenix-jwl.workers.dev',
     phoenixAuth: process.env.PHOENIX_AUTH,
     attempt: { field: 'total' },
   });
   ```
3. Confirm: the email/SMS arrives; `wrangler tail` shows the cron re-sending
   ~1/min with escalating subjects; hitting the ack link stops it and
   stamps `acknowledged_at` (`wrangler d1 execute phoenix_dev_db --remote
   --command "SELECT * FROM office_notifications ORDER BY id DESC LIMIT 3"`).
