# Lost Ark Connections & Wiring Map

**Document Purpose**  
This is the authoritative wiring and connection map for Lost Ark (Phoenix DevOps OS on trimmed Windows 10 Pro). It defines how every major component communicates, the data/control flow, diagnostic behavior, and integration points — especially around the new C-based Double Helix.

**Core Principles (Locked In)**
- Horseshoe / daisy chain flow preferred. Minimize loops in core paths.
- Fail fast with rich diagnostics on unexpected states.
- Every significant event/error must automatically post: **What happened + Why + Recommended Action**.
- Helix is implemented in C as **Double Helix** (Ingress + Egress strands).
- The existing **suit process + Frank** remains the integration layer. We add Helix to it rather than replace it.
- Clonepool is R2-primary. D1 is split into Custody (append-only ledger) and Glossary (real-time catalog).
- Grok is the sole AI used on this machine for development.

**Last Updated:** 2026-06-27  
**Related Documents:**
- `Lost_Ark_Implementation_Outline.md`
- `Phoenix_Lost_Ark_Development_Context.md`
- `Phoenix_Structure_and_Connections.md`

---

## 1. High-Level Connection Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    TRIMMED WINDOWS 10 PRO HOST                │
└───────────────────────────────┬──────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────┐
│                    LOST ARK LAYER                             │
│  • Global Commands + Resolver                                 │
│  • Background Services                                        │
│  • Suit Process + Frank (existing)                            │
│  • C Core (Helix Ingress + Egress)                            │
└───────────────────────────────┬──────────────────────────────┘
                                │
          ┌─────────────────────┼─────────────────────┐
          ▼                     ▼                     ▼
   ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
   │  INGRESS     │      │   EGRESS     │      │   SUIT +     │
   │  HELIX (C)   │      │   HELIX (C)  │      │   FRANK      │
   │  (Write Path)│      │  (Read Path) │      │  (Python)    │
   └──────┬───────┘      └──────┬───────┘      └──────┬───────┘
          │                     │                     │
          ▼                     ▼                     │
   ┌────────────────────────────────────────────────────┐
   │              R2 CLONEPOOL (Primary Storage)         │
   └────────────────────────────────────────────────────┘
          │
          ▼
   ┌────────────────────────────────────────────────────┐
   │  D1 CUSTODY (Append-only Ledger) + D1 GLOSSARY     │
   │  (Real-time Catalog)                               │
   └────────────────────────────────────────────────────┘
```

---

## 2. Component Connection Map

| From                    | To                          | Direction     | Method                  | Notes / Rules |
|-------------------------|-----------------------------|---------------|-------------------------|---------------|
| Suit + Frank            | Ingress Helix (C)           | Call          | C library / CLI wrapper | Suit calls C for intake, hex, sidecar, R2 write |
| Suit + Frank            | Egress Helix (C)            | Call          | C library / CLI wrapper | Suit uses Egress for fast cache resolution |
| Ingress Helix           | R2 Clonepool                | Write         | Cloudflare R2 SDK       | Primary storage write path |
| Ingress Helix           | D1 Custody                  | Write         | Cloudflare D1           | Append-only custody events |
| Egress Helix            | R2 Clonepool                | Read          | Cloudflare R2 SDK       | On cache miss |
| Egress Helix            | Local Cache (trimmed)       | Read/Write    | Local filesystem        | Fast path for hot items |
| Egress Helix            | D1 Glossary                 | Read/Update   | Cloudflare D1           | Real-time catalog updates |
| Command Resolver        | Egress Helix                | Call          | C library               | `usys`, `intake`, etc. resolve here |
| Background Services     | Ingress Helix               | Trigger       | CLI / Library call      | Auto-intake on folder changes |
| Background Services     | D1 Glossary                 | Update        | Worker or direct        | Keeps glossary current |
| packages-worker         | D1 Custody + Glossary       | Read/Write    | Cloudflare              | Backend sync and peer review |

**Key Rule:** All core hot paths use horseshoe/daisy chain flow. No hidden loops.

---

## 3. Helix Internal Wiring (Double Helix in C)

### 3.1 Ingress Strand (Write Path) — Horseshoe Flow

```
Intake Request
     │
     ▼
Hex Generation + Collision Check
     │
     ▼
