# Phoenix / Life First — Secrets

**No secret values are in the repo.** They live in one file, off-repo, on F::

```
F:\Phoenix\Vault\secrets\phoenix-secrets.env      <- real values (owner-only ACL)
F:\Phoenix\Vault\secrets\phoenix-secrets.env.template
F:\Phoenix\Vault\secrets\SECRETS.md               <- the full map + rotation notes
```

If that folder is gone (new machine, lost drive), rebuild from:
- `PHOENIX_AUTH` — recover from any of the three worker secrets, or rotate fresh
  with `sector2/package-handler/rotate-phoenix-auth.sh`
- everything else — see the recovery table in `F:\Phoenix\Vault\secrets\SECRETS.md`

## Quick reference — what unlocks what

| Secret | Unlocks | Missing? |
|--------|---------|----------|
| `PHOENIX_AUTH` (64 hex) | `packages-worker` (D1 custody), `phoenix-clonepool-r2` (R2), `office-notify-worker` (Office M3) | no — in Windows User env + 3 CF worker secrets |
| `RESEND_API_KEY` | Office M3 actually *sending* tamper alerts | **yes — never created.** resend.com free tier. |
| `PHOENIX_MAPTILER_KEY` | Dashboard MAP pane | yes — optional |
| `GOOGLE_OAUTH_CLIENT_ID` | Office "sign in with Google" author path | yes — optional (fingerprint + Windows SID cover internal use) |
| `ANTHROPIC_API_KEY` | nothing — we run on the Claude.ai subscription | n/a by design |
| `LF_API_SECRET` | Life First internal API (Debian VM `/etc/lifefirst/lifefirst.env` AND a `lifefirst-mcp` worker secret) | set both places |
| `LIFEFIRST_MCP_ACCESS_TOKEN` | The `lifefirst-mcp` worker's `/mcp` endpoint (static bearer — no OAuth) | in the vault; worker is live, all 5 secrets set — just add the claude.ai connector |

## Rotating PHOENIX_AUTH

Only ever with `sector2/package-handler/rotate-phoenix-auth.sh`. It pushes to all
three workers, verifies each via `/whoami`, and only then updates the registry.
Hand-editing one leg = the 2026-08-21 / 08-22 incidents.

## Health check

```
for w in packages-worker phoenix-clonepool-r2 office-notify-worker; do
  curl -s -H "Authorization: Bearer $PHOENIX_AUTH" https://$w.phoenix-jwl.workers.dev/whoami
done
```
Three `{"ok":true,...}` = all legs in sync.
