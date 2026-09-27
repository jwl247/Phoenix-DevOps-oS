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

| Day | Main job | Second job | J (Jerry's hands) |
|---|---|---|---|
| **1 · Sun 9/27** | **PBM site LIVE early (2026-09-27 00:40, Workers static assets, https://pbmconsultingservice.com)**; still open: Resend key for the form email + www redirect. Original: **PBM site live**: `pbm-consulting-website` deployed to Cloudflare Pages on pbmconsultingservice.com, Turnstile proven with a real browser, lead form end to end (C) | pbm-leads-worker email: reuse the domain's Resend setup so verification codes actually send (C) | Campaign day: approve anything before it posts · start the free SAM.gov registration for Laurie's company (login.gov) |
| **2 · Mon 9/28** | **Life First back up**: Laurie's page has been offline since the VM went off. Move it off the VM onto a real always-on box (Compaq or pbm3), tunnel it, prove it from outside (C) | meds-worker deploy prep: D1 schema, secrets list ready (C) | Call APEX Accelerator · Pushover app on Laurie's phone + keys for meds-worker |
| **3 · Tue 9/29** | **meds-worker live**: deploy, switch Laurie's guardrail on, full test (check-in, escalate, Jerry looped in, ack) (C) | Office sellable check: one real signed document with Google sign-in, end to end (C) | The Google sign-in click · Laurie OKs the reminder wording |
| **4 · Wed 9/30** | **Office ready to sell**: installer rebuilt + tested on a clean machine, first-run flow, a one-page "what you get" for the hosted tier ($15–25/mo) (C) | Set-Aside Radar: grade Polsia's first week honestly (C) | Try the installer as a customer would |
| **5 · Thu 10/1** | **Rewrite the Portal plan** to the agreed shape (web dash on the net + H.L.K's hands + PS7), phases re-cut (C) | Helix verdict, lean restart, runs overnight on the Compaq ("let her eat") (C) | Stay off the Compaq overnight |
| **6 · Fri 10/2** | ~~Dashboard v0 on the net~~ **DONE early 2026-09-26** (`portal/`, http://precision.phx:8470): `portal.phx` served from the hub: who's online, link health, service status (C) | Record Helix verdict + Compaq Phoronix in `docs/helix/BENCHMARKS.md` (C) | Look at it, say keep/change |
| **7 · Sat 10/3** | **H.L.K's hands v0** on this PC: headless helper, declared tools (open app, `.lol` pull, screen capture), permission tiers, PS7 both ways (C) | Dashboard buttons drive the hands (C) | Try: click, type, talk — same result |
| **8 · Sun 10/4** | **Hands on Compaq + pbm3** (PS7 on Linux), import-on-demand from the clone pool (C) | H.L.K (voice) drives the same hands (C) | — |
| **9 · Mon 10/5** | **Security leftovers**: `lifefirst-mustanswer` source into the repo + PHOENIX_AUTH, secret scanner over full history, Round 1 on the 4 unreviewed workers (C) | Orphan D1s (`workorder-kernel-db`, `phoenix-archive`): keep or drop (C) | Decide the orphan D1s |
| **10 · Tue 10/6** | **Mesh leftovers**: switchboard to its own Cloudflare account, "block direct" fallback test (C) | Discovery-call questions for PBM prospects (C) | Delete the exposed token in the new account first · audit tokens on the jerry.leftwich1 side |
| **11 · Wed 10/7** | **Catch-up day**: whatever the wrenches pushed off days 1–10 | Parity check: can the web dash replace the Electron one? | Keep/cut call on the old dashboard |

## After day 11 (next block, not scheduled yet)
Office Module 4 · PBM-branded Office build · Project Assist material tracking ·
Tool Hut + customer portal · Helix everywhere (restore the Dandelion) · paging
manager into Helix · the game's planning pass · the phone.
