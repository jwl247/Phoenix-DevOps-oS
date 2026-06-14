# Phoenix Peer Review Platform
**UnitedSys — United Systems | jwl247**
**Part of:** Phoenix DevOps OS
**Status:** Specification — Open for Contribution

---

## What This Is

The Phoenix Peer Review Platform is the community gate that sits between content creation and distribution. It provides a human-in-the-loop review pipeline for every artifact that enters the Phoenix ecosystem — before it becomes available, before it gets a QR, and before it is announced to any distribution channel.

> Nothing is pushed. Availability is announced. Users pull only what they choose.

This is opt-in distribution, not forced delivery. The review layer ensures that what gets advertised is what the community has agreed to.

---

## The Lifecycle

```
Create → Submit → Review → Approve → Hash → Register → Advertise → Opt-In Pull → Verify → Use
```

Each stage is **decoupled**. Failure or delay in one stage does not stall the others. Revocation can happen at any point after registration without deleting any artifact.

---

## Stage 1 — Submission

Any community member can submit an artifact for review.

An artifact can be:
- A script, config, or binary intaked via `intake.sh`
- A package registered in the glossary
- A document, specification, or public statement
- A patch or update to an existing approved artifact

**Submission creates a review record, not a distribution record.** The artifact is in the clonepool but is not yet advertised.

### Submission Fields

| Field | Type | Description |
|-------|------|-------------|
| `submission_hex` | string | Hex identity of the artifact (from clonepool or intake) |
| `submitter` | string | GitHub handle or identifier of the submitter |
| `category` | string | Category from the glossary (scripts, configs, direct, etc.) |
| `description` | string | What this artifact does and why it is being submitted |
| `version` | string | Version string if applicable |
| `platform` | string | Target platform (linux, macos, windows, all) |
| `submitted_at` | timestamp | When the submission was created |
| `status` | string | pending / in_review / approved / rejected / superseded |

---

## Stage 2 — Review

Review is a human or multi-party process. It is the gate.

Review determines **acceptability**, not authenticity. The hex hash handles authenticity — the review handles judgment.

### Review Types

**Single reviewer** — one maintainer approves or rejects.

**Multi-party** — requires N-of-M approvals before advancing. Threshold is configurable per category.

**Offline** — review result and metadata are committed without requiring real-time participation.

### What Reviewers Evaluate

- Does the artifact do what the submission claims?
- Are there unintended side effects or security concerns?
- Is it appropriate for the platform and category?
- Does it conflict with or supersede an existing approved artifact?

### Review does not modify content

The artifact's bytes are not touched during review. The hex hash remains the same from submission through approval. Review only attaches judgment metadata.

### Review Record Fields

| Field | Type | Description |
|-------|------|-------------|
| `review_id` | string | Unique review identifier |
| `submission_hex` | string | The artifact being reviewed |
| `reviewer` | string | GitHub handle or identifier of reviewer |
| `vote` | string | approve / reject / abstain |
| `notes` | string | Optional reviewer notes or conditions |
| `reviewed_at` | timestamp | When the review was recorded |
| `threshold_met` | boolean | Whether multi-party threshold has been reached |

---

## Stage 3 — Hash Anchoring (The Integrity Lock)

When an artifact is approved, its hex hash becomes its **permanent canonical identity**.

```
"nginx.conf" → a3f8c2...4d19e7
```

This hex is:
- Derived from content (SHA-256 or equivalent)
- Immutable — any byte change produces a different hash
- The D1 primary key in the clonepool and glossary
- The payload of the QR code
- The verification anchor at pull time

The hex is the truth. Not the filename. Not the URL. Not the location.

This is identical to how Linux ISOs and package managers (apt, dnf, brew) verify integrity — the hash is the identity.

---

## Stage 4 — QR Generation

After approval and hash anchoring, a QR code is generated.

**The QR does not embed the content.** It encodes:
- The content hash (hex), OR
- A resolvable reference to the registry entry

### QR State System (Phoenix Standard)

Consistent with the Phoenix clonepool QR model:

| QR Color | Meaning |
|----------|---------|
| White | Active — currently approved and distributable |
| Grey | Deprecated — superseded by a newer version, grace period active |
| Black | Revoked / Retired — do not use, verification will fail |

