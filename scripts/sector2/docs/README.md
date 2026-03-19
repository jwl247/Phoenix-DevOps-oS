# Phoenix DevOps — Full Propagator Framework
## jwl247 / Phoenix DevOps LLC — GPL-3.0

### Architecture
- **ring0/** — ZZZring0 bidirectional listener, COM1-4 routing (frankenhelix.py)
- **frank/** — RAM pressure daemon, sideload bridge (frank_helix.py)
- **translator/** — Platform edge translator, sector2/3 deployment (translator.sh)
- **propagator/** — dispatch.json routing rules (vault/sql/d1/frank3/peer/windows)
- **quadengine/** — Four simultaneous language streams
- **romeo_juliet/** — Ingress (Romeo) / Egress (Juliet) / Double-Barrel test harness
- **freewheel/** — Four Freewheeling instances (breach_coms1-4)
- **unitedsys/** — Universal package handler, cross-ecosystem
- **intake/** — TAV/intake.sh versioned vault intake
- **helix/** — Helix kernel, translator, HelixFS

### Sector layout
- sector2 = /etc/systemd          (backup/buffer)
- sector3 = /etc/systemd/system   (translator primary)
- sector4 = breach_coms4          (master/source — through intake)

### Deploy
Everything above this line is quadralingual.
Translation only fires at platform boundary (sector3 edge).
sudo required only at deploy time.
