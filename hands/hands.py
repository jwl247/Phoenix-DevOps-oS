#!/usr/bin/env python3
"""H.L.K's hands: the small helper on each PC that does the jobs a web page
can't. The Phoenix Console (click) and H.L.K (voice) both drive these same
hands, through the same fixed list of tools.

UnitedSys — United Systems | jwl247 | GPL-3.0

Permission tiers (CLAUDE.md, "THE INTERACTION MODEL"):
  base   runs without asking (read, open a local app, take a screenshot)
  ask    the caller must confirm first (anything with consequences)
  never  not a tool at all: nothing here touches breach_coms drives, the
         master vault, drive state, modprobe.d or udev rules (AI SAFETY RULES)

Every call is written to ~/.unitedsys/logs/hands.jsonl, so "what did you just
do" always has a real answer (GET /log).

v0 (2026-09-26): Windows, this PC only. Listens on 127.0.0.1 only; callers
need the token in ~/.phoenix/hands.token (made on first run, owner-only).
Standard library only.

  python hands/hands.py [--port 8471]
"""
import argparse
import ctypes
import datetime as dt
import http.server
import json
import os
import platform
import re
import secrets
import shutil
import socket
import string
import subprocess
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
IS_WIN = platform.system() == "Windows"
TOKEN_FILE = os.path.join(os.path.expanduser("~"), ".phoenix", "hands.token")
LOG_FILE = os.environ.get("PHOENIX_HANDS_LOG",
                          os.path.join(os.path.expanduser("~"), ".unitedsys", "logs", "hands.jsonl"))
SHOT_DIR = os.path.join(os.path.expanduser("~"), "Pictures", "Phoenix")
_log_lock = threading.Lock()
SELF = os.path.abspath(__file__)


def _sha3_file(path):
    import hashlib
    with open(path, "rb") as f:
        return hashlib.sha3_512(f.read()).hexdigest()


SELF_SHA3 = _sha3_file(SELF)          # the same fingerprint the clone pool keeps in custody


# ── tools ──────────────────────────────────────────────────────────────────
def _detached(args, cwd=None):
    """Start a program in this user's desktop session, not tied to us."""
    flags = 0x00000008 | 0x00000200 if IS_WIN else 0      # DETACHED_PROCESS | NEW_PROCESS_GROUP
    subprocess.Popen(args, cwd=cwd, creationflags=flags, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _hud_exe():
    for cfg in ("Release", "Debug"):
        p = os.path.join(REPO, "hud", "bin", cfg, "net9.0-windows", "Hud.exe")
        if os.path.exists(p):
            return p
    return None


APPS = {
    "office": "Phoenix Office",
    "hud": "the HUD (H.L.K)",
    "powershell": "PowerShell in the repo folder",
    "explorer": "File Explorer",
}


def tool_open_app(app, folder=None):
    if app not in APPS:
        raise ValueError(f"unknown app '{app}'; one of: {', '.join(APPS)}")
    if app == "office":
        exe = os.path.join(REPO, "phoenix-office", "node_modules", "electron", "dist", "electron.exe")
        if not os.path.exists(exe):
            raise FileNotFoundError("Phoenix Office isn't installed in the repo (npm install in phoenix-office)")
        _detached([exe, "."], cwd=os.path.join(REPO, "phoenix-office"))
    elif app == "hud":
        exe = _hud_exe()
        if not exe:
            raise FileNotFoundError("the HUD isn't built yet (dotnet build in hud/)")
        _detached([exe], cwd=os.path.dirname(exe))
    elif app == "powershell":
        wt = shutil.which("wt")
        _detached([wt, "-d", REPO, "pwsh"] if wt else [shutil.which("pwsh") or "powershell"], cwd=REPO)
    elif app == "explorer":
        target = folder or REPO
        if not os.path.isdir(target):
            raise FileNotFoundError(f"no such folder: {target}")
        _detached(["explorer.exe", os.path.normpath(target)])
    return {"opened": APPS[app]}


class _MemStatus(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def tool_status():
    out = {"host": socket.gethostname(), "os": f"{platform.system()} {platform.release()}",
           "hands_version": SELF_SHA3[:12]}
    if IS_WIN:
        m = _MemStatus(); m.dwLength = ctypes.sizeof(m)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        out["memory"] = {"total_gb": round(m.ullTotalPhys / 2**30, 1),
                         "free_gb": round(m.ullAvailPhys / 2**30, 1), "used_pct": m.dwMemoryLoad}
        out["uptime_h"] = round(ctypes.windll.kernel32.GetTickCount64() / 3_600_000, 1)
        drives = []
        for letter in string.ascii_uppercase:
            root = f"{letter}:\\"
            if ctypes.windll.kernel32.GetDriveTypeW(root) != 3:    # fixed disks only
                continue
            try:
                u = shutil.disk_usage(root)
            except OSError:
                continue
            label = ctypes.create_unicode_buffer(261)
            ctypes.windll.kernel32.GetVolumeInformationW(root, label, 261, None, None, None, None, 0)
            drives.append({"drive": f"{letter}:", "label": label.value,
                           "total_gb": round(u.total / 2**30), "free_gb": round(u.free / 2**30)})
        out["drives"] = drives
    return out


_SHOT_PS = r"""
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
$b = [System.Windows.Forms.SystemInformation]::VirtualScreen
$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($b.Left, $b.Top, 0, 0, $bmp.Size)
$bmp.Save($env:PHX_SHOT, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
"""


def tool_screenshot():
    os.makedirs(SHOT_DIR, exist_ok=True)
    path = os.path.join(SHOT_DIR, dt.datetime.now().strftime("shot-%Y%m%d-%H%M%S.png"))
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _SHOT_PS],
                       env={**os.environ, "PHX_SHOT": path}, capture_output=True, text=True, timeout=30)
    if r.returncode != 0 or not os.path.exists(path):
        raise RuntimeError((r.stderr or "screenshot failed").strip()[-300:])
    return {"saved": path, "bytes": os.path.getsize(path)}


