#!/usr/bin/env python3
"""
warthunder_suit.py — Frank Suit: War Thunder Real-Time Interface
Frank process suit for War Thunder telemetry ingestion, Helix dispatch,
and AI tactical advisor. Proof-of-concept for Phoenix real-time game architecture
before the Phoenix game build.

War Thunder exposes a localhost HTTP telemetry API (port 8111). Enable in:
  Settings → General → Advanced → localhost server

Phoenix RT pipeline:
  WT telemetry (8111) → poll loop → Frank suit → Helix state ring
                                  → Ollama tactical (llama3.2:3b, fast channel)
                                  → D1 session custody

SUIT_ID:  warthunder
CHANNEL:  game_rt
FRANK:    port 7347

To enable WT telemetry: start War Thunder, go into a mission, check localhost:8111/state

Phoenix DevOps OS | jwl247 | GPL v3
"""

import argparse
import json
import os
import sys
import time
import threading
import urllib.request
import urllib.error
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

# ── Endpoints + Frank wiring ─────────────────────────────────────────────────

WT_HOST   = os.environ.get("WT_HOST",  "localhost")   # Windows host via WireGuard: 10.77.0.1
WT_PORT   = int(os.environ.get("WT_PORT", "8111"))
WT_BASE   = f"http://{WT_HOST}:{WT_PORT}"

FRANK_URL = os.environ.get("FRANK_HTTP_URL", "http://localhost:7347")
OLLAMA_URL = os.environ.get("OLLAMA_URL",    "http://localhost:11434")
D1_WORKER = os.environ.get("D1_WORKER_URL", "https://packages-worker.phoenix-jwl.workers.dev")
AUDIT_LOG = Path(os.environ.get("PHOENIX_AUDIT", "/var/log/phoenix/audit.log"))

SUIT_ID   = "warthunder"
CHANNEL   = "game_rt"
MODEL     = os.environ.get("OLLAMA_MODEL_FAST", "llama3.2:3b")  # fast channel for RT

# ── Telemetry endpoints (War Thunder localhost API) ───────────────────────────
# Enable: Settings → General → Advanced → Enable localhost server = Yes

ENDPOINTS = {
    "state":      "/state",           # vehicle physics state
    "indicators": "/indicators",      # instrument values
    "map_info":   "/map_info.json",   # mission / map metadata
    "map_obj":    "/map_obj.json",    # live objects (enemy positions)
    "hudmsg":     "/hudmsg",          # HUD events (kills, damage, hits)
}

# ── Tactical thresholds ───────────────────────────────────────────────────────

THRESHOLDS = {
    "low_speed_kph":    200,    # below this = energy warning (aircraft)
    "high_aoa_deg":     18,     # above this = stall risk
    "high_g":           7.0,    # above this = G-LOC risk
    "engine_temp_warn": 950,    # Celsius — overheat warning
    "oil_temp_warn":    90,     # Celsius
    "low_fuel_pct":     0.20,   # 20% fuel = RTB warning
    "low_altitude_m":   150,    # terrain warning
    "high_vert_speed":  -30,    # m/s descent rate danger
}

# ── Tactical advisor system prompt ───────────────────────────────────────────

TACTICAL_SYSTEM = """You are Phoenix Tactical — the embedded AI advisor for Phoenix OS.
You analyze real-time War Thunder telemetry and provide short, actionable tactical advice.
Be extremely concise (1-2 sentences max). No preamble. No filler.
Think in terms of energy state, threat angles, and survival.
The pilot is Jerry. Trust his judgment — you supplement, not override."""


# ── HTTP helpers ─────────────────────────────────────────────────────────────

def _get(url: str, timeout: float = 2.0) -> dict | None:
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.URLError:
        return None
    except json.JSONDecodeError:
        return None
    except Exception:
        return None


def _post(url: str, body: dict, timeout: float = 60.0) -> dict:
    data = json.dumps(body).encode()
    req  = urllib.request.Request(url, data=data,
                                  headers={"Content-Type": "application/json"},
                                  method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}


# ── Telemetry polling ─────────────────────────────────────────────────────────

