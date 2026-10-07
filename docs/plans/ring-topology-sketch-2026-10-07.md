# Ring topology sketch (Jerry, 2026-10-07) — CAPTURED, NOT DESIGNED

Jerry: "here is something i have envisioned for later." Hand sketch (photo in the 10/7 evening chat).
Claude's reading below; Jerry corrects it when we talk it out. Do not build ahead of him
(see the 10/7 rule: architecture is a talk WITH Jerry as it develops).

- **Center: PRECISION = Phoenix primary** (PBMII). Ports around it: a **socket** (to the top node),
  a **phone** port, and arcs out to each node.
- **COMPAQ = router**: the link between the top node and the right node.
- **STORE / HP**: storage, between the right node and the small ring (matches "the HP = storage manager").
- **"Similar Typical Ring"** (small circle, lower left): each node carries its own ring of the same shape.
- **Outer arcs** join the nodes to each other, not only to the center: peers talk directly
  (fits "nodes heal each other over the mesh").
- **Callout, "typical" on every link:** **QuadEngine + Prefetch Engine + New Horizon + SMB**.
  New Horizon = `helix_new_horizon.py` (only copy in the Music ring, see the music-ring-to-suit note);
  QuadEngine = `sector4/quadengine.py` / `sector3/quadengine/`.

Open questions for Jerry: what the top and right circles are · whether "socket" is the Helix socket
(7701/7800) or a mesh port · whether "phone" means the phone node · whether SMB is the existing samba shares.
