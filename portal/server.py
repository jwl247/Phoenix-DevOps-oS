#!/usr/bin/env python3
"""Phoenix Portal (v0): the one dashboard, served ON Phoenix Net.

UnitedSys — United Systems | jwl247 | GPL-3.0

Jerry, 2026-09-26: "everyone dont need a dash board we will have this here".
One web page on the net, opened from any Phoenix machine at
http://precision.phx:8470 . v0 is read-only: who's online, every link's
health, and whether each Phoenix service is up. Buttons come later, through
H.L.K's hands (docs/plans/phoenix-portal-plan.md).

Security:
  - Listens on 127.0.0.1 and the mesh address only (10.47.0.x), never on the
    LAN or the internet. The Windows firewall rule allows the mesh range only.
  - The switchboard admin key (MESH_ADMIN) is read from the vault here and
    never sent to the browser; the page only gets the finished summary.
  - Host header allow-list (stops DNS-rebinding tricks from other sites).
  - Stdlib only. Idle until someone opens the page; answers are cached.

  python portal/server.py [--port 8470]
"""
import argparse
import datetime as dt
import http.server
import json
import os
import platform
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.environ.get("PHOENIX_CONSOLE_WEB") or os.path.join(HERE, "web")   # a test copy can serve web-next/
VAULT = os.environ.get("PHOENIX_SECRETS", r"F:\Phoenix\Vault\secrets\phoenix-secrets.env")
MESH_PREFIX = "10.47.0."
ONLINE_S = 90            # a machine that checked in within 90 s is online (agents beat every 30 s)
STATE_TTL = 10           # seconds a built summary is reused
SERVICE_TTL = 30
WINDOW_H = 1             # link history window on the page

# Plain names for people, not worker names (the worker is in `detail`).
SERVICES = [
    ("Network switchboard", "phoenix-mesh-worker", "https://phoenix-mesh-worker.phoenix-jwl.workers.dev/health"),
    ("Package handler", "packages-worker", "https://packages-worker.phoenix-jwl.workers.dev/health"),
    ("Office documents", "phoenix-office-worker", "https://phoenix-office-worker.phoenix-jwl.workers.dev/health"),
    ("Office tamper alerts", "office-notify-worker", "https://office-notify-worker.phoenix-jwl.workers.dev/health"),
    ("PBM website leads", "pbm-leads-worker", "https://pbm-leads-worker.phoenix-jwl.workers.dev/health"),
    ("Life First assistant", "lifefirst-mcp", "https://lifefirst-mcp.phoenix-jwl.workers.dev/"),
    ("Laurie's page", "lifefirst.authenticcoder.com", "https://lifefirst.authenticcoder.com/laurie/"),
]


