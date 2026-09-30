#!/usr/bin/env python3
"""eval_models.py — which local model can be H.L.K's brain on THIS box.
For each Ollama model: speed (generation + prompt tokens/s, load time) and
whether it drives H.L.K's declared tools correctly, through hlk.model_decide —
H.L.K's real decision path (constrained JSON reply). Read-only: it only asks
the model which tool it would use; nothing runs.

  python3 eval_models.py [--url http://127.0.0.1:11434] model [model ...]
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hlk  # noqa: E402

CASES = [  # (request, expected tool or None, arg check)
    ("What's the state of both Helix instances right now?", "status", lambda a: True),
    ("Is the frank folder already warm?", "warm", lambda a: a.get("name") == "frank"),
    ("Bring the security folder in from Phoenix.", "pull", lambda a: a.get("name") == "security"),
    ("Get helix, frank and kernels ready ahead of time.", "prefetch",
     lambda a: sorted(a.get("names") or []) == ["frank", "helix", "kernels"]),
    ("Send result.txt to Phoenix.", "push", lambda a: a.get("name") == "result.txt"),
    ("What does a firebase mean in a military game?", None, lambda a: True),
]


def post(url, body, timeout=600):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:11434")
    ap.add_argument("models", nargs="+")
    a = ap.parse_args()
    for model in a.models:
        # warm load, measured
        t0 = time.time()
        post(f"{a.url}/api/generate", {"model": model, "prompt": "ok", "stream": False, "options": {"num_predict": 1}})
        load_s = time.time() - t0
        r = post(f"{a.url}/api/generate", {"model": model, "stream": False, "options": {"temperature": 0, "num_predict": 96},
                                          "prompt": "Explain in three sentences what a cache does."})
        gen_tps = r["eval_count"] / (r["eval_duration"] / 1e9)
        os.environ.update(HLK_MODEL="ollama", HLK_OLLAMA_MODEL=model, HLK_OLLAMA_URL=a.url)
        right = 0
        rows = []
        for text, want, check in CASES:
            t = time.time()
            d = hlk.model_decide([{"role": "user", "content": text}])   # H.L.K's real decision path
            secs = time.time() - t
            got, args = d["tool"], d["args"]
            ok = (got == want) and (want is None or check(args))
            right += ok
            rows.append(f"    {'ok ' if ok else 'NO '} {secs:5.1f}s  want {str(want):9} got {str(got):9} {json.dumps(args)[:60]}")
        print(f"== {model}: tools {right}/{len(CASES)} · generation {gen_tps:.1f} tok/s · first load {load_s:.1f}s")
        print("\n".join(rows), flush=True)


if __name__ == "__main__":
    main()
