"""
test_game_session.py — Phoenix game process suite
==================================================
Proves Phoenix can import and run real game processes via node_session.
Modeled on Eve Online + Conflict of Nations core loops:

  world_tick    — advance game clock, territory control, frontline pressure
  combat_tick   — engagement resolution, damage, casualties, morale
  supply_tick   — logistics propagation, depot levels, route health
  intel_tick    — fog of war aging, recon decay, threat assessment
  command_tick  — order processing, objective assignment, theater control

All processes run inside one Frank session (login → run → sync → die).
State is pushed to R2 via packages-worker and verified on fresh login.

Usage:
    python3 test_game_session.py

Reads PHOENIX_AUTH from env.
"""

import os
import sys
import time
import json
import math
import random
import hashlib
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-22s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("game")

WORKER_URL = "https://packages-worker.phoenix-jwl.workers.dev"
AUTH_TOKEN  = os.environ.get("PHOENIX_AUTH", "").strip()
GAME_UID    = "game-node-001"

if not AUTH_TOKEN:
    log.error("PHOENIX_AUTH env var not set")
    sys.exit(1)

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), ".")
sys.path.insert(0, os.path.abspath(SCRIPTS_DIR))

try:
    from node_session import login, logout, content_hash, make_sidecar
    from node_session.session import blob_dir, sidecar_dir
except ImportError as e:
    log.error(f"Cannot import node_session: {e}")
    sys.exit(1)

# ── Seed world — first boot state ────────────────────────────────────────────

def seed_world() -> dict:
    """
    Initial world state. Mirrors what a real game server would hold per node.
    Eve-style: solar systems + jump gates.
    CON-style: provinces + frontlines + supply routes.
    """
    return {
        "meta": {
            "tick":       0,
            "game_time":  0.0,
            "node":       "game-node-001",
            "theater":    "EASTERN_FRONT",
            "season":     "winter",
        },
        "territories": {
            "alpha-prime":  {"controller": "PHOENIX", "pressure": 0.0, "pop": 1200, "industry": 4},
            "bravo-sector": {"controller": None,      "pressure": 0.6, "pop":  800, "industry": 2},
            "charlie-gate": {"controller": "ENEMY",   "pressure": 0.2, "pop":  400, "industry": 1},
            "delta-depot":  {"controller": "PHOENIX", "pressure": 0.1, "pop":  600, "industry": 3},
        },
        "units": {
            "squad-alpha-1": {
                "pos": [12.4, 7.2], "hp": 100, "ammo": 200,
                "supply": 85, "morale": 90, "fatigue": 10,
                "type": "infantry", "sector": "bravo-sector",
            },
            "squad-alpha-2": {
                "pos": [11.1, 8.0], "hp": 95, "ammo": 180,
                "supply": 70, "morale": 82, "fatigue": 22,
                "type": "infantry", "sector": "bravo-sector",
            },
            "armor-1":       {
                "pos": [10.5, 6.9], "hp": 140, "ammo": 60,
                "supply": 60, "morale": 88, "fatigue": 8,
                "type": "armor", "sector": "bravo-sector",
            },
            "artillery-1":   {
                "pos": [14.0, 7.5], "hp": 80, "ammo": 120,
                "supply": 90, "morale": 85, "fatigue": 5,
                "type": "artillery", "sector": "alpha-prime",
            },
        },
        "supply": {
            "depots": {
                "main-depot":    {"stock": 1000, "sector": "alpha-prime", "throughput": 50},
                "forward-depot": {"stock": 300,  "sector": "delta-depot", "throughput": 20},
            },
            "routes": [
                {"from": "main-depot",    "to": "forward-depot", "health": 0.9, "distance": 4.2},
                {"from": "forward-depot", "to": "squad-alpha-1",  "health": 0.7, "distance": 2.1},
                {"from": "forward-depot", "to": "squad-alpha-2",  "health": 0.7, "distance": 2.3},
                {"from": "forward-depot", "to": "armor-1",        "health": 0.5, "distance": 2.8},
            ],
        },
        "intel": {
            "fog": {
                "charlie-gate": {"certainty": 0.3, "last_recon": 0, "threat_level": "MEDIUM"},
                "bravo-sector": {"certainty": 0.8, "last_recon": 0, "threat_level": "HIGH"},
            },
            "recon": [],
            "sigint": [],
        },
        "combat": {
            "engagements": [],
            "total_casualties": 0,
            "kills":            0,
            "suppressed_units": [],
        },
        "command": {
            "orders": [
                {"id": "ORD-001", "type": "ATTACK",  "target": "charlie-gate", "priority": 1, "issued_tick": 0},
                {"id": "ORD-002", "type": "HOLD",    "target": "delta-depot",  "priority": 2, "issued_tick": 0},
                {"id": "ORD-003", "type": "RESUPPLY","target": "armor-1",      "priority": 1, "issued_tick": 0},
            ],
            "active_theater": "EASTERN_FRONT",
            "commander_uid":  None,   # set at runtime by shadow mechanic
            "objective":      "Seize charlie-gate within 5 ticks",
        },
    }


