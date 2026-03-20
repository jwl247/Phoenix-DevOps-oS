# Sector 2 — Services / Buffer / Backup

Path: `/etc/systemd/`

Main service layer. `intent_parser.py` sits at the top — nothing reaches the OS without going through it first.

## Files

| File | Role |
|------|------|
| `intent_parser.py` | Universal OS-agnostic service bus. All app intents route here before hitting OS primitives. |
| `propagator.py` | dispatch.json router. Targets: SQLite, D1, Frank3, vault, peer, windows, docworker. |
| `mega_system_manager.py` | Unified: pagefile/swap + port guardian + threat detection + web dashboard port 8888. Runs as root. |

## Life First Suite

`lifefirst/` — full Life First AI application for JW and Laurie.

```
lifefirst/
  ai/        PHP modules
  sql/       MySQL schemas
  install/   Setup scripts
  docs/      Module documentation
```

### Modules

| Module | File | Role |
|--------|------|------|
| 1 | `sql/module_1_database.sql` | Base schema — users, schedule, messages, memory, notifications, voice |
| 2 | `ai/api_router.php` | API router, intent detection, module routing |
| 3 | `ai/ai_schedule.php` | Calendar AI, conflict detection — shares tables with Phoenix scheduler |
| 4 | `ai/ai_messenger.php` | Cross-phone messaging, Laurie integration |
| 6 | `ai/ai_notifications.php` | Must-answer enforcer, 5-level escalation |
| 8 | `ai/budget_keeper.php` | 5-level accountability, bill reminders, real-time purchase checking |
| 9 | `ai/secure_settings.php` | Fort Knox — GPS + Bluetooth + WiFi + voice + photo + movement |

Modules 5 (Memory AI) and 7 (Voice AI) not yet built.

## Systemd Units

```
phoenix-intent-parser.service    top of S2, after frank-helix
phoenix-propagator.service       after intent-parser
phoenix-mega-security.service    after intent-parser, runs as root
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
