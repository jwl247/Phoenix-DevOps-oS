# Phoenix-DevOps-oS

> **⚠️ Status, verified 2026-09-24:** the systemd "corridor" install described below (this file,
> `docs/sector1..4/README.md`, `docs/systemd/README.md`, `docs/config/README.md`) was never
> fully completed or deployed — root `CLAUDE.md` § BUILD STATUS Phase 5 still shows
> `install-units.sh` as un-run. Confirmed live: `phoenix-sector1.target`/`phoenix-sector2.target`
> exist in `sector3/services/`, but `phoenix-sector3.target`/`phoenix-sector4.target` (which the
> "Quick Start" below tells you to start) **do not exist**, and `intent_parser.py` /
> `mega_system_manager.py` don't exist anywhere outside `archive/`. Some pieces described here
> did land, just under different paths than shown (e.g. `frankenhelix.py` → `sector2/ring0/`,
> `romeo.py`/`juliet.py` → `sector3/romeo_juliet/`). **For what's actually live and how to
> actually start Phoenix today, use root `CLAUDE.md` (canonical, updated every session) and the
> per-sector `CONNECTIONS.md` files (`sector1/CONNECTIONS.md` etc., verified against real code)
> instead of this doc set.** Left in place as historical/aspirational design intent, not a
> working install guide.

Multi-OS quad-native infrastructure framework. Distro-agnostic operation across Linux and Windows. Built by Jerry Leftwich (jwl247) — Phoenix DevOps LLC.

## Architecture

Four sector corridor managed by systemd (design intent). Everything travels the corridor in order. The `intent_parser.py` service bus this design routed everything through is not in this repo (neither the live tree nor `archive/`, checked 2026-09-29) — nothing live routes through it.

```
S1 → S2 → S3 → S4
```

| Sector | Path | Role |
|--------|------|------|
| 1 | `/etc/` | Kernels, hardware, boot layer |
| 2 | `/etc/systemd/` | Services, scheduler, doc worker, Life First suite |
| 3 | `/etc/systemd/system/` | Translator boundary — Romeo/Juliet ingress/egress |
| 4 | `breach_coms4` | Master vault, intake, rsync clone chain |

## Repo Structure

As it is on disk (verified 2026-09-28; each sector's `CONNECTIONS.md` is the authoritative inventory):

```
sector1/            Boot, kernels (frank3 slots, dm-helix), auth, concierge, CoPES security — sector1/CONNECTIONS.md
sector2/            Package handler (intake.sh, packages-worker), frank/, ring0/, propagator/ (dispatch.json), apps/ — sector2/CONNECTIONS.md
sector3/            translator/translator.sh, romeo_juliet/, quadengine/, phoenix-net/, services/ (all unit files + install-units.sh) — sector3/CONNECTIONS.md
sector4/            intake/intake.sh, vault/, paging.py — sector4/CONNECTIONS.md
docs/               This doc set, compliance/, history/, plans/, helix/BENCHMARKS.md — docs/CONNECTIONS.md
```

There is no root `systemd/` or `config/` directory: unit files live in `sector3/services/`, `dispatch.json` in `sector2/propagator/`.

## Quick Start

No working corridor start command exists today (see the banner). The unit installer that does exist is `sector3/services/install-units.sh`; it still tries to enable a `phoenix-log-setup.service` that does not exist (round-2 S34OPS-F03). The only targets are `phoenix-sector1.target`, `phoenix-sector2.target` and `phoenix-desktop.target` — there is no sector3 or sector4 target. For how Phoenix is actually started today, use root `CLAUDE.md` and `scripts/usys.ps1`.

## Key Components

Where the pieces named in this design actually live (verified 2026-09-28):

- `sector2/ring0/frankenhelix.py` — ring0 (see `sector2/CONNECTIONS.md`)
- `sector2/frank/frank_helix.py` — Frank RAM daemon (see `sector2/CONNECTIONS.md`)
- `sector2/propagator/propagator.py` + `dispatch.json` — dispatch router
- `sector3/translator/translator.sh` — output-only, Sector 3 boundary (Critical Rule #2)
- `sector4/intake/intake.sh` — vault intake; the live, canonical intake pipeline is `sector2/package-handler/intake.sh` (`usys clone`)
- `intent_parser.py`, `mega_system_manager.py` — not in this repo (neither the live tree nor `archive/`)

## Security

Persistent adversarial threat model. GPU drivers blacklisted. SurfShark VPN, closed firewall whitelisting Anthropic domains only. `phoenix_auth.py` SHA3-512 + BLAKE2b across 10 hardware signals.

## License

See `LICENSE` (GPL-3.0). Life First — `sector2/apps/lifefirst/README.md` (the old `sector2/lifefirst/docs/` path no longer exists). REALsure — Polyform Noncommercial 1.0.0.

## Acknowledgment

Claude (Anthropic) is the designated AI collaborator for this project.
