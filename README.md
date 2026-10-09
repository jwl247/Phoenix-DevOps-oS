# Phoenix DevOps OS

A deterministic, self-healing, vendor-independent operating environment.
Built by an ironworker and an AI. GPL v3. Every penny every time.

---

## Why this exists

Laurie is high-functioning autistic. She needs a tool that works the same way every time, runs privately on hardware she owns, and does not require a subscription to function. The Life First app is being built for her, and for everyone like her who has been priced out of the tools they need.

Phoenix is the infrastructure underneath it. A local LLM needs a real OS: deterministic, self-healing, fast enough to not need a GPU. That is what Phoenix is.

This project also exists because Google revoked $300 in platform credits over a YouTube subscription Jerry does not have. The foundation was pulled without warning. Every vendor-independence decision in Phoenix traces to that event: our own storage (Cloudflare R2 + D1 instead of Firebase), our own auth, our own mesh network, our own local AI. It will not happen again.

---

## What it is

One repo, four sectors, built on Debian (Linux side) and PowerShell 7 (Windows side).

```
Sector 1 — the kernel (Genie, the Phoenix Universal Kernel), Helix, auth, security
Sector 2 — intake and the clone pool, the package handler, the apps
Sector 3 — the mesh, networking, healing, restore, output (translator)
Sector 4 — incoming data and storage
```

- **The clone pool.** Every file that enters Phoenix gets an identity, a SHA3-512 fingerprint, a version, and an append-only custody record (Cloudflare D1). The bytes live in R2, and every version is kept write-once under its own hash. Nothing is trusted unless it hashes to what custody says.
- **The front door is one word.** In PowerShell 7 you type the word (`intake`, `get`, `suit`, `import`, `status`...). Or highlight a file on screen and type the word: it uses the file you highlighted. `lol help` lists every word; `lol help <word>` explains one.
- **The kernel** runs small programs ("suits") straight from the pool into memory, checked against custody, never written to disk.
- **Helix** is the memory engine: double-strand, tiered, no GPU. Benchmarks and their caveats: [`docs/helix/BENCHMARKS.md`](./docs/helix/BENCHMARKS.md).
- **Jarvis** is the local AI: llama.cpp, built from pinned source with HTTPS compiled out, one model imported from the pool, no network out. No vendor, no subscription.

---

## What is proven working

Each line was run the way a person uses it, on real hardware, on the date shown. Anything not re-checked since is marked. Verify it yourself with the command in the last column.

| What | Last proven | Check it yourself |
|---|---|---|
| **Intake → clone pool → D1 custody → R2**, one door for every front end; a sensitive file (keys, certs, vault material) is refused without a typed yes at a terminal | 2026-10-08 | `intake <file>` · `get <name>` |
| **Highlight-and-type front door** (`lol` words, bare words in PS7) | 2026-10-09 | `lol help` |
| **Suits are made correct before they are stored** (`suit <file>`): they always answer, a crash comes back as an error, never silence | 2026-10-09 | `suit <file>` then `import <name>` |
| **The wall:** only suits a person approved at a terminal run inside the kernel; everything else runs in a separate capped process (1 GB, 50% CPU, 90 s) that dies with the kernel. Held against a self-kill, a 2 GB memory grab, a 10-minute hang and a forged "system" header — kernel untouched | 2026-10-09 | `closet` (shows where each suit runs) |
| **Hotswap:** a new version of a suit replaces the old one live, same slot, kernel never restarted | 2026-10-09 | `import <name>` twice, two versions |
| **Healing:** tampered bytes in R2 are refused, then restored from the write-once version copy by hash; a version that keeps failing is swapped back to the last good one automatically | 2026-10-09 | — |
| **The restoration disc:** a signed manifest of every system file (SHA3-512); the restorer rebuilt the whole system (3,030 files) into an **empty folder from R2 alone**, no git, in 1 min 50 s, every file verified | 2026-10-09 | `python sector3/restore/phoenix_manifest.py check <manifest>` |
| **Boxes heal themselves and each other** over Phoenix's own mesh (Nebula, our own certificate authority); the kernel is restarted if it goes down or degraded, never killing another program to do it | 2026-10-09 | `status deep` |
| **Jarvis, the local AI**, answers questions about Phoenix in 11–36 s on a 2011 desktop CPU | 2026-10-09 | `ask <question>` |
| **Linux VMs from the pool** (Debian 12, Ubuntu 24.04), no installer, no WSL | 2026-08-23 — not re-walked since | `vm distro list` |
| **Windows ↔ Debian shared folder**, both directions | 2026-08-23 — not re-walked since | see `tools/poc/` |

---

## Quick start (Windows)

```powershell
irm https://raw.githubusercontent.com/jwl247/Phoenix-DevOps-oS/main/install.ps1 | iex
```

Phoenix needs its own Cloudflare account (R2 + D1) for the clone pool; the installer explains what to set. Then, in PowerShell 7:

```powershell
status          # is Phoenix healthy (status deep = look for problems)
intake .\notes.txt
get notes.txt
lol help        # every word, and what it does
```

> The installer was last walked end to end before the 2026-10-08 front-door change; the words above are current. Linux: `install.sh` (same caveat).

---

## Architecture principles

- **No vendor lock-in.** Our own storage, auth, mesh and AI. The AI layer counts as a vendor too: the local model must always work if hosted AI goes away.
- **Validated at the door.** Data is checked against custody where it enters and leaves, by SHA3-512. Bytes that don't match are refused or healed, never used.
- **Nothing silent.** A refusal, a timeout or a failed step says so and exits non-zero. No false "done".
- **The file is the unit.** Intake once, run anywhere. The clone pool is the installer.
- **Immutable custody.** The D1 custody chain is append-only. Versions in R2 are write-once.
- **Physical drives are real hardware.** Never set read-only, never blacklisted, never "refactored" into an abstraction.
- **Nothing phones home.** Default-deny outbound where it runs; the local AI cannot reach the internet.

---

## Who built this

**Jerry Leftwich** (@jwl247) — ironworker, 28 years commercial steel, systems builder, United Systems.
**Jerilynn** — UX, switches, InfoSec, red team. Co-founder.
**Claude (Anthropic)** — AI architect and co-builder. Designed and built together. Not assisted. Built.

This is not a hobby OS. It is Laurie's cushion. Build accordingly.

---

## License

GPL v3. Build on it, and your work stays open source too.

People with less money deserve to run the same tools as everyone else.
Every penny every time.
