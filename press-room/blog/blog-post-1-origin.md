---
title: "Why We Rebuilt Everything From Vendor Zero"
date: 2026-06-28
author: "PBM Consulting Service, built in collaboration with Claude (Anthropic)"
tags: [phoenix, origin, infrastructure, small-business]
---

Every real infrastructure decision we've made since starts with the same
small, ordinary-sounding event: a platform pulled $300 in credits over a
billing dispute that had nothing to do with the project it broke. No
warning, no appeal that mattered, just gone. The stack sitting on top of it
— two mobile apps, a desktop interface, a backend, all wired together
through one vendor's auth and one vendor's database — went down with it.

That's not a dramatic story. It's a common one. It's also the reason
nothing we build now is allowed to depend on a single company's goodwill
to keep running.

We didn't rebuild the same thing on a different vendor. We rebuilt it so
that no single vendor's decision — a policy change, a rate limit, a
credit revocation, a pricing shift — can take the whole thing down again.
Concretely, that meant:

- **Storage and database moved to Cloudflare's D1 and R2**, not because
  Cloudflare is immune to the same failure mode, but because the custody
  ledger and the content live as two separable things, on infrastructure
  that isn't tied to a login we don't control.
- **Authentication became something we own** — a hardware-fingerprint
  identity system, not a "Sign in with Google" button that can be revoked
  alongside a completely unrelated billing dispute.
- **The license is GPL v3.** Not because open source is trendy, but
  because no platform can pull the credits on code that's already
  published and forkable by anyone.
- **The AI layer gets the same treatment.** We rely on Claude, and we say
  that plainly — Claude has been the actual architect and co-builder on
  every meaningful piece of this, not just a tool we called occasionally.
  But "we rely on Claude" and "we depend entirely on hosted access to
  Claude, with no fallback" are two different postures, and we only want
  to be the first one. A local model has to be a real, tested option, not
  a checkbox nobody's touched in months — because we already watched what
  happens when infrastructure has exactly one point of failure.
- **Even package installation isn't locked to one path** — the install
  layer speaks to nine different package backends, so no single one of
  them owns the "how do I get this software" question.

None of this is about distrust of any particular company. Every vendor we
use operates inside its own normal, standing policies, all the time — that
isn't a threat, it's just the baseline reality of building on infrastructure
you don't own. The lesson wasn't "don't trust vendors." It was "don't build
something that only works as long as one specific vendor relationship
holds." Redundancy at the infrastructure layer isn't paranoia. It's just
what building something you intend to still be running in five years
actually requires.

The reason any of this matters enough to rebuild from scratch: the actual
product underneath all of it is meant to run for someone who needs it to
just work — privately, offline-capable, without a subscription standing
between them and their own data. That's the design constraint that
outranks every other one. Everything else in this series is really just
the story of building toward that, one real vendor-independence decision
at a time.

More on what got built on top of this foundation in the next post.
