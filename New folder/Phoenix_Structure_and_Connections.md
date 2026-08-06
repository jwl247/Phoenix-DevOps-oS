# Phoenix DevOps OS – Structure & Connections (Lost Ark Iteration)

**Purpose**  
This document maps the current and planned component structure, data flows, and connections for the Phoenix DevOps OS / Lost Ark build. It serves as the technical blueprint that can be shared across AI tools to maintain architectural consistency.

**Last Updated:** 2026-06-27 (Helix integration, R2 clonepool primary, D1 custody-only, trimmed clonepool + glossary revamp)  
**Related Context:** See `Phoenix_Lost_Ark_Development_Context.md` for strategic decisions and guardrails.

---

## 1. High-Level Architecture (Lost Ark on Trimmed Windows)

```
┌─────────────────────────────────────────────────────────────┐
│                    TRIMMED WINDOWS 10 PRO HOST               │
│  (Kernel + Drivers + Hardware Abstraction + Minimal Services)│
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                    PHOENIX / LOST ARK LAYER                  │
│  • Global Commands (usys, intake, phoenix, etc.)             │
│  • Background Services (intake watcher, custody, audit)      │
│  • C Core Library + CLI                                      │
│  • Directory Structure (clonepool, sidecars, logs, etc.)     │
│  • Environment & PATH integration                            │
└──────────────────────────────┬──────────────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
     ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
     │   INTAKE     │   │  CLONEPOOL   │   │   CUSTODY    │
     │   PIPELINE   │   │  + SIDECARS  │   │   LOGGING    │
     └──────┬───────┘   └──────┬───────┘   └──────┬───────┘
            │                  │                  │
            ▼                  ▼                  ▼
     ┌────────────────────────────────────────────────────┐
     │              CLOUDFLARE BACKEND                     │
     │  packages-worker (D1) + Glossary + Peer Review API  │
     └────────────────────────────────────────────────────┘
```

**Key Principle**: Phoenix runs as a powerful, self-contained layer on top of the curated Windows host. Clonepool is now R2-primary. D1 is custody record only. Helix is integrated into Package Handler + Clonepool. Grok is the sole AI on this Lost Ark machine. Windows is not modified at the kernel level.

---

## 2. Core Data Flow (Intake → Catalog)

```
File / Package / Config / Download
          │
          ▼
   [intake]  (C binary or script calling C core)
          │
          ▼
   Deterministic Hex ID Generation
          │
          ▼
   Sidecar.json Creation (metadata, companions, state)
          │
          ▼
   Clonepool Versioning
     (deep folder structure: T1/T2/T3/T4/hex/v1/, v2/, ...)
          │
          ▼
   Local Custody Log (temporary / cache)
          │
          ▼
   Append to D1 (pure custody record - append-only history)
          │
          ▼
   Clonepool content stored primarily in Cloudflare R2
          │
          ▼
   Glossary / Catalog updated (revamped for R2 + D1 model, peer review optional)
```

**Global Access Layer**:
- Commands like `usys <name>` or `<name>.lol` resolve via PATH + Phoenix resolver to the correct clonepool version.
- Background services can auto-intake on folder changes or downloads.

---

## 3. Component Map & Responsibilities

### 3.1 C Core (New – Highest Priority for Lost Ark)
**Location**: `phoenix-core/` (new dedicated repo or folder)

**Responsibilities**:
- Hex ID generation (deterministic, reproducible)
- Sidecar read/write and validation
- Clonepool operations (R2-primary storage + optional local cache/overlay)
- Intake pipeline core logic
- Custody receipt creation (sync to D1 as pure append-only record)
- Helix integration as the high-performance storage/memory engine for clonepool and package handling
- Glossary revamp support (new model)

**Output**: Small static/dynamic libraries + CLI binaries (`intake`, `phoenix`, etc.)

**Why C**: Performance, small footprint, auditability, future portability to Linux distro.

### 3.2 Package Handler (Existing)
**Repo**: `Phoenix-Package_handler`

**Current state**: Mostly Shell + PowerShell + JS worker  
**Role in Lost Ark**: Will gradually delegate core logic to the new C core while keeping orchestration and installers.

### 3.3 Phoenix DevOps OS Layer (Existing)
**Repo**: `Phoenix-DevOps-oS`