def tool_restart_pc():
    if IS_WIN:
        subprocess.run(["shutdown", "/r", "/t", "60", "/c", "Phoenix Console: restart requested. Cancel with the Console or 'shutdown /a'."],
                       check=True, capture_output=True)
    else:                                         # Linux counts in minutes
        subprocess.run(["shutdown", "-r", "+1", "Phoenix Console: restart requested"], check=True, capture_output=True)
    return {"restarting_in_s": 60}


def tool_cancel_restart():
    r = subprocess.run(["shutdown", "/a"] if IS_WIN else ["shutdown", "-c"], capture_output=True, text=True)
    return {"cancelled": r.returncode == 0}


# ── Linux (the headless boxes: no screen, so no open_app / screenshot) ─────
LINUX_SERVICES = ["nebula", "helix", "phoenix-paging", "phoenix-llm", "openjarvis", "ssh", "nftables"]  # Ollama removed 2026-10-07
RESTARTABLE = {"nebula": "the mesh agent (Nebula)", "phoenix-llm": "the local AI engine (llama.cpp)",
               "openjarvis": "Jarvis"}


def tool_status_linux():
    out = {"host": socket.gethostname(), "os": f"{platform.system()} {platform.release()}",
           "hands_version": SELF_SHA3[:12]}
    mem = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, _, v = line.partition(":")
            mem[k] = int(v.split()[0]) * 1024
    total, avail = mem.get("MemTotal", 0), mem.get("MemAvailable", 0)
    out["memory"] = {"total_gb": round(total / 2**30, 1), "free_gb": round(avail / 2**30, 1),
                     "used_pct": round(100 * (total - avail) / total) if total else None}
    with open("/proc/uptime") as f:
        out["uptime_h"] = round(float(f.read().split()[0]) / 3600, 1)
    out["load"] = [round(x, 2) for x in os.getloadavg()]
    out["cpus"] = os.cpu_count()
    drives, seen = [], set()
    with open("/proc/mounts") as f:
        for line in f:
            dev, mnt, fs = line.split()[:3]
            if fs not in ("ext4", "xfs", "btrfs", "vfat") or dev in seen:
                continue
            seen.add(dev)
            s = os.statvfs(mnt)
            drives.append({"drive": mnt, "label": dev.split("/")[-1],
                           "total_gb": round(s.f_blocks * s.f_frsize / 2**30), "free_gb": round(s.f_bavail * s.f_frsize / 2**30)})
    out["drives"] = drives
    return out


def tool_services():
    r = subprocess.run(["systemctl", "is-active", *LINUX_SERVICES], capture_output=True, text=True)
    states = r.stdout.split()
    return {"services": [{"name": n, "state": states[i] if i < len(states) else "unknown"}
                         for i, n in enumerate(LINUX_SERVICES)]}