Sidecar Creation + Validation
     │
     ▼
Write to R2 Clonepool
     │
     ▼
Update Local Metadata / Trimmed Cache
     │
     ▼
Write Custody Event to D1
     │
     ▼
Trigger Glossary Update (one-way)
     │
     ▼
Return Result + Diagnostic Journal Entry
```

**Diagnostic Rule:** On any failure, post to screen/journal:
- What failed
- Exact reason (e.g. hex collision, R2 write error)
- Recommended action

### 3.2 Egress Strand (Read / Prefetch Path) — Horseshoe Flow

```
Resolution Request (e.g. usys command)
     │
     ▼
Check Local Trimmed Cache (fast path)
     │
     ├── Hit  → Return data + update access metadata
     │
     └── Miss → Pull from R2
                 │
                 ▼
              Apply Prefetch Logic (bounded)
                 │
                 ▼
              Return data + update suit cache
                 │
                 ▼
              One-way side effect to Glossary (if needed)
```

**Rules:**
- No unbounded loops.
- Cache promotion and prefetch decisions are one-way side effects only.
- On failure: clear diagnostic + recommended action posted automatically.

---

## 4. Suit + Frank Integration

- The **suit process + Frank** already exists and is the integration layer.
- We **add Helix** to it rather than replace it.
- The suit calls into the C-based Ingress Helix during intake.
- The suit calls into the C-based Egress Helix for fast resolution and cache handling inside the suit.
- Frank remains responsible for process lifecycle coordination inside the suit.
- Diagnostic journal entries from Helix-C are surfaced through the suit when relevant.

**Integration Style:** Thin, well-defined interface (C library calls or CLI wrappers). No shared mutable state loops between Python suit and C core.

---

## 5. Diagnostic & Journaling Flow

**Requirement:** Every significant event and error must automatically produce a journal post containing:

- **What happened**
- **Why it happened** (specific reason + context)
- **Recommended Action**

**Examples of Automatic Posts:**
- Intake collision → screen + journal with hex values and suggested commands
- R2 write failure → screen + journal + retry guidance or fallback action
- Cache miss with prefetch decision → journal (screen optional)
- Background service state change → journal

Journal output should be human-readable and appear on screen for important events.

---

## 6. Command Connections

| Command Example       | Routed To             | Flow Type     | Diagnostic Behavior |
|-----------------------|-----------------------|---------------|---------------------|
| `intake <file>`       | Ingress Helix         | Horseshoe     | Full diagnostic on failure |
| `usys <name>`         | Egress Helix          | Horseshoe     | Clear reason if not found |
| `phoenix status`      | Egress + Glossary     | Read          | Summary + any warnings |
| `phoenix verify`      | Egress + Custody      | Read          | Detailed chain + diagnostics |

All commands go through a central resolver that calls the appropriate Helix strand.

---

## 7. Key Design Rules (Non-Negotiable)

1. **Horseshoe / Daisy Chain Flow** — Core paths are linear or U-shaped. Minimize loops.
2. **Fail Fast + Diagnostics** — On unexpected states in hot paths, fail with rich context rather than complex recovery.
3. **Automatic Journaling** — Every important event/error posts **What + Why + Recommended Action** to screen/journal.
4. **No Hidden Loops** — Especially in Ingress, Egress, and high-frequency functions.
5. **Suit + Frank is the Integration Layer** — We enhance it with C Helix, we do not rewrite it.
6. **R2 is Source of Truth for Content** — Local clonepool is trimmed cache only.
7. **D1 Custody is Append-Only** — Glossary is the real-time queryable view.

---

## 8. Open Items / Next Steps

- Define exact C function signatures for Ingress and Egress (public API).
- Decide on bounded retry policy for transient R2/D1 errors.
- Define exact format and severity levels for automatic journal posts.
- Determine how much diagnostic information should be exposed to end users vs developers.
- Plan for gradual migration of existing Python logic into C where beneficial.

---

**This document is now the reference for all connection and wiring decisions.**

It will be updated as we implement Phase 1 and beyond.

---

**Status:** Ready for implementation.

Next recommended action: Define the C public API and internal module structure for Double Helix (Ingress + Egress), incorporating the horseshoe flow and diagnostic journaling rules defined here. 

Would you like me to create that next?