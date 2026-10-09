#!/usr/bin/env python3
"""
genie_control.py — the Genie control socket for the Phoenix Universal Kernel.
Phoenix DevOps OS | jwl247 | GPL v3

Lets PS7 (genie.ps1) talk to the RUNNING kernel: see the live closet and
hot-load a cloned suit into it — no restart.

Started by main_kernel.boot() after the closet, spawner and Helix are up.

Security model (this endpoint can make the kernel execute code — a Python
suit's module is executed when it is registered — so it is locked down):
  * Binds 127.0.0.1 only. Never 0.0.0.0, no env override for the address.
  * Per-boot random token, written to <genie home>/control.token (owner-only
    on POSIX; on Windows it sits in the user's profile, which is per-user).
    Every request must carry it in X-Genie-Token; compared constant-time.
  * Any request with an Origin header is refused — browsers always send one
    on cross-origin fetches, so a web page can never drive this socket.
  * A suit can only be loaded from the Genie closet (<genie home>/closet),
    resolved through symlinks. Nothing else on disk is reachable.
  * The caller must supply the SHA3-512 that genie.ps1 checked against D1
    custody; the kernel re-hashes the file itself and refuses on mismatch.
  * Imported suits get least privilege: read only, plus write if asked.
    Never clone/translate/delete/kernel.
  * Core/system suits cannot be replaced — only suits Genie itself imported.

Imported suits persist in <genie home>/imports.json and are re-loaded at the
next boot, re-verified against the recorded SHA3-512 first. A suit whose
file changed or vanished is skipped and logged, never run.

Endpoints (JSON):
  GET  /health                 {"ok": true}            (token still required)
  GET  /kernel                 live library/Helix-I/Helix-E/Frank status
  GET  /closet                 every suit in the closet
  POST /suits                  hot-load {"file","sha3_512",...} from the closet
"""

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sys
import threading
import time
import types
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

log = logging.getLogger("genie_control")

GENIE_HOME   = Path(os.environ.get("PHOENIX_GENIE_HOME", Path.home() / ".phoenix" / "genie"))
CLOSET_DIR   = GENIE_HOME / "closet"
TOKEN_PATH   = GENIE_HOME / "control.token"
IMPORTS_PATH = GENIE_HOME / "imports.json"
CONTROL_PORT = int(os.environ.get("PHOENIX_GENIE_PORT", "8766"))
BIND_ADDR    = "127.0.0.1"          # deliberately not configurable
MAX_BODY     = 16 * 1024
NAME_RE      = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
SHA3_RE      = re.compile(r"^[0-9a-fA-F]{128}$")
GENIE_TAG    = "genie"
AUTO_RING_BASE = 100                # imported suits live above the 16 core rings
HEX_RE       = re.compile(r"^[0-9a-fA-F]{2,1024}$")   # folder/name identities make long hexes (2026-10-08)
MEM_MODPREFIX = "genie_mem_"        # in-RAM suit modules live in sys.modules under this prefix
# The wall (Jerry 2026-10-09): only SYSTEM suits run inside the kernel. A suit is system only when
# its header says so (suit_build.py stamps it inside the hashed bytes) AND its exact SHA3 is on the
# system list, which only the terminal "type SYSTEM" gate writes. A header alone never counts.
SYSTEM_LIST_PATH = GENIE_HOME / "system_suits.json"
SUIT_HEADER = re.compile(rb"^# phoenix-suit: name=\S+ class=(entertainment|system)\b")


def _suit_class(data: bytes) -> str:
    m = SUIT_HEADER.match(data[:400])
    return m.group(1).decode() if m else "entertainment"