Two QR codes per artifact:
- **Top QR** → status pointer (white/grey/black state)
- **Bottom QR** → location pointer (T1–T4 depth in clonepool)

### What Happens When Someone Scans

1. QR is scanned (phone, terminal, or scanner)
2. Hash or reference is extracted
3. Resolver queries the Phoenix registry
4. Registry returns: **verified / deprecated / revoked / unknown**
5. No download occurs unless the user explicitly requests it

Verification is **decoupled from delivery**.

---

## Stage 5 — Registration

Approved artifacts are registered in the Phoenix registry (packages-worker / D1).

The registry stores:
- Content hash (hex)
- Review metadata (who approved, when, threshold met)
- Current status (active / revoked / superseded)
- QR state

**The registry does not store the full artifact payload.**

It stores proof of review, identity, and status — the minimum needed for verification.

---

## Stage 6 — Advertisement (Zero-Cost Signaling)

Once registered, an availability signal is published.

The signal contains:
- Hash (hex)
- Version / changelog pointer
- Size estimate (optional)
- Category and platform tags

**No payload is transmitted at this stage.** The advertisement is metadata only and can be:
- Published to a distro / package index
- Syndicated via a feed or bulletin
- Cached indefinitely

This is the same economic model as OS update notifications — cheap to publish, cheap to cache, zero transmission cost until a user pulls.

---

## Stage 7 — Opt-In Pull (User Agency)

Nothing is delivered unless the user explicitly chooses it.

The user sees: *"Artifact X is available — version Y — approved by Z reviewers"*

The user decides:
- Ignore
- Fetch later
- Fetch now

If the user fetches:
1. Artifact is downloaded
2. Local hash is computed
3. Hash is compared with the advertised hex
4. Registry is optionally queried for current status
5. If all checks pass → artifact is usable

Many users never pull anything. Those users incur **zero transmission cost**.

---

## Stage 8 — Verification

Verification can happen at two points:

### At Pull Time
- Compute hash of downloaded artifact
- Compare with registry hex
- Reject if mismatch

### Post-Distribution (QR Scan)
- Scan QR from paper, screen, or offline media
- Resolver returns current registry status
- User sees: verified / deprecated / revoked / unknown

Verification is independent of location, transport, or filename. Only the hex matters.

---

## Stage 9 — Revocation and Supersession

Because identity == hash, revocation is clean:

- Old artifacts remain addressable by their hex
- Registry status changes to `revoked` or `superseded`
- Verification now returns the new status
- Already-downloaded copies fail verification going forward

**No content is deleted.** The clonepool retains all versions. The registry reflects reality.

### Revocation Record Fields

| Field | Type | Description |
|-------|------|-------------|
| `hex` | string | Hash of the artifact being revoked |
| `reason` | string | Human-readable reason for revocation |
| `revoked_by` | string | Reviewer or maintainer who issued the revocation |
| `revoked_at` | timestamp | When the revocation was recorded |
| `superseded_by` | string | Hex of the replacement artifact, if applicable |

---

## Integration with Phoenix Package Handler

The peer review platform is built on top of the existing Phoenix infrastructure:

| Phoenix Component | Peer Review Role |
|-------------------|-----------------|
| `intake/intake.sh` | Submission entry point — files enter the clonepool before review |
| `clonepool` (D1) | Stores all artifact versions, pre- and post-approval |
| `glossary` (D1) | Holds approved artifact metadata, indexed by hex |
| `custody` (D1) | Append-only log of every state change — intake, review, approval, revocation |
| `packages-worker` | Serves review status, verification endpoints, advertisement feed |
| QR system | Status and location pointers on every approved artifact |

### New Endpoints (packages-worker additions)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | /review | — | List all submissions. Filter by `?status=` (pending/approved/rejected) |
| GET | /review/:hex | — | Fetch review record for a specific artifact |
| POST | /review | ✓ | Submit an artifact for review |
| POST | /review/:hex/vote | ✓ | Cast a review vote (approve/reject/abstain) |
| GET | /review/:hex/votes | — | View all votes for a submission |
| POST | /review/:hex/revoke | ✓ | Revoke an approved artifact |
| GET | /verify/:hex | — | Verify an artifact by hex — returns current status + review provenance |
| GET | /feed | — | Advertisement feed — approved artifacts available for opt-in pull |

