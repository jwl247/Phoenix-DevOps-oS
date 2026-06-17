#!/usr/bin/env python3
"""
frank_pager.py — Frank Model Paging Manager
Manages which LLM is resident in RAM. Coordinates with Helix to avoid
RAM contention on 8GB machines. Frank calls this before every dispatch.

RAM budget (8GB total):
  Helix floor:   4.0 GB  (always resident, non-negotiable)
  Available:     4.0 GB  for one LLM at a time

Model sizes (approx, Q4):
  llama3.1:      4.9 GB  — needs Helix to yield ~1GB to fit
  llama3.2:3b:   2.0 GB  — fits clean, keep as hot standby
  phi3.5:latest: 2.2 GB  — fits clean
  deepseek-r1:   1.1 GB  — fits clean, evict immediately after

Paging strategy:
  - llama3.2:3b is the default hot model (always try to keep warm)
  - llama3.1 (Life First) loads on demand, signals Helix to yield, evicts after TTL
  - deepseek-r1 is one-shot: load → infer → evict immediately
  - phi3.5 shares the 2GB slot with llama3.2:3b (swap if needed)

Phoenix DevOps OS | jwl247 | GPL v3
"""

import json
import os
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

OLLAMA_URL   = os.environ.get("OLLAMA_URL",        "http://localhost:11434")
HELIX_SHM    = Path(os.environ.get("PHOENIX_SHM",  "/tmp/phoenix_shm"))
AUDIT_LOG    = Path(os.environ.get("PHOENIX_AUDIT", "/var/log/phoenix/audit.log"))

# RAM budget in GB
RAM_TOTAL    = 8.0
HELIX_FLOOR  = 4.0   # Helix minimum — never drop below this
HELIX_YIELD  = 1.0   # GB Helix can yield temporarily for large models
AVAILABLE    = RAM_TOTAL - HELIX_FLOOR  # 4.0 GB normally

# Model registry: size in GB + eviction policy
MODELS = {
    "llama3.1:latest":    {"gb": 4.9, "ttl": 300,  "needs_yield": True,  "channel": "lifefirst"},
    "llama3.2:3b":        {"gb": 2.0, "ttl": 120,  "needs_yield": False, "channel": "fast"},
    "phi3.5:latest":      {"gb": 2.2, "ttl": 120,  "needs_yield": False, "channel": "chat"},
    "deepseek-r1:1.5b":   {"gb": 1.1, "ttl": 0,    "needs_yield": False, "channel": "reason"},
}

# Hot standby — keep this model warm between requests when RAM allows
HOT_STANDBY = "llama3.2:3b"


# ── Ollama API ────────────────────────────────────────────────────────────────

def _ollama(path: str, method: str = "GET", body: dict | None = None) -> dict:
    url = f"{OLLAMA_URL}{path}"
    data = json.dumps(body).encode() if body else None
    req  = urllib.request.Request(url, data=data, method=method,
                                  headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}

def running_models() -> list[dict]:
    """Return list of models currently loaded in Ollama RAM via /api/ps."""
    r = _ollama("/api/ps")
    return r.get("models", [])

def resident_names() -> list[str]:
    return [m["name"] for m in running_models()]

def total_resident_gb() -> float:
    return sum(m.get("size", 0) for m in running_models()) / 1e9

def evict(model: str) -> bool:
    """Evict a model from RAM by sending a keep_alive=0 request."""
    body = {"model": model, "prompt": "", "stream": False, "keep_alive": 0}
    r = _ollama("/api/generate", "POST", body)
    _log(f"evict {model} — {'ok' if 'error' not in r else r['error']}")
    return "error" not in r

def prewarm(model: str, ttl: int = 120) -> bool:
    """Load a model into RAM with a 1-token dummy request."""
    body = {"model": model, "prompt": "hi", "stream": False,
            "keep_alive": ttl, "options": {"num_predict": 1}}
    r = _ollama("/api/generate", "POST", body)
    ok = "error" not in r and r.get("response") is not None
    _log(f"prewarm {model} ttl={ttl}s — {'ok' if ok else r.get('error','?')}")
    return ok


# ── Helix coordination ────────────────────────────────────────────────────────

def _helix_signal(signal: str) -> None:
    """Write a signal file to shared memory for Helix to read."""
    HELIX_SHM.mkdir(parents=True, exist_ok=True)
    sig_file = HELIX_SHM / "pager.sig"
    sig_file.write_text(json.dumps({
        "signal": signal,
        "ts": datetime.now(timezone.utc).isoformat(),
    }))

def helix_yield() -> None:
    """Ask Helix to yield ~1GB of compression buffer."""
    _helix_signal("YIELD")
    _log("helix YIELD requested")

def helix_reclaim() -> None:
    """Tell Helix to reclaim its full RAM footprint."""
    _helix_signal("RECLAIM")
    _log("helix RECLAIM signalled")


# ── Paging logic ──────────────────────────────────────────────────────────────

