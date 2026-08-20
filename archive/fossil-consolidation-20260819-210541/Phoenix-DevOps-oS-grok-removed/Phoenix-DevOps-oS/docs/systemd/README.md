# Phoenix Systemd Corridor

21 unit files covering all four sectors. One installer.

## Install

```zsh
sudo zsh install-units.sh
```

## Start / Stop

```zsh
# Start full stack
sudo systemctl start phoenix-sector4.target

# Stop full stack
sudo systemctl stop phoenix-sector4.target

# Watch live
journalctl -u 'phoenix-*' -f

# Status
systemctl status 'phoenix-*'
```

## Startup Order

```
log-setup → auto-config → frankenhelix → frank-helix
  → intent-parser → propagator + mega-security
      → unoserver → doc-worker + scheduler
          → translator → romeo + juliet
              → intake → rsync-clone.timer
```

## Notes

- All units run as `jwl247` except `phoenix-mega-security` (root)
- Delete `/var/lib/phoenix/auto-config.done` to re-run auto-config
- Starting `phoenix-sector4.target` pulls entire chain as dependencies
