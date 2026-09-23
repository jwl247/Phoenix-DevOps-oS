---
title: "Documents That Can't Lie: Building Tamper-Evident Paperwork for the Trades"
date: 2026-09-07
author: "PBM Consulting Service, built in collaboration with Claude (Anthropic)"
tags: [phoenix, office, trades, small-business]
---

Anyone who's run a small trade business knows the moment: a signed work
order says one thing, the customer swears it said another, and there's no
way to prove which version is real. A PDF can be edited. A scanned form can
be edited. Even "the signed copy is in the email thread somewhere" doesn't
actually prove nothing changed after the fact.

So we built the record to make that dispute structurally impossible instead
of just procedurally inconvenient.

**The core rule is simple: fields are read-and-fill, not read-and-write.**
Once a field is filled in, it's locked — permanently, even before anything
is signed, even by the same person who just typed it. Typing the wrong
thing twice isn't the failure mode we're defending against; a filled-in
number quietly becoming a different number later is. If you need to
correct something, you don't get to edit it. You fill in what's still
blank, and if the document's already been signed, the correction becomes
its own new document that explicitly points back to the original — a
change order, not a rewrite.

**Signing is the real event, not a formality.** The document moves through
three real states: drafted, handed to the other party for review, and
signed. Signing takes a hash of every field's content at that exact moment
and freezes it. From that instant forward, any edit to the file on disk —
not through the app, directly on disk, the way someone would try to get
away with it — gets caught. Reopen a tampered document and the mismatch
between what's on disk and the frozen hash shows up immediately, and the
other party gets notified automatically, repeatedly, until they
acknowledge it. Not a log entry nobody reads. An actual alert to a phone.

**None of this depends on us being the ones storing your documents.**
Every document is identified by the hash of its own content, not by a
filename — two different customers can each have an `invoice.json` and
they will never collide, and there's no "cache eviction" policy quietly
deleting old records because a business record isn't a temp file. And
because the whole thing runs as its own standalone product with its own
database and its own storage, you don't need our other infrastructure
installed to use it. It runs on its own.

**The uncomfortable design questions were the important ones.** What
happens when someone signs something and then wants to dispute it anyway?
(The tamper check doesn't care about intent — it just reports whether the
bytes match what was signed, and the history is there for a human to
interpret.) What happens if the notification can't reach anyone? (It says
so, honestly, instead of pretending the alert went out.) What happens to a
document from before any of this integrity checking existed? (It's marked
as a legacy record with no baseline, not silently treated as verified.)

A tamper-evident record system is only worth building if it's honest about
its own limits, not just aggressive about catching the other guy's.

Next: what it actually looks like to have an assistant handle the tedious
parts of this — without ever being handed more trust than the job needs.
