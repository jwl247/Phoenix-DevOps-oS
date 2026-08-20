# Sector 4 — Master Vault

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