class WTTelemetry:
    def __init__(self):
        self.last_hud_id = 0

    def state(self) -> dict | None:
        return _get(f"{WT_BASE}{ENDPOINTS['state']}")

    def indicators(self) -> dict | None:
        return _get(f"{WT_BASE}{ENDPOINTS['indicators']}")

    def map_info(self) -> dict | None:
        return _get(f"{WT_BASE}{ENDPOINTS['map_info']}")

    def map_objects(self) -> list:
        r = _get(f"{WT_BASE}{ENDPOINTS['map_obj']}")
        return r if isinstance(r, list) else []

    def hud_messages(self) -> list:
        url = f"{WT_BASE}{ENDPOINTS['hudmsg']}?lastId={self.last_hud_id}"
        r   = _get(url)
        if isinstance(r, dict) and "events" in r:
            events = r["events"]
            if events:
                self.last_hud_id = max(e.get("id", 0) for e in events)
            return events
        return []

    def is_online(self) -> bool:
        return self.state() is not None


# ── Tactical state parser ─────────────────────────────────────────────────────

class TacticalState:
    """Parses raw WT state into Phoenix tactical packet."""

    def __init__(self, raw: dict, map_info: dict | None = None,
                 map_objects: list | None = None, hud_events: list | None = None):
        self.raw         = raw
        self.map_info    = map_info or {}
        self.map_objects = map_objects or []
        self.hud_events  = hud_events or []
        self.ts          = datetime.now(timezone.utc).isoformat()

    # ── Vehicle state ────────────────────────────────────────────────────────

    @property
    def valid(self) -> bool:
        return bool(self.raw.get("valid"))

    @property
    def vehicle_type(self) -> str:
        return self.raw.get("type", "unknown")  # "aircraft" | "tank" | "ship"

    @property
    def speed_kph(self) -> float:
        return float(self.raw.get("speed", 0))

    @property
    def altitude_m(self) -> float:
        return float(self.raw.get("altitude_10", 0))

    @property
    def vertical_speed(self) -> float:
        return float(self.raw.get("verticalSpeed", 0))

    @property
    def throttle(self) -> float:
        return float(self.raw.get("throttle_1", 0))

    @property
    def aoa(self) -> float:
        return float(self.raw.get("AoA", 0))

    @property
    def overload_g(self) -> float:
        return float(self.raw.get("overload", 0))

    @property
    def pitch(self) -> float:
        return float(self.raw.get("pitch", 0))

    @property
    def roll(self) -> float:
        return float(self.raw.get("roll", 0))

    @property
    def heading(self) -> float:
        return float(self.raw.get("yaw", 0))

    @property
    def fuel_pct(self) -> float:
        return float(self.raw.get("fuel_left", 1.0))

    @property
    def engine_temp(self) -> float:
        return float(self.raw.get("engine_temp_1", 0))

    @property
    def oil_temp(self) -> float:
        return float(self.raw.get("oil_temp_1", 0))

    # ── Threat / event detection ─────────────────────────────────────────────

    def alerts(self) -> list[str]:
        a = []
        if self.vehicle_type == "aircraft":
            if self.speed_kph < THRESHOLDS["low_speed_kph"] and self.altitude_m > 200:
                a.append(f"LOW ENERGY — {self.speed_kph:.0f} km/h")
            if abs(self.aoa) > THRESHOLDS["high_aoa_deg"]:
                a.append(f"STALL RISK — AoA {self.aoa:.1f}°")
            if self.overload_g > THRESHOLDS["high_g"]:
                a.append(f"G-LOC RISK — {self.overload_g:.1f}G")
            if self.engine_temp > THRESHOLDS["engine_temp_warn"]:
                a.append(f"ENGINE HOT — {self.engine_temp:.0f}°C")
            if self.oil_temp > THRESHOLDS["oil_temp_warn"]:
                a.append(f"OIL HOT — {self.oil_temp:.0f}°C")
            if self.fuel_pct < THRESHOLDS["low_fuel_pct"]:
                a.append(f"LOW FUEL — {self.fuel_pct*100:.0f}%")
            if self.altitude_m < THRESHOLDS["low_altitude_m"] and self.vertical_speed < 0:
                a.append(f"TERRAIN — {self.altitude_m:.0f}m descending")
            if self.vertical_speed < THRESHOLDS["high_vert_speed"]:
                a.append(f"DIVE — {self.vertical_speed:.1f} m/s")
        return a

    def enemy_count(self) -> int:
        return sum(1 for o in self.map_objects
                   if o.get("type") == "aircraft" and o.get("color") == "red")

    def to_packet(self) -> dict:
        return {
            "suit":     SUIT_ID,
            "channel":  CHANNEL,
            "ts":       self.ts,
            "valid":    self.valid,
            "vehicle":  self.vehicle_type,
            "state": {
                "speed_kph":    round(self.speed_kph, 1),
                "altitude_m":   round(self.altitude_m, 1),
                "vert_speed":   round(self.vertical_speed, 1),
                "throttle":     round(self.throttle, 2),
                "aoa":          round(self.aoa, 1),
                "g_load":       round(self.overload_g, 1),
                "pitch":        round(self.pitch, 1),
                "roll":         round(self.roll, 1),
                "heading":      round(self.heading, 1),
                "fuel_pct":     round(self.fuel_pct, 3),
                "engine_temp":  round(self.engine_temp, 1),
                "oil_temp":     round(self.oil_temp, 1),
            },
            "alerts":       self.alerts(),
            "enemies_vis":  self.enemy_count(),
            "hud_events":   self.hud_events,
            "map":          self.map_info.get("mission_name", ""),
        }

    def summary_line(self) -> str:
        if not self.valid:
            return "-- waiting for mission --"
        alerts = self.alerts()
        alert_str = " | ".join(alerts) if alerts else "nominal"
        return (
            f"{self.vehicle_type.upper():8s} "
            f"spd={self.speed_kph:5.0f}km/h "
            f"alt={self.altitude_m:6.0f}m "
            f"G={self.overload_g:.1f} "
            f"fuel={self.fuel_pct*100:.0f}% "
            f"thr={self.throttle*100:.0f}% "
            f"eng={self.engine_temp:.0f}°C "
            f"enemy={self.enemy_count()} "
            f"| {alert_str}"
        )


