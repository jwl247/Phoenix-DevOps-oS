# ⛔ DECOY — DO NOT DEPLOY FROM THIS DIRECTORY

**Canonical deploy path:** `sector2/package-handler/worker/`

This directory (`sector3/workers/packages-worker/`) is an **intentionally bricked** stale copy of packages-worker. It predates the 2026-09-21 Gap 1 security fix — the `/custody`, `/clonepool`, and `/packages` GET routes here have **no auth**. Deploying from here would silently overwrite production and reopen those unprotected routes.

The `wrangler.jsonc` in this directory points at a nonexistent file on purpose so `wrangler deploy` fails loudly. **Do not fix it.**

If you landed here because wrangler said "entry-point file not found" with a `STALE-COPY-DO-NOT-DEPLOY` filename — that's the trip-wire working. Run:

```
cd F:\Phoenix\Phoenix-DevOps-oS\sector2\package-handler\worker
wrangler deploy
```
