# press-room — PBM's writing desk (drafts only)

Written 2026-09-30 from the code in this folder. Verify against current code before trusting a specific line number.

## What it is
Plain-text writing for PBM Consulting Service: blog posts, a B2B outreach email, a legal
disclaimer for a lawyer to start from, and the social media calendar. There is no code here
and nothing in this folder is published or sent automatically; every file is a draft waiting
for a person to review it and post it somewhere by hand.
- `blog/blog-post-1-origin.md` — "Why We Rebuilt Everything From Vendor Zero": the Firebase credits story and why Phoenix depends on no single vendor. Also the voice reference for the social posts.
- `blog/blog-post-2-tamper-evident.md` — "Documents That Can't Lie": Phoenix Office's lock-on-fill, sign-and-freeze, tamper-notice design, for trades businesses.
- `blog/blog-post-3-secretariat.md` — "Meet Secretariat": the Phoenix Office AI helper that acts through a fixed tool list and asks before anything that leaves the draft.
- `outreach/pbm-b2b-outreach-draft.md` — draft cold email about federal set-aside contracts (HUBZone, 8(a), WOSB), signed as PBM Consulting Service, with subject line options; not yet entered into HubSpot or sent.
- `legal-drafts/pbm-liability-disclaimer-draft.md` — draft terms-of-service and liability wording for the paid hosted Phoenix Office tier. Marked "not legal advice, not reviewed by an attorney".
- `social/content-calendar.md` — the standing social media calendar: voice notes, posts planned and their status, and what comes next. Extend it, don't rebuild it.
- `social/2026-09-24-poll.csv` — the 2026-09-24 "office headaches" poll for LinkedIn, Facebook, Twitter and Instagram, in a form a scheduling tool (Buffer, Later) can import.

## Dependencies
None. Markdown and CSV files read by people.

## Commands / entry points
None. Open the files in any editor. Import `social/2026-09-24-poll.csv` into a scheduling tool
by hand.

## Connects to / connected from
- `press-room/social/content-calendar.md` → `press-room/blog/blog-post-1-origin.md` (the voice reference for posts).
- `press-room/social/content-calendar.md` → `pbm-consulting-website/index.html` (the website's hero copy is the other voice reference).
- `press-room/social/content-calendar.md` → `press-room/social/2026-09-24-poll.csv` (the importable copy of the poll it plans).
- `press-room/blog/blog-post-2-tamper-evident.md` → `phoenix-office/lib/document.js` (describes how this engine locks and freezes documents; no code link).
- `press-room/blog/blog-post-3-secretariat.md` → `phoenix-office/lib/agent-tools.js` (describes Secretariat's tool tiers; no code link).
- `docs/plans/pbm-authority-plan.md` → `press-room/blog/blog-post-1-origin.md` (the authority plan counts the three blog posts as drafted but not published).

## Known issues (verified, not guessed)
- Nothing here has been published: no blog host or social scheduler is connected (the
  calendar's own "Next up" note; the HubSpot portal on Standard tier has no social staging).
- Blog post 3 (`blog/blog-post-3-secretariat.md`) says the tools that run without asking "don't leave your
  local draft or touch anyone else". That is not true of the code: in
  `phoenix-office/lib/agent-tools.js`, `create_project` and `set_bid_factor` are base tier
  and write to the shared worker database, and
  `fill_field` locks a field for good. Fix the wording before publishing (also recorded in the
  2026-09-28 Round 2 functionality report).
- The outreach email still has the placeholder "[First Name]" and no recipient list; its own
  closing note says the connected HubSpot contacts are not the right list.
