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


if __name__ == "__main__":
    with HeIX() as helix:
        helix.register("attack-analyzer")
        helix.declare_hot(["attack_data", "session_data"])
        helix.declare_cold(["historical_patterns", "old_logs"])
        print("HeIX configured!", helix.stats())
        for line in helix.intents():
            print("  intent:", line)
