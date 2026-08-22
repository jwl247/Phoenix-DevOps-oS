# Phoenix DevOps OS

A self-hosted, deterministic operating environment. Built to run a local LLM
for the Life First app without a cloud dependency — no vendor, no
subscription, no single point of failure. GPL v3.

Full reference: [`dashboard/manual/PHOENIX_MANUAL.md`](./dashboard/manual/PHOENIX_MANUAL.md).
Plain-English guide: [`dashboard/manual/LAURIE_GUIDE.md`](./dashboard/manual/LAURIE_GUIDE.md).

## What it is

Four sectors, one repo:

| Sector | Role |
|--------|------|
| 1 | Boot, GRUB, kernel |
| 2 | Package handler, clone pool, intake authority |
| 3 | Comms and networking |
| 4 | Helix engine, Frank orchestrator, vault |

**Helix** is the memory engine — double-strand, quadralingual, benchmarked at
700,000 ops/sec with a 100% cache hit rate. **Frank** is the import authority
and audit logger. The **clone pool** is D1 (custody/glossary) + R2 (raw
bytes) — content-addressed by SHA3-512, nothing is ever deleted from it.

## What's actually working

This is a proof of concept, not a finished product. What's verified working
today:

- The full intake pipeline, end to end: file → hex ID → sidecar.json → clone
  pool → D1 custody, confirmed syncing on a live Cloudflare Worker
- 7 global commands (`usys`, `intake`, `clone`, `status`, `run`,
  `align_dirs`, `get_distros`) on Windows and Linux
- The Electron dashboard, including a real PowerShell 7 shell (not a mock —
  it spawns actual `pwsh.exe`), a clonepool file browser, and screenshot
  analysis — verified live
- Silent, single-source auth (`usys init` writes once to the Windows
  registry / `~/.phoenix_env.sh` on Linux, every command reads from there)
- D1/R2 sync via `packages-worker` on Cloudflare, live with a `/stats`
  endpoint

What's not done yet, what's stubbed, and what's still in progress is
tracked honestly in `PHOENIX_BUILD_MASTER.md` and `CLAUDE.md` — read those
before assuming anything not listed above is finished.

## Install

**Windows:**
```powershell
irm https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/install.ps1 | iex
```

**Linux / macOS:**
```bash
curl -fsSL https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/install.sh | bash
```

Requirements, verification, dashboard setup, environment variables, and
troubleshooting are all in `PHOENIX_MANUAL.md` — not duplicated here.

## License

GPL v3. Build on it, and your work stays open source too.