def tool_restart_service(service):
    if service not in RESTARTABLE:
        raise ValueError(f"only these can be restarted from the Console: {', '.join(RESTARTABLE)}")
    subprocess.run(["systemctl", "restart", service], check=True, capture_output=True, timeout=60)
    r = subprocess.run(["systemctl", "is-active", service], capture_output=True, text=True)
    return {"service": service, "state": r.stdout.strip()}


# The declared tool list. The Console and H.L.K see exactly this, nothing else.
_RESTART = {"fn": tool_restart_pc, "tier": "ask", "label": "Restart this machine",
            "says": "Restarts this machine in about a minute. Anything unsaved is lost.",
            "question": "Restart {host} in about a minute? Anything unsaved on it will be lost."}
_CANCEL = {"fn": tool_cancel_restart, "tier": "base", "label": "Cancel a restart",
           "says": "Stops a restart that's counting down."}
if IS_WIN:
    TOOLS = {
        "status": {"fn": tool_status, "tier": "base", "label": "Machine status",
                   "says": "Memory, drives and uptime of this PC."},
        "open_app": {"fn": tool_open_app, "tier": "base", "label": "Open an app",
                     "says": "Opens an app on this PC's screen.", "params": {"app": list(APPS), "folder": "optional, explorer only"}},
        "screenshot": {"fn": tool_screenshot, "tier": "base", "label": "Take a screenshot",
                       "says": "Saves a picture of this PC's screen to Pictures\\Phoenix."},
        "restart_pc": _RESTART,
        "cancel_restart": _CANCEL,
    }
else:
    TOOLS = {
        "status": {"fn": tool_status_linux, "tier": "base", "label": "Machine status",
                   "says": "Memory, disks, load and uptime of this machine."},
        "services": {"fn": tool_services, "tier": "base", "label": "Phoenix services",
                     "says": "Which Phoenix services are running here."},
        "restart_service": {"fn": tool_restart_service, "tier": "ask", "label": "Restart a service",
                            "says": "Restarts the mesh agent or Ollama.", "params": {"service": list(RESTARTABLE)},
                            "question": "Restart {what} on {host}? It drops out for a few seconds."},
        "restart_pc": _RESTART,
        "cancel_restart": _CANCEL,
    }


def _name_from_hosts():
    """This PC's Phoenix name, readable without admin: the mesh agent writes
    '10.42.x.x<TAB>name.phx' for every member into the hosts file (a public
    file, no secrets), and this PC's own mesh address picks our line."""
    try:
        mine = {i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
    except OSError:
        mine = set()
    ip = mesh_ip()
    if ip:
        mine.add(ip)
    hosts = (os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "drivers", "etc", "hosts")
             if platform.system() == "Windows" else "/etc/hosts")
    try:
        with open(hosts, encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2 and parts[0] in mine and parts[0].startswith(MESH_PREFIX) and parts[1].endswith(".phx"):
                    return parts[1][:-4]
    except OSError:
        pass
    return None


def phoenix_name():
    """This PC's Phoenix name (pbmii, pbmiii...) from the mesh agent; else the OS name."""
    conf = (os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "PhoenixMesh", "device.json")
            if IS_WIN else "/etc/phoenix-mesh/device.json")
    try:
        with open(conf, encoding="utf-8") as f:
            return json.load(f).get("name") or socket.gethostname()
    except (OSError, ValueError):          # admin-only folder (it holds the mesh key): use the hosts file
        return _name_from_hosts() or socket.gethostname()


def public_tools():
    return [{"name": n, "tier": t["tier"], "label": t["label"], "says": t["says"], "params": t.get("params", {})}
            for n, t in TOOLS.items()]