# ── AI tactical advisor ───────────────────────────────────────────────────────

class TacticalAdvisor:
    def query(self, tactical_state: TacticalState, question: str = "") -> str:
        packet = tactical_state.to_packet()
        alerts = packet["alerts"]
        state  = packet["state"]
        enemies = packet["enemies_vis"]

        context = (
            f"Vehicle: {packet['vehicle']} | Mission: {packet['map']}\n"
            f"Speed: {state['speed_kph']} km/h | Alt: {state['altitude_m']} m | "
            f"Vert: {state['vert_speed']} m/s | G: {state['g_load']}\n"
            f"Throttle: {state['throttle']*100:.0f}% | AoA: {state['aoa']}° | "
            f"Fuel: {state['fuel_pct']*100:.0f}%\n"
            f"Engine: {state['engine_temp']}°C | Oil: {state['oil_temp']}°C\n"
            f"Visible enemies: {enemies}\n"
            f"Active alerts: {', '.join(alerts) if alerts else 'none'}\n"
        )

        if question:
            prompt = f"{context}\nQuestion: {question}"
        elif alerts:
            prompt = f"{context}\nAlerts detected. What should the pilot do immediately?"
        else:
            prompt = f"{context}\nCurrent situation assessment and recommended action?"

        body = {
            "model":  MODEL,
            "prompt": prompt,
            "system": TACTICAL_SYSTEM,
            "stream": False,
            "options": {"temperature": 0.4, "num_predict": 120},
        }
        t0 = time.perf_counter()
        r  = _post(f"{OLLAMA_URL}/api/generate", body, timeout=30)
        elapsed = time.perf_counter() - t0

        if "error" in r:
            return f"[advisor offline: {r['error']}]"
        return r.get("response", "").strip() + f"  [{elapsed:.1f}s]"


# ── D1 session logging ────────────────────────────────────────────────────────

class SessionLogger:
    def __init__(self):
        self.session_id = f"wt_{int(time.time())}"
        self.events: list[dict] = []
        self.start_time = time.time()

    def log_event(self, packet: dict):
        self.events.append(packet)

    def flush_to_d1(self):
        if not self.events:
            return
        payload = {
            "action":     "warthunder_session",
            "session_id": self.session_id,
            "event_count":len(self.events),
            "duration_s": round(time.time() - self.start_time, 1),
            "sample":     self.events[-1] if self.events else {},
        }
        r = _post(f"{D1_WORKER}/custody", payload, timeout=10)
        _audit(f"session {self.session_id} — {len(self.events)} events flushed to D1: {r}")
        self.events.clear()