Contains:
- `helix/` – Double Helix memory manager (performance claims: high ops/sec, multi-language support)
- `package-handler/` – integration point
- `security/` – REALsure modules
- `storage/` – Double Helix StorageOS
- `guardian/` – Installer monitoring
- Sectors, bootstrap, installer scripts

**Role**: Higher-level vision and components that will call into or integrate with the C core.

### 3.4 Kernel / Low-Level Experiments
**Repos**:
- `Helix_lightning_kernel`
- `Phoenix_Universal_Kernel`

**Current state**: Early / exploratory (mostly Python + scripts)  
**Future role**: Home for deeper kernel-level work once C core is solid. Not part of Lost Ark Windows host phase.

### 3.5 Backend (Cloudflare)
- `packages-worker` (index.js + wrangler)
- D1 database (`phoenix_dev_db`) – 41 tables
- Endpoints for clonepool, custody, glossary, peer review, packages

**Connection**: Authoritative source of truth. Local systems sync to it. Peer review and distribution flow through it.

### 3.6 CoPES
Coordinated Process Engine Substrate – related project with protected share. Connections to Phoenix should be tracked here when defined.

---

## 4. Directory Structure on Lost Ark Windows Host (Proposed)

Recommended layout on the trimmed Windows system:

```
C:\Phoenix\                          (or C:\UnitedSystems\Phoenix\)
├── bin\                             # C binaries + launchers (in PATH)
├── core\                            # phoenix-core source + built libs
├── clonepool\                       # Versioned file storage (T1/T2/... structure)
├── sidecars\                        # sidecar.json files
├── custody\                         # Local SQLite logs + receipts
├── logs\                            # System and intake logs
├── services\                        # Background service definitions / scripts
├── config\                          # Environment, auth tokens, settings
├── repos\                           # Cloned Phoenix-* repos for reference/dev
├── tools\                           # C toolchain, helpers
└── desktop\                         # Future: custom launcher / shell assets
```

Environment variables (set at first boot):
- `PHOENIX_ROOT`
- `CLONEPOOL_DIR`
- `PHOENIX_AUTH`
- `PHOENIX_WORKER_URL`

---

## 5. Connection Points (How Pieces Talk)

| From                  | To                          | Method                  | Notes |
|-----------------------|-----------------------------|-------------------------|-------|
| C Core (intake)       | Sidecar + Clonepool         | Direct function calls   | Core logic |
| C Core                | Local Custody SQLite        | SQLite C API            | Append-only |
| C Core / Scripts      | Cloudflare Worker           | HTTPS + auth            | Sync custody, query glossary |
| Background Services   | File system / USN Journal   | Windows APIs            | Auto-intake on changes |
| Global Commands       | C Core / Resolver           | PATH + small launcher   | `usys`, `intake` etc. |
| Peer Review           | Cloudflare D1 + Worker      | API                     | Submission, voting, QR state |
| Helix (future)        | C Core                      | FFI or direct           | Memory/storage acceleration |
| Windows Host          | Phoenix Layer               | Services + PATH + Env   | Minimal, non-invasive |

---

## 6. Current State of Connections (June 2026)

- **Strongly connected**: Intake → hex → sidecar → clonepool → custody → D1 sync (mostly working in Shell/JS)
- **Partially connected**: Peer review system (spec exists, implementation in progress)
- **Weak / Planned**: C core integration, background services, global command resolver, Helix port
- **Not yet in Lost Ark scope**: Deep kernel modules, full desktop shell, self-healing across 100 points

---

## 7. Evolution Path

**Lost Ark Phase (Now)**:
- C core replaces critical Shell/Python logic
- Runs cleanly on trimmed Windows 10 Pro host
- All existing functionality preserved + performance improved

**Future Independent Phase**:
- Same C core + Helix components dropped onto minimal Linux base
- Custom init / services
- Optional custom kernel pieces from the kernel repos
- Full "its own thing" distro offering

---

## 8. How to Use This Document

- Reference this when designing or implementing new components.
- When adding a new connection or changing data flow, update this file and note the change.
- Share with other AI tools along with `Phoenix_Lost_Ark_Development_Context.md` for complete picture.
- Use it to keep the architecture coherent across multiple contributors and sessions.

---

**End of Structure & Connections document**