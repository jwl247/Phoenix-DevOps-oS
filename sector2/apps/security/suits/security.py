"""security.py — Phoenix file motion sensor (from the metsec sketches, made real). Genie suit + CLI.
Phoenix DevOps OS | jwl247 | GPL v3

Defensive only: it watches, records, alerts and reports. It never touches another machine.

What it does on every scan:
  1. Walks the watched folders and takes METADATA only (size, mtime, mode, owner) — cheap.
  2. Compares with the last state: added / removed / modified / permissions-changed ("motion").
  3. Hashes only what moved (SHA3-512), in this process, after the walk.
  4. Appends each motion to a hash-chained log (every record carries the SHA3-512 of the one before,
     so an edited or deleted line breaks the chain — `verify` finds it).
  5. Flags ALERTS: permission/owner changes anywhere, and any change under an "alert" path
     (vault, sshd, nebula, the suits themselves).
  6. When the log passes the local cap it rolls into a numbered segment in outbox/ for shipping
     to Phoenix (intake on PBMII picks outbox/ up — nothing here talks to the network).
  7. `summary` asks local Ollama for a plain-English summary of recent motion (honest fallback).

Stage (Genie):  {"suit": "security", "action": "status" | "scan" | "events" | "alerts" | "summary" | "verify"}
CLI:            python security.py scan | status | events [N] | alerts [N] | summary | verify | baseline
                python security.py versions <path>                 every saved copy of one file
                python security.py restore <path> [live|master-...] [dest] [--force]   (default: beside it)
Config:         SECURITY_HOME (default ~/.phoenix/security) holds config.json, state.json, motion.jsonl, outbox/
                config.json: {"watch": [...], "alert": [...], "exclude": [...], "cap": 5000}
                Created with per-OS defaults on first run; edit it to change what's watched.
Env:            OLLAMA_HOST (default http://127.0.0.1:11434), SECURITY_MODEL (default llama3.2:3b)
Standard library only.
"""
import hashlib
import json
import os
import socket
import stat
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

NAME = "security"
VERSION = "security-1.2.0"
HOME = Path(os.environ.get("SECURITY_HOME", Path.home() / ".phoenix" / "security"))
IS_WIN = os.name == "nt"
GENESIS = "0" * 128
MAX_HASH_BYTES = 256 * 1024 * 1024        # bigger files: metadata only, noted as "hash_skipped"

def _fixed_drives() -> list:
    import ctypes, string
    mask = ctypes.windll.kernel32.GetLogicalDrives()
    return [f"{d}:\\" for i, d in enumerate(string.ascii_uppercase)
            if mask >> i & 1 and ctypes.windll.kernel32.GetDriveTypeW(f"{d}:\\") == 3]   # 3 = fixed disk


