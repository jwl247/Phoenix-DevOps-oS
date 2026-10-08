# Handoff — 2026-10-07 night (read this first, then CLAUDE.md NEXT SESSION)

Everything below is committed and pushed (`main`). Jerry called it at a stopping point.

## 0. Start the next session with
```
Read docs/history/HANDOFF-2026-10-07-night.md and CLAUDE.md. Check the file sweep finished (§3), run
heal_check for PBMII, then carry on with the Console list. Fix without asking, re-run every change the way
I would, commit + push as you go. Ask me only for real decisions, in plain text, never popups.
```

## 1. Done tonight (verified)
- **HUD:** Suit look-up (tray "Suit look-up…" + Console SUITS). The eye steps aside for full-screen apps + "Hide the eye" in the tray — verified live (hid with a full-screen window in front, came back after). HUD running.
- **Kernel:** Helix-I binds before reporting; a port held by another process -> banner DEGRADED (it used to say OPERATIONAL while `tools/poc/true_double_helix.py` ate every stage). PoC stopped; `stage_check` answers.
- **Intake:** path-aware identity (a name another file holds -> folder/name; folder intake guarded; clone/genie/HUD handle it); companion bug fixed. `scripts/pool-bundles.sh` = the repo section of the pool (phoenix-sector1..4.tar + phoenix-system.tar, deterministic).
- **Heal step 1** (`scripts/heal_check.py`, check only): pbmIII report in `docs/heal/`. Its 16 systemd units + the loaded `helix.ko` are now in the pool (Jerry's yes).
- **Compaq:** `ssh pbm-compaq` fixed; TV display (nomodeset kept + GRUB_GFXMODE 1024x768), LightDM, Chrome, HDMI audio forced. Don't switch back to GDM / don't retry nouveau on that TV.
- **romeo/juliet** create `~/.catalog` first.
- **The ring** — talked out with Jerry, recorded, NOT committed to build ("we can build the game"): `docs/plans/ring-build-plan.md` (+ sketch notes, press-room/1-4.jpg). Claude's honest estimate ~B.
- **Benches** (raw JSON committed next to each script): storage `sector1/helix/bench_three.py` (6 contenders), routers `bench_routers.py` (3), ring baseline `sector4/ring/bench_ring.py`. Jerry's dm-helix by-hand bench: `docs/helix/BENCH-BY-HAND.md` (not run).

## 2. Jerry's calls tonight (also in memory)
Ring/sisters/universe-and-satellites design recorded but the game comes first · Freewheeling = the stage + the ring's shared memory bus · Frank sorts, Free holds, Helix pushes/pulls · prefetch = 3 tiers on the 3 sisters · colors primary/secondary/tertiary = T1/T2/T3, bottom QR = tier color, top QR = shade · ring 4 = system · Compaq = router (to build), the other HP = final storage, both go headless eventually · Helix benches: Jerry runs his own dm-helix one; Claude ran the Python ones when asked.

## 3. In flight at session end
- **The per-file sweep** of every non-archive file (1,083) was running in the background (117 done at handoff time, 0 failures), then `pool-bundles.sh system`. If the session ended it: re-run
  `cd /f/Phoenix/Phoenix-DevOps-oS && git ls-files -co --exclude-standard | grep -v '^archive/' > /tmp/s.lf && mapfile -t F < /tmp/s.lf && bash scripts/hsf-intake.sh "${F[@]}" </dev/null` (Git Bash; already-pooled files come back "Kept existing").
  Sensitive-named files are refused unattended (rule 10) — `pbm-authority-plan.md` needs Jerry's yes at a terminal.
- Then `python scripts/heal_check.py --box pbmii`.

## 4. Open
- **Waiting on Jerry:** sync the 3 stale scripts on pbmIII (recover/harden/shares — changes the box); which `openjarvis.service` is current; 3.9.0 member keys so the Compaq can pull from R2 (mark qcow2 + vault.enc sensitive first); the HP powered on for its heal check; rename `Testing Facilty/juliet.py` -> `dbl_juliet.py` + the real juliet beside it; MSYS2 compiler only if he wants the C helix benched; plus the evening handoff §4 list.
- **Jerry added at session end:** (1) **a driver updater** — design with Jerry first: which machines, which drivers; never storage drivers or anything that blacklists/sets drives readonly (AI SAFETY rules 2-4), GPU drivers stay off Phoenix OS (rule 6), every driver change = rule 9 (state it, his yes); (2) **aliases** — the zsh-style PS7 aliases still on the backlog (the 10/7 evening set `g pulse pb3 aws1 box snap lastsnap repo .. ... glog gst here pool` already exists in `scripts/phoenix-aliases.ps1`); ask which ones he wants.
- **Claude can do:** Console list items 2-4; a directory's own version never advances past v1; security A2-N1 (keys on curl argv).

## 5. Gotchas learned tonight
- Heredocs eat backslashes (again): write Python edit scripts with the Write tool, or use the Edit tool.
- The HUD overlay takes ~45 s to appear after launch (voice models); test it after that.
- A desktop-window test from a background shell needs SetForegroundWindow, and PowerShell `Add-Type` helpers don't carry between calls — define and use them in one command.
- `ssh pbm-compaq` reads root-only units only via `sudo -n` (passwordless works for user a).
