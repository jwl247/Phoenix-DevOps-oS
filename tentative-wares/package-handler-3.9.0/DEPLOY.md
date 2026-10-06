# packages-worker 3.9.0 + intake: one key per person

**Why:** until now, packages-worker had a single key, PHOENIX_AUTH. Anyone holding it can
delete or overwrite anything in the pool, and every intake looks like it was yours. 3.9.0
keeps your key exactly as it is and adds **member keys**.

| A member key can | A member key can't |
|---|---|
| Read the pool, glossary, versions and receipts | See or download anything flagged sensitive |
| Intake **new** names, and new versions of its **own** names | Write a name you or anyone else owns ("rename your file") |
| Re-tier its own rows | Delete anything |
| | Rebuild Atlas, write the Atlas bundle key, issue keys, or see `/stats`, `/feed` and other owner routes |

Its receipts, its version-ledger entries and the row's `owner` all carry its name. That is
set by the worker, so a member can't put your name on them. Only the key's SHA-256 is stored.

## Files (in this folder)

| File | Goes to |
|---|---|
| `worker/index.js` | `sector2/package-handler/worker/index.js` |
| `worker/schema-d1.sql` | `sector2/package-handler/worker/schema-d1.sql` (fresh installs) |
| `worker/migrate-3.9.0-member-keys.sql` | `sector2/package-handler/worker/` (run once) |
| `intake.sh` | `sector2/package-handler/intake.sh` |

`intake.sh` change: before writing anything it asks the worker `GET /may-write/<hex>`. A
refused name prints `[intake:REFUSED] '<name>': <reason>` and nothing is written. In a
folder intake, refused files are left out of that snapshot. Against a 3.8.x worker the
check gets a 404 and intake behaves exactly as before.

## Deploy, in this order

The migration must run **before** the deploy. 3.9.0 writes `clonepool.owner` on every
intake, and without that column intake would fail.

```powershell
cd F:\Phoenix\Phoenix-DevOps-oS
Copy-Item tentative-wares\package-handler-3.9.0\worker\* sector2\package-handler\worker\ -Force
Copy-Item tentative-wares\package-handler-3.9.0\intake.sh sector2\package-handler\intake.sh -Force
cd sector2\package-handler\worker
npx wrangler d1 execute phoenix_dev_db --remote --file migrate-3.9.0-member-keys.sql
npx wrangler deploy
cd ..\..\..
genie doctor                       # worker should say 3.9.0
intake sector2\package-handler\intake.sh   # puts the new intake.sh in custody, so `genie intake setup` hands it out
git add sector2/package-handler tentative-wares && git commit -m "packages-worker 3.9.0: member keys; intake asks before writing"
```

Then give your son his key, from any PS7 window with your key loaded and the cloud Genie
dot-sourced:

```powershell
genie key new <his-name>           # shown once; send it over Signal or in person
genie key list
genie key revoke <his-name>        # if his laptop is ever lost; yours keeps working
```

**Cloudflare Access:** if packages-worker sits behind Access (it did as of 2026-10-03),
he also needs an Access service token. Make him his **own** token in Zero Trust → Access →
Service Auth, and add it to the worker's Access policy. Don't share `usys-cli`: a shared
token means revoking it cuts you off too.

## Tested (local wrangler 4.147.0, real worker code, local D1/R2)

- **Keys:** issue, shown once, duplicate refused, bad names refused, list, revoke (401 at
  once), re-issue after revoke, read-only scope.
- **Member refusals:** delete; overwrite your bytes, row, glossary or tier; deps on your
  package; the Atlas bundle key; Atlas rebuild; `/keys`; `/stats`; reading or copying from a
  sensitive row; a sensitive row in the list, search or glossary.
- **Member writes:** new file (bytes before the row, then the row); version copy;
  re-tiering its own row.
- **Ownership:**
  - The receipt actor and the ledger's `signed_by` are forced to the member's name.
  - The owner can still write a member's rows, and the row's owner is kept.
  - A second member can't take the first member's name, even in the gap between bytes
    and row.
- **The real `intake.sh` with a member key:**
  - A new file goes in.
  - Your name is refused with the reason.
  - In a folder, the refused file is left out and the rest go in.
  - Owner intake is unchanged.

## Known limits (not fixed here)

- **Names are global.** A file's identity is the hex of its file name, so once you own
  `README.md` or `main.py`, no member can intake a file with that name. A per-person
  namespace would change Phoenix's identity scheme, so that decision is yours.
- **`/packages` and `/deps` list names only, and don't filter sensitive names** for
  members. The bytes and records stay private.
- **`POST /clonepool/<hex>/validate` trusts the hash the client reports.** This was
  already true before 3.9.0.
