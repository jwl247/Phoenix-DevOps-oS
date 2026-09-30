#!/usr/bin/env python3
"""
hlk.py — H.L.K on a Phoenix worker box: the third of the triplet
(ingress Helix · egress Helix · H.L.K). docs/plans/compaq-road-test-plan.md, Phase 3.

H.L.K acts on the data. It tells ingress what is coming (pull / prefetch from
Phoenix in R2, every byte checked against its D1 SHA3), keeps ONE shared index
of what she already holds (content hash -> warm in ingress / staged in egress),
reads both Helix instances' own counters, and sends results out through egress
(push: R2 + D1 receipt). Ingress and egress never talk to each other — H.L.K is
the peer in the middle.

A director first, a model second (CLAUDE.md "the AI layer is a vendor too"):
every tool works over plain HTTP with no model at all; a model, when one is
configured (Ollama, or the Anthropic API), drives the SAME declared tools.

Permission tiers (CLAUDE.md, THE INTERACTION MODEL):
  auto  status, warm, pull, prefetch, verify, stage, jobs — local or read-only
  ask   push — changes shared state in R2/D1; waits for an explicit yes on
        POST /confirm (never inferred from chat text)
Every call is logged to audit.jsonl, so "what did you just do" has an answer.

Listens on 127.0.0.1 and, with --mesh, this box's mesh address; only callers in
--allow-from, and only with this box's token (~/.phoenix-hlk/token, 0600).
Standard library only. Linux.
"""
import argparse
import concurrent.futures
import hashlib
import http.server
import json
import os
import re
import secrets
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid

VERSION = "0.2.0"
HOME = os.path.expanduser("~")
STATE = os.environ.get("HLK_STATE", os.path.join(HOME, ".phoenix-hlk"))
CRED = os.environ.get("HLK_CRED", os.path.join(HOME, ".phoenix-worker"))
WORKDIR = os.environ.get("HLK_WORKDIR", "/srv/helix-ingress/phoenix-roadtest")
EGRESS = os.environ.get("HLK_EGRESS", "/srv/helix-egress/phoenix-roadtest-out")
INSTANCES = ("ingress", "egress")
NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,120}$")

_lock = threading.Lock()
_pending = {}                       # id -> {tool, args, question, created}
_jobs = {}                          # id -> {names, done, results, started}
_last_counters = {}                 # instance -> counters at the previous status()
_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)


# ── plumbing ──────────────────────────────────────────────────────────────
def now_ns():
    return time.time_ns()


def sha3_file(path):
    h = hashlib.sha3_512()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cred(name):
    with open(os.path.join(CRED, name), encoding="utf-8") as f:
        return f.read().strip()


def db():
    c = sqlite3.connect(os.path.join(STATE, "index.db"), timeout=10)
    c.execute("""CREATE TABLE IF NOT EXISTS items (
        name TEXT PRIMARY KEY, kind TEXT, side TEXT, path TEXT, sha3 TEXT,
        bytes INTEGER, files INTEGER, pulled_at REAL, used_at REAL, uses INTEGER DEFAULT 0,
        staged_at REAL, pushed_at REAL, pull_ms REAL)""")
    return c


def audit(entry):
    entry["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with _lock, open(os.path.join(STATE, "audit.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def run_intake(args, cwd):
    """intake.sh from the worker dir, isolated exactly like worker-bootstrap.sh.
    The data-plane key goes in the environment, never on this process's argv."""
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.path.join(WORKDIR, "home"),
           "PHOENIX_WORKER_URL": cred("url"), "PHOENIX_AUTH": cred("auth"),
           "CF_ACCESS_CLIENT_ID": "", "CF_ACCESS_CLIENT_SECRET": "",
           "CLONEPOOL_DIR": os.path.join(WORKDIR, "pool"), "INTAKE_YES": "1"}
    p = subprocess.run(["bash", os.path.join(WORKDIR, "bin", "intake.sh")] + args, cwd=cwd, env=env,
                       stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=3600)
    return p.returncode, (p.stdout + p.stderr)[-2000:]