def log(entry):
    entry = {"at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **entry}
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with _log_lock, open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def recent(n=20):
    try:
        with open(LOG_FILE, encoding="utf-8") as f:
            lines = f.readlines()[-n:]
    except OSError:
        return []
    return [json.loads(l) for l in reversed(lines) if l.strip()]


def run(tool, args, confirm, caller):
    """Tier check + run + audit. Returns (http_status, body)."""
    if not isinstance(args, dict):
        return 400, {"ok": False, "error": "args must be an object"}
    t = TOOLS.get(tool)
    if not t:
        log({"caller": caller, "tool": tool, "ok": False, "error": "no such tool"})
        return 404, {"ok": False, "error": f"no such tool '{tool}'"}
    if tool == "restart_service" and args.get("service") not in RESTARTABLE:   # refuse before asking anyone
        log({"caller": caller, "tool": tool, "args": args, "tier": "ask", "ok": False, "error": "not on the restart list"})
        return 400, {"ok": False, "error": f"only these can be restarted: {', '.join(RESTARTABLE)}"}
    if t["tier"] == "ask" and confirm is not True:
        log({"caller": caller, "tool": tool, "args": args, "tier": "ask", "ok": False, "error": "waiting for confirmation"})
        what = RESTARTABLE.get(args.get("service"), "") if isinstance(args, dict) else ""
        return 409, {"ok": False, "needs_confirm": True,
                     "question": t["question"].format(host=phoenix_name(), what=what)}
    try:
        result = t["fn"](**args)
    except TypeError as e:
        log({"caller": caller, "tool": tool, "args": args, "tier": t["tier"], "ok": False, "error": f"bad args: {e}"})
        return 400, {"ok": False, "error": f"bad arguments for {tool}"}
    except Exception as e:
        log({"caller": caller, "tool": tool, "args": args, "tier": t["tier"], "ok": False, "error": str(e)[:300]})
        return 500, {"ok": False, "error": str(e)[:300]}
    log({"caller": caller, "tool": tool, "args": args, "tier": t["tier"], "confirmed": bool(confirm), "ok": True})
    return 200, {"ok": True, "result": result}


# ── HTTP (127.0.0.1 only; token required) ──────────────────────────────────
def load_token():
    if os.path.exists(TOKEN_FILE):
        return open(TOKEN_FILE, encoding="utf-8").read().strip()
    os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
    tok = secrets.token_hex(32)
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(tok)
    if IS_WIN:                                    # owner-only, like the vault
        subprocess.run(["icacls", TOKEN_FILE, "/inheritance:r", "/grant:r", f"{os.environ.get('USERNAME')}:F"],
                       capture_output=True)
    else:
        os.chmod(TOKEN_FILE, 0o600)
    return tok


def make_handler(token, allow_from=()):
    def eq(a, b):
        return secrets.compare_digest(a.encode(), b.encode())

    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = "PhoenixHands/0"

        def log_message(self, *a):
            pass

        def _send(self, code, obj=None, raw=None, ctype="application/json"):
            body = raw if raw is not None else json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _authed(self):
            ip = self.client_address[0]
            if allow_from and ip != "127.0.0.1" and ip not in allow_from:
                return False                      # on the mesh, only the Console's PC may call
            got = (self.headers.get("Authorization") or "").replace("Bearer ", "", 1).strip()
            return bool(got) and eq(got, token)

        def do_GET(self):
            if not self._authed():
                return self._send(401, {"ok": False, "error": "unauthorized"})
            if self.path == "/tools":
                return self._send(200, {"ok": True, "host": phoenix_name(), "version": SELF_SHA3[:12], "tools": public_tools()})
            if self.path.startswith("/log"):
                return self._send(200, {"ok": True, "entries": recent(20)})
            if self.path == "/shot/latest":
                shots = sorted(f for f in os.listdir(SHOT_DIR) if f.startswith("shot-")) if os.path.isdir(SHOT_DIR) else []
                if not shots:
                    return self._send(404, {"ok": False, "error": "no screenshot yet"})
                with open(os.path.join(SHOT_DIR, shots[-1]), "rb") as f:
                    return self._send(200, raw=f.read(), ctype="image/png")
            return self._send(404, {"ok": False, "error": "not found"})

        def do_POST(self):
            if not self._authed():
                return self._send(401, {"ok": False, "error": "unauthorized"})
            if self.path != "/run":
                return self._send(404, {"ok": False, "error": "not found"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(min(n, 65536)) or b"{}")
            except ValueError:
                return self._send(400, {"ok": False, "error": "body must be JSON"})
            caller = str(self.headers.get("X-Caller") or "unknown")[:80]
            code, out = run(str(body.get("tool", "")), body.get("args") or {}, body.get("confirm"), caller)
            return self._send(code, out)

    return Handler


# ── import from the clone pool (the boxes) ─────────────────────────────────
# Build once: a new hands.py is intaked into the clone pool ONE time; the hub
# relays it (checked against custody) and every box swaps it in here. Only the
# very first install is by hand: a helper can't import itself before it exists.
UPDATE_EVERY_S = 300


def update_once(url, token):
    """-> 'current' | 'updated' | an error string. On 'updated' the caller exits
    and systemd starts the new version."""
    import hashlib
    import urllib.error
    import urllib.request
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "User-Agent": "phoenix-hands/0",
                                               "X-Have-SHA3": SELF_SHA3})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data, claimed = r.read(), (r.headers.get("X-Phoenix-SHA3") or "").lower()
    except urllib.error.HTTPError as e:
        if e.code == 304:                                # the hub says: you already have it
            return "current"
        return f"hub answered {e.code}"
    except Exception as e:
        return f"no answer from the hub ({type(e).__name__})"
    got = hashlib.sha3_512(data).hexdigest()
    if not claimed or got != claimed:
        return "refused: the file doesn't match its custody fingerprint"
    if got == SELF_SHA3:
        return "current"
    try:
        compile(data, "hands.py", "exec")               # never swap in a file that won't even start
    except SyntaxError as e:
        return f"refused: new version doesn't compile ({e.msg})"
    tmp = SELF + ".new"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, SELF)                                # atomic: old or new, never half
    log({"caller": "clone pool via hub", "tool": "self_update", "ok": True,
         "args": {"from": SELF_SHA3[:12], "to": got[:12]}})
    return "updated"


