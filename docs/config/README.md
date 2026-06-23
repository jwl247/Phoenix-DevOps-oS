# Config

Routing rules and environment config for the Phoenix stack.

## Files

| File | Role |
|------|------|
| `dispatch.json` | propagator.py routing rules — targets: vault, sql, d1, frank3, peer, windows, docworker |
| `.env` | Environment variables for all systemd units. Not committed — create on box. |

## .env Template

```zsh
ANTHROPIC_API_KEY=sk-ant-...
CLOUDFLARE_D1_WORKER=https://...
MYSQL_PASSWORD=...
PHOENIX_AUTH_SEED=...
```

## dispatch.json Targets

| Target | Notes |
|--------|-------|
| vault | `/media/jwl247/breach_coms4` |
| sql | `~/.catalog/catalog.db` |
| d1 | Set `worker_url` before enabling |
| frank3 | Flip `frank3: true` in docworker entry to enable |
| docworker | ZMQ port 5558 |
| peer | Disabled until peer OS configured |
| windows | Disabled until Win10 host configured |
