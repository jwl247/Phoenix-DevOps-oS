#!/usr/bin/env python3
"""playbox.py — the play box: entertainment suits run here, never inside the kernel (Jerry 2026-10-09).

Phoenix DevOps OS | jwl247 | GPL v3

"Separate system suit and entertainment so I'm not playing with shit and cripple the system."

The kernel keeps SYSTEM suits in its own process. Everything else (games, tests, Jarvis, any
suit nobody said SYSTEM to at a terminal) is loaded into this separate process:
  * its own process: a crash, a hang or a memory blow-up kills the box, never the kernel;
  * Windows: a Job Object caps its memory and CPU, and kills it the moment the kernel's
    handle closes (the kernel dies -> the box dies, nothing left running on its own);
    Linux: rlimit on address space + nice 10;
  * loopback only, every request carries a token the kernel made for this box;
  * a run that passes its time limit -> the kernel kills the box, starts a fresh one, re-loads
    the other suits, and the suit answers {"ok": false, ...}. The kernel never stops.

Two halves in one file:
  python playbox.py serve          the box itself (started by the kernel, never by hand)
  PlayBox(...)                      the kernel's side (genie_control uses it)
Env (kernel side): PHOENIX_PLAYBOX_PORT (8767), PHOENIX_PLAYBOX_MEM_MB (1024),
                   PHOENIX_PLAYBOX_CPU_PCT (50), PHOENIX_PLAYBOX_TIMEOUT (90 s per run; under genie's 120 s wait, so a stopped run still answers)
"""

import base64
import hmac
import json
import logging
import os
import secrets
import socket
import socketserver
import subprocess
import sys
import threading
import time
import types

log = logging.getLogger("playbox")

BIND = "127.0.0.1"                       # deliberately not configurable
MAX_MSG = 8 * 1024 * 1024


# ── wire: one JSON line each way per connection ─────────────────────────────
def _send(sock, obj):
    sock.sendall(json.dumps(obj).encode("utf-8") + b"\n")


def _recv(sock):
    buf = bytearray()
    while not buf.endswith(b"\n"):
        chunk = sock.recv(65536)
        if not chunk:
            break
        buf += chunk
        if len(buf) > MAX_MSG:
            raise ValueError("message too large")
    return json.loads(buf.decode("utf-8")) if buf else None


def _pack(v):
    if isinstance(v, (bytes, bytearray)):
        return {"b64": base64.b64encode(bytes(v)).decode("ascii")}
    return {"s": "" if v is None else str(v)}


def _unpack(d):
    return base64.b64decode(d["b64"]) if "b64" in d else d.get("s", "")


# ── the box (separate process) ──────────────────────────────────────────────
def serve():
    token = os.environ.pop("PHOENIX_PLAYBOX_TOKEN", "")
    port = int(os.environ.get("PHOENIX_PLAYBOX_PORT", "8767"))
    if len(token) < 32:
        print("playbox: no token; started by hand? the kernel starts the box", file=sys.stderr)
        return 2
    mods = {}

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            try:
                req = _recv(self.connection)
                if not req or not hmac.compare_digest(str(req.get("token", "")), token):
                    _send(self.connection, {"ok": False, "error": "bad token"})
                    return
                op, name = req.get("op"), str(req.get("name", ""))
                if op == "ping":
                    _send(self.connection, {"ok": True, "pid": os.getpid(), "suits": sorted(mods)})
                elif op == "load":
                    code = _unpack(req["code"])
                    mod = types.ModuleType("playbox_" + name)
                    mod.__file__ = f"<playbox:{name}>"
                    exec(compile(code, mod.__file__, "exec"), mod.__dict__)
                    if not callable(getattr(mod, "run", None)):
                        raise ValueError(f"{name}: no run(data, ...) - not a suit")
                    mods[name] = mod                         # a re-load is the swap
                    _send(self.connection, {"ok": True, "name": name})
                elif op == "run":
                    if name not in mods:
                        raise ValueError(f"{name} is not loaded in the play box")
                    out = mods[name].run(_unpack(req["data"]))
                    _send(self.connection, {"ok": True, "out": _pack(out)})
                else:
                    raise ValueError(f"unknown op {op!r}")
            except BaseException as e:                       # the box answers; it never just dies on a suit
                try:
                    _send(self.connection, {"ok": False, "error": f"{type(e).__name__}: {e}"})
                except OSError:
                    pass

    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = False
        daemon_threads = True

    with Server((BIND, port), Handler) as srv:
        srv.serve_forever()
    return 0


