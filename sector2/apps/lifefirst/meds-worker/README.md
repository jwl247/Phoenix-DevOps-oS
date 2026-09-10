# meds-worker — Laurie's medication guardrail

A once-a-day medication check-in that Laurie can **acknowledge but not turn
off**. Adaptive: the next reminder is anchored to when she last actually took
the dose (`last_dose_at + window_hours`), not a fixed clock time. If a dose
goes unconfirmed it escalates on her phone, then loops Jerry in.

Built for the week Jerry is out of town (leaves **Mon 2026-09-14**). Design
frozen in memory `laurie-medication-guardrail`.

## Why its own worker

Same call as Office's `notify-worker` vs `packages-worker`: the guardrail must
keep reminding her **with zero Phoenix machine running**. It shares the
`lifefirst-db` D1 but owns only three tables (`schema.sql`):
`medication_state`, `medication_log`, `med_alerts`. It does **not** touch
`lifefirst-mcp` (whose source isn't local).

Control lives with Jerry, structurally:
- every delivery channel is one of **Jerry's** accounts (his Pushover app, his
  Resend, his Twilio) — nothing Laurie can reconfigure
- `medication_state.active` is the only on/off switch and it's set via
  `POST /configure` (Bearer `PHOENIX_AUTH`) — not exposed to her
- there is no Laurie login anywhere in this worker

## Routes

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET  | `/health` | none | worker + D1 binding + which transports are configured |
| GET  | `/whoami` | `Bearer PHOENIX_AUTH` | auth round-trip, no side effects (drift check) |
| GET  | `/status?user_id=2` | `Bearer PHOENIX_AUTH` | current state + `ask` flag for the assistant |
| POST | `/configure` | `Bearer PHOENIX_AUTH` | Jerry sets up / adjusts a guardrail |
| POST | `/record-dose` | `Bearer PHOENIX_AUTH` | log a confirmed dose, advance the window, close open cycles |
| GET  | `/ack/:token` | the token itself | Laurie taps the reminder link → dose logged, cycle closed |

`POST /configure` body: `{ user_id, med_label?, window_hours?, grace_minutes?, active? }`
`POST /record-dose` body: `{ user_id, dose_at?, via?, note? }` (`via` ∈ `assistant`|`manual`)

`GET /status` returns `ask: true` when a dose is due (or was never recorded) —
that is the signal for the Life First assistant to open with *"Have you taken
your pills today? When?"* before anything else.

## The cron (`*/5 * * * *`)

Three timestamp-gated passes — the 5-minute interval is just resolution, not
the cadence:

1. **open** — for any `active` guardrail where `now >= next_check_at + grace`
   and no open cycle already exists for that `due_at`: create a `med_alerts`
   row (level 1) and send.
2. **escalate** — any open cycle whose last send is >14 min old: bump the
   escalation level (message gets more insistent, warmer-not-scolding; capped
   at 5), re-send. Pushover goes to emergency priority at level ≥3.
3. **caregiver** — once an open cycle has been unanswered ~55 min, every
   re-send from then on also goes to Jerry (`PUSHOVER_USER_JERRY` /
   `CAREGIVER_EMAIL` / `CAREGIVER_SMS`).

An ack (`/ack/:token`) or a `/record-dose` logs the dose, moves
`next_check_at` forward `window_hours`, and closes **every** open cycle for
that user.

## Channels

`sendPushover` / `sendEmail` / `sendSms` each return `ok` | `skip` | `err:…`
and **never throw** — a dead or unconfigured channel is skipped, the others
still go, the cron never crashes. `med_alerts.channels_last` records the
per-channel outcome of the most recent send as JSON.

- **Pushover** — primary. Emergency priority (retry 15 min / expire 6 h) once
  escalation hits level 3, so Pushover keeps nagging even between cron ticks.
- **Email (Resend)** — backup.
- **SMS (Twilio → GV `405-237-5727`)** — best-effort bonus. US A2P 10DLC
  registration + Google Voice spam filtering make this unreliable near-term;
  don't lean on it.

## Deploy (needs Jerry's Cloudflare auth)

```bash
cd sector2/apps/lifefirst/meds-worker

# 1. schema — adds the 3 medication_* tables to lifefirst-db
wrangler d1 execute lifefirst-db --file=schema.sql --remote

# 2. secrets — PHOENIX_AUTH must match the rest of Phoenix; the rest are the
#    channels (all optional at the code level, Pushover-for-Laurie is the point)
wrangler secret put PHOENIX_AUTH
wrangler secret put PUSHOVER_TOKEN
wrangler secret put PUSHOVER_USER_LAURIE
wrangler secret put PUSHOVER_USER_JERRY
wrangler secret put RESEND_API_KEY
wrangler secret put LAURIE_EMAIL
wrangler secret put CAREGIVER_EMAIL
# bonus SMS:
wrangler secret put TWILIO_ACCOUNT_SID
wrangler secret put TWILIO_AUTH_TOKEN
wrangler secret put TWILIO_FROM
wrangler secret put LAURIE_SMS
wrangler secret put CAREGIVER_SMS

# 3. deploy (registers the worker AND the cron trigger)
wrangler deploy

# 4. turn Laurie's guardrail on
curl -s -X POST https://meds-worker.phoenix-jwl.workers.dev/configure \
  -H "Authorization: Bearer $PHOENIX_AUTH" -H 'Content-Type: application/json' \
  -d '{"user_id":2,"med_label":"your morning pills","window_hours":24}'

# 5. verify
curl -s https://meds-worker.phoenix-jwl.workers.dev/health
curl -s -H "Authorization: Bearer $PHOENIX_AUTH" \
  "https://meds-worker.phoenix-jwl.workers.dev/status?user_id=2"
```

Then add `meds-worker` as a leg in
`sector2/package-handler/rotate-phoenix-auth.sh` so its `PHOENIX_AUTH` never
drifts (the 2026-08 incident class).

`wrangler deploy --dry-run --outdir .dryrun` validates config + bundle without
deploying (passing as of 2026-09-09).

## Live end-to-end test

1. Configure with a short window so a check-in fires fast:
   ```bash
   curl -s -X POST .../configure -H "Authorization: Bearer $PHOENIX_AUTH" \
     -H 'Content-Type: application/json' \
     -d '{"user_id":2,"med_label":"test pills","window_hours":24}'
   ```
   A brand-new guardrail has `next_check_at = now`, so the next cron tick
   (≤5 min) opens a check-in.
2. `wrangler tail` — watch the cron open the cycle and send.
3. Confirm the Pushover / email arrives with an `/ack/<token>` link.
4. Hit the link → the ack page shows, and:
   ```bash
   wrangler d1 execute lifefirst-db --remote --command \
     "SELECT * FROM medication_log ORDER BY id DESC LIMIT 2;
      SELECT id, escalation_level, acknowledged_at, acknowledged_via FROM med_alerts ORDER BY id DESC LIMIT 2;"
   ```
   shows the dose logged and the cycle closed; `next_check_at` has moved ~24 h.
5. Leave a cycle unanswered ~1 h in a staging config to confirm the caregiver
   pass fires to Jerry.

## Assistant wiring (Life First side)

The Life First assistant / `laurie/proxy.php` should, on every open:
`GET /status?user_id=2` → if `ask` is true, the first thing it says is
*"Have you taken your pills today? When?"* → on her answer,
`POST /record-dose {user_id:2, dose_at:<parsed>, via:"assistant"}`.
That path isn't built yet — the worker + cron is the guardrail and stands on
its own; the assistant question is the friendly front.