def worker_meta(name):
    """The D1 row for a name (hash baseline), from Phoenix."""
    hexid = name.encode().hex()
    req = urllib.request.Request(f"{cred('url')}/clonepool/{hexid}?meta=true",
                                 headers={"Authorization": f"Bearer {cred('auth')}",
                                          # Cloudflare answers Python's default UA with 403 (error 1010)
                                          "User-Agent": f"phoenix-hlk/{VERSION}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def safe_name(n):
    if not isinstance(n, str) or not NAME_RE.match(n) or n in (".", ".."):
        raise ValueError(f"not an item name: {n!r}")
    return n


def dir_stats(path):
    files = size = 0
    for root, _, fs in os.walk(path):
        for f in fs:
            files += 1
            size += os.path.getsize(os.path.join(root, f))
    return files, size


# ── the Helix instances ───────────────────────────────────────────────────
def helix_counters(instance):
    out = subprocess.run(["sudo", "-n", "dmsetup", "status", f"helix-{instance}"],
                         capture_output=True, text=True, timeout=10).stdout
    body = out.split(" helix ", 1)
    if len(body) != 2:
        return None
    toks = body[1].split()
    c = {}
    for i, t in enumerate(toks[:-1]):
        v = toks[i + 1]
        if re.fullmatch(r"-?\d+(\.\d+)?", v) and re.fullmatch(r"[a-z_0-9]+", t) and not re.fullmatch(r"-?\d+(\.\d+)?", t):
            c[t] = float(v) if "." in v else int(v)
    if "state" in toks:
        c["state"] = toks[toks.index("state") + 1]
    return c


def tool_status(_args):
    """Both Helix instances, from their own counters. hit_rate_now is since the
    last status() call — her honest load signal (heat alone reads ~0 under a
    steady stream: she cools herself with data)."""
    out = {}
    for inst in INSTANCES:
        c = helix_counters(inst)
        if c is None:
            out[inst] = {"up": False}
            continue
        served = c.get("hits", 0) + c.get("zhits", 0) + c.get("b_hits", 0)
        asked = served + c.get("misses", 0)
        prev = _last_counters.get(inst)
        now = None
        if prev:
            ds = served - (prev.get("hits", 0) + prev.get("zhits", 0) + prev.get("b_hits", 0))
            dm = c.get("misses", 0) - prev.get("misses", 0)
            now = round(100.0 * ds / (ds + dm), 1) if (ds + dm) > 0 else None
        _last_counters[inst] = c
        out[inst] = {"up": True, "state": c.get("state"), "heat": c.get("heat"),
                     "compression": c.get("compression"),
                     "hit_rate_total": round(100.0 * served / asked, 1) if asked else None,
                     "hit_rate_now": now, "hits": served, "misses": c.get("misses", 0),
                     "strandA_blocks": c.get("raw", 0), "strandB_used": c.get("used", 0)}
    with db() as con:
        n, warm_bytes = con.execute("SELECT count(*), coalesce(sum(bytes),0) FROM items WHERE side='ingress'").fetchone()
    out["index"] = {"warm_items": n, "warm_bytes": warm_bytes}
    return out


# ── tools ────────────────────────────────────────────────────────────────
def tool_pull(args):
    """R2 -> ingress through the import method; every file checked against D1.
    Into a fresh temp dir first, then swapped in, so a failed pull never
    leaves a half item where a good one was."""
    name = safe_name(args.get("name"))
    ops = os.path.join(WORKDIR, "ops")
    tmp = os.path.join(WORKDIR, "ops", f".pull-{uuid.uuid4().hex[:8]}")
    os.makedirs(tmp)
    t0 = now_ns()
    try:
        rc, log = run_intake(["clone", name], cwd=tmp)
        got = os.path.join(tmp, name)
        if rc != 0 or not os.path.exists(got):
            return {"ok": False, "name": name, "error": "pull failed", "log": log[-600:]}
        dest = os.path.join(ops, name)
        if os.path.isdir(dest) and not os.path.islink(dest):
            subprocess.run(["rm", "-rf", dest], check=True)
        elif os.path.exists(dest):
            os.remove(dest)
        os.rename(got, dest)
        # Flush now: with warm_write on ingress she warms blocks as they reach
        # the disk, and the filesystem would otherwise hold them 5-30 s first.
        subprocess.run(["sync", "-f", dest])
    finally:
        subprocess.run(["rm", "-rf", tmp])
    ms = (now_ns() - t0) / 1e6
    if os.path.isdir(dest):
        kind, (files, size), digest = "dir", dir_stats(dest), None
    else:
        kind, files, size, digest = "file", 1, os.path.getsize(dest), sha3_file(dest)
    with db() as con:
        con.execute("""INSERT INTO items(name,kind,side,path,sha3,bytes,files,pulled_at,pull_ms)
                       VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET kind=excluded.kind,
                       side='ingress', path=excluded.path, sha3=excluded.sha3, bytes=excluded.bytes,
                       files=excluded.files, pulled_at=excluded.pulled_at, pull_ms=excluded.pull_ms""",
                    (name, kind, "ingress", dest, digest, size, files, time.time(), ms))
    return {"ok": True, "name": name, "kind": kind, "files": files, "bytes": size, "ms": round(ms, 3),
            "verified": "every file against its D1 SHA3-512 (intake)"}


def tool_prefetch(args):
    """Pull several items ahead of need, in the background. Returns a job id."""
    names = [safe_name(n) for n in (args.get("names") or [])]
    if not names:
        raise ValueError("names: a non-empty list")
    jid = uuid.uuid4().hex[:10]
    _jobs[jid] = {"names": names, "done": 0, "results": {}, "started": time.time()}

    def one(n):
        try:
            r = tool_pull({"name": n})
        except Exception as e:                      # noqa: BLE001 — reported, not raised
            r = {"ok": False, "name": n, "error": str(e)}
        _jobs[jid]["results"][n] = r
        _jobs[jid]["done"] += 1
    for n in names:
        _pool.submit(one, n)
    return {"job": jid, "queued": names}


def tool_jobs(args):
    jid = args.get("job")
    if jid:
        return _jobs.get(jid) or {"error": "no such job"}
    return {k: {"names": v["names"], "done": v["done"]} for k, v in _jobs.items()}


def tool_warm(args):
    """What she already holds, from the shared index. With a name: is it warm."""
    with db() as con:
        con.row_factory = sqlite3.Row
        if args.get("name"):
            n = safe_name(args["name"])
            r = con.execute("SELECT * FROM items WHERE name=?", (n,)).fetchone()
            if r and r["side"] == "ingress" and os.path.exists(r["path"]):
                con.execute("UPDATE items SET used_at=?, uses=uses+1 WHERE name=?", (time.time(), n))
                return {"warm": True, **dict(r)}
            return {"warm": False, "name": n}
        return {"items": [dict(r) for r in con.execute(
            "SELECT name,kind,side,bytes,files,uses,pulled_at,staged_at,pushed_at FROM items ORDER BY pulled_at DESC")]}


def tool_verify(args):
    """Re-check a pulled FILE on disk against its D1 SHA3-512 right now."""
    name = safe_name(args.get("name"))
    path = os.path.join(WORKDIR, "ops", name)
    if not os.path.isfile(path):
        return {"ok": False, "name": name, "error": "not a pulled file (directories are verified file by file on pull)"}
    want = (worker_meta(name) or {}).get("hash_sha3") or ""
    got = sha3_file(path)
    return {"ok": bool(want) and got == want, "name": name, "local": got[:16], "d1": want[:16]}


def tool_stage(args):
    """Put something on egress to go out: text content, or a pulled item copied
    from ingress. Nothing leaves the box until push is confirmed."""
    name = safe_name(args.get("name"))
    os.makedirs(EGRESS, exist_ok=True)
    dest = os.path.join(EGRESS, name)
    if "text" in args:
        data = str(args["text"]).encode("utf-8")
        with open(dest, "wb") as f:
            f.write(data)
    elif args.get("from_pulled"):
        src = os.path.join(WORKDIR, "ops", safe_name(args["from_pulled"]))
        if not os.path.isfile(src):
            raise ValueError("from_pulled must name a pulled file")
        subprocess.run(["cp", src, dest], check=True)
    else:
        raise ValueError("give text or from_pulled")
    size = os.path.getsize(dest)
    with db() as con:
        con.execute("""INSERT INTO items(name,kind,side,path,sha3,bytes,files,staged_at) VALUES(?,?,?,?,?,?,1,?)
                       ON CONFLICT(name) DO UPDATE SET side='egress', path=excluded.path, sha3=excluded.sha3,
                       bytes=excluded.bytes, staged_at=excluded.staged_at""",
                    (name, "file", "egress", dest, sha3_file(dest), size, time.time()))
    return {"ok": True, "name": name, "bytes": size, "staged": dest}


def tool_push(args):
    """Egress -> Phoenix: R2 bytes + D1 custody, then read D1 back to prove the receipt."""
    name = safe_name(args.get("name"))
    path = os.path.join(EGRESS, name)
    if not os.path.isfile(path):
        return {"ok": False, "name": name, "error": "nothing staged under that name"}
    local = sha3_file(path)
    t0 = now_ns()
    rc, log = run_intake([path, "hlk", "H.L.K push"], cwd=EGRESS)
    ms = (now_ns() - t0) / 1e6
    d1 = (worker_meta(name) or {}).get("hash_sha3") or ""
    ok = rc == 0 and d1 == local
    if ok:
        with db() as con:
            con.execute("UPDATE items SET pushed_at=? WHERE name=?", (time.time(), name))
    return {"ok": ok, "name": name, "ms": round(ms, 3), "d1_receipt": d1[:16] if d1 else None,
            "local": local[:16], **({} if ok else {"log": log[-600:]})}


TOOLS = {
    "status":   {"tier": "auto", "fn": tool_status,   "params": {},
                 "says": "both Helix instances' own counters (hit rate now and total) + what the index holds"},
    "warm":     {"tier": "auto", "fn": tool_warm,     "params": {"name": "optional item name"},
                 "says": "is an item already warm in ingress; without a name, everything the index holds"},
    "pull":     {"tier": "auto", "fn": tool_pull,     "params": {"name": "item name (a file or a directory)"},
                 "says": "bring an item from Phoenix in R2 into ingress, every byte checked against D1"},
    "prefetch": {"tier": "auto", "fn": tool_prefetch, "params": {"names": "list of item names"},
                 "says": "pull several items ahead of need, in the background; returns a job id"},
    "jobs":     {"tier": "auto", "fn": tool_jobs,     "params": {"job": "optional job id"},
                 "says": "progress of prefetch jobs"},
    "verify":   {"tier": "auto", "fn": tool_verify,   "params": {"name": "a pulled file"},
                 "says": "re-check a pulled file against its D1 SHA3-512 now"},
    "stage":    {"tier": "auto", "fn": tool_stage,    "params": {"name": "item name", "text": "content, or", "from_pulled": "a pulled file"},
                 "says": "put something on egress to go out (nothing leaves until push is confirmed)"},
    "push":     {"tier": "ask",  "fn": tool_push,     "params": {"name": "a staged item"},
                 "says": "send a staged item to Phoenix (R2 + D1 receipt) — asks first"},
}


def call(tool, args, caller, via):
    spec = TOOLS.get(tool)
    if not spec:
        return 404, {"error": f"no tool {tool!r}", "tools": sorted(TOOLS)}
    args = args if isinstance(args, dict) else {}
    if spec["tier"] == "ask":
        pid = uuid.uuid4().hex[:10]
        q = f"{tool} {json.dumps(args)} — {spec['says']}. Confirm?"
        _pending[pid] = {"tool": tool, "args": args, "question": q, "created": time.time(), "via": via}
        audit({"event": "asked", "id": pid, "tool": tool, "args": _short(args), "caller": caller, "via": via})
        return 202, {"pending": pid, "question": q}
    return _run(tool, args, caller, via)


def _run(tool, args, caller, via, confirmed=None):
    t0 = now_ns()
    try:
        result, code = TOOLS[tool]["fn"](args), 200
    except ValueError as e:
        result, code = {"ok": False, "error": str(e)}, 400
    except Exception as e:                           # noqa: BLE001 — surfaced to the caller + audit
        result, code = {"ok": False, "error": f"{type(e).__name__}: {e}"}, 500
    audit({"event": "ran", "tool": tool, "args": _short(args), "caller": caller, "via": via,
           "confirmed": confirmed, "code": code, "ms": round((now_ns() - t0) / 1e6, 3),
           "ok": result.get("ok", code == 200) if isinstance(result, dict) else code == 200})
    return code, result


def _short(args):
    return {k: (v[:120] + "…" if isinstance(v, str) and len(v) > 120 else v) for k, v in args.items()}


def confirm(pid, answer, caller):
    p = _pending.pop(pid, None)
    if not p:
        return 404, {"error": "no such pending action"}
    if answer != "yes":
        audit({"event": "declined", "id": pid, "tool": p["tool"], "caller": caller})
        return 200, {"ok": True, "done": False, "said": "no — nothing was done"}
    return _run(p["tool"], p["args"], caller, p["via"], confirmed=pid)


# ── optional model tier (drives the same tools) ───────────────────────────
MODEL_RULES = ("You are H.L.K, directing a Phoenix worker box. Ingress Helix holds what came in from Phoenix; "
               "egress Helix holds what goes out. Answer with the JSON object only: say = a short plain answer for "
               "the human, tool = the ONE tool to run (or \"none\"), args = that tool's arguments. Use a tool whenever "
               "the request is about the box, its Helix, or items (files and folders like kernels, helix, frank, "
               "security). push asks the human first — tell them. Never claim a tool ran unless a [tool result] says so.\n"
               "Examples:\n"
               "\"how are the helixes doing\" -> {\"say\":\"Checking both.\",\"tool\":\"status\",\"args\":{}}\n"
               "\"is kernels warm\" -> {\"say\":\"Checking.\",\"tool\":\"warm\",\"args\":{\"name\":\"kernels\"}}\n"
               "\"bring in frank\" -> {\"say\":\"Pulling frank.\",\"tool\":\"pull\",\"args\":{\"name\":\"frank\"}}\n"
               "\"get a, b and c ready ahead of time\" -> {\"say\":\"Prefetching.\",\"tool\":\"prefetch\",\"args\":{\"names\":[\"a\",\"b\",\"c\"]}}\n"
               "\"send out.txt to Phoenix\" -> {\"say\":\"That needs your yes.\",\"tool\":\"push\",\"args\":{\"name\":\"out.txt\"}}\n"
               "\"what is a cache\" -> {\"say\":\"A fast copy kept close.\",\"tool\":\"none\",\"args\":{}}\n"
               "Tools:\n")


def reply_shape():
    """The only shape a local model may answer in. Constrained decoding (Ollama
    `format`) keeps a small model on the tool list instead of wandering into
    prose — measured on pbm-compaq 2026-09-29: free-form ACTION lines got 1-3/6
    right with 1-3B models."""
    return {"type": "object",
            "properties": {"say": {"type": "string"},
                           "tool": {"type": "string", "enum": sorted(TOOLS) + ["none"]},
                           "args": {"type": "object"}},
            "required": ["say", "tool", "args"]}


def system_prompt():
    return MODEL_RULES + "\n".join(f"- {n}: {s['says']} (args: {json.dumps(s['params'])})" for n, s in TOOLS.items())


def model_decide(history):
    """-> {"say": str, "tool": name or None, "args": dict}, whichever tier answers.
    Local (Ollama) is the tier that travels with the system; the API tier is
    optional and off unless someone chooses to fund it (Jerry, 2026-09-29)."""
    tier = os.environ.get("HLK_MODEL", "none")
    if tier == "ollama":
        body = {"model": os.environ.get("HLK_OLLAMA_MODEL", "qwen2.5:3b"), "stream": False, "format": reply_shape(),
                "messages": [{"role": "system", "content": system_prompt()}] + history,
                "options": {"temperature": 0}}
        req = urllib.request.Request(os.environ.get("HLK_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/") + "/api/chat",
                                     data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            content = json.loads(r.read())["message"]["content"]
        try:
            d = json.loads(content)
        except json.JSONDecodeError:
            return {"say": content, "tool": None, "args": {}}
        tool = d.get("tool")
        return {"say": str(d.get("say", "")), "tool": None if tool in (None, "none") else str(tool),
                "args": d.get("args") if isinstance(d.get("args"), dict) else {}}
    if tier == "api":
        key = open(os.environ["HLK_ANTHROPIC_KEY_FILE"], encoding="utf-8").read().strip()
        body = {"model": os.environ.get("HLK_API_MODEL", "claude-sonnet-5-5"), "max_tokens": 1024,
                "system": system_prompt() + "\nReply with the JSON object only.", "messages": history}
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", "x-api-key": key,
                                              "anthropic-version": "2023-06-01"})
        with urllib.request.urlopen(req, timeout=180) as r:
            text = "".join(b.get("text", "") for b in json.loads(r.read())["content"])
        m = re.search(r"\{.*\}", text, re.S)
        try:
            d = json.loads(m.group(0)) if m else {}
        except json.JSONDecodeError:
            d = {}
        if not d:
            return {"say": text, "tool": None, "args": {}}
        tool = d.get("tool")
        return {"say": str(d.get("say", "")), "tool": None if tool in (None, "none") else str(tool),
                "args": d.get("args") if isinstance(d.get("args"), dict) else {}}
    raise RuntimeError("no model tier configured (HLK_MODEL=ollama|api) — every tool still works on POST /call")


def chat(message, caller):
    history = [{"role": "user", "content": str(message)}]
    steps = []
    for _ in range(4):
        d = model_decide(history)
        if not d["tool"]:
            return {"reply": d["say"], "steps": steps}
        code, res = call(d["tool"], d["args"], caller, "chat")
        steps.append({"tool": d["tool"], "code": code})
        if code == 202:
            return {"reply": res["question"], "pending": res["pending"], "steps": steps}
        history += [{"role": "assistant", "content": json.dumps(d)},
                    {"role": "user", "content": f"[tool result] {json.dumps(res)[:4000]} — now answer the human "
                                                 f"(tool \"none\") unless another tool is really needed."}]
    return {"reply": "Stopped after four steps without a final answer.", "steps": steps}


# ── HTTP ─────────────────────────────────────────────────────────────────
PAGE = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>H.L.K confirmations</title><style>body{font:15px system-ui;margin:16px;max-width:760px}
.p{border:1px solid #8884;border-radius:8px;padding:12px;margin:10px 0}button{font:inherit;padding:6px 14px;margin-right:8px}
code{font-size:13px}</style></head><body><h1>H.L.K — waiting for your yes</h1><div id="list">…</div>
<script>
const tok = () => localStorage.getItem('hlk') || (localStorage.setItem('hlk', prompt('H.L.K token') || ''), localStorage.getItem('hlk'));
const api = (p, o={}) => fetch(p, {...o, headers:{'Authorization':'Bearer '+tok(),'Content-Type':'application/json'}}).then(r=>r.json());
async function load(){ const d = await api('/pending'); const el = document.getElementById('list');
  const ids = Object.keys(d); if(!ids.length){ el.textContent='Nothing waiting.'; return; } el.innerHTML='';
  for(const id of ids){ const p=d[id]; const b=document.createElement('div'); b.className='p';
    b.innerHTML='<p><code></code></p><button>Yes</button><button>No</button>'; b.querySelector('code').textContent=p.question;
    const [y,n]=b.querySelectorAll('button');
    y.onclick=async()=>{ b.textContent=JSON.stringify(await api('/confirm',{method:'POST',body:JSON.stringify({id,answer:'yes'})})); };
    n.onclick=async()=>{ await api('/confirm',{method:'POST',body:JSON.stringify({id,answer:'no'})}); load(); };
    el.appendChild(b);} }
load(); setInterval(load, 5000);
</script></body></html>"""


def load_token():
    p = os.path.join(STATE, "token")
    if not os.path.exists(p):
        with open(p, "w", encoding="utf-8") as f:
            f.write(secrets.token_hex(32))
        os.chmod(p, 0o600)
    with open(p, encoding="utf-8") as f:
        return f.read().strip()


def make_handler(token, allow_from):
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, obj, ctype="application/json"):
            body = obj.encode() if isinstance(obj, str) else json.dumps(obj, indent=1, default=str).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _ok_caller(self):
            ip = self.client_address[0]
            if ip != "127.0.0.1" and ip not in allow_from:
                self._send(403, {"error": "not an allowed caller"})
                return None
            got = self.headers.get("Authorization", "")
            if not secrets.compare_digest(got.encode(), f"Bearer {token}".encode()):
                self._send(401, {"error": "token required"})
                return None
            return ip

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > 1 << 20:
                raise ValueError("body too large")
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/health":
                return self._send(200, {"ok": True, "hlk": VERSION})
            if path == "/":
                ip = self.client_address[0]
                if ip != "127.0.0.1" and ip not in allow_from:
                    return self._send(403, {"error": "not an allowed caller"})
                return self._send(200, PAGE, "text/html; charset=utf-8")
            ip = self._ok_caller()
            if not ip:
                return
            if path == "/tools":
                return self._send(200, {n: {k: v for k, v in s.items() if k != "fn"} for n, s in TOOLS.items()})
            if path == "/pending":
                return self._send(200, _pending)
            if path == "/audit":
                with open(os.path.join(STATE, "audit.jsonl"), encoding="utf-8") as f:
                    return self._send(200, [json.loads(x) for x in f.readlines()[-50:]])
            return self._send(404, {"error": "no such path"})

        def do_POST(self):
            ip = self._ok_caller()
            if not ip:
                return
            try:
                b = self._body()
            except (ValueError, json.JSONDecodeError) as e:
                return self._send(400, {"error": str(e)})
            path = self.path.split("?", 1)[0]
            if path == "/call":
                return self._send(*call(str(b.get("tool")), b.get("args") or {}, ip, "http"))
            if path == "/confirm":
                return self._send(*confirm(str(b.get("id")), str(b.get("answer", "")).lower(), ip))
            if path == "/chat":
                try:
                    return self._send(200, chat(b.get("message", ""), ip))
                except (RuntimeError, OSError, urllib.error.URLError, KeyError) as e:
                    return self._send(503, {"error": str(e)})
            return self._send(404, {"error": "no such path"})
    return H


def mesh_ip():
    try:
        with open("/etc/phoenix-mesh/wg-phx.conf", encoding="utf-8") as f:
            for line in f:
                k, _, v = line.partition("=")
                if k.strip() == "Address" and v.strip().startswith("10.47.0."):
                    return v.strip().split("/")[0]
    except OSError:
        pass
    return None


def main():
    ap = argparse.ArgumentParser(prog="hlk")
    ap.add_argument("--port", type=int, default=8472)
    ap.add_argument("--mesh", action="store_true", help="also listen on this box's mesh address")
    ap.add_argument("--allow-from", default="", help="comma list of mesh IPs allowed to call")
    ap.add_argument("--bind", default="", help="this box's mesh address, when the WireGuard config isn't readable by this user")
    a = ap.parse_args()
    allow = tuple(x.strip() for x in a.allow_from.split(",") if x.strip())
    if (a.mesh or a.bind) and not allow:
        raise SystemExit("--mesh needs --allow-from (never open H.L.K to the whole mesh)")
    os.makedirs(STATE, mode=0o700, exist_ok=True)
    token = load_token()
    db().close()
    handler = make_handler(token, allow)
    addrs = ["127.0.0.1"]
    if a.bind:
        addrs.append(a.bind)
    elif a.mesh:
        while not mesh_ip():                         # the mesh can come up after us
            time.sleep(10)
        addrs.append(mesh_ip())
    for addr in addrs[:-1]:
        srv = http.server.ThreadingHTTPServer((addr, a.port), handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        print(f"hlk {VERSION}: http://{addr}:{a.port}", flush=True)
    print(f"hlk {VERSION}: http://{addrs[-1]}:{a.port}" + (f" (callers: {', '.join(allow)})" if allow else ""), flush=True)
    http.server.ThreadingHTTPServer((addrs[-1], a.port), handler).serve_forever()


if __name__ == "__main__":
    main()
