# Suite Execution Gate

`usys run <suite>` checks two things before it executes anything. One
mechanism, added for security audit **Tier 1 #1 (permission enforcement)** and
**#3 (local execution auth boundary)** — designed as one gate, not two.

Lives in `scripts/usys.ps1` (`Assert-UsysSuiteExecutionAllowed` and helpers,
just above `Invoke-UsysRun`). Tests: `scripts/usys-suite-gate.Tests.ps1`
(16/16, standalone — no Pester).

## What it checks

### 1. Provenance — is the suite trust-stamped on this machine? (#3)

A `.phoenix-trust` file in the suite directory holds an **HMAC-SHA256** over
the entry file's SHA-256 plus the core manifest fields
(`name`, `version`, `runtime`, `entry`), keyed by **this machine's
`PHOENIX_AUTH`**. This is the same "bearer token on every write" pattern the
Cloudflare worker has used since day one (`worker/index.js` `isAuthorized()`),
ported to the local execute-time boundary.

- `usys suite-trust <name>[@ver]` writes the stamp — a deliberate "I vouch for
  this" act.
- Change the entry file → its SHA-256 changes → the stamp no longer verifies →
  the gate treats the suite as unstamped again.
- The stamp is **machine-bound** (keyed by that box's `PHOENIX_AUTH`). A fresh
  machine re-stamps. A stamp copied from another machine does not verify.
- A future `intake.sh` should write this stamp automatically for suites that
  come through the canonical pipeline. Not wired yet.

### 2. Permission — does the manifest's `permissions` ask match what's granted? (#1)

`permissions` entries that count as **elevated**: `network`,
`filesystem:write` (unscoped), `process:spawn`, `env:write`.

| Situation | Result |
|---|---|
| `qemu` (or any non-host) runtime | **pass** — the VM boundary is the sandbox (audit #2). Logged, not challenged. |
| host runtime (`python`/`node`/`bash`/`powershell`/`binary`), trust-stamped | **pass** — granted whatever it declares |
| host runtime, unstamped, no elevated asks | **pass** with a note |
| host runtime, unstamped, **elevated asks** | **REFUSED** unless `--unverified` or an interactive `yes` |

A refusal (or a `--unverified` override) on an unstamped elevated-ask suite
also fires the CoPES **Beta guardian** — `copes_runtime.dispatch({type:
"suite_unrecognized", …})` — via a short-lived background python call. Harmless
when the guardian layer isn't armed (`dispatch` no-ops).

## This is a consent + audit boundary, not a sandbox

The gate does **not** confine what a suite does once it runs — it can't, from a
PowerShell wrapper around an arbitrary subprocess. Real write/network
confinement (Windows Job Object / capped token) is audit **Tier 1 #2**, still
open. What the gate gives you today: nothing host-executing runs with elevated
declared intent unless you've stamped it or explicitly accepted the risk, and
every decision is on the record.

## Audit log

Every decision appends one JSON line to
`~/.unitedsys/logs/suite_exec.jsonl` (override: `PHOENIX_SUITE_EXEC_LOG`):

```json
{"ts":"…","name":"…","version":"…","runtime":"python","entry":"main.py",
 "entry_sha256":"…","permissions":["network"],"trusted":false,
 "decision":"refused","gated_by":"gate"}
```

`decision` ∈ `allow` / `refused` / `bypassed` / `would-block` (dry run).
`gated_by` ∈ `trust-stamp` / `no-elevated-asks` / `vm-contained` /
`unverified-flag` / `interactive-consent` / `gate` / `PHOENIX_SUITE_NO_GATE`.

## Escape hatches

- `usys run <name> --unverified` — one-shot, for a suite you've reviewed
- `usys suite-trust <name>` — permanent (until the entry file changes)
- `PHOENIX_SUITE_NO_GATE=1` — disable the gate entirely (logged as `bypassed`)

## Not done here (rolls forward)

- `intake.sh` auto-stamping trusted suites
- Tier 1 #2 — real sandboxing (Job Object) scoped to the declared permissions
- Tier 3 #8/#9 — `Ball.authorize()` / `Ball.for_family()` in `franken5.py`
  should share this permission model instead of a hardcoded default set
