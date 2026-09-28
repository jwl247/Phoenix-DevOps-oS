# Desk run-sheet — 2026-09-28 (Jerry, from 5 pm)

Everything below needs a machine this cloud session could not reach: the Precision, the
Compaq, pbm3, Cloudflare, Stripe. Run in order; each step says what "done" looks like and
where its evidence lands. Repo branch: `claude/zealous-lamport-63hnfd` (pull it first on the
Precision: `git fetch origin && git checkout claude/zealous-lamport-63hnfd`).

**J** = only you can do it (login, key, decision). **C** = a Claude Code session on the
Precision (the HUD's CLAUDE CODE pane, or the terminal) can run it.

## 0. Ten-minute live probe (closes the "not re-verified" rows in round 3)
- **C** From the Precision (has egress), unauthenticated read-only GETs, paste the output into
  `docs/compliance/pentest/2026-09-28-round3-addendum-2.md`:
  ```bash
  for h in packages-worker pbm-radar-worker pbm-leads-worker phoenix-office-worker office-notify-worker lifefirst-mcp phoenix-mesh-worker lifefirst-mustanswer phoenix-clonepool-r2; do
    for p in / /health /whoami; do printf "%-24s %-8s " $h $p; curl -s -o /dev/null -w "%{http_code} " https://$h.phoenix-jwl.workers.dev$p; curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer garbage" https://$h.phoenix-jwl.workers.dev$p; done; done
  curl -sI https://get.authenticcoder.com/whoami | head -3
  curl -sI https://pbmconsultingservice.com/radar | grep -i content-security
  ```
  Done = every authenticated route answers 401/403/302 without a real token; `phoenix-clonepool-r2` should be gone (round-2 addendum 2); anything else is a new finding.

## 1. Helix team on the Compaq (Phase 1)
- **C** Check the verdict run is finished before deploying: `ssh pbm-compaq 'tail -3 ~/verdict-lean-20260927-1315.log; pgrep -fa phoronix'`. If still running, do step 2 first and come back.
- **C** `tools/helix-team/deploy-compaq.sh pbm-compaq` — ships HEAD to `/opt/phoenix`, installs `helix`, `phoenix-paging`, `helix-vram`, `helix-guardian`, runs `verify-team.sh` (16 checks), pulls the ledger back into `verification/2026-09-28/pbm-compaq-*`.
  Done = `team on pbm-compaq: 16 passed, 0 failed`. If `vram-round-trip` fails on `kernel_linked`, `helix.ko` is not loaded: `sudo systemctl status helix`.
- **C** Reboot the Compaq, run `ssh pbm-compaq 'sudo /opt/phoenix/tools/helix-team/verify-team.sh'` again. Done = same 16/16 after reboot.
- **C** Kernel load test for round 3 (S1-F32): `ssh pbm-compaq 'cd /opt/phoenix/sector1/kernels && sudo bash dm_helix_test.sh'` — exit 0, dmesg clean.
- **C** Commit the returned ledger files, push.

## 2. Ingress / egress clones, peered (Phase 2)
- **C** On the Precision (`CLONEPOOL_DIR=F:/Phoenix/clonepool` for every usys/intake command today, the E: drift is still your call):
  `bash tools/helix-team/stage.sh staging && bash scripts/hsf-intake.sh staging/helix-team-ingress/ && bash scripts/hsf-intake.sh staging/helix-team-egress/`
  Done = two `[intake:SUITE]` lines, two distinct hex buckets in D1.
- **J** Pick the hop secret: `openssl rand -hex 32` → vault as `PHOENIX_RJ_SECRET`. Put it on both boxes as `/etc/default/helix-team` (`PHOENIX_RJ_SECRET=…`, mode 600), plus on pbm3 `PHOENIX_RJ_BIND=<pbm3 mesh IP, 10.47.0.x>` and on the Compaq `PHOENIX_RJ_PEER=pbm3.phx:5581`.
- **C** nftables on pbm3 must accept 5581/tcp from the mesh (`harden_debian_box.sh` is default-drop): add the rule for the wg0 interface only.
- **C** Compaq: `ssh pbm-compaq 'cd /opt/phoenix && sudo bash sector2/package-handler/intake.sh pull helix-team-ingress && cd /opt/phoenix/clonepool/helix-team-ingress && sudo -E PHOENIX_HELIX_ROLE=ingress bash tools/helix-team/run-team.sh'` (as a service later; a tmux session is fine for the first proof). Same on pbm3 with `helix-team-egress` / `PHOENIX_HELIX_ROLE=egress`.
- **C** Proof: on pbm3 `python3 tools/helix-team/peer_check.py listen --juliet 127.0.0.1:5582`; on the Compaq `python3 tools/helix-team/peer_check.py send --romeo 127.0.0.1:5580 --type package_list`. Done = pbm3 prints the id with `translated=True`. Paste into the session log.

## 3. The game gate (Phase 3)
- **C** Main account first: on the Precision, `pwsh -File tools\cloudflare\pull-run-test.ps1` (stages, intakes, wipes a temp pool, `usys pull`, `usys run`). Then the two-machine shape: `ssh pbm-compaq 'cd /opt/phoenix && PHOENIX_WORKER_URL=… PHOENIX_AUTH=… CF_ACCESS_CLIENT_ID=… CF_ACCESS_CLIENT_SECRET=… bash tools/cloudflare/pull-run-test.sh'` with the suite already intaked from the Precision. Paste both result blocks into `docs/plans/game-gate-r2-test.md`.
- **C** Schema truth: `cd sector2/package-handler/worker && npx wrangler d1 export phoenix_dev_db --remote --no-data --output schema.live.sql && diff <(grep -i "create table" schema.live.sql | sort) <(grep -i "create table" schema.sql | sort)`. Commit `schema.live.sql`; fold any difference into `schema.sql`.
- **J** jerry.leftwich1 account: log in (fresh incognito window, or accept the Members invite), note the account id, **delete the exposed token there first**, create an API token (Workers Scripts, D1, R2: edit), vault it.
- **C** `CLOUDFLARE_API_TOKEN=… CLOUDFLARE_ACCOUNT_ID=… tools/cloudflare/new-account-bootstrap.sh` → prints the worker URL and writes `phoenix-auth.<account>.txt` (move to the vault, delete the file). Then the same pull-run test with `PHOENIX_WORKER_URL=<new url>`. Note: that host has no Cloudflare Access in front of it until you create one; `PHOENIX_AUTH` is its only gate until then.
- **J** Decision the test informs: if PASS on the real worker, the game's "pull Phoenix from R2 onto a player box" design stands; the open items that matter for the game are multipart upload (>100 MB assets) and the filename-hex identity collision.

## 4. Stripe on Radar (Phase 4)
- **J** Roll the test key you pasted into chat today (Stripe → Developers → API keys → roll).
- **J/C** `STRIPE_SECRET_KEY=sk_test_… tools/stripe/setup-radar.sh` (key from the vault in the environment, never on the command line). It creates the product, the $9.99/month price and the webhook endpoint and prints the exact `wrangler secret put` lines. The webhook signing secret is shown once: vault it immediately.
- **C** `cd pbm-consulting-website/radar-worker && printf '%s' "$STRIPE_SECRET_KEY" | npx wrangler secret put STRIPE_SECRET_KEY && printf '%s' "$STRIPE_WEBHOOK_SECRET" | npx wrangler secret put STRIPE_WEBHOOK_SECRET`; add `"STRIPE_PRICE_ID": "price_…"` to `wrangler.jsonc` vars; `npx wrangler d1 execute pbm_radar_db --remote --file=migrations/2026-09-28-billing.sql`; `npx wrangler deploy`; `curl -s https://pbm-radar-worker.phoenix-jwl.workers.dev/health` shows `"billing": "stripe"`.
- **J** One real test-mode checkout end to end: `curl -X POST -H "Authorization: Bearer $PHOENIX_AUTH" "https://pbm-radar-worker.phoenix-jwl.workers.dev/billing/checkout?subscriber=<your id>"`, open the emailed link, card `4242 4242 4242 4242`, then `GET /billing?subscriber=<id>` shows `active` and one `checkout.session.completed` event. Nobody else gets a link until you send it.
- Live mode waits for the LLC + EIN + bank account + the benefits-counselor call (Laurie's SSDI), as planned.

## 5. File the round, intake everything
- **C** After step 0, write `2026-09-28-round3-addendum-2.md` (probe results + kernel test + team verify); update the pentest README's daily log row for round 3; `scripts/hsf-intake.sh docs/compliance/pentest/2026-09-28-round3-security.md` and the other three new files; `scripts/hsf-intake.sh verification/2026-09-28/`.
- **J** The "needs Jerry" decisions in the round-3 reports (each is one line): the five unguarded fossil Life First installers, the dashboard's default AI provider and Laurie's Guide target, the old `Phoenix-Package_handler` repo's live `install.ps1`, portal viewer auth on the mesh, the compliance scorecard rewrite (XCUT-F15), sign-off on S1-S19/S1-F16.

## Constraints you asked about (for the record)
This session could not: reach any of your machines or the mesh; log into Cloudflare or Stripe (egress proxy blocks both APIs); build or load `helix.ko`; run PowerShell; do a live Stripe checkout. Everything above is the part that needs a desk.
