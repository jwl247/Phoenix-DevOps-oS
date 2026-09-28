# Game gate: can Phoenix run from R2? (mandatory before deciding how to build the game)

Jerry, 2026-09-28: "we put phoenix in the r2 in the account with jerry.leftwich1@gmail.com and
we test whether phoenix can run via this method ... the test is a mandatory thing before we can
decide how to build the game." Monster Phoenix's design is a player-hosted mesh with no
persistent exposed server: every player box pulls Phoenix from R2 and runs it. If that path
does not work, the game architecture changes. This file is the record.

## What "the method" is, exactly

1. **Put Phoenix in R2:** `intake.sh <dir>` (Frank's import method) sends every file's bytes to
   R2 at an immutable content key (`<filehex>/versions/<sha3[0:16]>`), the current bytes at
   `<filehex>`, and, since intake.sh 1.8.0, the directory's manifest (files + per-file SHA3-512)
   at the directory's own hex, with the manifest's hash recorded in the D1 `clonepool` row.
2. **Pull it on a box that has nothing:** `intake pull <name>` (Linux) / `usys pull <name>`
   (Windows) asks D1 for the row, fetches the manifest from R2, verifies it against the D1
   hash, fetches every file by its content key, verifies every SHA3-512, and only then writes
   `clonepool/<name>/` with the `.suite.json`. A single mismatch writes nothing.
3. **Run it:** `usys run <name>` / `bash tools/helix-team/run-team.sh` from the pulled
   directory. The Helix team (memory manager, guardian, Helix-I, Romeo) must come up and answer.

The test is scripted: `tools/cloudflare/pull-run-test.sh` (Linux, `--fake` for a local
stand-in worker) and `tools/cloudflare/pull-run-test.ps1` (Windows, real worker). Both write
their result to `verification/<date>/game-gate-pull-run*.log`.

## Results

### 2026-09-28 — local, fake worker (this container) — PASS

```
# game-gate pull-run test  commit=ba5f834  worker=http://127.0.0.1:29034  fake=1  host=vm
## 2. intake into the worker      intake rc=0  files=44  R2 PUTs=86  D1 posts=88  9.6s
## 3. wipe the local pool          pool entries: 0
## 4. intake pull helix-team-ingress
                                   pull rc=0  files=40 (staged 44)  bytes=410396  1.1s
                                   every .py/.sh staged is present and verified in the pulled suite
## 5. run the pulled suite         team up=1  members started=4 (helix-vram helix-guardian helix-i romeo)
                                   vram ping=pong  romeo active=1
## 6. PASS: Phoenix (helix-team-ingress, 40 files) was intaked, pulled onto an empty pool with
      every hash verified, and ran.
```

What this proves: the mechanism (intake → D1 + R2 → verified pull → run) is complete and
correct in code, with the worker's real routes and response shapes stood in for by
`sector2/package-handler/tests/fake_worker.py`. The 4 files not pulled were extensionless
(`Makefile`, `helix_run`) — fixed in the same session (extensionless scripts and Makefiles are
now intaked), so the next run pulls 44/44.

What it does NOT prove yet: the real Cloudflare path (Access in front of the worker, R2
latency, D1 from a new account). That is the desk run below.

### Pending — desk, main account (phoenix-jwl), real worker
```
PHOENIX_WORKER_URL=https://packages-worker.phoenix-jwl.workers.dev PHOENIX_AUTH=… CF_ACCESS_CLIENT_ID=… CF_ACCESS_CLIENT_SECRET=… \
  tools/cloudflare/pull-run-test.sh            # on pbm3 or the Compaq (Linux)
pwsh -File tools\cloudflare\pull-run-test.ps1  # on the Precision (Windows), -SkipIntake for the two-machine shape
```
Paste the result block here.

### Pending — desk, jerry.leftwich1 account
Blockers, all Jerry's: log into that account (9/26: the browser kept approving as
jw.leftwich1; use a fresh incognito window or accept the Members invite), record the account
id, delete the exposed token there, create an API token (Workers Scripts, D1, R2: edit), then:
```
CLOUDFLARE_API_TOKEN=… CLOUDFLARE_ACCOUNT_ID=… tools/cloudflare/new-account-bootstrap.sh
PHOENIX_WORKER_URL=<printed url> PHOENIX_AUTH=$(cat phoenix-auth.<account>.txt) tools/cloudflare/pull-run-test.sh
```
Note: the new workers.dev host has no Cloudflare Access in front of it until that is created
in the dashboard; until then `PHOENIX_AUTH` is the only gate on it.

## Known limits that affect the game (recorded, not fixed today)
- Objects over 100 MB are skipped by intake (no multipart upload in the worker). The team
  suite is 400 KB; game assets will not be. Needs multipart before asset distribution.
- Identity is the file name (hex of the basename), so two different files with the same name
  in different suites share a D1 row; the version ledger and content keys keep the bytes
  apart, and the directory manifest pins each suite to its exact content, but the catalog
  row itself is last-writer-wins (S2CORE-F09).
- `usys pull` on Windows needs SHA3-512: .NET 8+ on Windows 11 24H2 supports it natively;
  otherwise usys falls back to `python3` (hashlib) or `openssl` from Git for Windows, and
  refuses to stage anything it cannot verify.