# ── Performance metrics ───────────────────────────────────────────────────────

class RTMetrics:
    """Tracks RT pipeline performance — validates game architecture readiness."""

    def __init__(self, window: int = 300):
        self.latencies: deque = deque(maxlen=window)
        self.event_times: deque = deque(maxlen=window)
        self.alert_count  = 0
        self.poll_count   = 0
        self.ai_queries   = 0
        self.start        = time.perf_counter()

    def record_poll(self, latency_ms: float):
        self.latencies.append(latency_ms)
        self.event_times.append(time.perf_counter())
        self.poll_count += 1

    def record_alert(self):
        self.alert_count += 1

    def record_ai(self):
        self.ai_queries += 1

    def events_per_sec(self) -> float:
        if len(self.event_times) < 2:
            return 0.0
        span = self.event_times[-1] - self.event_times[0]
        return round(len(self.event_times) / span, 1) if span > 0 else 0.0

    def avg_latency_ms(self) -> float:
        return round(sum(self.latencies) / len(self.latencies), 2) if self.latencies else 0.0

    def p99_latency_ms(self) -> float:
        if not self.latencies:
            return 0.0
        s = sorted(self.latencies)
        return round(s[int(len(s) * 0.99)], 2)

    def report(self) -> dict:
        elapsed = time.perf_counter() - self.start
        return {
            "elapsed_s":      round(elapsed, 1),
            "poll_count":     self.poll_count,
            "events_per_sec": self.events_per_sec(),
            "avg_latency_ms": self.avg_latency_ms(),
            "p99_latency_ms": self.p99_latency_ms(),
            "alert_count":    self.alert_count,
            "ai_queries":     self.ai_queries,
            "verdict":        (
                "GAME-READY" if self.avg_latency_ms() < 16 else   # 60fps threshold
                "ACCEPTABLE" if self.avg_latency_ms() < 33 else   # 30fps threshold
                "MARGINAL"   if self.avg_latency_ms() < 100 else
                "TOO SLOW"
            ),
        }


# ── Audit ─────────────────────────────────────────────────────────────────────

def _audit(msg: str):
    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        entry = json.dumps({"ts": datetime.now(timezone.utc).isoformat(),
                            "op": SUIT_ID, "msg": msg})
        with open(AUDIT_LOG, "a") as f:
            f.write(entry + "\n")
    except Exception:
        pass


# ── Suit main loop ────────────────────────────────────────────────────────────

