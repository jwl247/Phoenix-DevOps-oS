---
title: "Meet Secretariat: An Assistant With Its Hands Actually on the Wheel"
date: 2026-09-22
author: "PBM Consulting Service, built in collaboration with Claude (Anthropic)"
tags: [phoenix, office, ai, secretariat]
---

Most "AI assistant" panes bolted onto office software do one thing: they
answer questions about the document you're looking at. Useful, but it's a
narrator, not a hand. You still do every click yourself.

We wanted something closer to K.I.T.T. from Knight Rider — not because
it's a cute reference, but because it's the right shape for the job. K.I.T.T.
didn't do the driving for Michael Knight. It handled what needed handling,
in the background, and only surfaced a real decision when there actually
was one to make. That's the model: an assistant that acts, but never past
the point where a human needs to say yes.

**So Secretariat can actually act now — through a fixed set of tools, not
a blank check.** Ask it to start a work order, draft a field, search past
sealed documents, and it just does it. No confirmation needed, because
none of that leaves your local draft or touches anyone else. But hand a
document to a client, or sign it — those are irreversible, and they touch
someone outside the app. For those, Secretariat stops, shows you exactly
what it's about to run and with what arguments, in plain text, and waits
for an explicit yes. Not a vague "are you sure?" — the literal tool call,
visible, before it happens. If you can't see exactly what it did when you
ask, the automation isn't actually trustworthy, no matter how smooth it
feels in the moment.

**It's built to work without the internet, by default.** These are often
confidential business records — customer names, pricing, inspection
findings — and there's no good reason filling one out should require
sending anything to a cloud API. So the assistant tries a locally-running
model first, every time, and only reaches out to a hosted one if there's
no local model available. The cloud tier isn't gone — it's just not the
default. Self-contained and secure came before "the smoothest possible
demo," on purpose.

**And it never gets a shell.** This is the part that actually matters more
than the persona. The model driving Secretariat cannot run arbitrary code,
touch the filesystem, or do anything outside a short, explicit list of
named actions we wrote ourselves. If a capability isn't on that list, no
amount of clever prompting gets it to happen anyway. That's not a
limitation we're apologizing for — it's the entire reason this is safe to
hand to someone who isn't us.

The honest state, as of today: this is built and tested against every
scenario we could script — but it hasn't been run live in front of a real
person having a real conversation with it yet. That's next. We'd rather
say that plainly than demo something we haven't actually watched work.

If there's a feature you'd want an assistant like this to have before
you'd trust it with your own paperwork, that's exactly the kind of
feedback we're gathering right now — say so.
