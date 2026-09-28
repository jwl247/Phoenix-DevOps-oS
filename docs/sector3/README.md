# Sector 3 — Translator Boundary

> **⚠️ Design-intent doc, not verified current — see `docs/README.md`'s status banner.** The
> output-only rule and romeo/juliet ingress-egress split are still real and current (this is
> Phoenix's Critical Rule #2/#3), but `romeo.py`/`juliet.py` now live at
> `sector3/romeo_juliet/`, not a bare path under `/etc/systemd/system/`, and are not currently
> run as systemd services. For what's actually live in Sector 3 today, use
> `sector3/CONNECTIONS.md`.

Path: `/etc/systemd/system/`

Platform edge. `translator.sh` fires on output only. Everything upstream stays quadralingual until this boundary. Romeo handles ingress, Juliet handles egress.

## Files

| File | Role |
|------|------|
| `translator.sh` | Output-only translator. Fires at sector boundary. Quadralingual kept clean upstream. |
| `romeo.py` | Ingress handler. ZMQ PULL on 5580 (loopback), pushes to Juliet at `PHOENIX_RJ_PEER` (default localhost:5581), signs the hop with `PHOENIX_RJ_SECRET`. |
| `juliet.py` | Egress handler. ZMQ PULL on 5581 in, PUSH on 5582 out (barrel N: 5581+2(N-1) / 5582+2(N-1)). Refuses unsigned/replayed messages when the secret is set; refuses to bind off-loopback without it. `translator.sh` fires here, on output only. |
| `dbl_juliet.py` | Two barrels + a boundary monitor (PULL on 5582 and 5584). |

## Critical Rule

Translator fires on **output only**. Never on ingress. Everything stays quad-native (NoSQL / relational / vector / time-series) until this boundary.

## Systemd Units

```
phoenix-translator.service    after sector2.target
(no romeo/juliet units exist yet — they run inside the helix-team suite,
 tools/helix-team/run-team.sh, as the ingress and egress halves)
```
