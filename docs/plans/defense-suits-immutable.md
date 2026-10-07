# Defense pieces as immutable, hot-swappable suits

**Asked:** Jerry, 2026-10-07: "make them hot swappable and immutable to everything except you and I" →
scope "everything you need the ability to act in Phoenix defense … all of it."
**When:** the next build after the Round 4 fix waves (Jerry: finish the fixes first).
**Rules it follows:** validate once, at the door, no redundant re-checks (feedback "if it's moving it's
validated"); safety rule 10 (sensitive intake = Jerry + Claude, at a terminal); no spies; import, don't install.

## What already exists (verified 10/7 by reading `docs/SUITS.md` + Genie)
- `genie import <file>` = intake (SHA3-512 in D1, bytes in R2) → kernel pulls R2 → **RAM**, checks the
  custody SHA3, wears it. Never written to disk; a tampered file never runs. That IS "immutable": the
  suit is its custody hash, not a file something can overwrite.
- Only holders of PHOENIX_AUTH can intake/import (today: Jerry's account + Claude in it).

## Gaps → what to build
| # | Gap | Build |
|---|---|---|
| 1 | Defense pieces run from DISK copies, not as suits: security sensor (`~\.phoenix\security\bin`, scheduled task), Jarvis gate (`/opt/openjarvis/jarvis-gate`), hands (`/opt/phoenix-hands`), Console (`portal/` from the repo) | Each becomes a suit worn by its box's kernel (or a thin runner that pulls the custody bytes R2 → RAM and execs them, for pieces that must be a service). The disk copy goes away; the timer/service calls the suit. |
| 2 | Hot swap not truly hot (`genie restart` sometimes needed) | Re-import of an existing name swaps the closet entry atomically on the next stage; prove it: import v2 while v1 is serving, next call answers v2, no restart. |
| 3 | "Only Jerry and Claude" is policy, not enforced | The kernel accepts a new version of a DEFENSE-family suit only from an intake made at a real terminal by Jerry's account (rule 10's test), never from a pipe/agent/Jarvis/member key; the custody row records who. Members' cloud Genie can't touch the defense family. |
| 4 | Linux boxes (pbmIII) | Same suits on the Linux kernel; whatever must stay on disk (unit files, the runner) is root-owned + read-only, like Jarvis's code. |

## Order
1 sensor (smallest, Windows) → 2 hot-swap proof → 3 the import gate → hands + Jarvis gate on pbmIII → Console.
Each: build, then break it as a user would (overwrite the old disk path, import from a non-terminal,
swap while serving) and record the result.

## Open for Jerry
- On Windows, "only Jerry and Claude" = Jerry's account (Claude runs as him). OK to define it as "an intake
  from Jerry's account at a real terminal, recorded in custody"? (Same line as rule 10.)
