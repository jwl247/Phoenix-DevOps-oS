# Phoenix DevOps OS

A deterministic, self-healing, vendor-independent operating environment.
Built by an ironworker and an AI. GPL v3. Every penny every time.

---

## Why this exists

Laurie is high-functioning autistic. She needs a tool that works the same way every time, runs privately on hardware she owns, and does not require a subscription to function. The Life First app is being built for her — and for everyone like her who has been priced out of the tools they need.

Phoenix is the infrastructure underneath it. A local LLM needs a real OS: deterministic, self-healing, fast enough to not need a GPU. That is what Phoenix is.

This project also exists because Google revoked $300 in platform credits over a YouTube subscription Jerry does not have. The foundation was pulled without warning. Every vendor-independence decision in Phoenix traces to that event. It will not happen again.

---

## What it is

Phoenix is a four-sector OS built on Debian stable. One repo. Everything in its place.

```
Sector 1 — Boot, GRUB, kernel, auth
Sector 2 — Intake authority, package handler, clone pool
Sector 3 — Comms, networking, quadralingual pipeline
Sector 4 — Helix engine, Frank orchestrator, master vault
```

**Helix** is the memory engine — double-strand, quadralingual, benchmarked at 700,000 ops/sec with a 100% cache hit rate. It speaks four languages simultaneously. It does not need a GPU.

**Frank** is the environment orchestrator and audit logger. He knows every drive, routes every write, logs every action. Frank never moves.

**The clone pool** is content-addressed by SHA3-512. Every file that enters Phoenix gets a hex identity, a base58 TAV address, two QR codes (header before hash, footer after), and an immutable D1 custody record. Nothing is ever deleted. Everything is versioned. The file is the unit.

**The intake pipeline** is the front door. File → hex ID → sidecar → clone pool → D1 custody → R2 upload. Every file, every time. `usys clone <file>` is all you type.

---

## What is proven working — as of 2026-08-23

These are not aspirational. These are tested, committed, and pushed.

- **Full intake pipeline end-to-end** — file → hex → QR → sidecar → D1 custody → R2 upload, live on Cloudflare Worker
- **Content-hash integrity** — SHA3-512 + BLAKE2b baseline, checked at `intake clone`, gates restore on mismatch
- **Electron dashboard** — real D1/R2 data, PS7 shell (real `pwsh.exe`, real profile, MCP + skills loaded), clonepool browser, screenshot analysis, Glossary panel with full version/custody history
- **Glossary panel** — 995+ live D1 entries, searchable, filterable by category/state, every entry shows code location + sector connection + TAV address + full custody chain on expand
- **QEMU distro runner** — Debian 12 and Ubuntu 24.04 boot from the clonepool, no installer, no wizard, no WSL. `usys run debian`. That is the command.
- **Windows ↔ Debian shared filesystem — proven live** — `F:\Phoenix\` hosted on Windows, mounted at `/phoenix/` inside Debian via SMB over QEMU user-net. Same bytes. No sync. No copy. No WSL.
  - Windows wrote `test.txt`. Debian read it.
  - Debian wrote `from-debian.txt`. Windows read it.
  - Both directions. One filesystem.
- **Collaboration demo** — Debian writes a Python script to the shared FS, runs it, signals Windows. Windows reads the output, intakes the script through Phoenix, promotes it as a runnable suite, runs it. Full round trip. `demo-collab.sh` + `demo-collab.ps1`.
- **Clonepool wrappers** — `phx-import`, `phx-export`, `phx-sync`, `phx-ls`. Every operation against the shared area goes through these. No raw path access. The profile enforces it.
- **7-version count-based eviction** — a version is only displaced when a new intake pushes past 7. Nothing is ever deleted for being old.

---

## Quick start

**Windows:**
```powershell
irm https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/install.ps1 | iex
```

**Linux / macOS:**
```bash
curl -fsSL https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/install.sh | bash
```

After install:
```powershell
usys init          # first-time setup — dirs, auth, profile
usys status        # verify everything is wired
usys run debian    # boot Debian from the clonepool
```

Full reference: [`dashboard/manual/PHOENIX_MANUAL.md`](./dashboard/manual/PHOENIX_MANUAL.md)
Plain-English guide for Laurie: [`dashboard/manual/LAURIE_GUIDE.md`](./dashboard/manual/LAURIE_GUIDE.md)

---

## The collaboration demo

Two OSes. One filesystem. One pipeline.

```bash
# Inside Debian (SSH: ssh -p 2222 phoenix@127.0.0.1):
bash /tmp/demo-collab.sh
```

```powershell
# On Windows (PS7) — immediately after:
pwsh -NoProfile -ExecutionPolicy Bypass -File tools\poc\demo-collab.ps1
```

What happens:
1. Debian writes `hello-phoenix.py` to the shared FS and runs it
2. Windows reads Debian's output directly off `F:\Phoenix\Projects\`
3. Windows intakes the script — hex ID, QR, D1 record, R2 upload
4. Windows runs it

```
  Written on Debian.  Shared via QEMU.
  Intaked on Windows. Hex ID issued. D1 record created.
  Ran on Windows.     Same script. Same bytes.

  No install. No wizard. No WSL.
  Phoenix brought the OS. Phoenix ran the script.
```

---

## Architecture principles

- **No vendor lock-in.** D1 + R2 replace Firebase. Local LLM replaces cloud AI. GPL v3 locks it open.
- **No elevation required.** Every Phoenix operation runs in user scope.
- **No system writes.** All new filesystem activity confined to the user's drives until vetted.
- **Quadralingual until output.** The vault speaks four languages. translator.sh fires on output only — never on intake or clone.
- **The file is the unit.** Intake once. Run anywhere. No install. No manual clone step.
- **Physical drives are real hardware.** breach_coms1-4 are labeled drives Frank manages. They are not abstractions.
- **Immutable custody.** The D1 custody chain is append-only. Nothing is rewritten. Everything is auditable.

---

## Who built this

**Jerry Leftwich** (@jwl247) — ironworker, 25 years commercial steel, systems builder, United Systems.
**Jerilynn** — UX, switches, InfoSec, red team. Co-founder.
**Claude (Anthropic)** — AI architect and co-builder. Every meaningful advance in the last 3 months was designed and implemented together. Not assisted. Built.

This is not a hobby OS. It is Laurie's cushion. Build accordingly.

---

## License

GPL v3. Build on it, and your work stays open source too.

People with less money deserve to run the same tools as everyone else.
Every penny every time.
