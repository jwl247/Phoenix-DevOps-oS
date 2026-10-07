# Clone -- Sector 2: getting files OUT of the clone pool
**USys -- United Systems | jwl247**
**Sector:** 2 -- Intake / Package Handler
**Status:** Active (rewritten 2026-10-07: `clone` is OUT since 10-02/10-06, d68007f; audit CMDWALK-F05/F06)

---

## IN and OUT

| Direction | Command | What it does |
|-----------|---------|--------------|
| **IN** | `intake <file-or-folder>` (also `scripts/hsf-intake.sh`) | hex identity, sidecar, pool version, custody, D1 + R2 |
| **OUT** | `clone <name> [vN] [folder] [--force]` | the pool's copy into this folder (or `folder`), checked against its D1 hash first |

`clone` never puts anything INTO the pool. If a name isn't in the pool yet, it says so and tells you to `intake` it.

---

## Files

| File | Purpose |
|------|---------|
| `bin/clone` | The one clone engine (bash): runs `intake.sh clone` |
| `bin/clone.cmd` | Windows (cmd / PS7): runs `bin/clone` through Git Bash |
| `scripts/usys.ps1` | `usys clone` = `Invoke-UsysCloneOut` → `bin/clone` |
| `tools/clone.sh`, `tools/clone.ps1` | Forwarders to `bin/clone` / `bin/clone.cmd` (were the old IN command) |
| `sector2/package-handler/intake.sh` | The engine behind both IN and OUT |
| `sector2/package-handler/worker/index.js` | packages-worker -- D1 custody + R2 bytes |

Installed by `install.ps1` / `install.sh` (`~/.usys/bin` forwarders); no profile line needed.

---

## Environment

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `PHOENIX_AUTH` | for R2/D1 | -- | packages-worker key (read from a 0600 header file, never argv) |
| `PHOENIX_WORKER_URL` | for R2/D1 | packages-worker | worker URL |
| `CLONEPOOL_DIR` | No | `~/Phoenix/clonepool` | Local pool |

---

## Usage

```bash
clone frank_helix.py          # latest version into this folder
clone frank_helix.py v3       # a ledger version (D1's label), checked byte-for-byte
clone kernels ./ops           # a whole intaked folder into ./ops
clone frank_helix.py --force  # overwrite an existing local file
```

## What happens

```
clone <name> [vN]
   |
 local pool has it?  -- no --> R2 (current key, or <hex>/versions/<sha3[0:16]> for an older vN)
   |                                |
 hash vs the D1 baseline  <---------+
   |
 match: copied out, "Integrity verified"   mismatch / unvouched: STOP, nothing handed out
```

Offline, the local copy is checked against its own sidecar sha256 and the output says it is unverified.

---

## QR State

| QR | State | Meaning |
|----|-------|---------|
| Top -- White | Active | File is good, current |
| Top -- Grey | Deprecated | Older version, superseded |
| Top -- Black | Compromised | Do not use |
| Bottom | Location | T1/T2/T3/T4 -- max 4 deep |

---

*Built by JW -- Phoenix DevOps OS | USys -- United Systems | GPL-3.0*
