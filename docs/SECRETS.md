# Phoenix / Life First — Secrets

**No secret values are in the repo.** They live in one file, off-repo, on F::

```
F:\Phoenix\Vault\secrets\phoenix-secrets.env      <- real values (owner-only ACL)
F:\Phoenix\Vault\secrets\phoenix-secrets.env.template
F:\Phoenix\Vault\secrets\SECRETS.md               <- the full map + rotation notes
```

If that folder is gone (new machine, lost drive), rebuild from:
- `PHOENIX_AUTH` — Cloudflare worker secrets are write-only (they can't be read
  back), so recover it from the Windows User env var, or rotate fresh with
  `sector2/package-handler/rotate-phoenix-auth.sh`
- everything else — see the recovery table in `F:\Phoenix\Vault\secrets\SECRETS.md`

## Quick reference — what unlocks what

| Secret | Unlocks | Missing? |
|--------|---------|----------|
| `PHOENIX_AUTH` | `packages-worker` (D1 custody + R2 clonepool), `office-notify-worker` (Office M3) | no — in Windows User env + 2 live CF worker secrets. `phoenix-clonepool-r2` (retired 2026-09-21) is **still deployed** with an old, out-of-sync value (verified 2026-09-25: current token → `401`) — delete that worker rather than resync it |
| `CF_ACCESS_CLIENT_ID` / `CF_ACCESS_CLIENT_SECRET` | The `usys-cli` Cloudflare Access service token — required on top of `PHOENIX_AUTH` for anything calling `packages-worker.phoenix-jwl.workers.dev` (Security Gap 1) | no — Windows User env |
| `OFFICE_AUTH` (worker secret) / `PHOENIX_OFFICE_AUTH` (client env var, `phoenix-office/main.js`) | `phoenix-office-worker` (standalone Office product — deliberately *not* `PHOENIX_AUTH`) | CF worker secret + Windows User env. **Not in the vault file** as of 2026-09-25 — add it, since worker secrets can't be read back |
| `RESEND_API_KEY` | Email sending for `office-notify-worker` and `phoenix-office-worker` | no — set on both workers (2026-09-23). Still missing on `pbm-leads-worker` (verification emails record but don't send) |
| `TURNSTILE_SECRET` | `pbm-leads-worker` bot check | no — CF worker secret |
| `MUSTANSWER_ACCESS_TOKEN` | `lifefirst-mustanswer` `/register` + `/sweep` (bespoke — not yet migrated to `PHOENIX_AUTH`, see `docs/compliance/pentest/`) | no — rotated 2026-09-25, in the vault |
| `PHOENIX_MAPTILER_KEY` | Dashboard MAP pane | yes — optional |
| `PHOENIX_OFFICE_GOOGLE_CLIENT_ID` / `_SECRET` | `phoenix-office` "sign in with Google" (device flow — required for Sign / Legal hold) | set as local env vars on this machine (2026-09-23); not needed by the worker |
| `ANTHROPIC_API_KEY` | nothing — we run on the Claude.ai subscription | n/a by design |
| `LF_API_SECRET` | Life First internal API (Debian VM `/etc/lifefirst/lifefirst.env` AND a `lifefirst-mcp` worker secret) | set both places |
| `LIFEFIRST_MCP_ACCESS_TOKEN` | The `lifefirst-mcp` worker's `/mcp` endpoint (static bearer — no OAuth) | in the vault; worker is live, all 5 secrets set — just add the claude.ai connector |

## Rotating PHOENIX_AUTH

Only ever with `sector2/package-handler/rotate-phoenix-auth.sh`. It pushes to both
live legs (`packages-worker`, `office-notify-worker`), verifies each via `/whoami`,
and only then updates the registry. Hand-editing one leg = the 2026-08-21 / 08-22 /
09-21 incidents. (`phoenix-clonepool-r2` was a leg until its 2026-09-21 retirement.)

## Health check

```
# packages-worker's workers.dev hostname is behind Cloudflare Access — send the
# service-token headers too, or you get a 302 to the Access login page.
curl -s -H "Authorization: Bearer $PHOENIX_AUTH" \
  -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET" \
  https://packages-worker.phoenix-jwl.workers.dev/whoami
curl -s -H "Authorization: Bearer $PHOENIX_AUTH" https://office-notify-worker.phoenix-jwl.workers.dev/whoami
```
Two `{"ok":true,...}` = both legs in sync.
