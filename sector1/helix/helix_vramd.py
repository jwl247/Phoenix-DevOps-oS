#!/usr/bin/env python3
"""
helix_vramd.py - the Helix memory manager as a service (jwl247 / GPL v3)

helix_vram.py is a library: a full userspace double Helix (HelixMemoryManager)
that follows the kernel Dandelion. Until 2026-09-28 nothing hosted it, so on
the Compaq "the memory manager" existed only for the length of its own test
run. This daemon keeps ONE HelixMemoryManager alive for the machine and lets
any local process use her over a Unix socket:

    /run/phoenix/helix-vram.sock   (HELIX_VRAM_SOCK)   mode 0660

Protocol: one JSON object per line, one reply per line.
    {"op":"ping"}
    {"op":"alloc","key":"k","data":<json>}        {"op":"alloc","key":"k","b64":"..."}
    {"op":"write","key":"k","data":<json>}        (or "b64" for raw bytes)
    {"op":"read","key":"k"}                       -> {"ok":true,"found":true,"data":<json>} or "b64"
    {"op":"free","key":"k"}                       -> {"ok":true,"freed":true|false}
    {"op":"stat"}                                 -> HelixMemoryManager.get_stats() + snapshot
    {"op":"tick"}                                 -> one Dandelion tick (tests; the daemon ticks itself)
Errors: {"ok":false,"error":"..."}; a full Helix answers {"ok":false,"error":"helix full"}
(HelixFullError - she refuses rather than dropping data, same as the library).

Sizes (MiB) come from the environment so /etc/default/helix-vram can set them
per machine: HELIX_VRAM_HOT_MB (256) HELIX_VRAM_WARM_MB (1024) HELIX_VRAM_COLD_MB
(3072) HELIX_VRAM_STRAND_B_MB (8192) HELIX_VRAM_STRAND_B (dir for Strand B,
default /var/lib/helix/vram). HELIX_VRAM_NO_KERNEL=1 runs without helix.ko.

HelixVramClient (same file) is the client library, and it presents the
`.memory` (malloc/free/read/write) and `.fs` (read_file/write_file) faces that
sector1/helix/helix_translator.py's HelixTranslator expects, so the translator
finally has a real Helix behind it instead of its demo's MockHelix.

    helix_vramd.py serve            run (systemd: helix-vram.service)
    helix_vramd.py status           print stats from the running daemon
"""
import base64
import json
import os
import signal
import socket
import socketserver
import stat
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from helix_vram import HelixMemoryManager, HelixFullError  # noqa: E402

DEFAULT_SOCK = "/run/phoenix/helix-vram.sock"
MAX_LINE = 64 * 1024 * 1024        # one request line; bigger than this is refused, not buffered forever
FS_PREFIX = "file:"                # translator file paths live in the same key space


def _env_int(name, default):
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


# ============================================================================
# SERVER
# ============================================================================
class _Handler(socketserver.StreamRequestHandler):
    def handle(self):
        srv = self.server
        while True:
            line = self.rfile.readline(MAX_LINE + 1)
            if not line:
                return
            if len(line) > MAX_LINE:
                self._reply({"ok": False, "error": "request too large"})
                return
            try:
                req = json.loads(line)
            except ValueError as e:
                self._reply({"ok": False, "error": f"invalid json: {e}"})
                continue
            if not isinstance(req, dict):
                self._reply({"ok": False, "error": "request must be an object"})
                continue
            self._reply(srv.dispatch(req))

    def _reply(self, obj):
        self.wfile.write((json.dumps(obj) + "\n").encode())
        self.wfile.flush()


class HelixVramServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, path, manager):
        self.manager = manager
        self.started = time.time()
        self.requests = 0
        self._lock = threading.Lock()
        if os.path.exists(path):
            os.unlink(path)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        super().__init__(path, _Handler)
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP)
        # the daemon runs as root (it opens /dev/helix_intent); members of the
        # `phoenix` group (install-team.sh creates it) get the socket
        try:
            import grp
            os.chown(path, -1, grp.getgrnam(os.environ.get("HELIX_VRAM_GROUP", "phoenix")).gr_gid)
        except (KeyError, PermissionError, OSError):
            pass

    # ------------------------------------------------------------ requests
    def dispatch(self, req):
        with self._lock:
            self.requests += 1
        op = req.get("op")
        key = req.get("key")
        m = self.manager
        try:
            if op == "ping":
                return {"ok": True, "pong": True, "uptime_s": round(time.time() - self.started, 3)}
            if op in ("alloc", "write", "read", "free") and (not isinstance(key, str) or not key):
                return {"ok": False, "error": "key required"}
            if op in ("alloc", "write"):
                data, err = _decode_payload(req)
                if err:
                    return {"ok": False, "error": err}
                (m.allocate if op == "alloc" else m.write)(key, data)
                return {"ok": True, "key": key}
            if op == "read":
                value = m.read(key)
                if value is None:
                    return {"ok": True, "found": False}
                return {"ok": True, "found": True, **_encode_payload(value)}
            if op == "free":
                return {"ok": True, "freed": bool(m.free(key))}
            if op == "stat":
                s = m.get_stats()
                s["snapshot"] = m.get_tier_snapshot()
                s["daemon"] = {"uptime_s": round(time.time() - self.started, 3), "requests": self.requests,
                               "pid": os.getpid(), "socket": self.server_address}
                return {"ok": True, **s}
            if op == "tick":
                return {"ok": True, **m.tick()}
            return {"ok": False, "error": f"unknown op: {op!r}"}
        except HelixFullError:
            return {"ok": False, "error": "helix full"}
        except Exception as e:  # a bad request must never take the daemon down
            return {"ok": False, "error": f"{type(e).__name__}: {e}"[:400]}


def _decode_payload(req):
    if "b64" in req:
        try:
            return base64.b64decode(req["b64"], validate=True), None
        except (ValueError, TypeError) as e:
            return None, f"bad b64: {e}"
    if "data" in req:
        return req["data"], None
    return None, "data or b64 required"


def _encode_payload(value):
    if isinstance(value, (bytes, bytearray)):
        return {"b64": base64.b64encode(bytes(value)).decode()}
    return {"data": value}


def make_manager():
    return HelixMemoryManager(
        max_hot_mb=_env_int("HELIX_VRAM_HOT_MB", 256),
        max_warm_mb=_env_int("HELIX_VRAM_WARM_MB", 1024),
        max_cold_mb=_env_int("HELIX_VRAM_COLD_MB", 3072),
        strand_b_mb=_env_int("HELIX_VRAM_STRAND_B_MB", 8192),
        strand_b_dir=os.environ.get("HELIX_VRAM_STRAND_B") or "/var/lib/helix/vram",
        use_kernel=os.environ.get("HELIX_VRAM_NO_KERNEL") != "1",
    )


def serve(path=None, manager=None, ready=None):
    """Run until SIGTERM/SIGINT. `ready` (threading.Event) is set once listening."""
    path = path or os.environ.get("HELIX_VRAM_SOCK", DEFAULT_SOCK)
    manager = manager or make_manager()
    server = HelixVramServer(path, manager)
    stop = threading.Event()

    def _stop(*_):
        # Python runs signal handlers on the main thread, which is the thread
        # inside serve_forever(); shutdown() waits for serve_forever() to
        # return, so calling it here deadlocks (round-3 S1-F22: alive 8 s
        # after SIGTERM, killed by systemd's TimeoutStopSec). Ask from a
        # helper thread instead.
        if not stop.is_set():
            stop.set()
            threading.Thread(target=server.shutdown, name="helix-vramd-stop", daemon=True).start()

    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)
    print(f"helix_vramd: listening on {path} (kernel {'linked' if manager._feed is not None else 'standalone'})", flush=True)
    if ready is not None:
        ready.set()
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
        try:
            os.unlink(path)
        except OSError:
            pass
        manager.close()
        print("helix_vramd: stopped", flush=True)
    return server


