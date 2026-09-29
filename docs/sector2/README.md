# Sector 2 — Services / Buffer / Backup

> **⚠️ Design-intent doc, not verified current — see `docs/README.md`'s status banner.** The
> Life First suite described below (`lifefirst/ai/*.php` on MySQL) is the retired PHP tree —
> per root `CLAUDE.md`, confirmed a fossil 2026-08-19, superseded by `sector2/apps/lifefirst/`
> (real, deployed at lifefirst.authenticcoder.com) and the `lifefirst-mcp` Cloudflare Worker.
> For what's actually live in Sector 2 today, use `sector2/CONNECTIONS.md`.

Path: `/etc/systemd/`

Main service layer. In this design `intent_parser.py` sat at the top — that file is not in this repo (neither the live tree nor `archive/`); nothing live routes through it.

## Files — where they actually are (verified 2026-09-28)

| File named in this design | Today |
|------|------|
| `intent_parser.py`, `mega_system_manager.py` | not in this repo (neither the live tree nor `archive/`) |
| `propagator.py` | `sector2/propagator/propagator.py` + `dispatch.json` |

What Sector 2 actually contains today (`package-handler/` — the live intake pipeline and packages-worker, `frank/`, `ring0/`, `propagator/`, `unitedsys/`, `apps/`) is inventoried in `sector2/CONNECTIONS.md`.

## Life First Suite

The `lifefirst/ai/*.php` + `sql/` tree this section described does not exist. What exists (verified 2026-09-28):

- `sector2/apps/lifefirst/` — the retired PHP module tree (`module_1_database.sql`, `module_2_api_router.php` … `module_7_voice_ai.php`, `budget_keeper.php`) plus its installers. Per root `CLAUDE.md` it is a fossil with hardcoded creds — never run its setup/deploy scripts. Its own guide: `sector2/apps/lifefirst/README.md`.
- `sector2/apps/lifefirst/meds-worker/` — Cloudflare Worker (meds reminders + escalation; not yet deployed per `docs/history/NEXT-SESSION-BACKLOG.md`).
- The real Life First backend is the `lifefirst-mcp` Cloudflare Worker (exposed to Claude as the `mcp__claude_ai_lifefirst-current__*` tools).

## Systemd Units

All six unit files exist in `sector3/services/` (not deployed on the build target — see `docs/README.md`'s banner); the first and third point at scripts that are not in this repo:

```
phoenix-intent-parser.service    top of S2, after frank-helix (intent_parser.py: not in repo)
phoenix-propagator.service       after intent-parser
phoenix-mega-security.service    after intent-parser, runs as root (mega_system_manager.py: not in repo)
phoenix-unoserver.service        LibreOffice UNO daemon port 2003
phoenix-doc-worker.service       shade, hooks A-F, after unoserver
phoenix-scheduler.service        calendar + bill reminders, shares MySQL
```

## Doc Worker Hooks

| Hook | Target |
|------|--------|
| A | Claude API |
| B | Web search |
| C | Auto-suggest |
| D | unoserver port 2003 |
| E | Export / print |
| F | propagator.py relay |
