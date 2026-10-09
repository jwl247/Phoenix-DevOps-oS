# Sector map 2026-10-09: now -> goes

Rule (8 sectors, by ROLE judged from code): S1 ring zero/kernel/boot · S2 apps people use · S3 system function + output (mesh, heal, restore, translator, romeo/juliet, units, output workers) · S4 storage (pool tiers, userspace Helix, paging, best_drive, drive layout) · S5 .lol hub = package handler · S6 security/guard · S7 AI layer · S8 faces (console, dashboard, HUD look). Not sectors: PRODUCT (stays top-level), ARCHIVE, DOCS (stays). Labels only, NOT move orders.

| Now (path) | Goes | Why (<=8 words) |
|---|---|---|
| sector1/auth/ | S1 | phoenix_auth hardware fingerprint |
| sector1/concierge/ | S3 | TCP 9900 envelope bridge (WSL-era text) |
| sector1/grub/ | SPLIT | see Splits |
| sector1/helix/ | SPLIT | userspace Helix stack; see Splits |
| sector1/helix-lightning/ | S1 | H.L.K: Frank5, spawn, process library, gate |
| sector1/kernel/ | SPLIT | Universal Kernel + LLM engine; see Splits |
| sector1/kernels/ | S1 | dm-helix, helix_kmod, frank3 slots, libhelix |
| sector1/security/ | S6 | CoPES guardians, honeypot, harden script |
| sector1/saddle_block.sh | ARCHIVE | WSL /etc overwrite; WSL is out (10/9 call) |
| sector2/apps/game/ | PRODUCT | companion voice note for the game |
| sector2/apps/jarvis/ | S7 | Jarvis gate, tools, identity, llm unit |
| sector2/apps/lifefirst/ | SPLIT | PHP fossil + live meds-worker; see Splits |
| sector2/apps/lifefirst-android/ | ARCHIVE | Firebase Android fossil |
| sector2/apps/office/ | SPLIT | internal Office; notify-worker is output |
| sector2/apps/peer-review/ | S2 | Review Platform worker (webauthn, discord) |
| sector2/apps/scriptforge/ | S2 | ScriptForge app |
| sector2/apps/security/ | S6 | security suit + installers |
| sector2/assets/ | S2 | logo only |
| sector2/frank/ | SPLIT | best_drive storage + HTTP status bridge |
| sector2/package-handler/ | SPLIT | the hub; key rotation scripts are S6 |
| sector2/propagator/ | S3 | signal propagator + dispatch |
| sector2/ring0/ | S4 | Frank orchestrator, not privileged (10/9 call) |
| sector2/unitedsys/ | S5 | us.py, 9+ backends, catalog, glossary, verify |
| sector3/encompass/ (untracked) | S3 | multi-PC compute fabric coordination |
| sector3/hlk/ | SPLIT | model brain -> S7, ingress/egress movers -> S4 (10/9 call) |
| sector3/mailbox/ (untracked) | S3 | ingress/egress courier between boxes |
| sector3/mesh/ | S3 | Nebula hosts, buddy healer, peer agent |
| sector3/netboot/ | S3 | netboot |
| sector3/phoenix-net/ | ARCHIVE | retired WireGuard net |
| sector3/phone-node/ | S3 | phone mesh node |
| sector3/quadengine/ | S3 | four-stream language engine |
| sector3/restore/ | S3 | manifest + restore |
| sector3/romeo_juliet/ | S3 | ingress/egress |
| sector3/services/ | S3 | systemd units + install-units |
| sector3/translator/ | S3 | translator.sh, output only |
| sector3/worker-up/ | S3 | worker box bring-up scripts |
| sector3/workers/packages-worker/ | ARCHIVE | stale copy, differs from package-handler/worker |
| sector4/intake/ | S5 | second intake engine (B->C); marry into one |
| sector4/paging*.py, pcs.py | S4 | Doppelganger paging (Linux/Windows/kernel) |
| sector4/vault/ | S4 | rsync into breach_coms4 master vault (10/9 call; worker/ checked at move) |
| sector4/ring/ (bench tracked, rest untracked) | SPLIT | engine team; see Splits |
| sector4/*.py,*.sh,*.json (untracked) | SPLIT | same team as ring/; see Duplicates |
| scripts/usys.ps1, usys.cmd, intake.ps1, hsf-intake.sh, pool-bundles.sh, phoenix-aliases.ps1, phoenix-commands-sheet.ps1, usys-suite-gate.Tests.ps1 | S5 | .lol/usys front door + intake |
| scripts/system_snapshot.py | S5 | whole system as one custody object |
| scripts/handoff.ps1 (untracked) | S5 | handoff in the pool, SHA3 marker |
| scripts/phoenix_vault.py, test_phoenix_vault.py, phoenix-rotate.ps1, setup-rotate-token.ps1 | S6 | vault + key rotation |
| scripts/phoenix-seal.ps1 (untracked) | S6 | signed catalog of profile files |
| scripts/hardening/, compliance-local-check.ps1, install-compliance-check-autostart.ps1 | S6 | hardening + compliance checks |
| scripts/shares/, heal_check.py, node-up.sh, node_session*, test_node_session.py, pbmiii-up.ps1, compaq_bootstrap.sh, phoenix-box-setup.sh | S3 | node bring-up, shares, healing |
| scripts/phoenix-paths.ps1, phoenix_paths.py, phoenix-goto.ps1 | S4 | slash-insensitive path layer |
| scripts/phoenix-engine.ps1 | S7 | Jarvis alternate engine, CPU-pinned |
| scripts/snap-to-claude.ps1 | S7 | screenshot to Claude |
| scripts/test_game_session.py | PRODUCT | game session test |
| scripts/hooks/ | S5 | post-commit hook |
| tools/align_dirs.sh | S4 | path parity VM vs bare metal |
| tools/clone.ps1, clone.sh, get_distros.sh | S5 | clone out + distro catalog |
| tools/driver-updater/ | S1 | driver updates (privileged) |
| tools/notation/ | S2 | Music Notation |
| tools/phoenix-tray.* | S8 | tray face |
| tools/poc/ | SPLIT | Helix POC, VM boot, suites; see Splits |
| tools/video/ | PRODUCT | PBM channel art, OBS, voice record |
| hud/ | SPLIT | WPF face + AI/voice brain; see Splits |
| hud.checks/ | S8 | HUD checks harness |
| dashboard/ | SPLIT | Electron face; see Splits |
| portal/ | S8 | Console web page on the mesh |
| hands/ | S7 | AI's fixed tool list, permission tiers |
| bin/ | SPLIT | command shims; see Splits |
| bootstrap/ | S5 | lol-bootstrap |
| deploy/ | S3 | deploy.sh (windows/start-wsl.sh -> ARCHIVE) |
| phoenix-core/ | SPLIT | C Helix engine + intake.py engine C |
| install.ps1, install.sh (root) | S5 | installs the .lol hub |
| status.sh (root) | S3 | system status |
| franken.py (root, untracked) | S4 | duplicate of sector4/franken.py |
| Testing Facilty/ (untracked) | SPLIT | scratch copies; see Duplicates |
| .claude/ | S7 | Atlas skill + look command |
| tentative-wares/ | SPLIT | staged: dashboard S8, genie-cloud S1, PH 3.9.0 S5, peer-review S2 |
| metsec files/ | SPLIT | sec, sec2, motiondet, grounds-keeper S6; sec3 ARCHIVE |
| game/ | PRODUCT | Sacrifice game + worker |
| phoenix-office/ | PRODUCT | standalone Office sister |
| pbm-consulting-website/ | PRODUCT | PBM site + radar worker |
| press-room/ | PRODUCT | build plan, blog, outreach |
| docs/ | DOCS | stays |
| archive/ | ARCHIVE | fossil consolidations |
| .metadata/ | ARCHIVE | Eclipse junk |

## Splits
- **sector1/grub/**: grub/grub.cfg, scripts/build_*.sh, install_phoenix_grub.sh -> S1 · gen_key.sh, pam_phoenix_key.sh -> S6 · usys.sh, phoenix_aliases.sh, d1_config.json, phoenix_dev_db.sql -> S5 · recover_scripts.sh -> S3
- **sector1/helix/**: helix_complete_stack/package, helix_fuse, helix_slim, helix_vram, benches -> S4 · kernel/ (helix_kernel.c) -> S1 · conf/helix_mesh.conf, helix_translator.py -> S3
- **sector1/kernel/**: genie/, main_kernel.py, phoenix_core.py, phoenix_kernel/, setup.sh -> S1 · llm_engine.py -> S7 · file_tree_service.py -> S4 · phoenix_status_server.py -> S3
- **sector2/apps/lifefirst/**: *.php, *.sql, *.sh, laurie/, security/ -> ARCHIVE · meds-worker/ -> S3 · suits/lifefirst_checkin.py -> S2
- **sector2/apps/office/**: index.html, lib/, templates/, test/ -> S2 · notify-worker/ -> S3
- **sector2/frank/**: frank_save.py (best_drive), frank_helix.py -> S4 · frank_http.py, frank_client.js -> S3
- **sector2/package-handler/**: intake.sh, worker/, r2-worker/, suit_build.py, parse-connections.js, pool-tidy, backfill -> S5 · rotate-access-token.sh, rotate-phoenix-auth.sh -> S6 · push-context.*, sync-standalone.sh -> S3
- **sector4/ring/ + sector4/ loose**: franken.py, freewheeling.py, helix_api.py, helix_new_horizon.py, conductor_sync.py, syncthing_module.*, bench_ring.py -> S4 · propcoms.*, quadengine.py, rebound.* -> S3 · integrated_guardian.py, file_guardian.json, helixaudit.sh -> S6 · installer_registry.json, member.py, ring.json, team.json, ringhome.py -> S5
- **tools/poc/**: true_double_helix.py, *double-helix*, run-helix-poc.*, install-helix-autostart, setup-shared-fs, persist-smb-mount, start-debian-persist -> S4 · run-debian/ubuntu, *-seed/, qemu/debian/ubuntu suites -> S1 · google/steam/yt-dlp/hello suites, watch-downloads.ps1 -> S5 · demo-collab.* -> ARCHIVE
- **hud/**: *.xaml, Controls/, TrayIcon, HudOverlay*, CheatSheet, UsysButtons, ConsoleActions -> S8 · AiChatService, ClaudeCodeSession, HandsClient, ScreenCaptureService, Voice/ -> S7 · Desktop/ (PoolClient, AtlasClient, FileActions), SuitLookup -> S5
- **dashboard/**: index.html, main.js, hud-*, launchers, terminal-pty, ps7-shell, styles -> S8 · config-centralizer* -> S2 · manual/LAURIE_GUIDE.md -> S2 · clonepool-workdir.js, slot-transfer.js -> S5 · screenshot-analysis.js -> S7 · _backup-2026-10-03/ -> ARCHIVE
- **bin/**: intake, clone, lol, usys, get_distros, phoenix-map -> S5 · align_dirs, phoenix-paths.sh -> S4 · jarvis -> S7 · status, run -> S3
- **phoenix-core/**: src/, include/, tests/, tools/main.c -> S1 · tools/intake.py -> S5 (engine C, retire into the one intake)
- **Testing Facilty/**: all five files are copies; capulet.py, juliet.py -> S3 · franken.py, helix_slim.py, helix_new_horizon.py -> S4

## Duplicates / same file in two places (sha256, first 12)
- franken.py: root = sector4/ = sector4/ring/ = Testing Facilty/ (d8790092dec3, all 4 identical)
- Identical sector4/ vs sector4/ring/: conductor_sync.py, file_guardian.json, freewheeling.py, helixaudit.sh, integrated_guardian.py, propcoms.sh
- DIFFER sector4/ vs sector4/ring/: helix_api.py, installer_registry.json, propcoms.py, quadengine.py
- sector4/syncthing_module.py = sector4/ring/syncthing_module.js (same bytes; JS under a .py name)
- quadengine.py: three different versions (sector3/quadengine, sector4/, sector4/ring)
- propcoms.sh: sector2/propagator differs from sector4/ (= sector4/ring)
- helix_slim.py: sector1/helix = Testing Facilty (identical)
- helix_new_horizon.py: sector4/ring differs from Testing Facilty
- juliet.py: sector3/romeo_juliet differs from Testing Facilty
- main_kernel.py: sector1/kernel differs from sector1/helix-lightning
- frank_ring.py = frank_ring-1.py (sector1/helix-lightning, identical)
- packages-worker index.js: sector2/package-handler/worker differs from sector3/workers/packages-worker (stale)
- helix.h: sector1/kernels differs from phoenix-core/include
- hardening: sector1/security/harden_debian_box.sh differs from scripts/hardening/phoenix-harden.sh (overlapping role)
- intake engines: sector2/package-handler/intake.sh (A) vs sector4/intake/intake.sh (B) -> phoenix-core/tools/intake.py (C)

## Counts (table rows; SPLIT rows counted as SPLIT)
S1 5 · S2 4 · S3 16 · S4 5 · S5 9 · S6 6 · S7 6 · S8 3 · PRODUCT 7 · ARCHIVE 5 · DOCS 1 · SPLIT 17 (84 rows)