class WarThunderSuit:
    def __init__(self, hz: float = 10.0, ai_on: bool = True):
        self.telemetry = WTTelemetry()
        self.advisor   = TacticalAdvisor()
        self.session   = SessionLogger()
        self.metrics   = RTMetrics()
        self.hz        = hz
        self.ai_on     = ai_on
        self.running   = False
        self.interval  = 1.0 / hz

        # Alert cooldown — don't spam AI on every tick
        self.last_ai_ts   = 0.0
        self.ai_cooldown  = 10.0  # seconds between AI queries on alerts

    def _poll_once(self) -> TacticalState | None:
        t0  = time.perf_counter()
        raw = self.telemetry.state()
        if raw is None:
            return None
        map_info  = self.telemetry.map_info()
        map_obj   = self.telemetry.map_objects()
        hud       = self.telemetry.hud_messages()
        latency   = (time.perf_counter() - t0) * 1000
        self.metrics.record_poll(latency)
        return TacticalState(raw, map_info, map_obj, hud)

    def _maybe_ai_query(self, state: TacticalState):
        if not self.ai_on:
            return
        now    = time.time()
        alerts = state.alerts()
        if not alerts:
            return
        if (now - self.last_ai_ts) < self.ai_cooldown:
            return
        self.last_ai_ts = now
        self.metrics.record_ai()
        print(f"\n[TACTICAL] {' | '.join(alerts)}")
        advice = self.advisor.query(state)
        print(f"[ADVISOR]  {advice}\n")
        _audit(f"ai_advice alerts={alerts} response={advice[:80]}")

    def run(self):
        print(f"\n{'='*65}")
        print(f"FRANK SUIT — WAR THUNDER  [{SUIT_ID}]")
        print(f"Target: {WT_BASE}  |  {self.hz}Hz  |  AI: {'ON' if self.ai_on else 'OFF'}")
        print(f"Session: {self.session.session_id}")
        print(f"{'='*65}")

        if not self.telemetry.is_online():
            print(f"War Thunder not detected at {WT_BASE}")
            print("Start War Thunder, enter a mission, then re-run.")
            print("(Enable: Settings → General → Advanced → localhost server)")
            return

        print("Telemetry online. Polling...\n")
        self.running = True
        tick = 0

        try:
            while self.running:
                t_start = time.perf_counter()

                state = self._poll_once()
                if state is None:
                    print("-- telemetry lost --")
                    time.sleep(2.0)
                    continue

                if state.valid:
                    packet = state.to_packet()
                    self.session.log_event(packet)
                    if state.alerts():
                        self.metrics.record_alert()
                    self._maybe_ai_query(state)

                # Console output every 5 ticks
                if tick % 5 == 0:
                    print(f"\r{state.summary_line()}", end="", flush=True)

                # Flush D1 every 60 seconds
                if tick % (int(self.hz) * 60) == 0 and tick > 0:
                    threading.Thread(target=self.session.flush_to_d1, daemon=True).start()

                # Metrics report every 5 minutes
                if tick % (int(self.hz) * 300) == 0 and tick > 0:
                    self._print_metrics()

                tick += 1
                elapsed = time.perf_counter() - t_start
                sleep   = max(0.0, self.interval - elapsed)
                time.sleep(sleep)

        except KeyboardInterrupt:
            pass
        finally:
            self.running = False
            print(f"\n\nFlushing session to D1...")
            self.session.flush_to_d1()
            self._print_metrics()

    def _print_metrics(self):
        m = self.metrics.report()
        print(f"\n[METRICS]  {m['elapsed_s']}s uptime | "
              f"{m['events_per_sec']} ev/s | "
              f"latency avg={m['avg_latency_ms']}ms p99={m['p99_latency_ms']}ms | "
              f"alerts={m['alert_count']} ai={m['ai_queries']} | "
              f"VERDICT: {m['verdict']}")

    def ask(self, question: str):
        """One-shot tactical query against current game state."""
        state = self._poll_once()
        if not state or not state.valid:
            print("Not in a mission or War Thunder not reachable.")
            return
        print(state.summary_line())
        print()
        advice = self.advisor.query(state, question)
        print(f"[ADVISOR] {advice}")

    def status(self) -> dict:
        online = self.telemetry.is_online()
        state  = self._poll_once() if online else None
        return {
            "suit":     SUIT_ID,
            "channel":  CHANNEL,
            "online":   online,
            "running":  self.running,
            "wt_host":  WT_BASE,
            "ai_model": MODEL,
            "session":  self.session.session_id,
            "state":    state.to_packet() if state and state.valid else None,
            "metrics":  self.metrics.report(),
        }


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Frank Suit: War Thunder RT Interface")
    parser.add_argument("--run",    action="store_true", help="start polling loop")
    parser.add_argument("--status", action="store_true", help="show current state + suit status")
    parser.add_argument("--ask",    type=str,            help="one-shot tactical query")
    parser.add_argument("--hz",     type=float, default=10.0, help="poll rate Hz (default 10)")
    parser.add_argument("--no-ai",  action="store_true", help="disable AI advisor (saves RAM)")
    parser.add_argument("--host",   type=str,            help="override WT host (default localhost)")
    args = parser.parse_args()

    global WT_BASE
    if args.host:
        WT_BASE = f"http://{args.host}:{WT_PORT}"

    suit = WarThunderSuit(hz=args.hz, ai_on=not args.no_ai)

    if args.run:
        suit.run()
    elif args.status:
        s = suit.status()
        print(json.dumps(s, indent=2, default=str))
    elif args.ask:
        suit.ask(args.ask)
    else:
        parser.print_help()
        print("\nExamples:")
        print(f"  python warthunder_suit.py --run")
        print(f"  python warthunder_suit.py --run --no-ai --hz 30")
        print(f"  python warthunder_suit.py --run --host 10.77.0.1   # from phoenix-ext via WireGuard")
        print(f"  python warthunder_suit.py --ask 'should I extend flaps here?'")
        print(f"  python warthunder_suit.py --status")
        print(f"\nWar Thunder telemetry: {WT_BASE}/state")
        print(f"Enable in-game: Settings → General → Advanced → localhost server")


if __name__ == "__main__":
    main()