def _system_listed(sha3: str) -> bool:
    try:
        return sha3.lower() in json.loads(SYSTEM_LIST_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False


# The heal stage (Jerry 2026-10-09: "hotswap would be included in the healing tool box"). Every
# version of a suit is kept in R2 under <hex>/versions/<sha3[:16]> (write-once) and listed in D1's
# `versions` ledger, so a heal always fetches bytes BY THE HASH IT WANTS and checks them first:
#   * R2's current copy does not match custody -> load custody's own version copy, put it back as
#     current. No good copy -> refused, as before.
#   * a version that answers ok:false FAIL_LIMIT times in a row -> swap back to the last version
#     that answered ok (known_good.json), pinned so a reboot does not bring the bad one back. The
#     pinned SHA3 must be in the D1 ledger for that suit. A person's own `lol import` clears the pin.
KNOWN_GOOD_PATH = GENIE_HOME / "known_good.json"
FAIL_LIMIT = 3


def _r2_version(hex_id: str, sha3: str) -> bytes:
    """The bytes of one exact version, by its SHA3 (raises unless they hash to it)."""
    url = f"{_worker_base()}/clonepool/{urllib.parse.quote(hex_id)}/versions/{sha3[:16]}"
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(urllib.request.Request(url, headers=_worker_headers()), timeout=30) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        raise ValueError(f"no version copy {sha3[:16]} in R2 (HTTP {e.code})")
    if not hmac.compare_digest(hashlib.sha3_512(data).hexdigest(), sha3.lower()):
        raise ValueError(f"version copy {sha3[:16]} does not hash to its own name")
    return data


def _r2_put_current(hex_id: str, data: bytes, sha3: str) -> None:
    req = urllib.request.Request(f"{_worker_base()}/clonepool/{urllib.parse.quote(hex_id)}", data=data, method="PUT",
                                 headers=dict(_worker_headers(), **{"X-Phoenix-SHA3": sha3,
                                                                    "Content-Type": "application/octet-stream"}))
    with urllib.request.build_opener(_NoRedirect()).open(req, timeout=30) as r:
        r.read()


def _ledger_version(pool_name: str, sha3: str) -> str:
    """The version label D1's ledger has for this exact SHA3 of this suit ('' = not in the ledger)."""
    rows = _worker_json(f"{_worker_base()}/versions?package={urllib.parse.quote(pool_name)}&limit=500").get("versions") or []
    for r in rows:
        if str(r.get("hash_sha3", "")).lower() == sha3.lower():
            return str(r.get("version") or "?")
    return ""


def _playbox_class():
    import importlib.util
    spec = importlib.util.spec_from_file_location("phoenix_playbox", Path(__file__).with_name("playbox.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.PlayBox


def _sha3_512_file(path: Path) -> str:
    h = hashlib.sha3_512()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _worker_headers() -> dict:
    """The same auth genie.ps1/intake use: Bearer PHOENIX_AUTH + CF Access service token."""
    auth = os.environ.get("PHOENIX_AUTH")
    if not auth:
        raise ValueError("kernel has no PHOENIX_AUTH — it cannot reach R2 to pull a suit")
    h = {"Authorization": f"Bearer {auth}", "User-Agent": "phoenix-genie-kernel"}
    cid, csec = os.environ.get("CF_ACCESS_CLIENT_ID"), os.environ.get("CF_ACCESS_CLIENT_SECRET")
    if cid and csec:
        h["CF-Access-Client-Id"] = cid
        h["CF-Access-Client-Secret"] = csec
    return h


def _worker_base() -> str:
    return os.environ.get("PHOENIX_WORKER_URL", "https://packages-worker.phoenix-jwl.workers.dev").rstrip("/")


def _r2_pull(hex_id: str) -> tuple:
    """Pull a clonepool object's BYTES from R2 (via the worker). Never writes to disk.
    Returns (raw_bytes, content_type). A redirect or an HTML/JSON body = no real bytes (worker
    fell back to the D1 catalog) — treated as a hard failure, the same trap intake.py hit."""
    url = f"{_worker_base()}/clonepool/{urllib.parse.quote(hex_id)}"
    req = urllib.request.Request(url, headers=_worker_headers())
    opener = urllib.request.build_opener(_NoRedirect())
    with opener.open(req, timeout=30) as r:
        ctype = r.headers.get("Content-Type", "")
        if "octet-stream" not in ctype:
            raise ValueError(f"no bytes in R2 for {hex_id} (worker returned {ctype or 'no type'} — re-intake it)")
        return r.read(), ctype


def _worker_json(url: str) -> dict:
    """GET a worker JSON route and say plainly why it failed (2026-10-08: a 404 or an Access
    login page used to come back as 'HTTP 500: HTTPError...' or 'Expecting value')."""
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(urllib.request.Request(url, headers=_worker_headers()), timeout=20) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise ValueError("packages-worker said 401: the kernel's PHOENIX_AUTH is stale - restart it (usys stop, usys start)")
        if e.code in (301, 302, 303, 307, 308, 403):
            raise ValueError("Cloudflare Access refused the kernel: CF_ACCESS_* missing or stale - restart it (usys stop, usys start)")
        if e.code == 404:
            raise ValueError("not in the clonepool")
        raise ValueError(f"packages-worker answered HTTP {e.code}")
    try:
        return json.loads(body)
    except ValueError:
        raise ValueError("packages-worker sent something that isn't JSON (a Cloudflare Access page?)")


def _r2_meta(ref: str) -> dict:
    """Resolve a name-or-hex to its clonepool row (hex_id + hash_sha3 + name + version). Metadata only."""
    if HEX_RE.match(ref) and len(ref) % 2 == 0:
        try:
            return _worker_json(f"{_worker_base()}/clonepool/{urllib.parse.quote(ref)}?meta=true")
        except ValueError as e:
            if "not in the clonepool" not in str(e) or len(ref) > 48:   # a short hex-looking NAME falls through to search
                raise
    # a bare name: search, require exactly one hit (D1 LIKE refuses patterns over 50 bytes)
    if len(ref.encode()) > 48:
        raise ValueError(f"'{ref[:40]}...' is too long to search by name - import it by its pool id (hex)")
    found = _worker_json(f"{_worker_base()}/search?q={urllib.parse.quote(ref)}")
    hits = [x for x in (found.get("clonepool") or []) if x.get("name") == ref or x.get("hex_id") == ref]
    if len(hits) != 1:
        raise ValueError(f"'{ref}' matched {len(hits)} clonepool rows — import by hex_id" if hits
                         else f"'{ref}' is not in the clonepool")
    return _r2_meta(hits[0]["hex_id"])


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):            # a login redirect is a failure, not a 200
        return None


def _write_private(path: Path, data: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(data)
    os.replace(tmp, path)


class GenieControl:
    def __init__(self, library, frank=None, spawner=None, helix_i=None, helix_e=None,
                 helix=None, pager=None):
        self.library  = library
        self.frank    = frank
        self.spawner  = spawner
        self.helix_i  = helix_i
        self.helix_e  = helix_e
        self.helix    = helix
        self.pager    = pager
        self.token    = secrets.token_hex(32)
        self.started  = time.time()
        self._lock    = threading.Lock()
        self._imports = self._read_imports()
        self._server: Optional[ThreadingHTTPServer] = None
        self.playbox  = None                      # started the first time an entertainment suit loads

    def _playbox(self):
        if self.playbox is None:
            self.playbox = _playbox_class()()
        return self.playbox

    # ── persistence ──────────────────────────────────────────────────────────
    def _read_imports(self) -> dict:
        try:
            data = json.loads(IMPORTS_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            return {}
        except Exception as e:
            log.error("imports.json unreadable (%s) — starting with none", e)
            return {}

    def _save_imports(self):
        _write_private(IMPORTS_PATH, json.dumps(self._imports, indent=2))

    # ── the one write operation ──────────────────────────────────────────────
    def load_suit(self, req: dict, persist: bool = True) -> dict:
        from frank_ring import SuitSpec, SuitType

        file_name = str(req.get("file", ""))
        if not NAME_RE.match(file_name):
            raise ValueError("file must be a plain file name inside the closet")
        path = (CLOSET_DIR / file_name).resolve()
        closet = CLOSET_DIR.resolve()
        if path.parent != closet:
            raise ValueError("file is outside the Genie closet")
        if not path.is_file():
            raise ValueError(f"{file_name} is not in the closet — genie clone it first")

        want = str(req.get("sha3_512", ""))
        if not SHA3_RE.match(want):
            raise ValueError("sha3_512 (128 hex chars) is required")
        got = _sha3_512_file(path)
        if not hmac.compare_digest(got.lower(), want.lower()):
            raise ValueError("SHA3-512 mismatch: the closet file is not the bytes custody verified — refusing")

        name = str(req.get("name") or Path(file_name).stem)
        if not NAME_RE.match(name):
            raise ValueError("invalid suit name")

        type_name = str(req.get("suit_type", "")).upper()
        if not type_name:
            type_name = {".py": "PYTHON", ".sh": "SHELL", ".js": "NODE",
                         ".mjs": "NODE", ".ps1": "POWER"}.get(path.suffix.lower(), "BINARY")
        if type_name not in SuitType.__members__:
            raise ValueError(f"suit_type must be one of {', '.join(SuitType.__members__)}")

        sector = int(req.get("sector", 2))
        if sector not in (1, 2, 3, 4):
            raise ValueError("sector must be 1-4")

        family = str(req.get("family", "user")).lower()
        if family not in ("physics", "network", "ai", "assets", "system", "user"):
            raise ValueError("family must be physics|network|ai|assets|system|user")

        with self._lock:
            existing = self.library._suits.get(name)
            if existing is not None and GENIE_TAG not in existing.tags:
                raise ValueError(f"'{name}' is a core/system suit — Genie will not replace it")

            ring_pos = req.get("ring_pos")
            if ring_pos is None:
                if name in self._imports:
                    ring_pos = self._imports[name]["ring_pos"]
                else:
                    used = {e.spec.ring_pos for e in self.library._suits.values() if e.spec.sector == sector}
                    ring_pos = AUTO_RING_BASE
                    while ring_pos in used:
                        ring_pos += 1
            ring_pos = int(ring_pos)
            if ring_pos < AUTO_RING_BASE:
                raise ValueError(f"ring_pos below {AUTO_RING_BASE} is reserved for core rings")

            spec = SuitSpec(
                name        = name,
                suit_type   = SuitType[type_name],
                entry       = str(path),
                sector      = sector,
                ring_pos    = ring_pos,
                family      = family,
                description = str(req.get("description", ""))[:200] or f"imported by Genie from {file_name}",
                permissions = {"read": True, "write": bool(req.get("write", False)),
                               "clone": False, "translate": False, "delete": False, "kernel": False},
            )
            entry = self.library.register(spec, tags=[GENIE_TAG, "imported"])

            if persist:
                self._imports[name] = {
                    "file": file_name, "sha3_512": got, "suit_type": type_name,
                    "sector": sector, "ring_pos": ring_pos, "family": family,
                    "write": bool(req.get("write", False)), "description": spec.description,
                    "imported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
                self._save_imports()

        result = {
            "ok": True, "name": name, "sector": sector, "ring_pos": ring_pos,
            "suit_type": type_name, "family": family,
            "preloaded": entry._mod is not None, "checksum": entry.checksum,
            "suits_in_closet": len(self.library),
        }
        log.info("Genie loaded suit %s [%s] s%d r%d preloaded=%s",
                 name, type_name, sector, ring_pos, result["preloaded"])
        return result

    # ── in-RAM load: bytes come from R2, get verified, and run from memory ─────
    # The point of the exercise (Jerry, 2026-10-06): the suit's bytes NEVER hit
    # disk. The kernel pulls them from R2, checks their SHA3-512 against D1
    # custody in memory, execs the module into sys.modules, and registers it with
    # its `entry` set to that module NAME — so when a stage lands, _run_python's
    # importlib.import_module(entry) finds it already in sys.modules and runs it
    # from RAM. Nothing is ever written to the closet.
    def load_suit_memory(self, req: dict, persist: bool = True) -> dict:
        from frank_ring import SuitSpec, SuitType

        ref = str(req.get("hex") or req.get("name") or "")
        if not ref:
            raise ValueError("hex (or name) of the clonepool suit is required")
        row = _r2_meta(ref)
        hex_id = str(row["hex_id"])
        custody = (str(row.get("hash_sha3") or "")).lower()
        if not SHA3_RE.match(custody):
            raise ValueError(f"{row.get('name', ref)}: D1 has no SHA3 baseline — refusing to run unverified bytes")
        want = str(req.get("sha3_512", "")).lower()
        if want and not hmac.compare_digest(want, custody):
            raise ValueError("the SHA3-512 you passed does not match D1 custody — refusing")

        healed = ""
        pin = str(req.get("pin_sha3", "")).lower()
        if pin:
            # a swap-back pin: that exact version, only if D1's ledger has it for this suit
            if not SHA3_RE.match(pin):
                raise ValueError("pinned SHA3-512 is malformed — refusing")
            label = _ledger_version(str(row.get("name") or ref), pin)
            if not label:
                raise ValueError(f"pinned version {pin[:16]} is not in the D1 ledger for {row.get('name', ref)} — refusing")
            data = _r2_version(hex_id, pin)
            custody = pin
            healed = f"pinned to known-good {label} (swapped back)"
        else:
            data, _ = _r2_pull(hex_id)                              # bytes, in memory only
            got = hashlib.sha3_512(data).hexdigest()
            if not hmac.compare_digest(got.lower(), custody):
                # HEAL: R2's current copy is not what custody says. Custody's own version copy is
                # write-once and named by its hash; if it checks out, run it and put it back.
                try:
                    data = _r2_version(hex_id, custody)
                except ValueError as e:
                    raise ValueError(f"SHA3-512 mismatch: R2 bytes do not match D1 custody, and no good copy to heal from ({e}) — not loaded")
                try:
                    _r2_put_current(hex_id, data, custody)
                    healed = "R2 current copy did not match custody: restored from its version copy"
                except (OSError, ValueError) as e:
                    healed = f"R2 current copy did not match custody: ran the version copy, but R2 not repaired ({e})"
                log.warning("HEAL %s: %s", row.get("name", ref), healed)

        name = str(req.get("name") or row.get("name") or "").removesuffix(".py")
        if not NAME_RE.match(name):
            raise ValueError("invalid suit name")

        type_name = str(req.get("suit_type", "")).upper() or \
            {".py": "PYTHON", ".sh": "SHELL", ".js": "NODE", ".mjs": "NODE", ".ps1": "POWER"}.get(
                Path(str(row.get("name", ""))).suffix.lower(), "PYTHON")
        if type_name != "PYTHON":
            raise ValueError("in-RAM import is Python-only (a shell/binary suit must exist as a file)")

        sector = int(req.get("sector", 2))
        if sector not in (1, 2, 3, 4):
            raise ValueError("sector must be 1-4")
        family = str(req.get("family", "user")).lower()
        if family not in ("physics", "network", "ai", "assets", "system", "user"):
            raise ValueError("family must be physics|network|ai|assets|system|user")

        with self._lock:
            existing = self.library._suits.get(name)
            if existing is not None and GENIE_TAG not in existing.tags:
                raise ValueError(f"'{name}' is a core/system suit — Genie will not replace it")

            # a fresh module, parked in sys.modules under a unique name. SYSTEM suits are exec'd
            # here, in the kernel; every other suit is exec'd in the play box and this module is
            # only its doorway (a crash, hang or memory blow-up there never reaches the kernel).
            modname = MEM_MODPREFIX + name
            mod = types.ModuleType(modname)
            mod.__file__ = f"<genie-memory:{name}@{hex_id}>"
            in_kernel = _suit_class(data) == "system" and _system_listed(custody)
            if in_kernel:
                try:
                    exec(compile(data, mod.__file__, "exec"), mod.__dict__)
                except Exception as e:
                    raise ValueError(f"suit failed to load in memory: {type(e).__name__}: {e}")
                if not hasattr(mod, "run"):
                    raise ValueError(f"{name}: no run(data, ...) — not a suit")
            else:
                box = self._playbox()
                box.load(name, data)                  # ValueError if it won't load there

                def _run(data, ball=None, pcs=None, _suit=name, **_):
                    return box.run(_suit, data)
                mod.run = _run
            mod.PHOENIX_WHERE = "kernel" if in_kernel else "playbox"
            mod.PHOENIX_SHA3 = custody
            self._watch(mod, name, hex_id, custody, dict(req, name=name))
            sys.modules[modname] = mod

            ring_pos = req.get("ring_pos")
            if ring_pos is None:
                ring_pos = self._imports.get(name, {}).get("ring_pos")
            if ring_pos is None:
                used = {e.spec.ring_pos for e in self.library._suits.values() if e.spec.sector == sector}
                ring_pos = AUTO_RING_BASE
                while ring_pos in used:
                    ring_pos += 1
            ring_pos = int(ring_pos)

            spec = SuitSpec(
                name=name, suit_type=SuitType.PYTHON, entry=modname,   # entry = module NAME, not a path
                sector=sector, ring_pos=ring_pos, family=family,
                description=str(req.get("description", ""))[:200] or f"imported in-RAM from R2 {hex_id}",
                permissions={"read": True, "write": bool(req.get("write", False)),
                             "clone": False, "translate": False, "delete": False, "kernel": False},
            )
            entry = self.library.register(spec, tags=[GENIE_TAG, "imported", "memory"])
            entry._mod = mod                                          # already live; closet shows it preloaded

            if persist:
                self._imports[name] = {
                    "kind": "memory", "hex": hex_id, "sha3_512": custody, "suit_type": "PYTHON",
                    "sector": sector, "ring_pos": ring_pos, "family": family,
                    "write": bool(req.get("write", False)), "description": spec.description,
                    "imported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
                if pin:                                   # a swap-back stays swapped back across reboots
                    self._imports[name]["pin_sha3"] = pin
                    self._imports[name].pop("sha3_512", None)
                self._save_imports()

        log.info("Genie loaded suit %s [PYTHON] s%d r%d IN-RAM in the %s (hex %s, %d bytes, nothing on disk)",
                 name, sector, ring_pos, "KERNEL (system)" if in_kernel else "play box", hex_id, len(data))
        return {"ok": True, "name": name, "sector": sector, "ring_pos": ring_pos, "suit_type": "PYTHON",
                "family": family, "preloaded": True, "in_ram": True, "hex": hex_id, "bytes": len(data),
                "where": mod.PHOENIX_WHERE, **({"healed": healed} if healed else {}),
                "suits_in_closet": len(self.library)}

    def _known_good(self) -> dict:
        try:
            return json.loads(KNOWN_GOOD_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _watch(self, mod, name, hex_id, sha3, req):
        """Wrap run(): an ok answer marks this version known-good; FAIL_LIMIT failures in a row on a
        version that is not the known-good one swap the suit back to it."""
        inner = mod.run
        state = {"fails": 0}

        def run(data, ball=None, pcs=None, **kw):
            out = inner(data, ball=ball, pcs=pcs, **kw)
            try:
                ok = json.loads(out if isinstance(out, str) else out.decode("utf-8", "replace")).get("ok")
            except (ValueError, AttributeError):
                return out                                   # not a JSON answer: nothing to judge
            if ok is True:
                state["fails"] = 0
                good = self._known_good()
                if good.get(name, {}).get("sha3") != sha3:
                    good[name] = {"sha3": sha3, "hex": hex_id, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
                    _write_private(KNOWN_GOOD_PATH, json.dumps(good, indent=2))
            elif ok is False:
                state["fails"] += 1
                good = self._known_good().get(name, {}).get("sha3", "")
                if state["fails"] >= FAIL_LIMIT and good and good != sha3:
                    state["fails"] = 0
                    threading.Thread(target=self._swap_back, args=(name, good, req), daemon=True).start()
            return out
        mod.run = run

    def _swap_back(self, name, good_sha3, req):
        try:
            rec = dict(self._imports.get(name) or req)
            rec.update(name=name, pin_sha3=good_sha3)
            rec.pop("sha3_512", None)
            r = self.load_suit_memory(rec, persist=True)
            log.warning("HEAL %s: failed %d times in a row - SWAPPED BACK to known-good %s (%s)",
                        name, FAIL_LIMIT, good_sha3[:16], r.get("healed", ""))
        except Exception as e:                               # never take the kernel down healing a suit
            log.error("HEAL %s: swap back to %s FAILED: %s", name, good_sha3[:16], e)

    def reload_persisted(self):
        loaded = 0
        for name, rec in list(self._imports.items()):
            try:
                if rec.get("kind") == "memory":
                    self.load_suit_memory(dict(rec, name=name), persist=False)
                else:
                    self.load_suit(dict(rec, name=name), persist=False)
                loaded += 1
            except Exception as e:
                log.error("Genie import %s NOT reloaded: %s", name, e)
        if self._imports:
            log.info("Genie re-loaded %d/%d imported suits", loaded, len(self._imports))

    # ── read views ───────────────────────────────────────────────────────────
    def kernel_view(self) -> dict:
        def safe(obj):
            try:
                return obj.status() if obj is not None else None
            except Exception as e:
                return {"error": str(e)}
        lib = safe(self.library) or {}
        return {
            "kernel":   "operational",
            "pid":      os.getpid(),
            "python":   sys.version.split()[0],
            "uptime_s": round(time.time() - self.started, 1),
            "library":  {"version": lib.get("version"), "loaded": lib.get("loaded"),
                         "suit_count": lib.get("suit_count"),
                         "imported": sorted(n for n in self._imports
                                            if n in self.library._suits and GENIE_TAG in self.library._suits[n].tags),
                         "refused":  sorted(n for n in self._imports
                                            if not (n in self.library._suits and GENIE_TAG in self.library._suits[n].tags))},
            "frank":    safe(self.frank),
            "helix_i":  safe(self.helix_i),
            "helix_e":  safe(self.helix_e),
            "helix":    self._helix_view(),
            "paging":   safe(self.pager),
        }

    def _helix_view(self):
        if self.helix is None:
            return None
        try:
            st = self.helix.get_stats()
        except Exception as e:
            return {"error": str(e)}
        keep = ("total_blocks", "hot_blocks", "warm_blocks", "cold_blocks", "rungs",
                "hot_usage_mb", "warm_usage_mb", "cold_usage_mb", "raw_budget_mb", "z_budget_mb",
                "strand_b_budget_mb", "strand_b_base_mb", "bytes_saved_mb", "hit_rate",
                "compressions", "evictions", "refused", "dandelion")
        return {k: st[k] for k in keep if k in st}

    def closet_view(self) -> dict:
        lib = self.library.status()
        for name, s in lib.get("suits", {}).items():
            s["imported"] = name in self._imports
            mod = sys.modules.get(MEM_MODPREFIX + name)
            s["where"] = getattr(mod, "PHOENIX_WHERE", "kernel")
        lib["playbox"] = self.playbox.view() if self.playbox else {"running": False}
        return lib

    # ── server ───────────────────────────────────────────────────────────────
    def start(self):
        GENIE_HOME.mkdir(parents=True, exist_ok=True)
        CLOSET_DIR.mkdir(parents=True, exist_ok=True)
        _write_private(TOKEN_PATH, self.token)
        self.reload_persisted()

        control = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "PhoenixGenie/1"

            def log_message(self, fmt, *args):
                log.debug("genie_control %s", fmt % args)

            def _send(self, code: int, obj: dict):
                body = json.dumps(obj, default=str).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _gate(self) -> bool:
                if self.headers.get("Origin") is not None:
                    self._send(403, {"error": "browser requests are not accepted"})
                    return False
                tok = self.headers.get("X-Genie-Token", "")
                if not hmac.compare_digest(tok, control.token):
                    self._send(401, {"error": "bad or missing X-Genie-Token"})
                    return False
                return True

            def do_GET(self):
                if not self._gate():
                    return
                if self.path == "/health":
                    return self._send(200, {"ok": True})
                if self.path == "/kernel":
                    return self._send(200, control.kernel_view())
                if self.path == "/closet":
                    return self._send(200, control.closet_view())
                self._send(404, {"error": "no route"})

            def do_POST(self):
                if not self._gate():
                    return
                if self.path != "/suits":
                    return self._send(404, {"error": "no route"})
                try:
                    n = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    n = -1
                if n <= 0 or n > MAX_BODY:
                    return self._send(400, {"error": "body required (max 16 KB)"})
                try:
                    req = json.loads(self.rfile.read(n))
                    if not isinstance(req, dict):
                        raise ValueError("body must be a JSON object")
                    # hex (or a name with no closet file) => pull from R2 and run in RAM, nothing on disk.
                    # file => legacy disk load from the closet.
                    if req.get("hex") or (req.get("name") and not req.get("file")):
                        self._send(200, control.load_suit_memory(req))
                    else:
                        self._send(200, control.load_suit(req))
                except ValueError as e:
                    self._send(400, {"error": str(e)})
                except Exception as e:
                    log.exception("genie_control load failed")
                    self._send(500, {"error": f"{type(e).__name__}: {e}"})

        self._server = ThreadingHTTPServer((BIND_ADDR, CONTROL_PORT), Handler)
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, name="genie-control", daemon=True).start()
        log.info("  Genie control  online  http://%s:%d (token-gated)", BIND_ADDR, CONTROL_PORT)

    def stop(self):
        if self.playbox:
            self.playbox.stop()
        if self._server:
            self._server.shutdown()
            self._server.server_close()
        try:
            TOKEN_PATH.unlink()
        except FileNotFoundError:
            pass


def start_control(library, frank=None, spawner=None, helix_i=None, helix_e=None,
                  helix=None, pager=None) -> GenieControl:
    ctl = GenieControl(library, frank=frank, spawner=spawner, helix_i=helix_i, helix_e=helix_e,
                       helix=helix, pager=pager)
    ctl.start()
    return ctl