# ── Process ticks ─────────────────────────────────────────────────────────────

def world_tick(state: dict) -> dict:
    """
    Advance game clock. Update territory pressure, frontline drift.
    Eve-style: each tick is one server cycle. CON-style: real-time territorial shift.
    """
    t0 = time.perf_counter()

    state["meta"]["tick"]      += 1
    state["meta"]["game_time"] += 1.0   # 1 tick = 1 game-hour

    tick = state["meta"]["tick"]

    # Territory pressure shifts based on adjacent unit presence
    unit_sectors = {}
    for uid, u in state["units"].items():
        s = u.get("sector")
        if s:
            unit_sectors[s] = unit_sectors.get(s, 0) + 1

    for tname, terr in state["territories"].items():
        units_here = unit_sectors.get(tname, 0)
        ctrl       = terr["controller"]

        if ctrl == "PHOENIX" and units_here > 0:
            terr["pressure"] = max(0.0, terr["pressure"] - 0.05 * units_here)
        elif ctrl == "ENEMY" and units_here > 0:
            terr["pressure"] = min(1.0, terr["pressure"] + 0.03 * units_here)
        elif ctrl is None:
            # contested — tip toward PHOENIX if units present
            if units_here >= 2:
                terr["pressure"] = max(0.0, terr["pressure"] - 0.08)
            elif units_here == 1:
                terr["pressure"] = max(0.0, terr["pressure"] - 0.03)

        # Capture threshold
        if terr["pressure"] <= 0.05 and ctrl != "PHOENIX":
            terr["controller"] = "PHOENIX"
            log.info(f"    CAPTURE  {tname} → PHOENIX  tick={tick}")
        elif terr["pressure"] >= 0.95 and ctrl != "ENEMY":
            terr["controller"] = "ENEMY"
            log.info(f"    CAPTURE  {tname} → ENEMY  tick={tick}")

    ms = int((time.perf_counter() - t0) * 1000)
    log.info(f"  world_tick done  tick={tick}  {ms}ms")
    return state