# "A motion camera in every directory" (Jerry, 2026-10-06): the whole filesystem is watched. Only
# places that change every second by design (kernel pseudo-files, logs, caches, temp, swap) are left
# out, or they would bury real motion. ALERT paths are the ones where any change matters.
DEFAULTS_WIN = {
    # The spots that actually matter on PBMII — NOT the whole game/ops drives. At D:/E:/F:+home it
    # was 1.34M files / 17-min scan, unusable on a 5-min timer (measured 2026-10-06). This set
    # sweeps in seconds and is what an attacker/tamper would touch.
    "watch": [r"F:\Phoenix\Vault", r"F:\Phoenix\Phoenix-DevOps-oS",
              str(Path.home() / ".ssh"), str(Path.home() / ".phoenix" / "genie" / "closet"),
              str(Path.home() / ".phoenix" / "security" / "bin"),
              r"C:\Windows\System32\drivers\etc",
              r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Startup",
              str(Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup")],
    "alert": [r"F:\Phoenix\Vault", str(Path.home() / ".ssh"), str(Path.home() / ".phoenix" / "genie" / "closet"),
              r"C:\Windows\System32\drivers\etc", r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Startup",
              str(Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup")],
    "exclude": ["$Recycle.Bin", "System Volume Information", "C:/Windows/Temp", "C:/Windows/Prefetch",
                "C:/Windows/Logs", "C:/Windows/SoftwareDistribution", "C:/Windows/ServiceProfiles",
                "C:/Windows/System32/LogFiles", "C:/Windows/System32/winevt", "C:/ProgramData/Microsoft/Windows Defender",
                "C:/ProgramData/Microsoft/Search", "C:/pagefile.sys", "C:/hiberfil.sys", "C:/swapfile.sys",
                "AppData/Local/Temp", "AppData/Local/Microsoft/Windows/INetCache", "AppData/Local/Packages",
                "Cache", "Code Cache", "GPUCache", "CacheStorage", "Service Worker"],
}
DEFAULTS_LINUX = {
    "watch": ["/"],
    "alert": ["/etc/ssh", "/etc/nebula", "/etc/sudoers", "/etc/sudoers.d", "/etc/passwd", "/etc/shadow",
              "/etc/group", "/etc/crontab", "/etc/cron.d", "/etc/systemd/system", "/etc/phoenix",
              "/usr/local/sbin", "/usr/local/bin", "/root/.ssh", "/opt/openjarvis/jarvis-gate", "/boot"],
    "exclude": ["/proc", "/sys", "/dev", "/run", "/tmp", "/var/tmp", "/var/log", "/var/cache", "/var/spool",
                "/var/lib/systemd", "/var/lib/ollama", "/var/lib/jarvis", "/var/lib/phoenix-security",
                "/var/lib/apt/lists", "/var/lib/samba", "/var/lib/sss", "/swapfile", "/lost+found"],
}
EXCLUDE = [".git", "node_modules", "__pycache__", ".cache", ".phoenix/security"]


# ---------------------------------------------------------------- config / files
def config() -> dict:
    HOME.mkdir(parents=True, exist_ok=True)
    p = HOME / "config.json"
    if not p.exists():
        base = DEFAULTS_WIN if IS_WIN else DEFAULTS_LINUX
        cfg = {"watch": base["watch"] or _fixed_drives(), "alert": base["alert"],
               "exclude": base["exclude"] + EXCLUDE, "cap": 5000}
        p.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    cfg = json.loads(p.read_text(encoding="utf-8"))
    cfg.setdefault("exclude", EXCLUDE)
    cfg.setdefault("cap", 5000)
    return cfg


def _excluded(path: str, excl: list) -> bool:
    norm = path.replace("\\", "/")
    for e in excl:
        e2 = e.replace("\\", "/")
        if e2.startswith("/"):
            if norm == e2 or norm.startswith(e2 + "/"):
                return True
        elif f"/{e2}/" in f"{norm}/":
            return True
    return False


F_SIZE, F_MTIME, F_MODE, F_UID, F_GID, F_LINK = range(6)   # compact state row (whole-disk scale)


def _meta(p: str) -> list | None:
    try:
        st = os.lstat(p)
    except OSError:
        return None
    return [st.st_size, int(st.st_mtime), stat.S_IMODE(st.st_mode),
            getattr(st, "st_uid", 0), getattr(st, "st_gid", 0), int(stat.S_ISLNK(st.st_mode))]


def _show(m: list) -> dict:
    return {"size": m[F_SIZE], "mode": oct(m[F_MODE]), "uid": m[F_UID], "gid": m[F_GID]}


def walk(cfg: dict) -> dict:
    """path -> metadata, for every file under every watched path (files may be watched directly)."""
    out = {}
    for root in cfg["watch"]:
        if not os.path.exists(root) or _excluded(root, cfg["exclude"]):
            continue
        if os.path.isfile(root) or os.path.islink(root):
            m = _meta(root)
            if m:
                out[root] = m
            continue
        for d, dirs, files in os.walk(root, onerror=lambda e: None):
            dirs[:] = [x for x in dirs if not _excluded(os.path.join(d, x), cfg["exclude"])]
            for f in files:
                p = os.path.join(d, f)
                if _excluded(p, cfg["exclude"]):
                    continue
                m = _meta(p)
                if m:
                    out[p] = m
    return out


def sha3(path: str, meta: list) -> str | None:
    if meta[F_LINK] or meta[F_SIZE] > MAX_HASH_BYTES:
        return None
    h = hashlib.sha3_512()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def is_alert(path: str, cfg: dict) -> bool:
    n = path.replace("\\", "/")
    return any(n == a.replace("\\", "/") or n.startswith(a.replace("\\", "/").rstrip("/") + "/")
               for a in cfg["alert"])


# ---------------------------------------------------------------- the chained log
def _last_hash(log: Path) -> str:
    if not log.exists() or log.stat().st_size == 0:
        seg = sorted((HOME / "outbox").glob("motion-*.jsonl")) if (HOME / "outbox").exists() else []
        if seg:
            return _last_hash(seg[-1])
        return GENESIS
    with log.open("rb") as f:
        f.seek(max(0, log.stat().st_size - 8192))
        last = f.read().splitlines()[-1]
    return json.loads(last)["hash"]


def append(records: list) -> None:
    log = HOME / "motion.jsonl"
    prev = _last_hash(log)
    with log.open("a", encoding="utf-8") as f:
        for r in records:
            r["prev"] = prev
            body = json.dumps(r, sort_keys=True)
            r["hash"] = hashlib.sha3_512(body.encode()).hexdigest()
            f.write(json.dumps(r, sort_keys=True) + "\n")
            prev = r["hash"]


def verify() -> dict:
    files = sorted((HOME / "outbox").glob("motion-*.jsonl")) if (HOME / "outbox").exists() else []
    files.append(HOME / "motion.jsonl")
    prev, n = GENESIS, 0
    for p in files:
        if not p.exists():
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            r = json.loads(line)
            h = r.pop("hash")
            if r.get("prev") != prev or hashlib.sha3_512(json.dumps(r, sort_keys=True).encode()).hexdigest() != h:
                return {"ok": False, "broken_at": f"{p.name}:{i}", "records_checked": n}
            prev, n = h, n + 1
    return {"ok": True, "records_checked": n}


def roll(cfg: dict) -> str | None:
    log = HOME / "motion.jsonl"
    if not log.exists():
        return None
    lines = sum(1 for _ in log.open("rb"))
    if lines < cfg["cap"]:
        return None
    out = HOME / "outbox"
    out.mkdir(exist_ok=True)
    seg = out / f"motion-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
    log.replace(seg)
    return seg.name


def tail(n: int, only_alerts=False) -> list:
    log = HOME / "motion.jsonl"
    if not log.exists():
        return []
    rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    if only_alerts:
        rows = [r for r in rows if r.get("alert")]
    return rows[-n:]


# ---------------------------------------------------------------- snapshots: emergency versioning
# Jerry, 2026-10-06: "rotate what gets snapshotted randomly and we use the snapshots as emergency
# versioning, rotating master shot".
#   - every file that MOVES gets a content copy at that moment
#   - every sweep also copies a RANDOM batch of unchanged files, so coverage of the whole disk builds
#     up over days with no big full copy
#   - once a day the current picture (path -> copy) is frozen as a MASTER; the newest N are kept
#     (default 4 = Phoenix's 4-day window); copies no master or the live picture needs are dropped
# Copies are content-addressed (SHA3-512, so duplicates cost nothing) and zlib level 5 (the Helix
# constant). Secret material (private keys, shadow, the vault's secrets) is fingerprinted, never copied.
import random
import zlib

SNAP_DEFAULTS = {"per_scan": 200, "bytes_per_scan_mb": 256, "max_file_mb": 64, "budget_gb": 5,
                 "masters": 4, "master_every_h": 24,
                 "never_copy": ["/etc/shadow", "/etc/gshadow", "/etc/ssh/ssh_host_", "/etc/nebula/host.key",
                                "/etc/nebula/ca.key", "Vault/secrets", "/.ssh/id_", "_ed25519", "_rsa", ".key",
                                ".pem", ".pfx", "vault.enc", ".smbpass"]}


def _snapcfg(cfg):
    sc = dict(SNAP_DEFAULTS, **cfg.get("snap", {}))
    sc["dir"] = Path(sc.get("dir") or HOME / "snap")
    return sc


def _never_copy(path, sc):
    n = path.replace("\\", "/")
    return any(x in n for x in sc["never_copy"])


def _obj(sc, h):
    return sc["dir"] / "objects" / h[:2] / (h + ".z")


def snapshot(path, meta, sc):
    """Read once: hash + (if allowed) store a compressed copy. -> (sha3 or None, bytes_read, copied)"""
    if meta[F_LINK] or meta[F_SIZE] > MAX_HASH_BYTES:
        return None, 0, False
    copy = meta[F_SIZE] <= sc["max_file_mb"] << 20 and not _never_copy(path, sc)
    try:
        with open(path, "rb") as f:
            if not copy:
                h = hashlib.sha3_512()
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
                return h.hexdigest(), meta[F_SIZE], False
            data = f.read()
    except OSError:
        return None, 0, False
    h = hashlib.sha3_512(data).hexdigest()
    o = _obj(sc, h)
    if not o.exists():
        o.parent.mkdir(parents=True, exist_ok=True)
        tmp = o.with_suffix(".tmp")
        tmp.write_bytes(zlib.compress(data, 5))
        tmp.replace(o)
    return h, len(data), True


def _load(p, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def snap_cycle(cfg, new, moved):
    """moved = {path: sha3} for files copied during this scan. Adds the random batch, rolls masters."""
    sc = _snapcfg(cfg)
    sc["dir"].mkdir(parents=True, exist_ok=True)
    live_f = sc["dir"] / "live.json"
    live = _load(live_f, {})                                   # path -> [sha3, size, mtime]
    for p in list(live):
        if p not in new:
            del live[p]                                        # gone from disk: masters still hold it
    for p, h in moved.items():
        live[p] = [h, new[p][F_SIZE], new[p][F_MTIME]]
    budget, copied = sc["bytes_per_scan_mb"] << 20, 0
    pool = [p for p, m in new.items() if not m[F_LINK] and m[F_SIZE] <= sc["max_file_mb"] << 20
            and not _never_copy(p, sc)
            and not (p in live and live[p][1:] == [m[F_SIZE], m[F_MTIME]])]
    for p in random.sample(pool, min(sc["per_scan"], len(pool))):
        if budget <= 0:
            break
        h, n, ok = snapshot(p, new[p], sc)
        if ok:
            live[p] = [h, new[p][F_SIZE], new[p][F_MTIME]]
            budget -= n
            copied += 1
    _save(live_f, live)
    mdir = sc["dir"] / "masters"
    mdir.mkdir(exist_ok=True)
    masters = sorted(mdir.glob("master-*.json"))
    made = None
    if not masters or time.time() - masters[-1].stat().st_mtime >= sc["master_every_h"] * 3600:
        made = mdir / ("master-" + time.strftime("%Y%m%d-%H%M%S") + ".json")
        _save(made, live)
        masters.append(made)
    dropped = []
    while len(masters) > sc["masters"]:
        dropped.append(masters.pop(0).name)
        (mdir / dropped[-1]).unlink()
    gc = _gc(sc, masters, live) if (made or dropped) else {}
    return {"random_copied": copied, "coverage": str(len(live)) + "/" + str(len(new)),
            "master_made": made.name if made else None, "masters_dropped": dropped, **gc}


def _gc(sc, masters, live):
    keep = {v[0] for v in live.values()}
    for m in masters:
        keep |= {v[0] for v in _load(m, {}).values()}
    removed = 0
    for o in (sc["dir"] / "objects").glob("*/*.z"):
        if o.stem not in keep:
            o.unlink()
            removed += 1
    size = sum(o.stat().st_size for o in (sc["dir"] / "objects").glob("*/*.z"))
    over = size > sc["budget_gb"] << 30
    while over and len(masters) > 1:                           # over budget: oldest master goes first
        masters.pop(0).unlink()
        return {**_gc(sc, masters, live), "budget_dropped_master": True}
    return {"objects_removed": removed, "store_mb": round(size / 1048576, 1), "over_budget": over}


def versions(path):
    sc = _snapcfg(config())
    out = []
    live = _load(sc["dir"] / "live.json", {})
    if path in live:
        out.append({"shot": "live", "sha3": live[path][0][:16], "size": live[path][1],
                    "mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(live[path][2]))})
    for m in sorted((sc["dir"] / "masters").glob("master-*.json"), reverse=True):
        v = _load(m, {}).get(path)
        if v:
            out.append({"shot": m.stem, "sha3": v[0][:16], "size": v[1],
                        "mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(v[2]))})
    return {"path": path, "versions": out}


def restore(path, shot="live", dest=None, force=False):
    """Write a saved copy back out. Default destination is beside the file, never over it."""
    sc = _snapcfg(config())
    src = sc["dir"] / "live.json" if shot == "live" else sc["dir"] / "masters" / (shot + ".json")
    v = _load(src, {}).get(path)
    if not v:
        return {"ok": False, "error": "no copy of " + path + " in " + shot}
    o = _obj(sc, v[0])
    if not o.exists():
        return {"ok": False, "error": "copy missing from the store"}
    data = zlib.decompress(o.read_bytes())
    if hashlib.sha3_512(data).hexdigest() != v[0]:
        return {"ok": False, "error": "SHA3-512 mismatch: the stored copy is damaged, not restored"}
    dest = dest or (path + ".restored-" + time.strftime("%Y%m%d-%H%M%S"))
    if os.path.exists(dest) and not force:
        return {"ok": False, "error": dest + " exists (use --force to overwrite)"}
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    Path(dest).write_bytes(data)
    return {"ok": True, "restored": dest, "from": shot, "sha3": v[0][:16], "bytes": len(data)}


# ---------------------------------------------------------------- scan
def _save(statef: Path, state: dict) -> None:
    tmp = statef.with_suffix(".tmp")                            # never leave a half-written state
    tmp.write_text(json.dumps(state, separators=(",", ":")), encoding="utf-8")
    tmp.replace(statef)


PAUSE_FILE = HOME / "paused"


def set_paused(on: bool, who: str = "") -> dict:
    """Off-switch. Honoured by scan(); the timer keeps firing but does nothing while paused.
    Writing/removing the file needs write access to the state dir (root on Linux, you on Windows)."""
    if on:
        HOME.mkdir(parents=True, exist_ok=True)
        PAUSE_FILE.write_text(json.dumps({"at": int(time.time()), "by": who or socket.gethostname()}),
                              encoding="utf-8")
        return {"paused": True, "by": who or socket.gethostname()}
    PAUSE_FILE.unlink(missing_ok=True)
    return {"paused": False}


def is_paused() -> dict | None:
    try:
        return json.loads(PAUSE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def scan(baseline_only=False) -> dict:
    p = is_paused()
    if p and not baseline_only:
        return {"paused": True, "since": p.get("at"), "by": p.get("by"), "note": "security scan is OFF — `security on` to resume"}
    cfg = config()
    t0 = time.time()
    statef = HOME / "state.json"
    old = json.loads(statef.read_text(encoding="utf-8")) if statef.exists() else None
    if old and isinstance(next(iter(old.values())), dict):      # 1.0.0 state: re-baseline once
        old = None
    new = walk(cfg)
    host = socket.gethostname()
    if old is None or baseline_only:
        _save(statef, new)
        append([{"t": int(time.time()), "host": host, "type": "baseline", "files": len(new), "alert": False}])
        return {"baseline": True, "files": len(new), "ms": int((time.time() - t0) * 1000)}
    motion = []
    for p in new.keys() - old.keys():
        motion.append(("added", p, None, new[p]))
    for p in old.keys() - new.keys():
        motion.append(("removed", p, old[p], None))
    for p in new.keys() & old.keys():
        a, b = old[p], new[p]
        if a[F_MODE:F_GID + 1] != b[F_MODE:F_GID + 1]:
            motion.append(("permissions_changed", p, a, b))
        elif a[F_SIZE:F_MTIME + 1] != b[F_SIZE:F_MTIME + 1]:
            motion.append(("modified", p, a, b))
    recs, moved, sc = [], {}, _snapcfg(cfg)
    for kind, p, a, b in sorted(motion, key=lambda m: m[1]):
        r = {"t": int(time.time()), "host": host, "type": kind, "path": p,
             "alert": kind == "permissions_changed" or is_alert(p, cfg)}
        if a:
            r["was"] = _show(a)
        if b:
            r["now"] = _show(b)
            h, _, copied = snapshot(p, b, sc)                 # one read: fingerprint + emergency copy
            r["sha3"] = h if h else "hash_skipped"
            if copied:
                moved[p] = h
                r["copied"] = True
        recs.append(r)
    if recs:
        append(recs)
    _save(statef, new)
    seg = roll(cfg)
    snap = snap_cycle(cfg, new, moved) if cfg.get("snap", {}).get("enabled", True) else {"enabled": False}
    alerts = [r for r in recs if r["alert"]]
    (HOME / "last_scan.json").write_text(json.dumps({"t": int(time.time()), "files": len(new),
                                                     "motion": len(recs), "alerts": len(alerts)}),
                                         encoding="utf-8")
    return {"files": len(new), "motion": len(recs), "alerts": len(alerts),
            "alert_paths": [f'{r["type"]}: {r["path"]}' for r in alerts][:20],
            "rolled": seg, "snap": snap, "ms": int((time.time() - t0) * 1000)}


def status() -> dict:
    cfg = config()
    last = HOME / "last_scan.json"
    out = {"version": VERSION, "host": socket.gethostname(), "home": str(HOME),
           "watch": cfg["watch"], "last_scan": json.loads(last.read_text()) if last.exists() else None,
           "chain": verify(),
           "outbox_segments": len(list((HOME / "outbox").glob("motion-*.jsonl"))) if (HOME / "outbox").exists() else 0}
    out["healthy"] = out["chain"]["ok"] and out["last_scan"] is not None and \
        time.time() - out["last_scan"]["t"] < 3600
    return out


def summary() -> dict:
    rows = tail(200)
    if not rows:
        return {"ai": False, "summary": "No motion recorded yet."}
    lines = [f'{r.get("type")} {r.get("path", "")}{" ALERT" if r.get("alert") else ""}' for r in rows]
    prompt = ("You are a security log reader. Summarize these file-change events from one machine in "
              "5 short bullet points for the owner: what changed, anything that looks risky, and what to "
              "check. Do not invent anything that is not in the list.\n\n" + "\n".join(lines[-150:]))
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    body = json.dumps({"model": os.environ.get("SECURITY_MODEL", "llama3.2:3b"), "prompt": prompt,
                       "stream": False}).encode()
    try:
        req = urllib.request.Request(host + "/api/generate", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=90) as r:
            return {"ai": True, "summary": json.loads(r.read())["response"]}
    except (urllib.error.URLError, OSError, KeyError, ValueError) as e:
        alerts = [l for l in lines if l.endswith("ALERT")]
        return {"ai": False, "summary": f"Ollama not available ({e}). Last {len(rows)} events, "
                                        f"{len(alerts)} alerts: " + "; ".join(alerts[-10:] or lines[-10:])}


# ---------------------------------------------------------------- suit + CLI
ACTIONS = {"status": lambda m: status(), "scan": lambda m: scan(),
           "events": lambda m: {"events": tail(int(m.get("n", 20)))},
           "alerts": lambda m: {"alerts": tail(int(m.get("n", 20)), only_alerts=True)},
           "summary": lambda m: summary(), "verify": lambda m: verify(),
           "versions": lambda m: versions(m["path"]),
           "off": lambda m: set_paused(True, m.get("by", "")), "on": lambda m: set_paused(False),
           "paused": lambda m: {"paused": bool(is_paused()), **(is_paused() or {})}}


def run(data, ball=None, pcs=None, **_):
    try:
        msg = json.loads(data)
    except (ValueError, TypeError):
        return json.dumps({"ok": False, "suit": NAME, "error": "stage is not JSON"})
    if not isinstance(msg, dict):
        return json.dumps({"ok": False, "suit": NAME, "error": "stage must be a JSON object"})
    action = msg.get("action", "status")
    if action not in ACTIONS:
        return json.dumps({"ok": False, "suit": NAME, "error": f"action must be one of {sorted(ACTIONS)}"})
    try:
        return json.dumps({"ok": True, "suit": NAME, "action": action, **ACTIONS[action](msg)})
    except Exception as e:                                   # a suit never raises
        return json.dumps({"ok": False, "suit": NAME, "error": f"{type(e).__name__}: {e}"})


def main(argv) -> int:
    cmd = argv[1] if len(argv) > 1 else "status"
    if cmd == "versions" and len(argv) > 2:
        print(json.dumps(versions(argv[2]), indent=2)); return 0
    if cmd == "restore" and len(argv) > 2:                    # restore <path> [shot] [dest] [--force]
        rest = [a for a in argv[3:] if a != "--force"]
        out = restore(argv[2], rest[0] if rest else "live", rest[1] if len(rest) > 1 else None, "--force" in argv)
        print(json.dumps(out, indent=2)); return 0 if out["ok"] else 5
    if cmd == "baseline":
        print(json.dumps(scan(baseline_only=True), indent=2)); return 0
    if cmd in ACTIONS:
        n = {"n": int(argv[2])} if len(argv) > 2 and argv[2].isdigit() else {}
        out = ACTIONS[cmd](n)
        print(json.dumps(out, indent=2))
        if cmd == "scan":
            return 3 if out.get("alerts") else 0
        if cmd == "verify":
            return 0 if out["ok"] else 4
        return 0
    if cmd.startswith("{"):                                   # test as a suit: python security.py '{"action":"status"}'
        print(run(cmd)); return 0
    print(__doc__); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
