# Sector 4 — Master Vault

> **⚠️ Design-intent doc, not verified current — see `docs/README.md`'s status banner.** Per
> `sector4/CONNECTIONS.md`, Sector 4 today is much thinner on disk than this doc implies —
> `helix/`/`frank/` subdirectories described elsewhere in root `CLAUDE.md` don't currently
> exist here (likely relocated; a fossil copy is archived). The real, current file is
> `sector4/intake/intake.sh`, which has a known live bash syntax bug — `usys clone` (routing to
> the separate, canonical `sector2/package-handler/intake.sh`) is the working intake path, not
> this one. breach_coms1-4 ARE real physical drives (see root `CLAUDE.md` AI SAFETY RULES) —
> that part of this doc is accurate, just not reachable via `/media/jwl247/...` specifically on
> every machine. For what's actually live in Sector 4 today, use `sector4/CONNECTIONS.md`.

Path: `breach_coms4`

End of the corridor. Master vault through intake. rsync clone chain populates breach_coms3 → 2 → 1 every 15 minutes.

## Files

| File | Role |
|------|------|
| `intake.sh` | TAV SQL versioning chain. All data enters the vault through here. |

## Clone Chain

```
breach_coms4 (master)
    └─ rsync → breach_coms3
                   └─ rsync → breach_coms2
                                   └─ rsync → breach_coms1
```

Timer fires 5 minutes after boot, every 15 minutes thereafter. Persistent — catches up on missed runs after downtime.

## Systemd Units

```
phoenix-intake.service         after sector3.target
phoenix-rsync-clone.service    oneshot clone chain
phoenix-rsync-clone.timer      5min after boot, every 15min
```