# ── pure pieces (tested in test_server.py) ─────────────────────────────────
def parse_at(s):
    """SQLite's 'YYYY-MM-DD HH:MM:SS' (UTC) -> aware datetime; None stays None."""
    if not s:
        return None
    return dt.datetime.strptime(s[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc)


def summarize(devices, rows, now):
    """Switchboard devices + link-health rows -> what the page draws."""
    machines = []
    for d in devices:
        if d.get("revoked_at"):
            continue
        seen = parse_at(d.get("last_seen"))
        age = (now - seen).total_seconds() if seen else None
        machines.append({
            "name": d["name"], "host": f"{d['name']}.phx", "mesh_ip": d["mesh_ip"],
            "hub": bool(d.get("hub")), "kind": d.get("kind", "agent"),
            "online": age is not None and age <= ONLINE_S, "seen_s": None if age is None else int(age),
            "lan": [e["addr"] for e in d.get("endpoints", []) if e.get("family") == 4],
        })
    names = {m["name"] for m in machines}

    pairs = {}
    for r in sorted(rows, key=lambda r: r["at"]):        # oldest first
        if r["from_device"] in names and r["to_device"] in names:
            pairs.setdefault((r["from_device"], r["to_device"]), []).append(r)

    links = []
    for (a, b), rs in sorted(pairs.items()):
        n = len(rs)
        share = {p: round(100 * sum(r["path"] == p for r in rs) / n) for p in ("direct", "fallback", "down")}
        rtts = [r["rtt_ms"] for r in rs if r["rtt_ms"] is not None]
        last = rs[-1]
        last_at = parse_at(last["at"])
        links.append({
            "from": a, "to": b, "reports": n,
            "path": last["path"], "relay": (last.get("endpoint") or "").startswith("relay"),
            "rtt_ms": last["rtt_ms"], "share": share,
            "flips": sum(1 for x, y in zip(rs, rs[1:]) if x["path"] != y["path"]),
            "rtt_avg": round(sum(rtts) / len(rtts), 2) if rtts else None,
            "rtt_max": max(rtts) if rtts else None,
            "series": [r["rtt_ms"] for r in rs[-60:]],
            "stale": last_at is None or (now - last_at).total_seconds() > 3 * ONLINE_S,
        })
    return {"machines": machines, "links": links}


# ── switchboard + services ─────────────────────────────────────────────────
def read_vault():
    v = {}
    with open(VAULT, encoding="utf-8") as f:
        for line in f:
            if "=" in line and not line.lstrip().startswith("#"):
                k, _, val = line.partition("=")
                v[k.strip()] = val.strip().strip('"')
    return v


def switchboard(path):
    v = read_vault()
    req = urllib.request.Request(v["MESH_WORKER_URL"].rstrip("/") + path,
                                 headers={"Authorization": f"Bearer {v['MESH_ADMIN']}", "User-Agent": "phoenix-portal/0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def check_url(url):
    t0 = time.monotonic()
    try:
        with _opener.open(urllib.request.Request(url, headers={"User-Agent": "phoenix-portal/0"}), timeout=8) as r:
            code = r.status
    except urllib.error.HTTPError as e:
        code = e.code
    except Exception as e:                       # DNS, refused, timeout
        return {"up": False, "note": type(e).__name__, "ms": None}
    ms = round((time.monotonic() - t0) * 1000)
    if code in (301, 302, 303, 307, 308):
        return {"up": True, "note": "locked behind sign-in", "ms": ms}
    if code < 500:
        return {"up": True, "note": f"answered {code}", "ms": ms}
    return {"up": False, "note": f"error {code}", "ms": ms}


def local_checks():
    """Things only the hub itself can see. Windows today (the hub is the Precision)."""
    out = []
    if platform.system() != "Windows":
        return out
    try:
        r = subprocess.run(["sc", "query", "Cloudflared"], capture_output=True, text=True, timeout=5)
        up = "RUNNING" in r.stdout
        out.append({"name": "Cloudflare tunnel", "detail": "Cloudflared service on this PC", "up": up,
                    "note": "running" if up else "stopped", "ms": None})
    except Exception as e:
        out.append({"name": "Cloudflare tunnel", "detail": "Cloudflared service on this PC", "up": False, "note": type(e).__name__, "ms": None})
    return out


_cache = {"state": None, "state_t": 0, "svc": None, "svc_t": 0}
_lock = threading.Lock()


def services():
    if _cache["svc"] is None or time.time() - _cache["svc_t"] > SERVICE_TTL:
        with ThreadPoolExecutor(8) as ex:
            res = list(ex.map(lambda s: {"name": s[0], "detail": s[1], **check_url(s[2])}, SERVICES))
        _cache["svc"], _cache["svc_t"] = res + local_checks(), time.time()
    return _cache["svc"]


def build_state():
    with _lock:
        if _cache["state"] and time.time() - _cache["state_t"] < STATE_TTL:
            return _cache["state"]
        now = dt.datetime.now(dt.timezone.utc)
        since = (now - dt.timedelta(hours=WINDOW_H)).strftime("%Y-%m-%d %H:%M:%S")
        state = {"generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "window_h": WINDOW_H}
        try:
            devices = switchboard("/devices")["devices"]
            rows = switchboard(f"/links?since={urllib.parse.quote(since)}&limit=5000")["links"]
            state.update(summarize(devices, rows, now))
            state["switchboard"] = "ok"
        except Exception as e:                   # the page still loads and says what's wrong
            state.update({"machines": [], "links": [], "switchboard": f"unreachable ({type(e).__name__})"})
        # The mesh agent runs as SYSTEM, so a normal user can't ask Windows about
        # its task (that read as "not running", found live 2026-09-26). The honest
        # test is the switchboard itself: is this PC checking in?
        me = local_name()
        mine = next((m for m in state.get("machines", []) if m["name"] == me), None)
        agent = {"name": "Mesh agent on this PC", "detail": "checking in with the switchboard", "ms": None,
                 "up": bool(mine and mine["online"]),
                 "note": (f"last check-in {mine['seen_s']} s ago" if mine and mine["seen_s"] is not None
                          else "not checking in")}
        state["services"] = services() + [agent]
        _cache["state"], _cache["state_t"] = state, time.time()
        return state


# ── H.L.K's hands (hands/hands.py) ─────────────────────────────────────────
# v0: this PC's hands only, on 127.0.0.1. Remote machines' hands come on day 8.
HANDS_URL = os.environ.get("PHOENIX_HANDS_URL", "http://127.0.0.1:8471")
HANDS_TOKEN_FILE = os.path.join(os.path.expanduser("~"), ".phoenix", "hands.token")
MACHINE_RE = __import__("re").compile(r"^[a-z][a-z0-9-]{1,30}$")


def _name_from_hosts():
    """This PC's Phoenix name, readable without admin: the mesh agent writes
    '10.47.0.x<TAB>name.phx' for every member into the hosts file (a public
    file, no secrets), and this PC's own mesh address picks our line."""
    try:
        mine = {i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
    except OSError:
        return None
    hosts = (os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "drivers", "etc", "hosts")
             if platform.system() == "Windows" else "/etc/hosts")
    try:
        with open(hosts, encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2 and parts[0] in mine and parts[0].startswith("10.47.0.") and parts[1].endswith(".phx"):
                    return parts[1][:-4]
    except OSError:
        pass
    return None


def local_name():
    """This machine's Phoenix name (from the mesh agent's device file)."""
    conf = (os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "PhoenixMesh", "device.json")
            if platform.system() == "Windows" else "/etc/phoenix-mesh/device.json")
    try:
        with open(conf, encoding="utf-8") as f:
            return json.load(f).get("name")
    except (OSError, ValueError):          # admin-only folder (it holds the mesh key): use the hosts file
        return _name_from_hosts()


HANDS_TOKENS_FILE = os.path.join(os.path.expanduser("~"), ".phoenix", "hands-tokens.json")   # the boxes' tokens (install_remote.py)
HANDS_PORT = 8471


def hands_targets():
    """{machine: (url, token)} for every machine whose hands the Console can reach:
    this PC on 127.0.0.1, the boxes on their mesh address."""
    out = {}
    me = local_name()
    try:
        out[me] = (HANDS_URL, open(HANDS_TOKEN_FILE, encoding="utf-8").read().strip())
    except OSError:
        pass
    try:
        with open(HANDS_TOKENS_FILE, encoding="utf-8") as f:
            remote = json.load(f)
    except (OSError, ValueError):
        remote = {}
    if remote:
        ips = {m["name"]: m["mesh_ip"] for m in (build_state().get("machines") or [])}
        for name, tok in remote.items():
            if MACHINE_RE.match(name) and name in ips and name != me:
                out[name] = (f"http://{ips[name]}:{HANDS_PORT}", tok)
    return {k: v for k, v in out.items() if k}


def hands_call(machine, method, path, body=None, caller=""):
    """-> (status, bytes, content-type). Never raises."""
    target = hands_targets().get(machine)
    if not target:
        return 404, json.dumps({"ok": False, "error": f"no hands on {machine}"}).encode(), "application/json"
    url, tok = target
    req = urllib.request.Request(url + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json",
                                          "X-Caller": caller[:80]})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, r.read(), r.headers.get("Content-Type", "application/json")
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers.get("Content-Type", "application/json")
    except Exception as e:
        return 503, json.dumps({"ok": False, "error": f"hands unreachable ({type(e).__name__})"}).encode(), "application/json"



# ── Clone pool relay: the family imports from the pool THROUGH the hub ──────
# Build once, every machine imports (Jerry, 2026-09-26: "i thought we were
# going to have a helper import them so you only had to build 1"). Only the
# hub holds the pool keys (PHOENIX_AUTH + the Access service token); the boxes
# never get them. The hub fetches the file from the clone pool, checks it
# against its custody fingerprint (SHA3-512 in D1), and only then hands it on,
# with that fingerprint, to a box that shows its own hands token. The box
# checks the fingerprint again before it swaps anything in.
import hashlib  # noqa: E402

POOL_WORKER = os.environ.get("PHOENIX_WORKER_URL", "https://packages-worker.phoenix-jwl.workers.dev")
POOL_SERVES = {"hands.py"}                 # what the family may import; grow on purpose, never by pattern
POOL_TTL = 300                             # the pool is asked at most every 5 minutes per file
_pool_cache = {}


def _pool_get(path):
    v = read_vault()
    req = urllib.request.Request(POOL_WORKER + path, headers={
        "Authorization": f"Bearer {v['PHOENIX_AUTH']}", "User-Agent": "phoenix-console/0",
        "CF-Access-Client-Id": v.get("CF_ACCESS_CLIENT_ID", ""),
        "CF-Access-Client-Secret": v.get("CF_ACCESS_CLIENT_SECRET", "")})
    with _opener.open(req, timeout=30) as r:            # no redirects: an Access login page is a failure
        if r.status != 200:
            raise RuntimeError(f"pool answered {r.status}")
        return r.read()


def pool_fetch(name):
    """-> (bytes, sha3_hex). Raises if the pool copy doesn't match its custody record."""
    hit = _pool_cache.get(name)
    if hit and time.time() - hit[2] < POOL_TTL:
        return hit[0], hit[1]
    hex_id = name.encode().hex()
    meta = json.loads(_pool_get(f"/clonepool/{hex_id}?meta=true"))
    row = meta.get("result") or meta.get("item") or meta
    want = (row.get("hash_sha3") or "").lower()
    if not want:
        raise RuntimeError(f"{name} has no custody fingerprint in the pool")
    data = _pool_get(f"/clonepool/{hex_id}")
    got = hashlib.sha3_512(data).hexdigest()
    if got != want:
        raise RuntimeError(f"{name}: pool bytes don't match custody ({got[:12]} vs {want[:12]})")
    _pool_cache[name] = (data, got, time.time())
    return data, got


def box_token_ok(header):
    got = (header or "").replace("Bearer ", "", 1).strip()
    if len(got) != 64:
        return False
    try:
        with open(HANDS_TOKENS_FILE, encoding="utf-8") as f:
            toks = json.load(f).values()
    except (OSError, ValueError):
        return False
    import secrets as _s
    return any(_s.compare_digest(got, t) for t in toks)


# ── HTTP ───────────────────────────────────────────────────────────────────
ALLOWED_HOSTS = {"precision.phx", "portal.phx", "localhost", "127.0.0.1"}


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "PhoenixPortal/0"

    def log_message(self, *a):                   # quiet: no per-request console spam
        pass

    def _host_ok(self):
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        return host in ALLOWED_HOSTS or host.startswith(MESH_PREFIX)

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self._host_ok():
            return self._send(421, b"wrong host", "text/plain")
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/pool/"):
            name = path[len("/pool/"):]
            if name not in POOL_SERVES:
                return self._send(404, b"not served", "text/plain")
            if not box_token_ok(self.headers.get("Authorization")):
                return self._send(401, b"unauthorized", "text/plain")
            try:
                data, sha3 = pool_fetch(name)
            except Exception as e:
                return self._send(502, f"pool: {e}".encode()[:300], "text/plain")
            if (self.headers.get("X-Have-SHA3") or "").lower() == sha3:     # nothing new: no file sent
                self.send_response(304)
                self.send_header("X-Phoenix-SHA3", sha3)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Phoenix-SHA3", sha3)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/api/state":
            return self._send(200, json.dumps(build_state()).encode(), "application/json")
        if path == "/api/hands":
            me = local_name()
            machines = {}
            for name in sorted(hands_targets(), key=lambda n: (n != me, n)):     # this PC first
                st, body, _ = hands_call(name, "GET", "/tools")
                try:
                    info = json.loads(body)
                except ValueError:
                    info = {}
                machines[name] = info if st == 200 else {"ok": False, "error": info.get("error", f"HTTP {st}")}
            return self._send(200, json.dumps({"machines": machines, "here": me}).encode(), "application/json")
        m = self._hands_path(path)
        if m and m[1] in ("log", "shot"):
            st, body, ctype = hands_call(m[0], "GET", "/log" if m[1] == "log" else "/shot/latest")
            return self._send(st, body, ctype if st == 200 else "application/json")
        files = {"/": ("index.html", "text/html; charset=utf-8"),
                 "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                 "/style.css": ("style.css", "text/css; charset=utf-8")}
        if path in files:
            name, ctype = files[path]
            with open(os.path.join(WEB, name), "rb") as f:
                return self._send(200, f.read(), ctype)
        return self._send(404, b"not found", "text/plain")

    def _hands_path(self, path):
        """/api/hands/<machine>/<what> for a machine whose hands we know -> (machine, what) or None."""
        parts = path.strip("/").split("/")
        if len(parts) == 4 and parts[:2] == ["api", "hands"] and MACHINE_RE.match(parts[2]) and parts[2] in hands_targets():
            return parts[2], parts[3]
        return None

    def do_POST(self):
        if not self._host_ok():
            return self._send(421, b"wrong host", "text/plain")
        # A plain form on another site can't set this header or send JSON
        # without a CORS preflight we never answer: blocks cross-site clicks.
        if self.headers.get("X-Phoenix-Console") != "1" or                 not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return self._send(403, b'{"ok":false,"error":"console requests only"}', "application/json")
        m = self._hands_path(urllib.parse.urlparse(self.path).path)
        if not m or m[1] != "run":
            return self._send(404, b'{"ok":false,"error":"not found"}', "application/json")
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(min(n, 65536)) or b"{}")
        except ValueError:
            return self._send(400, b'{"ok":false,"error":"body must be JSON"}', "application/json")
        fwd = {"tool": str(body.get("tool", "")), "args": body.get("args") or {}, "confirm": body.get("confirm") is True}
        via = " (H.L.K)" if self.headers.get("X-Phoenix-Via") == "hlk" else ""
        st, out, _ = hands_call(m[0], "POST", "/run", fwd, caller=f"console from {self.client_address[0]}{via}")
        return self._send(st, out, "application/json")


def mesh_address():
    """This machine's 10.47.0.x, once the mesh interface is up."""
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            if info[4][0].startswith(MESH_PREFIX):
                return info[4][0]
    except OSError:
        pass
    try:                                         # the WireGuard config meshd writes: "Address = 10.47.0.x/24"
        conf = (os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "PhoenixMesh", "wg-phx.conf")
                if platform.system() == "Windows" else "/etc/phoenix-mesh/wg-phx.conf")
        with open(conf, encoding="utf-8") as f:
            for line in f:
                k, _, v = line.partition("=")
                if k.strip() == "Address" and v.strip().startswith(MESH_PREFIX):
                    return v.strip().split("/")[0]
    except OSError:
        pass
    return None


def serve(addr, port):
    httpd = http.server.ThreadingHTTPServer((addr, port), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    print(f"portal: http://{addr}:{port}", flush=True)


def main():
    ap = argparse.ArgumentParser(prog="phoenix-portal")
    ap.add_argument("--port", type=int, default=8470)
    ap.add_argument("--local-only", action="store_true", help="127.0.0.1 only (a test copy)")
    a = ap.parse_args()
    serve("127.0.0.1", a.port)
    if a.local_only:
        while True:
            time.sleep(3600)
    bound = None
    while True:                                  # the mesh can come up after us (boot order)
        ip = mesh_address()
        if ip and ip != bound:
            try:
                serve(ip, a.port)
                bound = ip
            except OSError as e:
                print(f"portal: can't listen on {ip} yet ({e})", flush=True)
        time.sleep(30)


if __name__ == "__main__":
    main()
