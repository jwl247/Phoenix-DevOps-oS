#!/usr/bin/env python3
"""
file_tree_service.py — Phoenix Universal Kernel / File Tree & Clone Service
Serves the click-clone-drag-and-drop file tree for Phoenix Desktop.

Exposes two socket channels (mapped to Helix-I):
  Port 7703 — File tree queries (list dir, get node, search)
  Port 7704 — Clone operations (clone file/dir → destination)

Protocol: newline-delimited JSON over TCP.
  Request:  {"cmd": "...", ...params}
  Response: {"ok": true, "data": ...} | {"ok": false, "error": "..."}

Commands:
  tree    {"path": "/some/dir", "depth": 2}
            → directory tree as nested JSON
  node    {"path": "/some/file"}
            → stat + TAV address + clone pool status
  search  {"root": "/home", "pattern": "*.py"}
            → matching paths
  clone   {"src": "/path/to/file", "dst": "/clone/dest/", "into_pool": true}
            → copies file, registers in Helix clone pool, returns TAV
  intake  {"path": "/path/to/file"}
            → runs Phoenix intake pipeline (hex identity, sidecar, clone pool)
  status  {}
            → service health

The clone pool registration calls CoPES/helix.py if COPES_PATH is set,
otherwise it writes a sidecar.json alongside the destination file.

jwl247 / Phoenix DevOps LLC / GPL v3
"""

import os
import sys
import json
import socket
import shutil
import hashlib
import fnmatch
import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("phoenix_filetree")

# ── Config ───────────────────────────────────────────────────────────────────

TREE_PORT   = int(os.environ.get("PHOENIX_TREE_PORT",  "7703"))
CLONE_PORT  = int(os.environ.get("PHOENIX_CLONE_PORT", "7704"))
MAX_DEPTH   = int(os.environ.get("PHOENIX_TREE_DEPTH", "5"))
COPES_PATH  = os.environ.get("COPES_PATH", str(Path(__file__).parent.parent / "CoPES"))

# ── TAV identity (matches CoPES/helix.py) ────────────────────────────────────

def _tav(name: str) -> str:
    try:
        import base58 as _b58
        raw = hashlib.sha3_512(name.encode()).digest()[:8]
        return _b58.b58encode(raw).decode()
    except ImportError:
        # fallback without base58 — hex prefix
        return hashlib.sha3_512(name.encode()).hexdigest()[:16]

def _sha3(path: str) -> str:
    h = hashlib.sha3_512()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    except Exception:
        return ""
    return h.hexdigest()

# ── Helix clone pool (CoPES integration) ─────────────────────────────────────

def _get_helix():
    """Lazy-load CoPES Helix if available."""
    try:
        sys.path.insert(0, COPES_PATH)
        import helix as _h
        return _h._get_global_helix()
    except Exception:
        return None

# ── File tree builder ─────────────────────────────────────────────────────────

def build_tree(root: str, depth: int = 2, _current: int = 0) -> Dict:
    p = Path(root)
    node: Dict[str, Any] = {
        "name":  p.name or str(p),
        "path":  str(p),
        "type":  "dir" if p.is_dir() else "file",
        "tav":   _tav(p.name),
    }
    if p.is_file():
        try:
            st = p.stat()
            node["size"]  = st.st_size
            node["mtime"] = st.st_mtime
        except Exception:
            pass
    if p.is_dir() and _current < depth:
        children = []
        try:
            entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
            for child in entries:
                try:
                    children.append(build_tree(str(child), depth, _current + 1))
                except PermissionError:
                    pass
        except PermissionError:
            pass
        node["children"] = children
    return node

def node_info(path: str) -> Dict:
    p = Path(path)
    if not p.exists():
        return {"error": f"not found: {path}"}
    info: Dict[str, Any] = {
        "name":   p.name,
        "path":   str(p),
        "type":   "dir" if p.is_dir() else "file",
        "tav":    _tav(p.name),
        "exists": True,
    }
    if p.is_file():
        st = p.stat()
        info["size"]        = st.st_size
        info["mtime"]       = st.st_mtime
        info["fingerprint"] = _sha3(str(p))
    return info

def search_files(root: str, pattern: str) -> List[str]:
    results = []
    try:
        for dirpath, _dirs, files in os.walk(root):
            for fname in files:
                if fnmatch.fnmatch(fname, pattern):
                    results.append(os.path.join(dirpath, fname))
                    if len(results) >= 500:
                        return results
    except PermissionError:
        pass
    return results

# ── Clone operation ───────────────────────────────────────────────────────────

