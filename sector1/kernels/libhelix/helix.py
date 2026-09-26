"""
helix.py - Python bindings for libhelix (HeIX userspace library)
jwl247 / Jerry Leftwich - GPL

Jerry's original ctypes binding, completed: every function has argtypes and
restype set (the original only declared init/register, so declare_hot/cold ran
on ctypes guesswork), errors carry errno, and stats()/intents() are new for the
userspace bridge.

    from helix import HeIX
    h = HeIX()
    h.register("attack-analyzer")
    h.declare_hot(["attack_data", "session_data"])
    h.declare_cold(["historical_patterns", "old_logs"])
    print(h.stats())
    for line in h.intents():
        print(line)

Needs libhelix.so next to this file (or HELIX_LIB=/path/libhelix.so), helix.ko
loaded, and permission to open /dev/helix_intent (root by default).
"""
import ctypes
import os

_here = os.path.dirname(os.path.abspath(__file__))
_lib = ctypes.CDLL(os.environ.get("HELIX_LIB", os.path.join(_here, "libhelix.so")),
                   use_errno=True)


class HelixStats(ctypes.Structure):
    # Must match struct helix_stats in ../helix.h (u64 x4, then u32 x4).
    _fields_ = [
        ("uptime_s", ctypes.c_uint64),
        ("ticks", ctypes.c_uint64),
        ("intents_posted", ctypes.c_uint64),
        ("intents_dropped", ctypes.c_uint64),
        ("mem_pressure_pct", ctypes.c_uint32),
        ("apps", ctypes.c_uint32),
        ("slots", ctypes.c_uint32),
        ("intents_queued", ctypes.c_uint32),
        ("dandelion_heat", ctypes.c_uint32),         # 0..1000
        ("dandelion_state", ctypes.c_uint32),        # cold/warm/hot/surging/cooling
        ("dandelion_compression", ctypes.c_uint32),  # 300..1000
        ("_pad", ctypes.c_uint32),
    ]

    def as_dict(self):
        return {name: getattr(self, name) for name, _ in self._fields_}


_c_str_array = ctypes.POINTER(ctypes.c_char_p)
_lib.helix_init.argtypes = []
_lib.helix_init.restype = ctypes.c_int
_lib.helix_register.argtypes = [ctypes.c_char_p]
_lib.helix_register.restype = ctypes.c_int
_lib.helix_declare_hot.argtypes = [_c_str_array, ctypes.c_int]
_lib.helix_declare_hot.restype = ctypes.c_int
_lib.helix_declare_cold.argtypes = [_c_str_array, ctypes.c_int]
_lib.helix_declare_cold.restype = ctypes.c_int
_lib.helix_get_stats.argtypes = [ctypes.POINTER(HelixStats)]
_lib.helix_get_stats.restype = ctypes.c_int
_lib.helix_read_intent.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
_lib.helix_read_intent.restype = ctypes.c_int
_lib.helix_mem_sync.argtypes = [ctypes.c_uint64, ctypes.c_size_t, ctypes.c_int]
_lib.helix_mem_sync.restype = ctypes.c_int
_lib.helix_virtual_mode.argtypes = []
_lib.helix_virtual_mode.restype = ctypes.c_int
_lib.helix_cleanup.argtypes = []
_lib.helix_cleanup.restype = None


class HelixError(OSError):
    pass


def _check(rc, what):
    if rc < 0:
        err = ctypes.get_errno()
        raise HelixError(err, f"HeIX: {what} failed: {os.strerror(err)}")
    return rc


def _array(items):
    arr = (ctypes.c_char_p * len(items))()
    for i, s in enumerate(items):
        arr[i] = s.encode("utf-8")
    return ctypes.cast(arr, _c_str_array), arr  # keep arr alive


class HeIX:
    def __init__(self):
        _check(_lib.helix_init(), "init")

    def register(self, app_name):
        _check(_lib.helix_register(app_name.encode("utf-8")), f"register {app_name}")
        return True

    def declare_hot(self, data_types):
        ptr, _keep = _array(data_types)
        _check(_lib.helix_declare_hot(ptr, len(data_types)), "declare_hot")
        return True

    def declare_cold(self, data_types):
        ptr, _keep = _array(data_types)
        _check(_lib.helix_declare_cold(ptr, len(data_types)), "declare_cold")
        return True

    @property
    def virtual(self):
        """True when helix.ko isn't loaded and libhelix is in Virtual Mode."""
        return bool(_lib.helix_virtual_mode())

    def mem_sync(self, ptr, size, tier=0):
        """Tell the kernel the VMMU placed `size` bytes at `ptr` in `tier`
        (0 HOT, 1 WARM, 2 COMPRESSED, 3 COLD). Same call AgnosticLayer makes."""
        _check(_lib.helix_mem_sync(ptr, size, tier), "mem_sync")
        return True

    def stats(self):
        st = HelixStats()
        _check(_lib.helix_get_stats(ctypes.byref(st)), "get_stats")
        return st.as_dict()

    def intents(self):
        """Drain queued intent lines (non-blocking)."""
        buf = ctypes.create_string_buffer(256)
        while True:
            n = _check(_lib.helix_read_intent(buf, len(buf)), "read_intent")
            if n == 0:
                return
            yield buf.value.decode("utf-8", "replace")

    def close(self):
        _lib.helix_cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


