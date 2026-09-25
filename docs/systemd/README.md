# Phoenix Systemd Corridor

> **⚠️ Never fully deployed — verified 2026-09-24.** Root `CLAUDE.md` § BUILD STATUS Phase 5
> still lists `install-units.sh` as un-run on the real external Ubuntu build target. The real,
> current unit files live at `sector3/services/` (not a flat `systemd/` dir), and today only
> `phoenix-sector1.target` and `phoenix-sector2.target` actually exist there — there is no
> `phoenix-sector3.target` or `phoenix-sector4.target`, so the "Start full stack" command below
> does not work as written. `phoenix-log-setup.service` (which the installer tries to enable
> first) doesn't currently exist either. Units that DID land: `phoenix-dashboard.service`,
> `phoenix-helix-kernel.service`, `phoenix-ollama.service`, `frank3-slot-a/b.service`,
> `phoenix-desktop.target` — none of them mentioned in this doc, because it predates them.

The real path today, until Phase 5 is finished for real, is the Windows-side dev flow (repo
root `README.md` → `usys` CLI + the Electron dashboard), not this systemd corridor. Everything
below describes the original design intent for the eventual external-Ubuntu deployment.

## Install (design intent — partially real, not verified end-to-end)

```zsh
cd sector3/services
sudo zsh install-units.sh
```

## Start / Stop (only the sector1/2 targets currently exist)

```zsh
# What actually exists today:
sudo systemctl start phoenix-sector1.target
sudo systemctl start phoenix-sector2.target

# Watch live
journalctl -u 'phoenix-*' -f

# Status
systemctl status 'phoenix-*'
```

## Startup Order (as designed — sector3/4 portion not built)

```
log-setup → auto-config → frankenhelix → frank-helix
  → intent-parser → propagator + mega-security
      → unoserver → doc-worker + scheduler
          → translator → romeo + juliet         [not wired into systemd yet]
              → intake → rsync-clone.timer       [not wired into systemd yet]
```

## Notes

- All units run as `jwl247` except `phoenix-mega-security` (root)
- Delete `/var/lib/phoenix/auto-config.done` to re-run auto-config
- The sector3/4 half of this chain (translator/romeo/juliet/intake/rsync-clone) has real code
  (`sector3/translator/translator.sh`, `sector3/romeo_juliet/romeo.py`+`juliet.py`,
  `sector2/package-handler/intake.sh`) but is not currently invoked via systemd units — it's
  run directly (`usys clone`, etc.) on the Windows/Debian-VM dev flow instead.