# ── Windows Job Object (memory + CPU cap, killed with the kernel) ───────────
def _windows_job(proc, mem_mb, cpu_pct):
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.restype = wintypes.HANDLE

    class BASIC(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class IO(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in ("r", "w", "o", "rt", "wt", "ot")]

    class EXT(ctypes.Structure):
        _fields_ = [("Basic", BASIC), ("Io", IO), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    class CPU(ctypes.Structure):
        _fields_ = [("ControlFlags", wintypes.DWORD), ("CpuRate", wintypes.DWORD)]

    job = k32.CreateJobObjectW(None, None)
    if not job:
        raise OSError(ctypes.get_last_error(), "CreateJobObject failed")
    ext = EXT()
    ext.Basic.LimitFlags = 0x100 | 0x2000 | 0x200     # PROCESS_MEMORY | KILL_ON_JOB_CLOSE | JOB_MEMORY
    ext.ProcessMemoryLimit = mem_mb * 1024 * 1024
    ext.JobMemoryLimit = mem_mb * 1024 * 1024
    if not k32.SetInformationJobObject(job, 9, ctypes.byref(ext), ctypes.sizeof(ext)):
        raise OSError(ctypes.get_last_error(), "job memory limit failed")
    cpu = CPU(0x1 | 0x4, max(1, min(100, cpu_pct)) * 100)   # ENABLE | HARD_CAP, rate in 1/100 %
    if not k32.SetInformationJobObject(job, 15, ctypes.byref(cpu), ctypes.sizeof(cpu)):
        raise OSError(ctypes.get_last_error(), "job CPU cap failed")
    if not k32.AssignProcessToJobObject(job, wintypes.HANDLE(int(proc._handle))):
        raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject failed")
    return job                                            # keep the handle: closing it kills the box


# ── the kernel's side ───────────────────────────────────────────────────────
class PlayBox:
    def __init__(self, port=None, mem_mb=None, cpu_pct=None, timeout=None):
        self.port = int(port or os.environ.get("PHOENIX_PLAYBOX_PORT", "8767"))
        self.mem_mb = int(mem_mb or os.environ.get("PHOENIX_PLAYBOX_MEM_MB", "1024"))
        self.cpu_pct = int(cpu_pct or os.environ.get("PHOENIX_PLAYBOX_CPU_PCT", "50"))
        self.timeout = float(timeout or os.environ.get("PHOENIX_PLAYBOX_TIMEOUT", "90"))
        self._lock = threading.RLock()
        self._proc = None
        self._job = None
        self._token = ""
        self._code = {}                                   # name -> bytes, re-loaded into a fresh box
        self.restarts = 0

    # life cycle
    def _alive(self):
        return self._proc is not None and self._proc.poll() is None

    def _spawn(self):
        self._token = secrets.token_hex(32)
        env = dict(os.environ, PHOENIX_PLAYBOX_TOKEN=self._token, PHOENIX_PLAYBOX_PORT=str(self.port),
                   PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        cmd = [sys.executable, "-I", os.path.abspath(__file__), "serve"]
        kw = dict(env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                  close_fds=True)
        if os.name == "nt":
            kw["creationflags"] = 0x08000000             # CREATE_NO_WINDOW
            self._proc = subprocess.Popen(cmd, **kw)
            self._job = _windows_job(self._proc, self.mem_mb, self.cpu_pct)
        else:
            mem = self.mem_mb * 1024 * 1024

            def limits():
                import resource
                resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
                os.nice(10)
            self._proc = subprocess.Popen(cmd, preexec_fn=limits, **kw)
        deadline = time.time() + 15
        while time.time() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError(f"play box exited at start (code {self._proc.returncode}); port {self.port} in use?")
            try:
                if self._call({"op": "ping"}, timeout=2).get("ok"):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            self._kill()
            raise RuntimeError("play box did not answer within 15 s")
        for name, code in list(self._code.items()):      # a fresh box gets every suit back
            r = self._call({"op": "load", "name": name, "code": _pack(code)}, timeout=30)
            if not r.get("ok"):
                log.error("play box: %s not re-loaded: %s", name, r.get("error"))
        log.info("play box up: pid %s, port %s, %d MB / %d%% CPU cap, %d suit(s)",
                 self._proc.pid, self.port, self.mem_mb, self.cpu_pct, len(self._code))

    def _kill(self):
        if self._proc is not None and self._proc.poll() is None:
            self._proc.kill()
            try:
                self._proc.wait(5)
            except subprocess.TimeoutExpired:
                pass
        if self._job is not None and os.name == "nt":
            import ctypes
            ctypes.WinDLL("kernel32").CloseHandle(self._job)
        self._proc, self._job = None, None

    def _ensure(self):
        with self._lock:
            if not self._alive():
                if self._proc is not None:
                    self.restarts += 1
                    log.warning("play box was down (exit %s) - starting a fresh one", self._proc.returncode)
                self._spawn()

    def _call(self, req, timeout):
        req = dict(req, token=self._token)
        with socket.create_connection((BIND, self.port), timeout=timeout) as s:
            s.settimeout(timeout)
            _send(s, req)
            r = _recv(s)
        if r is None:
            raise ConnectionError("play box closed the connection")
        return r

    # what the kernel calls
    def load(self, name, code: bytes):
        self._ensure()
        r = self._call({"op": "load", "name": name, "code": _pack(code)}, timeout=30)
        if not r.get("ok"):
            raise ValueError(f"suit failed to load in the play box: {r.get('error')}")
        self._code[name] = bytes(code)

    def run(self, name, data):
        try:
            self._ensure()
            r = self._call({"op": "run", "name": name, "data": _pack(data)}, timeout=self.timeout)
        except (socket.timeout, TimeoutError):
            with self._lock:
                log.error("play box: %s ran past %ss - box killed and restarted; the kernel never stopped", name, self.timeout)
                self._kill()
                self.restarts += 1
            return json.dumps({"ok": False, "suit": name, "error": f"ran past {self.timeout:g}s in the play box; stopped"})
        except (OSError, ConnectionError, RuntimeError) as e:
            with self._lock:
                self._kill()                              # next call starts a fresh box
                self.restarts += 1
            return json.dumps({"ok": False, "suit": name, "error": f"play box failed: {e}"})
        if not r.get("ok"):
            return json.dumps({"ok": False, "suit": name, "error": r.get("error", "play box error")})
        return _unpack(r["out"])

    def view(self):
        return {"running": self._alive(), "pid": self._proc.pid if self._alive() else None, "port": self.port,
                "mem_mb": self.mem_mb, "cpu_pct": self.cpu_pct, "timeout_s": self.timeout,
                "suits": sorted(self._code), "restarts": self.restarts}

    def stop(self):
        with self._lock:
            self._kill()


if __name__ == "__main__":
    if sys.argv[1:] == ["serve"]:
        sys.exit(serve())
    print(__doc__)
    sys.exit(1)