def update_loop(url, token):
    time.sleep(20)
    while True:
        result = update_once(url, token)
        if result == "updated":
            print("hands: new version imported from the clone pool; restarting", flush=True)
            os._exit(0)                                  # systemd (Restart=always) starts the new one
        if result != "current":
            print(f"hands: update check: {result}", flush=True)
        time.sleep(UPDATE_EVERY_S)


MESH_PREFIX = "10.42."                  # Phoenix Mesh = Nebula 10.42.0.0/16 (sector3/mesh/hosts.json)
MESH_DEV = "PhoenixMesh" if IS_WIN else "nebula1"   # the Nebula interface (sector3/mesh/phoenix_net.py)
_IPV4_RE = re.compile(r"\b(10\.42\.\d{1,3}\.\d{1,3})\b")


def mesh_ip():
    """This machine's Nebula 10.42.x address, read from the Nebula interface
    (Linux `nebula1`, Windows adapter `PhoenixMesh`); else any local 10.42.x.
    None while the mesh is down. (The old WireGuard mesh, 10.47.0.x, is retired.)"""
    cmds = ([["netsh", "interface", "ipv4", "show", "addresses", f"name={MESH_DEV}"]] if IS_WIN
            else [["ip", "-4", "-o", "addr", "show", "dev", MESH_DEV], ["ip", "-4", "-o", "addr", "show"]])
    for cmd in cmds:
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=5,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        m = _IPV4_RE.search(out)
        if m:
            return m.group(1)
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            if info[4][0].startswith(MESH_PREFIX):
                return info[4][0]
    except OSError:
        pass
    return None


def main():
    ap = argparse.ArgumentParser(prog="phoenix-hands")
    ap.add_argument("--port", type=int, default=8471)
    ap.add_argument("--mesh", action="store_true", help="also listen on this machine's mesh address (the headless boxes)")
    ap.add_argument("--allow-from", default="", help="comma list of mesh IPs allowed to call (the Console's PC)")
    ap.add_argument("--update-from", default="", help="the hub's clone-pool relay, e.g. http://10.42.0.1:8470/pool/hands.py")
    a = ap.parse_args()
    allow = tuple(x.strip() for x in a.allow_from.split(",") if x.strip())
    if a.mesh and not allow:
        raise SystemExit("--mesh needs --allow-from (never open the hands to the whole mesh)")
    token = load_token()
    handler = make_handler(token, allow)
    if a.update_from:
        threading.Thread(target=update_loop, args=(a.update_from, token), daemon=True).start()
    addrs = ["127.0.0.1"]
    if a.mesh:
        ip, waited = mesh_ip(), 0
        while not ip:                             # Nebula can come up after us; say so instead of hanging silently
            if waited % 300 == 0:
                print(f"hands: waiting for the Phoenix Mesh (Nebula {MESH_DEV}, {MESH_PREFIX}x) to come up", flush=True)
            time.sleep(10)
            waited += 10
            ip = mesh_ip()
        addrs.append(ip)
    for addr in addrs[:-1]:
        srv = http.server.ThreadingHTTPServer((addr, a.port), handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        print(f"hands: http://{addr}:{a.port}", flush=True)
    print(f"hands: http://{addrs[-1]}:{a.port}" + (f" (callers: {', '.join(allow)})" if allow else ""), flush=True)
    http.server.ThreadingHTTPServer((addrs[-1], a.port), handler).serve_forever()


if __name__ == "__main__":
    main()