---

## D1 Schema Additions

### `submissions` table

```sql
CREATE TABLE submissions (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  hex         TEXT NOT NULL UNIQUE,
  submitter   TEXT NOT NULL,
  category    TEXT,
  description TEXT,
  version     TEXT,
  platform    TEXT,
  status      TEXT NOT NULL DEFAULT 'pending',
  submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### `reviews` table

```sql
CREATE TABLE reviews (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  submission_hex TEXT NOT NULL,
  reviewer      TEXT NOT NULL,
  vote          TEXT NOT NULL CHECK(vote IN ('approve','reject','abstain')),
  notes         TEXT,
  reviewed_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (submission_hex) REFERENCES submissions(hex)
);
```

### `revocations` table

```sql
CREATE TABLE revocations (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  hex           TEXT NOT NULL,
  reason        TEXT NOT NULL,
  revoked_by    TEXT NOT NULL,
  revoked_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
  superseded_by TEXT
);
```

### `advertisement_feed` table

```sql
CREATE TABLE advertisement_feed (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  hex           TEXT NOT NULL,
  name          TEXT NOT NULL,
  version       TEXT,
  category      TEXT,
  platform      TEXT,
  size          INTEGER,
  changelog     TEXT,
  published_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
  status        TEXT NOT NULL DEFAULT 'active'
);
```

---

## Website Integration

The peer review platform is served from the Phoenix DevOps OS website and exposed via the packages-worker API.

### Pages

| Page | Path | Description |
|------|------|-------------|
| Review Queue | `/review` | Active submissions awaiting review. Filterable by category, status, platform |
| Submission Detail | `/review/:hex` | Full artifact record, reviewer votes, QR, verification status |
| Submit | `/submit` | Form to submit an artifact (hex + metadata) |
| Verified Feed | `/feed` | Opt-in availability feed — approved artifacts ready to pull |
| Verify | `/verify/:hex` | Single-artifact verification — paste a hex or scan a QR |
| Revocation Log | `/revoked` | Public log of all revoked artifacts and reasons |

### Verification Widget

A lightweight embeddable widget for the Phoenix website that:
- Accepts a hex or QR scan
- Queries `/verify/:hex`
- Returns: verified / deprecated / revoked / unknown
- Shows review provenance (reviewer count, approval date)

---

## What This System Does Not Do

- ❌ Push content to users automatically
- ❌ Enforce DRM or access control
- ❌ Require identity verification to browse or verify
- ❌ Delete revoked artifacts from the clonepool
- ❌ Make distribution decisions on behalf of users
- ❌ Charge per pull or per verification

---

## Economic Model

The publisher pays once — to get the artifact reviewed, hashed, and registered.

After that:
- Mirrors sync once and cache
- Users pull asynchronously, if at all
- Verification queries are lightweight (metadata only)
- Marginal cost per user approaches zero

This is the same scaling trick used by every major Linux distro. Phoenix applies it to community-reviewed content.

---

## Where Community Help Is Wanted

This is an open system. Contributions are welcome at every layer:

| Area | What's Needed |
|------|--------------|
| Review workflow | Multi-party threshold logic, reviewer assignment, quorum rules |
| Hashing standards | SHA-256 vs SHA-3 vs BLAKE2 — tradeoffs for this use case |
| QR encoding | Encoding format, offline resolver spec, print standards |
| Registry schema | Schema review, index optimization, mirror protocol |
| Distro integration | apt/dnf/brew feed compatibility, delta update support |
| Website UI | Review queue UX, opt-in pull flow, verification widget |
| Edge cases | What happens when a reviewer is unavailable? Stale submissions? |
| Security model | Reviewer identity, Sybil resistance, vote manipulation |

---

## Mental Model

> Version control meets package manager meets document verification —  
> with user consent as a first-class primitive.

---

## Status

**Early / Composable.** Most components are standard and already exist in Phoenix infrastructure. The review layer and advertisement feed are the primary additions.

The spec is intentionally minimal — designed to invite discussion, not foreclose it.

---

Built by JW — Phoenix DevOps OS | UnitedSys — United Systems
GPL-3.0 — Free as in freedom