def ensure_resident(model: str) -> dict:
    """
    Core paging operation. Called before every dispatch.
    Returns {"ok": True/False, "action": "already_resident"|"loaded"|"failed", "yielded_helix": bool}
    """
    meta     = MODELS.get(model, {})
    model_gb = meta.get("gb", 2.0)
    ttl      = meta.get("ttl", 120)
    needs_yield = meta.get("needs_yield", False)

    residents = resident_names()

    # Already loaded — just extend TTL
    if model in residents:
        _log(f"page hit — {model} already resident")
        return {"ok": True, "action": "already_resident", "yielded_helix": False}

    # Evict anything that won't fit alongside the new model
    evicted = []
    for r in list(residents):
        r_gb = MODELS.get(r, {}).get("gb", 2.0)
        if (total_resident_gb() + model_gb) > (AVAILABLE + (HELIX_YIELD if needs_yield else 0)):
            evict(r)
            evicted.append(r)

    # Signal Helix to yield if model is large (llama3.1)
    yielded = False
    if needs_yield:
        helix_yield()
        yielded = True
        time.sleep(1)  # Give Helix a moment to release

    # Load the model
    ok = prewarm(model, ttl)

    if not ok:
        if yielded:
            helix_reclaim()
        _log(f"page FAIL — could not load {model}")
        return {"ok": False, "action": "failed", "yielded_helix": yielded}

    _log(f"page load — {model} resident (evicted: {evicted}, helix_yielded: {yielded})")

    # Schedule Helix reclaim after TTL if we yielded
    if yielded and ttl > 0:
        _schedule_reclaim(ttl)

    return {"ok": True, "action": "loaded", "yielded_helix": yielded, "evicted": evicted}


def _schedule_reclaim(delay_s: int) -> None:
    """Write a reclaim-after timestamp so a background process can honour it."""
    HELIX_SHM.mkdir(parents=True, exist_ok=True)
    (HELIX_SHM / "pager_reclaim_at").write_text(
        str(time.time() + delay_s)
    )


def restore_standby() -> None:
    """After a large-model session ends, evict it and restore the hot standby."""
    residents = resident_names()
    for r in residents:
        if r != HOT_STANDBY and MODELS.get(r, {}).get("gb", 0) > AVAILABLE / 2:
            evict(r)
            helix_reclaim()
    if HOT_STANDBY not in resident_names():
        prewarm(HOT_STANDBY, ttl=300)


# ── Status ────────────────────────────────────────────────────────────────────

def status() -> dict:
    models    = running_models()
    res_gb    = sum(m.get("size", 0) for m in models) / 1e9
    helix_sig = "unknown"
    sig_file  = HELIX_SHM / "pager.sig"
    if sig_file.exists():
        try:
            helix_sig = json.loads(sig_file.read_text()).get("signal", "unknown")
        except Exception:
            pass
    return {
        "resident":      [m["name"] for m in models],
        "resident_gb":   round(res_gb, 2),
        "available_gb":  round(AVAILABLE - res_gb, 2),
        "helix_floor_gb": HELIX_FLOOR,
        "helix_signal":  helix_sig,
        "hot_standby":   HOT_STANDBY,
        "ts":            datetime.now(timezone.utc).isoformat(),
    }


# ── Audit ─────────────────────────────────────────────────────────────────────

def _log(msg: str) -> None:
    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"ts": datetime.now(timezone.utc).isoformat(),
                           "op": "frank_pager", "msg": msg})
        with open(AUDIT_LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse, sys

    parser = argparse.ArgumentParser(description="Frank Model Paging Manager")
    parser.add_argument("--status",   action="store_true", help="show resident models + RAM")
    parser.add_argument("--ensure",   type=str,            help="ensure model is resident")
    parser.add_argument("--evict",    type=str,            help="evict a model from RAM")
    parser.add_argument("--prewarm",  type=str,            help="prewarm a model")
    parser.add_argument("--standby",  action="store_true", help="restore hot standby")
    args = parser.parse_args()

    if args.status:
        s = status()
        print(f"\n{'='*50}")
        print("FRANK PAGER STATUS")
        print(f"{'='*50}")
        print(f"Resident:     {', '.join(s['resident']) or 'none'}")
        print(f"RAM used:     {s['resident_gb']} GB")
        print(f"RAM free:     {s['available_gb']} GB  (of {AVAILABLE} GB budget)")
        print(f"Helix floor:  {s['helix_floor_gb']} GB  (always reserved)")
        print(f"Helix signal: {s['helix_signal']}")
        print(f"Hot standby:  {s['hot_standby']}")
        print(f"{'='*50}\n")

    elif args.ensure:
        r = ensure_resident(args.ensure)
        print(json.dumps(r, indent=2))

    elif args.evict:
        ok = evict(args.evict)
        print("evicted" if ok else "failed")

    elif args.prewarm:
        ok = prewarm(args.prewarm)
        print("warmed" if ok else "failed")

    elif args.standby:
        restore_standby()
        print("standby restored")

    else:
        parser.print_help()