def clone_path(src: str, dst: str, into_pool: bool = False) -> Dict:
    """
    Clone src → dst.
    If into_pool=True, register in Helix clone pool (CoPES must be on path).
    Always writes a sidecar.json next to the destination.
    """
    sp = Path(src)
    dp = Path(dst)

    if not sp.exists():
        return {"ok": False, "error": f"source not found: {src}"}

    dp.parent.mkdir(parents=True, exist_ok=True)

    try:
        if sp.is_dir():
            if dp.exists():
                shutil.rmtree(str(dp))
            shutil.copytree(str(sp), str(dp))
        else:
            shutil.copy2(str(sp), str(dp))
    except Exception as e:
        return {"ok": False, "error": str(e)}

    tav = _tav(sp.name)
    sha = _sha3(str(dp)) if dp.is_file() else ""

    sidecar = {
        "name":        sp.name,
        "tav":         tav,
        "fingerprint": sha,
        "src":         str(sp),
        "dst":         str(dp),
        "cloned_at":   time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tier":        "T1",
        "state":       "active",
    }

    sidecar_path = dp.parent / f"{tav}.sidecar.json"
    try:
        sidecar_path.write_text(json.dumps(sidecar, indent=2))
    except Exception:
        pass

    pool_result = None
    if into_pool:
        helix = _get_helix()
        if helix:
            try:
                rec = helix.store(sp.name, {"path": str(dp), "sha3": sha}, meta=sidecar)
                pool_result = rec.to_sidecar()
            except Exception as e:
                pool_result = {"error": str(e)}

    return {
        "ok":      True,
        "tav":     tav,
        "src":     str(sp),
        "dst":     str(dp),
        "sidecar": str(sidecar_path),
        "pool":    pool_result,
    }

def intake_file(path: str) -> Dict:
    """Run the Phoenix intake pipeline on a single file."""
    p = Path(path)
    if not p.exists():
        return {"ok": False, "error": f"not found: {path}"}

    tav = _tav(p.name)
    sha = _sha3(str(p))
    sidecar = {
        "name":        p.name,
        "tav":         tav,
        "fingerprint": sha,
        "path":        str(p),
        "intaked_at":  time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tier":        "T1",
        "state":       "active",
    }
    sidecar_path = p.parent / f"{tav}.sidecar.json"
    sidecar_path.write_text(json.dumps(sidecar, indent=2))

    helix = _get_helix()
    pool_result = None
    if helix:
        try:
            rec = helix.store(p.name, {"path": str(p), "sha3": sha}, meta=sidecar)
            pool_result = rec.to_sidecar()
        except Exception as e:
            pool_result = {"error": str(e)}

    return {"ok": True, "tav": tav, "sidecar": str(sidecar_path), "pool": pool_result}

# ── Request dispatcher ────────────────────────────────────────────────────────

def dispatch(req: Dict) -> Dict:
    cmd = req.get("cmd", "")
    try:
        if cmd == "tree":
            return {"ok": True, "data": build_tree(
                req.get("path", str(Path.home())),
                depth=min(int(req.get("depth", 2)), MAX_DEPTH)
            )}
        elif cmd == "node":
            return {"ok": True, "data": node_info(req["path"])}
        elif cmd == "search":
            return {"ok": True, "data": search_files(
                req.get("root", str(Path.home())),
                req.get("pattern", "*")
            )}
        elif cmd == "clone":
            return clone_path(req["src"], req["dst"],
                              into_pool=req.get("into_pool", False))
        elif cmd == "intake":
            return intake_file(req["path"])
        elif cmd == "status":
            return {"ok": True, "data": {
                "tree_port":  TREE_PORT,
                "clone_port": CLONE_PORT,
                "copes_path": COPES_PATH,
                "uptime":     time.time(),
            }}
        else:
            return {"ok": False, "error": f"unknown command: {cmd}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ── Socket server ─────────────────────────────────────────────────────────────

def _handle_conn(conn: socket.socket, addr):
    try:
        data = b""
        conn.settimeout(10)
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                break
            data += chunk
            if b"\n" in data:
                break
        line = data.split(b"\n")[0].strip()
        if not line:
            return
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            conn.sendall(json.dumps({"ok": False, "error": "invalid JSON"}).encode() + b"\n")
            return
        result = dispatch(req)
        conn.sendall(json.dumps(result).encode() + b"\n")
    except Exception as e:
        try:
            conn.sendall(json.dumps({"ok": False, "error": str(e)}).encode() + b"\n")
        except Exception:
            pass
    finally:
        conn.close()

def _serve(port: int):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", port))
    sock.listen(20)
    log.info(f"FileTree service listening on port {port}")
    while True:
        try:
            conn, addr = sock.accept()
            t = threading.Thread(target=_handle_conn, args=(conn, addr), daemon=True)
            t.start()
        except Exception as e:
            log.error(f"accept error: {e}")

def start():
    """Start both file tree and clone socket servers."""
    for port in [TREE_PORT, CLONE_PORT]:
        t = threading.Thread(target=_serve, args=(port,), daemon=True,
                             name=f"filetree-{port}")
        t.start()
    log.info("FileTree service started (ports %d, %d)", TREE_PORT, CLONE_PORT)
