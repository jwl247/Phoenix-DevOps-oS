# Life First — Laurie's AI system

> **This README was completely rewritten 2026-09-24.** The previous version
> described a plan from before the system was ever deployed — it claimed
> Modules 5 and 7 didn't exist yet (they do — `module_5_ai_memory.php`,
> `module_7_voice_ai.php` are both on disk and deployed), and it documented
> `lifefirst_setup.sh` + `deploy_modules.sh`/`deploy_lifefirst.sh` as the way
> to install this. **Those three scripts are deprecated** — still on disk for
> history, but superseded by `install.sh` (see its own header comment: "Replaces
> lifefirst_setup.sh + deploy_lifefirst.sh"). Everything below reflects what's
> actually here and actually deployed, verified against `install.sh` and the
> real directory listing, not the old plan.
>
> **Note on scope:** the root `CLAUDE.md`'s SESSION PROTOCOL section calls this
> PHP tree "a retired fossil... never run its setup/deploy scripts" (dated
> 2026-08-19) and says the real Life First backend is the `lifefirst-mcp`
> Cloudflare Worker. That note predates `install.sh` (built 2026-09-04) and
> this system's actual live deployment at `lifefirst.authenticcoder.com` — it
> looks stale, not this README. Worth reconciling in `CLAUDE.md` directly;
> not resolved here since that's a bigger call than a README fix.

## What this is

Laurie's own AI system — schedule checking, cross-phone/cross-person
messaging, escalating notifications, memory/preferences, and a voice/general
conversation fallback — backed by a real MySQL/MariaDB database and served
over Apache + PHP. **Deployed and live** on Phoenix's Debian VM, publicly
reachable at `https://lifefirst.authenticcoder.com` (`/laurie/` is Laurie's
own zero-install front door — see `laurie/`).

Modules on disk (all 7 exist, all deployed by `install.sh`):

| Module | File | What it does |
|---|---|---|
| 1 | `module_1_database.sql` | Schema — users (you + laurie), schedule, messages, notifications |
| 2 | `module_2_api_router.php` | Single entry point (`api.php` once deployed) — routes by `action` |
| 3 | `module_3_schedule_ai.php` | Schedule AI — availability, conflicts, "am I free at 3pm" |
| 4 | `module_4_messenger_ai.php` | Cross-phone messaging — "ask Laurie about pickles" |
| 5 | `module_5_ai_memory.php` | Memory/preferences — "what does Laurie like" |
| 6 | `module_6_notification_ai.php` | Escalating notifications (5 levels, 30s re-escalation) |
| 7 | `module_7_voice_ai.php` | General conversation / voice-command fallback |

Also here: `secure_settings.php` + `secure_settings_schema.sql` (settings
storage), `budget_keeper.php` + `budget_keeper_schema.sql` (a separate budget
feature — see `README_BUDGET_KEEPER.md`), `laurie/` (her zero-install web
front door), `meds-worker/` (a separate Cloudflare Worker — Laurie's
medication guardrail; code-complete and tested, **not yet deployed** — see
`meds-worker/README.md`), `security/` (a duplicate/older copy of some of the
above — verify which is current before editing blind).

## Installing / deploying

**Use `install.sh`. Nothing else.** `lifefirst_setup.sh`, `deploy_modules.sh`,
and `deploy_lifefirst.sh` are all deprecated (hardcoded secrets, two
overlapping scripts, Ubuntu-only) — don't run them.

```bash
# On the target Debian or Ubuntu box (Phoenix's Debian VM: usys run debian), as root:
sudo bash install.sh
```

What it actually does (read directly from the script, not assumed):
1. Installs Apache, MariaDB, PHP 8 + extensions (idempotent — skips if already present)
2. **Generates real random secrets on first run, never regenerates them on a
   re-run** — no hardcoded passwords anywhere, unlike the old scripts
3. Creates the `lifefirst` database + schema (seed users: you + laurie) —
   safe to re-run, won't duplicate seed users on a second pass
4. Deploys all 7 modules + `api.php` + `secure_settings.php` to
   `/var/www/html/lifefirst/`
5. Writes `/etc/lifefirst/lifefirst.env` (mode 600, root-only) + an Apache vhost
6. Installs `lifefirst-escalator.service` (systemd) — a 30-second loop that
   actually calls module 6's `escalate` action (this infrastructure didn't
   exist before `install.sh` — module 6 had the escalation logic but nothing
   was ever calling it on a timer)
7. Prints the local/network test URLs and the next step (Cloudflare Tunnel)

**Safe to re-run** — `git pull && sudo bash install.sh` is the documented way
to update. It never touches an existing secret and never re-runs the seed-user
insert.

### After install: expose it off-LAN (Cloudflare Tunnel)

Printed by `install.sh` itself at the end of a run:
```bash
cloudflared tunnel login
cloudflared tunnel create lifefirst
cloudflared tunnel route dns lifefirst <your-hostname>
cloudflared tunnel run --url http://localhost:80 lifefirst
```
For a persistent deployment, install this as a systemd service too (a bare
foreground `cloudflared tunnel run` dies with the SSH session) — see how the
live deployment did it: `systemctl enable --now cloudflared`.

## Testing it

```bash
# Health check (no auth)
curl http://localhost/api.php?action=health
# or, once tunneled:
curl https://lifefirst.authenticcoder.com/api.php?action=health

# Laurie's front door
curl http://localhost/laurie/          # or the public URL

# A real authenticated request — LF_API_SECRET is in /etc/lifefirst/lifefirst.env
curl -X POST http://localhost/api.php \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $LF_API_SECRET" \
  -d '{"username": "you", "message": "Am I free at 3pm today?", "action": "query"}'
```

The old README's example used a raw `Authorization: your_secret_token...`
header with no `Bearer` prefix and a hardcoded placeholder secret
(`your_secret_token_change_me_12345`) — that's not how the real deployed
system authenticates; there is no hardcoded secret anymore, `install.sh`
generates a real one into `/etc/lifefirst/lifefirst.env`'s `LF_API_SECRET`.

## Claude API key / AI backend

`module_3_schedule_ai.php`'s `callClaudeAPI` tries **Ollama first**, and only
falls back to the real Claude API if `CLAUDE_API_KEY` is set in
`/etc/lifefirst/lifefirst.env` — if neither is reachable, it degrades to a
plain-English fallback rather than failing. This is different from the old
README's instructions to hand-edit a hardcoded key into 3 separate PHP files;
that pattern is gone — set `CLAUDE_API_KEY` once in `lifefirst.env` instead
(or install Ollama on the VM and skip the key entirely).

## Troubleshooting

```bash
# Apache/DB status
sudo systemctl status apache2 mariadb lifefirst-escalator

# Logs
sudo tail -f /var/log/apache2/lifefirst-error.log

# DB access
mysql -u root -p lifefirst   # password is in /etc/lifefirst/lifefirst.env, not a hardcoded default anymore
```

## See also

- `laurie/README.md` (if present) — her front door
- `meds-worker/README.md` — the medication guardrail worker (separate deploy, not yet live)
- `README_BUDGET_KEEPER.md`, `README_SECURE_SETTINGS.md` — the two other features living in this same directory
- Root `CLAUDE.md`, sector2/CONNECTIONS.md — broader architecture context