# ============================================================================
# CLIENT
# ============================================================================
class HelixVramClient:
    """Line-JSON client. Thread-safe (one socket, one lock). Exposes .memory
    and .fs so HelixTranslator(HelixVramClient()) is a real translator."""

    def __init__(self, path=None, timeout=10.0):
        self.path = path or os.environ.get("HELIX_VRAM_SOCK", DEFAULT_SOCK)
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.settimeout(timeout)
        self._sock.connect(self.path)
        self._f = self._sock.makefile("rwb")
        self._lock = threading.Lock()
        self.memory = _MemoryFace(self)
        self.fs = _FsFace(self)

    def call(self, **req):
        with self._lock:
            self._f.write((json.dumps(req) + "\n").encode())
            self._f.flush()
            line = self._f.readline()
        if not line:
            raise ConnectionError("helix_vramd closed the connection")
        return json.loads(line)

    # convenience -------------------------------------------------------
    def ping(self):
        return self.call(op="ping").get("pong") is True

    def alloc(self, key, data):
        return self._checked(self.call(op="alloc", key=key, **_encode_payload(data)))

    def write(self, key, data):
        return self._checked(self.call(op="write", key=key, **_encode_payload(data)))

    def read(self, key):
        r = self._checked(self.call(op="read", key=key))
        if not r.get("found"):
            return None
        return base64.b64decode(r["b64"]) if "b64" in r else r["data"]

    def free(self, key):
        return bool(self._checked(self.call(op="free", key=key)).get("freed"))

    def stat(self):
        return self._checked(self.call(op="stat"))

    def close(self):
        try:
            self._f.close()
        finally:
            self._sock.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    @staticmethod
    def _checked(r):
        if not r.get("ok"):
            if r.get("error") == "helix full":
                raise HelixFullError("helix full")
            raise RuntimeError(r.get("error", "helix_vramd error"))
        return r


class _MemoryFace:
    """What HelixTranslator calls self.helix.memory: malloc/free/read/write."""
    def __init__(self, c):
        self._c = c

    def malloc(self, key, data):
        self._c.alloc(key, data)
        return True

    def free(self, key):
        return self._c.free(key)

    def read(self, key):
        return self._c.read(key)

    def write(self, key, data):
        self._c.write(key, data)
        return True


class _FsFace:
    """What HelixTranslator calls self.helix.fs: read_file/write_file."""
    def __init__(self, c):
        self._c = c

    def read_file(self, path):
        return self._c.read(FS_PREFIX + path)

    def write_file(self, path, data):
        self._c.write(FS_PREFIX + path, data)
        return True


# ============================================================================
# CLI
# ============================================================================
def main(argv):
    cmd = argv[1] if len(argv) > 1 else "serve"
    if cmd == "serve":
        serve()
        return 0
    if cmd == "status":
        try:
            with HelixVramClient() as c:
                s = c.stat()
        except (OSError, ConnectionError) as e:
            print(f"helix_vramd: not reachable at {os.environ.get('HELIX_VRAM_SOCK', DEFAULT_SOCK)}: {e}")
            return 1
        d = s["dandelion"]
        print(f"helix-vram  pid {s['daemon']['pid']}  up {s['daemon']['uptime_s']:.0f}s  requests {s['daemon']['requests']}")
        print(f"  Dandelion: heat {d['heat']:.3f} state {d['state']} compression {d['compression']:.2f} "
              f"kernel {'linked' if d['kernel_linked'] else 'standalone'}")
        print(f"  blocks {s['total_blocks']} (hot {s['hot_blocks']} warm {s['warm_blocks']} cold {s['cold_blocks']}, rungs {s['rungs']})")
        print(f"  Strand A raw {s['hot_usage_mb']:.2f} MB, zlib5 {s['warm_usage_mb']:.2f} MB; Strand B {s['cold_usage_mb']:.2f} MB; "
              f"hit rate {s['hit_rate']:.1f}%  refused {s['refused']}")
        print(f"  temperatures {s['temperatures']}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
