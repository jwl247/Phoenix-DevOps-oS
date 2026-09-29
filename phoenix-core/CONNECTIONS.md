# phoenix-core — standalone C intake engine

Written 2026-09-12; refreshed 2026-09-29 against the 2026-09-28 Round 2 audit (S1 + CONN).
Verify against current code before trusting a specific line number.

## What it is
A standalone C project ("phoenix-helix-c"). Treat it as a lab / secondary intake path —
its identities are not compatible with the canonical pool (see Known issues).
- `Makefile` — `make` (all) builds `libhelix.a` only; `make intake` builds the `phoenix-intake` CLI; `make test` builds + runs `tests/test_core`.
- `include/helix.h` — public types/API (sidecar struct, result codes).
- `include/helix_http.h` — worker HTTP client API (libcurl).
- `src/helix_core.c` — hex ID (SHA-256 of file content), sidecar build, JSON.
- `src/helix_diagnostics.c` — event log / diagnostics.
- `src/helix_ingress.c` — write path: sidecar → D1 glossary → R2 bytes → custody → local sidecar.json.
- `src/helix_egress.c` — read path: local cache → R2 fetch → cache store.
- `src/helix_http.c` — packages-worker client; sends `Authorization` + `CF-Access-Client-Id/Secret` on every call (incl. the R2 byte PUT since 2026-09-29).
- `tools/main.c` — the `phoenix-intake` CLI (`make intake`).
- `tools/intake.py` — legacy Python intake pipeline, **deprecated** (banner + stderr warning).
- `tests/test_core.c` — 16 assertions (`make test`; 16/16 on pbm3 2026-09-25).
- `.gitignore` — build artifacts (`*.o`, `*.a`, `*.exe`); `libhelix.a` is not tracked.

## Dependencies
C toolchain (gcc/make) + **libcurl** dev headers (`-lcurl` in `Makefile:49,57`;
`libcurl4-openssl-dev` on Debian). Python 3 for `tools/intake.py`. Online steps read
`PHOENIX_WORKER_URL`, `PHOENIX_AUTH`, `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET`;
`PHOENIX_CACHE` sets the local cache dir.

## Commands / entry points
- `make` in `phoenix-core/` — builds `libhelix.a`.
- `make intake` — builds `phoenix-intake`; `make test` — 16 checks. Linux (pbm3); no toolchain on the Windows dev box.
- `phoenix-core/tools/intake.py` — **deprecated**. Do not add new callers.

## Connects to / connected from
- `phoenix-core/src/helix_http.c` → `sector2/package-handler/worker/index.js` (packages-worker `/clonepool`, `/custody` routes).
- `sector4/intake/intake.sh` → `phoenix-core/tools/intake.py` (live wrapper on the deprecated path, `intake.sh:21-28`).
- `tools/phoenix-tray.py` → `phoenix-core/tools/intake.py` (tray intake still uses the deprecated path — S34OPS-F25).
- `dashboard/main.js` → `phoenix-core` (the `helix` slot maps to this dir, `main.js:170`).
- `scripts/usys.ps1` no longer calls `tools/intake.py` — its four former call sites go through `Invoke-UsysIntakeFile` / `intake.sh` since 2026-09-21 (only comments remain).
- `dashboard/manual/PHOENIX_MANUAL.md` documents `make intake` and "do not mix Python intake and C phoenix-core" (~lines 353/431).

## Known issues (verified, not guessed)
- `tools/intake.py` has **no R2 upload, no integrity baseline, and a stub QR sidecar** (`qr:sha3:` placeholder) — anything intaked through it (via `sector4/intake/intake.sh` or the tray) lacks the custody guarantees of `sector2/package-handler/intake.sh`.
- `hex_id` is SHA-256 of file *content*; canonical `intake.sh` uses `to_hex(basename)` and the TAV spec says SHA3-512 — the same file gets different IDs/D1 rows depending on path. `hash_sha3` is a placeholder copy of the SHA-256. Decision for Jerry: first-class path or lab (audit S1-F29).
- A failed R2 byte PUT is non-fatal in `helix_ingress.c` — intake can still return `HELIX_OK` with a D1 row and no bytes (S1-F22; the CF-Access header part is fixed, needs a pbm3 rebuild to verify).
- Bounded prefetch (egress step 4) is not implemented; ingress never writes `<cache>/<id>/content`, so the cache is seeded only by an egress R2 fetch.
- JSON is built with `snprintf` and no escaping into fixed buffers (S1-F13).
