# sector1/security — CoPES guardian / honeypot layer

Moving-target defense for Phoenix. Four guardians, one active at a time, the
other three sitting as honeypots. Rotation is randomized (180–600s) so a
prober can't learn who's watching; hit an inactive guardian and it
force-rotates and logs you.

| Guardian | Sector | Watches for |
|---|---|---|
| Alpha | 1 — boot/auth | `auth_failure` (3 → escalate), `auth_success` (resets), `kernel_tamper` |
| Beta  | 2 — process/intake | `process_spawn` (nc/socat/proxychains…), `clone_pool_tamper`, `suite_unrecognized` |
| Gamma | 3 — net/file | `file_motion` on sensitive paths, `network_connection` on SOCKS/proxy ports, `translator_breach` |
| Delta | 4 — custody/vault | `integrity_check` mismatch, `vault_write` not from Frank, `helix_tamper` |

## History

Written months ago, then sat in `archive/…/SECTOR4/copes/src/security/` with
**zero call sites** — `copes_runtime.py`'s own docstring claimed it was
"called at CoPES boot"; nothing called it. Resurrected 2026-09-09 per the
security audit (`docs/sec audit doc from you to you.txt`, Tier 1 #4):

- moved into the live tree here, made an importable package (relative imports,
  `__init__.py`), removed the library-rude `logging.basicConfig` from the rotator
- added the **dispatch / escalation seam** (`copes_runtime.dispatch`,
  `copes_runtime.boot(on_escalate=…)`, `escalation_sink` on the rotator) — an
  active guardian hitting its threshold and a honeypot being probed now both
  land in one choke point that logs + persists + calls the app sink
- wired two real event sources: `sector1/kernel/main_kernel.py` `boot()` arms
  it; `sector1/auth/phoenix_auth.py` feeds `auth_failure` / `auth_success`

The fossil copy under `archive/` is left as historical record; **this** copy
is authoritative.

## Use

```python
# boot entrypoint (once)
from security import copes_runtime
copes_runtime.boot(on_escalate=my_sink)     # my_sink(incident: dict), optional

# any event source (safe before boot, never raises)
copes_runtime.dispatch({"type": "auth_failure", "source": "10.0.0.5"})

copes_runtime.status()   # {"armed": True, "active_guardian": "beta", ...}
```

Escalations are always appended to `PHOENIX_GUARDIAN_LOG` (default
`~/.unitedsys/logs/guardian_incidents.jsonl`), one JSON object per line, plus
whatever `on_escalate` does.

## Test

```
cd sector1 && python -m security.test_guardians      # 20/20
```

Covers: boot arms the rotator · dispatch is inert before boot and on unknown
events · an ACTIVE guardian escalates on threshold · a HONEYPOT guardian
reports the contact → forced rotation + sink fires · every escalation is
persisted.

## Not yet wired (audit T1 #1 + #3, next)

- `usys.ps1` → a Beta `suite_unrecognized` event when `usys run` executes an
  unknown or permission-violating suite. Deferred: it's coupled to the
  suite-permission-enforcement work that doesn't exist yet. The route
  (`suite_unrecognized` → Beta) is already in `_ROUTE`.
- Gamma/Delta have no live feeders yet (no file/network watcher, no vault
  write hook). Their detection logic is ready; they need event sources.

## Note

`honeypot.py` (the standalone `Honeypot` wrapper class) is kept for reference
but is **not** on the live path — honeypot behavior lives in
`GuardianBase.go_honeypot()` / `handle_contact()`, which the rotator drives.
It also passes a `str` where the rotator expects a `GuardianID`; don't wire it
without fixing that.
