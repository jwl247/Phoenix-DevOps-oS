# Phoenix Office — Frank3 Save Layer

Three files. That's the whole save pipeline.

## Files

| File | Role |
|------|------|
| `frank_save.py` | Core logic — pressure check, drive selection, vault write, catalog, D1 fan-out, L2 buffer |
| `frank_http.py` | HTTP bridge on 127.0.0.1:7347 — serves `/status`, `/save`, `/catalog` |
| `frank_client.js` | Browser side — polls status bars, calls save, auto-save debounce, local fallback queue |

## Start Frank

```bash
# Run once, stays resident alongside your stack
python3 frank_http.py &
```

## How Frank decides

```
drive_pressure() on all four breach_coms drives
  < 60%  → write freely to lowest-pressure drive
  60-75% → still write, prefer lighter drive
  75-88% → write but warn in status bar
  > 88%  → buffer in L2 deque, flush thread retries every 2s
  all drives > 88% → buffer everything, no write until one cools
```

## Wire into Phoenix Office worker

```js
import { frankStart, frankSave, frankRenderBars, frankAutoSave } from './frank_client.js';

// start the status bar polling when app opens
frankStart(frankRenderBars);

// on every keystroke in the doc editor
frankAutoSave(docId, title, 'doc', () => editor.value);
```

## Endpoints

```
GET  http://127.0.0.1:7347/status   → drive pressures, tier, buffer count
POST http://127.0.0.1:7347/save     → { doc_id, title, doc_type, content }
GET  http://127.0.0.1:7347/catalog  → last 50 saves from SQLite
```

## What Frank writes

```
/media/jwl247/breach_comsN/VAULT/<doc_type>/<doc_id>/<timestamp>.<ext>
~/.catalog/catalog.db               ← indexed, versioned, queryable
```

Every save is versioned. Roll back any document to any point with:
```bash
ls ~/.catalog/  # see the db
sqlite3 ~/.catalog/catalog.db "SELECT * FROM documents WHERE title LIKE '%Brief%';"
```

## D1 sync

Set `"d1_sync": true` in `dispatch.json` and Frank fans out a summary
to Cloudflare D1 via `propagator.py` after every successful vault write.
Fire-and-forget — never blocks the save.
