#!/usr/bin/env python3
"""Tests for helix_vramd: the memory manager as a service, and the translator
on top of it. Runs without helix.ko (HELIX_VRAM_NO_KERNEL=1). Exit code =
number of failures.  python3 sector1/helix/test_helix_vramd.py"""
import json
import os
import socket
import sys
import tempfile
import threading
import time

os.environ["HELIX_VRAM_NO_KERNEL"] = "1"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import helix_vramd  # noqa: E402
from helix_vram import HelixMemoryManager, HelixFullError  # noqa: E402
from helix_translator import HelixTranslator  # noqa: E402

TMP = tempfile.mkdtemp(prefix="vramd-test-")
SOCK = os.path.join(TMP, "helix-vram.sock")
os.environ["HELIX_VRAM_STRAND_B"] = TMP
failures = 0


def t(name, fn):
    global failures
    try:
        fn()
        print(f"  ok  {name}")
    except Exception as e:  # noqa: BLE001
        failures += 1
        print(f"FAIL  {name}\n      {type(e).__name__}: {e}")


# a small Helix so the "full" path is reachable in a test
manager = HelixMemoryManager(max_hot_mb=1, max_warm_mb=1, max_cold_mb=1, strand_b_mb=2,
                             strand_b_dir=TMP, use_kernel=False)
ready = threading.Event()
server_holder = {}


def _run():
    server_holder["srv"] = helix_vramd.serve(SOCK, manager, ready)


th = threading.Thread(target=_run, daemon=True)
th.start()
assert ready.wait(10), "daemon did not start"


def socket_mode():
    mode = os.stat(SOCK).st_mode & 0o777
    assert mode == 0o660, oct(mode)


def ping_and_stat():
    with helix_vramd.HelixVramClient(SOCK) as c:
        assert c.ping()
        s = c.stat()
        assert "dandelion" in s and "snapshot" in s and s["daemon"]["requests"] >= 2, s.keys()
        assert s["dandelion"]["kernel_linked"] is False


def alloc_read_write_free():
    with helix_vramd.HelixVramClient(SOCK) as c:
        c.alloc("k1", {"a": 1, "b": [1, 2, 3]})
        assert c.read("k1") == {"a": 1, "b": [1, 2, 3]}
        c.write("k1", "changed")
        assert c.read("k1") == "changed"
        assert c.free("k1") is True
        assert c.free("k1") is False
        assert c.read("k1") is None


def raw_bytes_round_trip():
    blob = os.urandom(70000)
    with helix_vramd.HelixVramClient(SOCK) as c:
        c.alloc("blob", blob)
        assert c.read("blob") == blob
        c.free("blob")


def bad_requests_do_not_kill_daemon():
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(SOCK)
    f = s.makefile("rwb")
    for raw, want in [(b"not json\n", "invalid json"),
                      (b"[1,2]\n", "must be an object"),
                      (b'{"op":"nope"}\n', "unknown op"),
                      (b'{"op":"read"}\n', "key required"),
                      (b'{"op":"alloc","key":"x"}\n', "data or b64 required"),
                      (b'{"op":"alloc","key":"x","b64":"%%%"}\n', "bad b64")]:
        f.write(raw); f.flush()
        r = json.loads(f.readline())
        assert r["ok"] is False and want in r["error"], (raw, r)
    f.close(); s.close()
    with helix_vramd.HelixVramClient(SOCK) as c:
        assert c.ping(), "daemon still answers after the garbage"


def full_helix_refuses():
    with helix_vramd.HelixVramClient(SOCK) as c:
        refused = False
        for i in range(80):
            try:
                c.alloc(f"big{i}", os.urandom(200 * 1024))
            except HelixFullError:
                refused = True
                break
        assert refused, "a 3 MiB Helix accepted 16 MiB without refusing"
        s = c.stat()
        assert s["refused"] >= 1
        for i in range(80):
            c.free(f"big{i}")