def combat_tick(state: dict) -> dict:
    """
    Resolve engagements. Damage, suppression, morale effects.
    Eve-style: DPS/EHP math. CON-style: combat power ratios + terrain.
    """
    t0   = time.perf_counter()
    tick = state["meta"]["tick"]

    engagements = []
    total_dmg   = 0
    kills       = 0

    # Units in contested sectors engage enemy
    contested = {n for n, t in state["territories"].items() if t["controller"] is None}
    enemy_held = {n for n, t in state["territories"].items() if t["controller"] == "ENEMY"}

    for uid, u in state["units"].items():
        sector = u.get("sector", "")
        if sector not in contested and sector not in enemy_held:
            continue
        if u["hp"] <= 0:
            continue

        # Simulate enemy contact — DPS based on unit type
        dps_table = {"infantry": 8, "armor": 22, "artillery": 35}
        armor_table = {"infantry": 5, "armor": 40, "artillery": 2}

        enemy_dps   = dps_table.get("infantry", 10)    # generic enemy
        enemy_armor = armor_table.get("infantry", 5)
        own_dps     = dps_table.get(u["type"], 10)
        own_armor   = armor_table.get(u["type"], 5)

        # Ammo consumption
        ammo_used = min(u["ammo"], random.randint(5, 15))
        u["ammo"] = max(0, u["ammo"] - ammo_used)

        # Damage dealt / received
        dmg_dealt    = max(0, own_dps - enemy_armor // 4) if u["ammo"] > 0 else own_dps // 4
        dmg_received = max(0, enemy_dps - own_armor // 4)

        u["hp"]      = max(0, u["hp"] - dmg_received)
        u["fatigue"] = min(100, u["fatigue"] + 5)
        u["morale"]  = max(0, u["morale"] - (2 if dmg_received > 10 else 0))

        total_dmg += dmg_received
        engagement = {
            "tick":       tick,
            "unit":       uid,
            "sector":     sector,
            "dmg_dealt":  dmg_dealt,
            "dmg_taken":  dmg_received,
            "ammo_used":  ammo_used,
        }
        engagements.append(engagement)

        if u["hp"] <= 0:
            kills += 1
            log.info(f"    KIA  {uid}  sector={sector}")

    state["combat"]["engagements"].extend(engagements)
    state["combat"]["total_casualties"] += total_dmg
    state["combat"]["kills"]            += kills

    # Suppression: units below 30% HP are suppressed
    suppressed = [uid for uid, u in state["units"].items() if 0 < u["hp"] <= 30]
    state["combat"]["suppressed_units"] = suppressed

    ms = int((time.perf_counter() - t0) * 1000)
    log.info(f"  combat_tick done  engagements={len(engagements)}  dmg={total_dmg}  kills={kills}  {ms}ms")
    return state


def supply_tick(state: dict) -> dict:
    """
    Propagate supply along routes. Depot drain. Unit resupply.
    CON-style: supply lines, attrition when cut. Eve-style: cargo flow.
    """
    t0 = time.perf_counter()

    depots  = state["supply"]["depots"]
    routes  = state["supply"]["routes"]
    units   = state["units"]

    # Drain main depot from industry
    for dname, depot in depots.items():
        sector  = depot["sector"]
        terr    = state["territories"].get(sector, {})
        industry = terr.get("industry", 1)
        if terr.get("controller") == "PHOENIX":
            depot["stock"] = min(depot["stock"] + industry * 10, 2000)

    # Flow along routes
    for route in routes:
        src_name = route["from"]
        dst_name = route["to"]
        health   = route["health"]

        src = depots.get(src_name)
        dst = depots.get(dst_name)

        if src and dst:
            # Depot-to-depot flow
            flow = int(src["throughput"] * health)
            transfer = min(flow, src["stock"])
            src["stock"]    -= transfer
            dst["stock"]    += transfer
            dst["stock"]     = min(dst["stock"], 1000)
        elif src and dst_name in units:
            # Depot to unit resupply
            u    = units[dst_name]
            flow = int(20 * health)
            ammo_need    = max(0, 200 - u["ammo"])
            supply_need  = max(0, 100 - u["supply"])
            ammo_given   = min(ammo_need,   flow // 2, src["stock"] // 2)
            supply_given = min(supply_need, flow // 2, src["stock"] // 2)
            u["ammo"]    = min(200, u["ammo"]   + ammo_given)
            u["supply"]  = min(100, u["supply"] + supply_given)
            src["stock"] = max(0, src["stock"] - ammo_given - supply_given)

        # Route degrades in contested sectors — improves if controlled
        mid_sector = "bravo-sector"  # most routes transit bravo
        terr_ctrl  = state["territories"].get(mid_sector, {}).get("controller")
        if terr_ctrl == "PHOENIX":
            route["health"] = min(1.0, route["health"] + 0.02)
        elif terr_ctrl is None:
            route["health"] = max(0.1, route["health"] - 0.03)
        else:
            route["health"] = max(0.0, route["health"] - 0.08)

    ms = int((time.perf_counter() - t0) * 1000)
    total_stock = sum(d["stock"] for d in depots.values())
    log.info(f"  supply_tick done  total_stock={total_stock}  {ms}ms")
    return state


def intel_tick(state: dict) -> dict:
    """
    Age recon data. Update fog of war certainty. Threat assessment.
    Eve-style: dscan decay. CON-style: intel fog.
    """
    t0   = time.perf_counter()
    tick = state["meta"]["tick"]

    fog = state["intel"]["fog"]

    # Decay certainty every tick
    for sector, data in fog.items():
        age_factor = (tick - data["last_recon"]) * 0.05
        data["certainty"] = max(0.05, data["certainty"] - age_factor)

        # Recon if PHOENIX units are adjacent
        terr   = state["territories"].get(sector, {})
        units_near = sum(
            1 for u in state["units"].values()
            if u.get("sector") == sector and u["hp"] > 0
        )
        if units_near > 0:
            data["certainty"]  = min(1.0, data["certainty"] + 0.15 * units_near)
            data["last_recon"] = tick

        # Threat reassessment
        if terr.get("controller") == "ENEMY" and data["certainty"] > 0.5:
            data["threat_level"] = "HIGH"
        elif terr.get("controller") is None and data["certainty"] > 0.3:
            data["threat_level"] = "MEDIUM"
        else:
            data["threat_level"] = "LOW"

    # New recon entry
    recon_event = {
        "tick":    tick,
        "sector":  "bravo-sector",
        "method":  "unit-contact",
        "contact": "enemy-infantry",
        "count":   random.randint(1, 4),
    }
    state["intel"]["recon"].append(recon_event)

    ms = int((time.perf_counter() - t0) * 1000)
    log.info(f"  intel_tick done  fog_sectors={len(fog)}  {ms}ms")
    return state


def command_tick(state: dict) -> dict:
    """
    Process active orders. Assign objectives. Shadow commander check.
    Monster Phoenix: commander may be a real player who doesn't know it.
    """
    t0   = time.perf_counter()
    tick = state["meta"]["tick"]

    orders    = state["command"]["orders"]
    units     = state["units"]
    territory = state["territories"]

    completed = []
    for order in orders:
        oid   = order["id"]
        otype = order["type"]
        tgt   = order["target"]

        if otype == "ATTACK":
            terr = territory.get(tgt, {})
            if terr.get("controller") == "PHOENIX":
                completed.append(oid)
                log.info(f"    ORDER COMPLETE  {oid}  target={tgt} captured")
            elif terr.get("pressure", 1.0) < 0.3:
                log.info(f"    ORDER PROGRESS  {oid}  pressure={terr['pressure']:.2f}")

        elif otype == "HOLD":
            terr = territory.get(tgt, {})
            if terr.get("controller") == "ENEMY":
                log.info(f"    ORDER FAILED  {oid}  {tgt} lost to enemy")
                completed.append(oid)

        elif otype == "RESUPPLY":
            unit = units.get(tgt, {})
            if unit.get("supply", 0) >= 80 and unit.get("ammo", 0) >= 150:
                completed.append(oid)
                log.info(f"    ORDER COMPLETE  {oid}  {tgt} resupplied")

    # Remove completed orders
    state["command"]["orders"] = [o for o in orders if o["id"] not in completed]

    # Shadow commander: elevate a live unit randomly if no commander set
    if state["command"]["commander_uid"] is None:
        live_units = [uid for uid, u in units.items() if u["hp"] > 30]
        if live_units:
            shadow = random.choice(live_units)
            state["command"]["commander_uid"] = shadow
            log.info(f"    SHADOW COMMAND  elevated={shadow}  (player unaware)")

    state["command"]["last_tick"] = tick

    ms = int((time.perf_counter() - t0) * 1000)
    log.info(f"  command_tick done  active_orders={len(state['command']['orders'])}  {ms}ms")
    return state


# ── Sidecar blob: game map snapshot ──────────────────────────────────────────

def make_map_snapshot(state: dict) -> tuple[bytes, str]:
    """
    Serialize the current world map state as a blob.
    Hash is the name — deterministic for same map state.
    In production this would be a binary sector map or nav mesh patch.
    """
    snapshot = {
        "tick":        state["meta"]["tick"],
        "territories": state["territories"],
        "frontlines":  [
            t for t, d in state["territories"].items()
            if d["controller"] is None or d["pressure"] > 0.4
        ],
        "generated":   time.time(),
    }
    data = json.dumps(snapshot, sort_keys=True).encode()
    h    = content_hash(data)
    return data, h


# ── Main suite ────────────────────────────────────────────────────────────────

results = {}
TICKS   = 3    # run 3 full game ticks per session

log.info("=" * 60)
log.info(f"PHOENIX GAME PROCESS SUITE")
log.info(f"TARGET   {WORKER_URL}")
log.info(f"NODE UID {GAME_UID}")
log.info(f"TICKS    {TICKS}")
log.info("=" * 60)

# ── 1. Login / mount ──────────────────────────────────────────────────────────
t0 = time.perf_counter()
ctx = login(
    uid         = GAME_UID,
    ingress_url = WORKER_URL,
    egress_url  = WORKER_URL,
    auth_token  = AUTH_TOKEN,
)
results["login_ms"] = int((time.perf_counter() - t0) * 1000)
log.info(f"MOUNT OK  {results['login_ms']}ms")

# ── 2. Seed or resume world state ─────────────────────────────────────────────
if len(ctx.get("state", {})) > 0:
    world = ctx["state"]
    log.info(f"RESUME  tick={world['meta']['tick']}  theater={world['meta']['theater']}")
else:
    world = seed_world()
    log.info("SEED  fresh world — tick 0")

results["start_tick"] = world["meta"]["tick"]

# ── 3. Run game ticks ─────────────────────────────────────────────────────────
log.info("-" * 60)
log.info("RUN GAME TICKS")
log.info("-" * 60)

tick_times = []
for i in range(TICKS):
    t_tick = time.perf_counter()
    log.info(f"TICK {world['meta']['tick'] + 1}")
    world = world_tick(world)
    world = combat_tick(world)
    world = supply_tick(world)
    world = intel_tick(world)
    world = command_tick(world)
    tick_ms = int((time.perf_counter() - t_tick) * 1000)
    tick_times.append(tick_ms)
    log.info(f"  tick complete  {tick_ms}ms")
    log.info("")

results["end_tick"]  = world["meta"]["tick"]
results["tick_avg_ms"] = int(sum(tick_times) / len(tick_times))

# ── 4. Map snapshot blob ──────────────────────────────────────────────────────
map_data, map_hash = make_map_snapshot(world)
blob_dir(GAME_UID).mkdir(parents=True, exist_ok=True)
sidecar_dir(GAME_UID).mkdir(parents=True, exist_ok=True)

(blob_dir(GAME_UID) / map_hash).write_bytes(map_data)
sc = make_sidecar(
    map_hash,
    sector      = 1,
    depth       = 4,
    location    = "game-node-001",
    description = f"map-snapshot tick={world['meta']['tick']}",
)
import json as _json
(sidecar_dir(GAME_UID) / f"{map_hash}.sidecar.json").write_text(_json.dumps(sc))
log.info(f"MAP SNAPSHOT  hash={map_hash[:16]}…  size={len(map_data)}B")
results["map_hash"] = map_hash

# ── 5. Write world back into session state ────────────────────────────────────
ctx["state"] = world

# ── 6. Logout / sync / die ────────────────────────────────────────────────────
t1 = time.perf_counter()
ok = logout(ctx, wipe_local=True)
results["logout_ms"] = int((time.perf_counter() - t1) * 1000)
results["logout_ok"] = ok
log.info(f"SYNC {'OK' if ok else 'ERRORS'}  {results['logout_ms']}ms")

# ── 7. Verify — fresh login pulls game state back from R2 ────────────────────
log.info("VERIFY — fresh mount to confirm R2 round-trip…")
t2  = time.perf_counter()
ctx2 = login(
    uid         = GAME_UID,
    ingress_url = WORKER_URL,
    egress_url  = WORKER_URL,
    auth_token  = AUTH_TOKEN,
)
results["verify_ms"] = int((time.perf_counter() - t2) * 1000)

w2 = ctx2.get("state", {})

results["verify_tick"]         = w2.get("meta", {}).get("tick", -1)
results["verify_sidecars"]     = ctx2.get("pulled_sidecars", 0)
results["verify_blobs"]        = ctx2.get("fetched_blobs", 0)
results["verify_territory_ok"] = len(w2.get("territories", {})) == 4
results["verify_units_ok"]     = len(w2.get("units", {})) == 4
results["verify_supply_ok"]    = "depots" in w2.get("supply", {})
results["verify_intel_ok"]     = "fog" in w2.get("intel", {})
results["verify_command_ok"]   = "orders" in w2.get("command", {})
results["verify_tick_match"]   = results["verify_tick"] == results["end_tick"]

log.info(
    f"VERIFY LOGIN  {results['verify_ms']}ms"
    f"  tick={results['verify_tick']}"
    f"  sidecars={results['verify_sidecars']}"
    f"  blobs={results['verify_blobs']}"
)
log.info(f"  territories={len(w2.get('territories', {}))}  units={len(w2.get('units', {}))}"
         f"  supply_routes={len(w2.get('supply', {}).get('routes', []))}"
         f"  intel_fog={len(w2.get('intel', {}).get('fog', {}))}"
         f"  active_orders={len(w2.get('command', {}).get('orders', []))}")

# Final wipe
logout(ctx2, wipe_local=True)

# ── Summary ───────────────────────────────────────────────────────────────────
all_pass = (
    results.get("logout_ok", False)     and
    results.get("verify_tick_match")    and
    results.get("verify_territory_ok")  and
    results.get("verify_units_ok")      and
    results.get("verify_supply_ok")     and
    results.get("verify_intel_ok")      and
    results.get("verify_command_ok")    and
    results.get("verify_blobs", 0) > 0  and
    results.get("verify_sidecars", 0) > 0
)

log.info("")
log.info("=" * 60)
log.info("GAME PROCESS SUITE SUMMARY")
log.info("=" * 60)
log.info(f"  ticks run          {TICKS}  ({results['start_tick']} → {results['end_tick']})")
log.info(f"  avg tick time      {results['tick_avg_ms']} ms")
log.info(f"  login/mount        {results['login_ms']} ms")
log.info(f"  logout/sync        {results['logout_ms']} ms")
log.info(f"  verify mount       {results['verify_ms']} ms")
log.info(f"  tick round-trip    {'PASS' if results['verify_tick_match'] else 'FAIL'}")
log.info(f"  territory state    {'PASS' if results['verify_territory_ok'] else 'FAIL'}")
log.info(f"  unit state         {'PASS' if results['verify_units_ok'] else 'FAIL'}")
log.info(f"  supply state       {'PASS' if results['verify_supply_ok'] else 'FAIL'}")
log.info(f"  intel state        {'PASS' if results['verify_intel_ok'] else 'FAIL'}")
log.info(f"  command state      {'PASS' if results['verify_command_ok'] else 'FAIL'}")
log.info(f"  map blob           {'PASS' if results['verify_blobs'] > 0 else 'FAIL'}")
log.info(f"  map sidecar        {'PASS' if results['verify_sidecars'] > 0 else 'FAIL'}")
log.info("=" * 60)
log.info(f"RESULT: {'ALL PASS' if all_pass else 'CHECK LOGS ABOVE'}")
sys.exit(0 if all_pass else 1)
