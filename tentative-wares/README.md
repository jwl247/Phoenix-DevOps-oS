# tentative-wares

Work in progress that has passed its own tests but is NOT yet "tested, polished,
pro+" for the real tree. Nothing here is wired into the kernel, Genie, Atlas or
any deploy. When a ware graduates it moves to its real home and is removed here.

| Ware | Graduates to | State |
|---|---|---|
| `peer-review/` | `sector2/apps/peer-review/` | Building blocks only: SHA3-512, passkeys (WebAuthn), Discord two-way bridge. Tests: 12 + 12 + 22 pass. Forum schema, worker, website still to build. |

Run the peer-review tests (Node 18+, Python on PATH for the SHA3 cross-check):

```powershell
cd F:\Phoenix\Phoenix-DevOps-oS\tentative-wares\peer-review
node test\sha3.test.mjs; node test\webauthn.test.mjs; node test\discord.test.mjs
```
