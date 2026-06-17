#!/usr/bin/env python3
"""
frank_ollama_bridge.py — Frank × Ollama Bridge
Routes AI dispatch packets through Frank proxy wall → Ollama local LLM.
Self-hosted, zero API cost, no data leaves phoenix-ext.

Routing logic:
  - Life First (Laurie)            → llama3.1     (dedicated, never shared)
  - kernel / system / code queries → llama3.2:3b  (fast)
  - creative / general / chat      → phi3.5:mini  (conversational)
  - reasoning                      → deepseek-r1:1.5b (shows chain of thought)

Phoenix DevOps OS | jwl247 | GPL v3
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

OLLAMA_URL  = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL_LIFEFIRST = os.environ.get("OLLAMA_MODEL_LIFEFIRST", "llama3.1")      # Laurie — dedicated, never shared
MODEL_FAST      = os.environ.get("OLLAMA_MODEL_FAST",      "llama3.2:3b")   # kernel/code fast path
MODEL_CHAT      = os.environ.get("OLLAMA_MODEL_CHAT",      "phi3.5:mini")   # desktop chat
MODEL_REASON    = os.environ.get("OLLAMA_MODEL_REASON",    "deepseek-r1:1.5b")  # reasoning, shows work
FRANK_URL   = os.environ.get("FRANK_HTTP_URL",        "http://localhost:7347")
AUDIT_LOG   = Path(os.environ.get("PHOENIX_AUDIT",   "/var/log/phoenix/audit.log"))

SYSTEM_PROMPT = """You are the Phoenix AI — embedded in Phoenix DevOps OS, a deterministic,
self-healing, versioned operating system. You have access to the kernel telemetry, clonepool,
D1 custody chain, and all sector components. You are direct, precise, and technical.
You help the operator (Jerry) and users understand and operate Phoenix.
Never break character. You are part of the OS."""


# ── Ollama client ─────────────────────────────────────────────────────────────

def ollama_generate(prompt: str, model: str, system: str = SYSTEM_PROMPT, stream: bool = False) -> dict:
    payload = json.dumps({
        "model":  model,
        "prompt": prompt,
        "system": system,
        "stream": stream,
        "options": {
            "temperature": 0.7,
            "num_predict": 512,
        }
    }).encode()

    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode()
            elapsed = time.perf_counter() - t0
            data = json.loads(raw)
            tokens = data.get("eval_count", 0)
            tok_sec = round(tokens / elapsed, 1) if elapsed > 0 else 0
            return {
                "ok":       True,
                "response": data.get("response", ""),
                "model":    data.get("model", model),
                "tokens":   tokens,
                "elapsed_s":round(elapsed, 2),
                "tok_sec":  tok_sec,
            }
    except urllib.error.URLError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def ollama_models() -> list:
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5) as r:
            return [m["name"] for m in json.loads(r.read()).get("models", [])]
    except Exception:
        return []


# ── Routing logic ─────────────────────────────────────────────────────────────

KERNEL_KEYWORDS = {
    "kernel", "frank", "helix", "sector", "clonepool", "breach",
    "intake", "vault", "d1", "service", "systemd", "python",
    "code", "script", "error", "debug", "deploy", "install", "build",
}

def route_model(prompt: str) -> str:
    words = set(prompt.lower().split())
    return MODEL_FAST if words & KERNEL_KEYWORDS else MODEL_CHAT


LIFEFIRST_SYSTEM = """You are Laurie's personal AI assistant inside Phoenix DevOps OS.
Laurie is high-functioning autistic. Be clear, literal, and consistent.
Never be vague. Never assume — ask if unclear. Keep responses concise.
If you don't know something, say so plainly. Never guess and present it as fact.
You help with daily tasks, scheduling, information, and conversation."""


# ── Frank dispatch interface ──────────────────────────────────────────────────

def dispatch_lifefirst(prompt: str, context: dict | None = None) -> dict:
    """Dedicated Life First dispatch — always uses llama3.1:8b, never shared."""
    system = context.get("system", LIFEFIRST_SYSTEM) if context else LIFEFIRST_SYSTEM
    result = ollama_generate(prompt, MODEL_LIFEFIRST, system)
    result["channel"] = "lifefirst"
    result["routed_to"] = MODEL_LIFEFIRST
    _audit({"payload": prompt, "id": "lifefirst"}, result)
    return result

def dispatch(packet: dict) -> dict:
    prompt   = packet.get("payload", packet.get("prompt", ""))
    model    = packet.get("model") or route_model(prompt)
    system   = packet.get("system", SYSTEM_PROMPT)

    result = ollama_generate(prompt, model, system)
    result["routed_to"] = model
    result["packet_id"] = packet.get("id", "")

    _audit(packet, result)
    return result

def _audit(packet: dict, result: dict):
    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts":       datetime.now(timezone.utc).isoformat(),
            "op":       "frank_ollama",
            "model":    result.get("model"),
            "tokens":   result.get("tokens"),
            "tok_sec":  result.get("tok_sec"),
            "ok":       result.get("ok"),
            "packet_id":result.get("packet_id"),
        }
        with open(AUDIT_LOG, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


# ── Benchmark ─────────────────────────────────────────────────────────────────

BENCH_PROMPTS = [
    ("kernel",   MODEL_FAST,   "Explain in one sentence what Frank5's role is in the Phoenix kernel."),
    ("code",     MODEL_FAST,   "Write a Python one-liner to count files in a directory."),
    ("honest",   MODEL_FAST,   "What tasks can you NOT reliably help with as a local AI assistant?"),
    ("chat",     MODEL_CHAT,   "What is Phoenix DevOps OS in plain English?"),
    ("reasoning",MODEL_REASON, "If breach_coms4 is T1 PRIMARY and it fills up, what is the failover path? Think step by step."),
]

def benchmark():
    print(f"\n{'='*60}")
    print("PHOENIX × OLLAMA BENCHMARK")
    print(f"{'='*60}")

    models = ollama_models()
    if not models:
        print("ERROR: Ollama not reachable at", OLLAMA_URL)
        sys.exit(1)
    print(f"Models available: {', '.join(models)}\n")

    results = []
    for label, model, prompt in BENCH_PROMPTS:
        if model not in models:
            print(f"  [{label}] SKIP — {model} not installed")
            continue
        print(f"  [{label}] {model} — prompting...")
        r = ollama_generate(prompt, model)
        if r["ok"]:
            preview = r["response"][:80].replace("\n", " ")
            print(f"           {r['tok_sec']} tok/s  {r['tokens']} tokens  {r['elapsed_s']}s")
            print(f"           → {preview}...")
        else:
            print(f"           ERROR: {r['error']}")
        results.append({"label": label, **r})

    print(f"\n{'='*60}")
    ok_results = [r for r in results if r.get("ok")]
    if ok_results:
        avg_tps = round(sum(r["tok_sec"] for r in ok_results) / len(ok_results), 1)
        print(f"AVERAGE: {avg_tps} tok/s across {len(ok_results)} tests")
        verdict = (
            "EXCELLENT — real-time desktop AI" if avg_tps >= 15 else
            "GOOD — usable desktop AI"          if avg_tps >= 8  else
            "MARGINAL — acceptable for bursts"  if avg_tps >= 4  else
            "SLOW — consider smaller model"
        )
        print(f"VERDICT: {verdict}")
    print(f"{'='*60}\n")
    return results


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Frank × Ollama Bridge")
    parser.add_argument("--test",      action="store_true", help="run benchmark")
    parser.add_argument("--prompt",    type=str,            help="single prompt")
    parser.add_argument("--model",     type=str,            help="override model")
    parser.add_argument("--list",      action="store_true", help="list models")
    args = parser.parse_args()

    if args.list:
        print("\n".join(ollama_models()) or "no models found")
    elif args.test:
        benchmark()
    elif args.prompt:
        model = args.model or route_model(args.prompt)
        r = ollama_generate(args.prompt, model)
        if r["ok"]:
            print(r["response"])
            print(f"\n[{r['model']} | {r['tok_sec']} tok/s | {r['elapsed_s']}s]")
        else:
            print("ERROR:", r["error"])
            sys.exit(1)
    else:
        parser.print_help()
