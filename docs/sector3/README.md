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
| `romeo.py` | Ingress handler. ZMQ PULL port 5560. |
| `juliet.py` | Egress handler. ZMQ PUSH port 5561. |

## Critical Rule

Translator fires on **output only**. Never on ingress. Everything stays quad-native (NoSQL / relational / vector / time-series) until this boundary.

## Systemd Units

```
phoenix-translator.service    after sector2.target
phoenix-romeo.service         after translator, ingress port 5560
phoenix-juliet.service        after translator, egress port 5561
```