def translator_on_the_real_helix():
    with helix_vramd.HelixVramClient(SOCK) as c:
        tr = HelixTranslator(c)
        p = tr.translate_malloc(64)
        assert tr.translate_write(p, b"hello helix"), "write"
        assert tr.translate_read(p, 11) == b"hello helix", tr.translate_read(p, 11)
        assert tr.inspect_pointer(p) is not None
        assert tr.translate_free(p)
        fd = tr.translate_open("/virtual/notes.txt", "w")
        assert tr.translate_write_file(fd, b"line one\n")
        assert tr.translate_read_file(fd, 100) == b"line one\n"
        assert tr.translate_close(fd)
        st = tr.get_stats()
        assert st["malloc_intercepts"] == 1 and st["free_intercepts"] == 1, st


def many_clients_at_once():
    errors = []

    def worker(n):
        try:
            with helix_vramd.HelixVramClient(SOCK) as c:
                for i in range(50):
                    c.write(f"w{n}-{i}", i)
                    assert c.read(f"w{n}-{i}") == i
                for i in range(50):
                    c.free(f"w{n}-{i}")
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    ths = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    [x.start() for x in ths]
    [x.join(20) for x in ths]
    assert not errors, errors[:2]


def status_cli():
    os.environ["HELIX_VRAM_SOCK"] = SOCK
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = helix_vramd.main(["helix_vramd.py", "status"])
    assert rc == 0 and "Dandelion" in buf.getvalue(), buf.getvalue()


def stops_cleanly():
    _find_server().shutdown()          # what SIGTERM does in serve()
    th.join(10)
    assert not th.is_alive(), "serve() did not return after shutdown"
    assert not os.path.exists(SOCK), "socket file left behind"


def _find_server():
    import gc
    for obj in gc.get_objects():
        if isinstance(obj, helix_vramd.HelixVramServer):
            return obj
    raise AssertionError("server instance not found")


t("socket is 0660", socket_mode)
t("ping + stat", ping_and_stat)
t("alloc/read/write/free", alloc_read_write_free)
t("raw bytes round trip (70 KB)", raw_bytes_round_trip)
t("bad requests are rejected, daemon survives", bad_requests_do_not_kill_daemon)
t("full Helix refuses instead of dropping data", full_helix_refuses)
t("HelixTranslator runs on the real Helix", translator_on_the_real_helix)
t("8 clients at once", many_clients_at_once)
t("status CLI", status_cli)
t("stops cleanly, socket removed", stops_cleanly)


def real_sigterm_in_a_subprocess():
    """The daemon as systemd runs it: main thread in serve_forever, SIGTERM
    from outside, must exit 0 within a few seconds and remove its socket."""
    import subprocess, signal as _sig
    sock = os.path.join(TMP, "sig.sock")
    env = dict(os.environ, HELIX_VRAM_SOCK=sock, HELIX_VRAM_NO_KERNEL="1", HELIX_VRAM_STRAND_B=TMP,
               HELIX_VRAM_HOT_MB="1", HELIX_VRAM_WARM_MB="1", HELIX_VRAM_COLD_MB="1", HELIX_VRAM_STRAND_B_MB="2")
    p = subprocess.Popen([sys.executable, os.path.join(HERE, "helix_vramd.py"), "serve"], env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for _ in range(100):
        if os.path.exists(sock):
            break
        time.sleep(0.1)
    with helix_vramd.HelixVramClient(sock) as c:
        assert c.ping()
    t0 = time.time()
    p.send_signal(_sig.SIGTERM)
    try:
        out, _ = p.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        p.kill(); raise AssertionError("still alive 10 s after SIGTERM (deadlock)")
    assert p.returncode == 0, (p.returncode, out[-300:])
    assert time.time() - t0 < 8, "took too long to stop"
    assert not os.path.exists(sock), "socket left behind"
    assert "stopped" in out, out[-300:]


t("real SIGTERM in a subprocess stops it (no deadlock)", real_sigterm_in_a_subprocess)

print(f"\n{11 - failures} passing, {failures} failing")
sys.exit(failures)
