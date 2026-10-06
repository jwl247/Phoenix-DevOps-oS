# Day-by-day plan — finish the open work, load-balanced

Made 2026-09-26 (Jerry: "load balance the days and maybe i wont throw wrenches
at us"). Sources: CLAUDE.md NEXT SESSION, docs/plans/phoenix-portal-plan.md,
the parking lot, the server + PBM notes.

## Rules for the days
1. **Money first.** Overhead is real (Claude $125/mo and climbing bills), so
   anything that can bring revenue in goes ahead of polish. Then Laurie. Then
   the build.
2. **Same load each day:** the morning pentest round + one main job + a small
   second job + a **buffer** (the wrenches).
3. **J** = needs Jerry's hands (a click, a login, hardware, a phone call).
   **C** = Claude runs it. J items are kept short so they fit around work.
4. New ideas go to the parking lot, not into the day. The day's job finishes.
5. Every morning, first: the pentest + functionality round (standing order,
   `docs/compliance/pentest/PROTOCOL.md`) until 3 passes in a row.

**SAM.gov registration is FREE.** The $600 offers are private "registration
services". Don't pay them. The Oklahoma APEX Accelerator helps for free.

## The days

**Re-planned 2026-09-29 night (Jerry):** "there were questions surrounding what was and wasn't done and on disk, so we had to deviate — shift the day plan; it needs a CATCH DATE for what backlog is preventing function now; anything we have going is good; we need a completion on our record before we go all-out on the game — namely the Set-Aside Radar (money) and the rest — we need Phoenix done."
So: days 2 and 3 slipped (9/28–9/29 went to the Round 2 audit + fix pass and the Compaq road test, which answered what was really done/on disk). Everything moves on, ordered money → Laurie → what blocks function now, and ends at the **catch date** below. The game waits for the completion gate.

| Day | Status / Main job | Second job | J (Jerry's hands) |
|---|---|---|---|
| **1 · Sun 9/27** | DONE: PBM site live (pbmconsultingservice.com), Resend key → pbm-leads-worker. Left: www redirect, stamp logo on site → Wed 9/30 | — | — |
| **2 · Mon 9/28** | SLIPPED (Round 2 audit): Life First back up → **Thu 10/1** | meds-worker prep → Thu 10/1 | APEX call · Pushover on Laurie's phone (still open) |
| **3 · Tue 9/29** | SLIPPED (fix pass + road test — see `docs/plans/compaq-road-test-plan.md`): meds-worker live → Thu 10/1; Office signed doc → Fri 10/2 | — | — |
| **Wed 9/30** | PROGRESS: Radar billing built + proven end to end in Stripe TEST mode (ask-to-pay → 4242 → webhook → `active`); live mode waits on Laurie's SSI confirmation (appt Thu 10/1). Site: mission retheme (Laurie's story, her OK), Radar "Contract bidding made easy" up top, pink bee, stamp logo, www — all live. Still open: real browser test application, Laurie admin + subscriber, NAICS OK. — **MONEY — Set-Aside Radar taking payment**: one real browser test application (Turnstile proof), Laurie added as admin + subscriber, her OK on NAICS/states, Stripe payment links wired (test mode until the bank account) (C) | PBM site leftovers: www redirect, logo stamp (C) | Submit the test application · Laurie's OK · bank account status |
| **Thu 10/1** | FIRST (Jerry 9/30 night): SSH to the Compaq (`pbm-compaq`) AND the HP both fail — check them before anything that needs them [CHECKED Wed 9/30 11:02: Compaq OK (SSH + mesh 10.47.0.3, up 17h). HP on the direct cable (192.168.137.142) is DEAD: no ARP, nothing on .137.x answers ping, mesh 10.47.0.1 down too. Needs hands: power, cable, screen.] (Life First moves onto the Compaq or pbm3). Laurie's SSI appointment today. — **LAURIE — Life First back up** off the VM onto an always-on box (Compaq or pbm3), tunnelled, proven from outside; **meds-worker live** (check-in, escalate, Jerry looped in, ack) (C) | Radar: first week of digests spot-checked vs SAM.gov (C) | Pushover on Laurie's phone + keys · Laurie OKs reminder wording |
| **Fri 10/2** | **MONEY — Office sellable**: one real signed document with Google sign-in end to end; installer rebuilt + tested on a clean machine; one-page "what you get" ($15–25/mo) (C) | Radar/PBM: discovery-call questions for prospects (C) | The Google sign-in click · try the installer as a customer |
| **Sat 10/3** | **SECURITY — Round 2 security round** filed; close **A2-N1** (keys on `curl` argv) first (C) | A2-N2 VNC OR-policy · A2-N5 narrow sudoers (C) | Decide A2-N2/N3; check jerry.leftwich1 audit log / members / tokens (A2-N4) |
| **Sun 10/4** | **PHOENIX — clone pool done**: R2 is home, local only when pinned; big suites in R2, qemu/debian pinned into E:, `usys` finds its suites again, D:/F: old pools tidied (C) | HUD + dashboard: Jerry's play-test findings fixed (C) | Play with HUD + dashboard, list what's wrong |
| **Mon 10/5** | **PHOENIX — "worker up" is one command** (`usys worker up/down <machine>` over `sector3/worker-up/`), runbook `docs/runbooks/worker-up.md` (C) | Security leftovers: `lifefirst-mustanswer` into the repo + PHOENIX_AUTH, secret scan of full history, Round 1 on the 4 unreviewed workers (C) | Decide orphan D1s (`workorder-kernel-db`, `phoenix-archive`) |
| **Tue 10/6** | **PHOENIX — the deciding test**: Helix vs standard caching, working set larger than RAM (page cache, bcache/lvmcache) → keep/replace ingress Helix (C) | Mesh leftovers: switchboard to its own account, block-direct fallback test (C) | Stay off the Compaq while it runs · swap its network cable |
| **Wed 10/7** | **Buffer** — whatever the wrenches pushed (C) | Portal plan re-cut (web dash on the net + H.L.K's hands + PS7) (C) | — |
| **CATCH DATE · Thu 10/8** | **Completion gate** — every item below checked and recorded (commit + SESSION-LOG + addendum), or moved with a reason. Then the game. | | Sign off |

## Completion gate — "Phoenix done" for the record (catch date Thu 10/8)
Nothing here is new work; it's what's already started or promised, finished and proven:
1. **Money:** Set-Aside Radar live AND able to take payment (Stripe links; live mode the day the bank account exists). Office sellable (signed doc end to end, installer tested).
2. **Laurie:** Life First page back up and reachable from outside; meds-worker live with her guardrail on.
3. **Security:** Round 2 security round filed; A2-N1 closed; pentest rounds continue every morning toward 3 passes.
4. **Phoenix core:** versioning real (DONE 9/29 — 408 version keys backfilled) · Atlas current (DONE 9/29, 138 nodes) · packages-worker 3.6.0 live (DONE 9/29) · clone pool = R2 home, local only when pinned · `worker up` one command · Helix-vs-standard decided on numbers.
5. **Tools Jerry uses:** HUD and dashboard play-tested by Jerry, findings fixed.
6. **Record:** CLAUDE.md BUILD STATUS, SESSION-LOG and the compliance addenda say all of the above.

**After the catch date: the game** — Windows client path, content packs from R2, game-server design, H.L.K on a modern PC, the KITT master class (see plan §6 and CLAUDE.md NEXT SESSION).

## Parked for after the game starts
Office Module 4 · PBM-branded Office build · Project Assist material tracking ·
Tool Hut + customer portal · Helix everywhere (restore the Dandelion) · paging
manager into Helix · the game's planning pass · the phone.
