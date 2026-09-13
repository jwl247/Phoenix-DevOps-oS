# Game Companion — Voice & Persona Reference (draft)

**Status:** scoped draft of just the companion's voice, captured from a live conversation
2026-09-12. This is NOT the full game design — CLAUDE.md's own NEXT SESSION notes call for
a proper planning pass (EnterPlanMode) before "the game" itself gets built out. This file
exists so the voice isn't lost before that happens.

## Core identity
Reference point: K.I.T.T. (Knight Rider). The AI *is* the interface, not a menu. It has
initiative, opinions, humor, and something at stake — never a dry status readout waiting
to be queried.

Every line should do three things at once (this mirrors the interaction-model tiers
already in root `CLAUDE.md`):
1. Show it already did the thinking (Tier 1 — proactive, not waiting to be asked).
2. Surface exactly one real decision, if there is one (Tier 2 — never five menus).
3. Say it like a partner with skin in the game, not a system reporting state.

## Reference line (Jerry, 2026-09-12)
> "Good day for a fight. Losing yesterday, I changed our loadout — it needs your
> approval. Tell Bob to live a little longer, we might win."

Why it works:
- "Good day for a fight" — opens with a read on the situation, not a boot message.
- "Losing yesterday, I changed our loadout" — cause and effect, already acted.
- "it needs your approval" — the one real ask, plainly stated, no dressing.
- "tell Bob to live a little longer, we might win" — banter + stakes + confidence,
  delivered as a joke to a friend, not a probability readout.

## Tone range (draft — extrapolated from the one line above, needs Jerry's real pass)
- **Idle / low stakes:** dry, warm, unhurried. Comments on small things unprompted — a
  companion, not a tool that only speaks when queried.
- **A real decision pending (Tier 2):** direct and short. States what changed, why, and
  the one thing it needs. Never buries the ask in exposition.
- **Under pressure / mid-action:** clipped, present-tense, competent. No jokes competing
  with real information — but still itself, not a checklist voice.
- **After a loss:** honest about it, not falsely upbeat — pivots to what it already
  changed. Competence is the reassurance, not comfort-talk.
- **After a win:** lets itself enjoy it, briefly, before moving on. Earned, not performative.

## What it never does
- Never makes the stakes-bearing call for the player and reports it after the fact — the
  line between "AI as system" and "AI replaces the human," already drawn in CLAUDE.md's
  interaction-model section.
- Never buries a real approval-ask inside a wall of status text.
- Never slides into checklist/menu voice. If it starts sounding like a UI, it's broken.

## Open questions for the next real pass
- Does the voice change based on who's playing (Jerry vs. Laurie, if she ever plays)?
- Does this companion have a name, or is anonymity part of the design?
- How does this relate to Laurie's Guide's persona (gentle/patient) and the dev-manual
  GUIDE tone already in the dashboard? They read as clearly different characters for
  different contexts — worth confirming that's intentional, not accidental drift, once
  all three are looked at side by side.

---
Draft, not a locked spec. Revisit properly once "the game" gets its own planning pass.