_BLOCK = 4096
_STATE_NAMES = ("cold", "warm", "hot", "surging", "cooling")


def _dm_helix_status():
    """Sum `dmsetup status` over every dm-helix target (root). Returns a dict of
    her counters, or {} when no helix target is up."""
    import re
    import shutil
    import subprocess
    dmsetup = shutil.which("dmsetup") or "/usr/sbin/dmsetup"
    try:
        out = subprocess.run([dmsetup, "status", "--target", "helix"],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    total = {}
    for line in out.splitlines():
        # "<name>: <start> <len> helix double dandelion heat 0.412 state hot ..."
        body = line.split(" helix ", 1)
        if len(body) != 2:
            continue
        toks = body[1].split()
        for key, val in re.findall(r"(\w+) (-?[0-9]+(?:\.[0-9]+)?)(?= |$)", " ".join(toks)):
            num = float(val) if "." in val else int(val)
            if key in ("heat", "compression"):
                total[key] = max(total.get(key, 0), num)
            else:
                total[key] = total.get(key, 0) + num
        if "state" in toks:
            total["state"] = toks[toks.index("state") + 1]
        total["targets"] = total.get("targets", 0) + 1
    return total


class KernelHelixFeed:
    """The kernel Helix as a tier source for her companions (paging manager,
    VRAM manager). One Helix underneath: tier sizes come from dm-helix's own
    counters, the Dandelion's heat/state from GET_STATS through libhelix.

    get_tier_snapshot() keys match sector4/paging.py's TierSnapshot:
      hot_mb    = raw blocks held in Strand A (RAM)
      warm_mb   = zlib-5 compressed bytes held in Strand A
      cold_mb   = blocks held on Strand B (her relief strand)
      frozen_mb = blocks Strand B had to evict since the last snapshot, i.e.
                  she ran out of relief room. >0 is the paging manager's cue.
    """

    def __init__(self, register_as="phoenix-paging"):
        self._helix = None
        try:
            self._helix = HeIX()
            if not self._helix.virtual:
                self._helix.register(register_as)
        except OSError:
            self._helix = None
        self._last_b_evictions = None

    def dandelion(self):
        if self._helix is None:
            return {}
        try:
            st = self._helix.stats()
        except OSError:
            return {}
        state = st["dandelion_state"]
        return {
            "heat": st["dandelion_heat"] / 1000.0,
            "state": _STATE_NAMES[state] if state < len(_STATE_NAMES) else str(state),
            "compression": st["dandelion_compression"] / 1000.0,
            "mem_pressure_pct": st["mem_pressure_pct"],
        }

    def get_tier_snapshot(self):
        import time
        s = _dm_helix_status()
        mb = 1024 * 1024
        b_ev = s.get("b_evictions", 0)
        fresh = 0 if self._last_b_evictions is None else max(0, b_ev - self._last_b_evictions)
        self._last_b_evictions = b_ev
        served = s.get("hits", 0) + s.get("zhits", 0) + s.get("b_hits", 0)
        asked = served + s.get("misses", 0)
        snap = {
            "timestamp": time.time(),
            "hot_mb": s.get("raw", 0) * _BLOCK / mb,
            "warm_mb": s.get("zbytes", 0) / mb,
            "cold_mb": s.get("used", 0) * _BLOCK / mb,
            "frozen_mb": fresh * _BLOCK / mb,
            "hit_rate": (served / asked * 100.0) if asked else 0.0,
            "promotions": s.get("inserts", 0),
            "demotions": s.get("compressed", 0) + s.get("b_writes", 0),
            "evictions": s.get("evictions", 0) + b_ev,
            "targets": s.get("targets", 0),
        }
        snap.update({"dandelion_" + k: v for k, v in self.dandelion().items()})
        if "heat" in s and "dandelion_heat" not in snap:
            snap["dandelion_heat"] = s["heat"]
            snap["dandelion_state"] = s.get("state")
        return snap

    def mem_sync(self, ptr, size, tier):
        """Report a companion's placement to her ledger. Never raises."""
        if self._helix is None:
            return False
        try:
            return self._helix.mem_sync(ptr, size, tier)
        except OSError:
            return False

    def close(self):
        if self._helix is not None:
            self._helix.close()
            self._helix = None


if __name__ == "__main__":
    with HeIX() as helix:
        helix.register("attack-analyzer")
        helix.declare_hot(["attack_data", "session_data"])
        helix.declare_cold(["historical_patterns", "old_logs"])
        print("HeIX configured!", helix.stats())
        for line in helix.intents():
            print("  intent:", line)
