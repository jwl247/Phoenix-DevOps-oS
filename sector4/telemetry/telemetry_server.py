#!/usr/bin/env python3
"""
telemetry_server.py — Phoenix Desktop Telemetry Server
Port 7899 — WebSocket + HTTP filesystem API

Streams live JSON to the HUD dashboard every 2 seconds:
  - Kernel state (Frank5, Helix channels, suits)
  - breach_coms tier status (T1-T4)
  - Clonepool stats
  - System metrics (CPU, RAM, disk)
  - WireGuard mesh status

Handles client messages:
  - {"op":"ls","path":"/some/dir"}          → directory listing
  - {"op":"mv","src":"...","dst":"..."}      → move file
  - {"op":"run","path":"..."}               → execute in run-it drawer
  - {"op":"assign","drawer":"A","path":"..."} → assign drawer to directory

Phoenix DevOps OS | jwl247 | GPL v3
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import websockets
except ImportError:
    print("[telemetry] installing websockets...")
    subprocess.run([sys.executable, "-m", "pip", "install", "websockets", "psutil"], check=True)
    import websockets

try:
    import psutil
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "psutil"], check=True)
    import psutil

PORT         = int(os.environ.get("TELEMETRY_PORT", 7899))
CLONEPOOL    = Path(os.environ.get("CLONEPOOL_DIR", "/breach_coms4/clonepool"))
BREACH_TIERS = {
    "t1": Path("/breach_coms4"),
    "t2": Path("/breach_coms3"),
    "t3": Path("/breach_coms2"),
    "t4": Path("/breach_coms1"),
}
KERNEL_SHM   = Path(os.environ.get("PHOENIX_SHM", "/tmp/phoenix_shm"))
KERNEL_START = time.time()

# Drawer assignments: key = drawer ID, value = directory path
# 30 slots — A-Z + D1-D4 + RUN. Assign at runtime via {"op":"assign","drawer":"X","path":"..."}
_home = str(Path.home())
DRAWER_ASSIGNMENTS: dict[str, str] = {
    # Pre-assigned Phoenix core dirs
    "A":   str(Path.home() / "phoenix-devops"),
    "B":   str(CLONEPOOL),
    "C":   "/var/log/phoenix",
    "D":   str(Path.home() / "Phoenix"),
    "E":   "/breach_coms4",
    "F":   "/breach_coms3",
    "G":   "/breach_coms2",
    "H":   "/breach_coms1",
    "I":   str(Path.home() / "phoenix-devops/sector1"),
    "J":   str(Path.home() / "phoenix-devops/sector2"),
    "K":   str(Path.home() / "phoenix-devops/sector3"),
    "L":   str(Path.home() / "phoenix-devops/sector4"),
    "M":   str(Path.home() / "phoenix-devops/sector2/glossary"),
    "N":   str(Path.home() / "phoenix-devops/sector2/review-platform"),
    "O":   str(Path.home() / "phoenix-devops/helix_lightning_kernel"),
    "P":   str(Path.home() / "phoenix-devops/phoenix_universal_kernel"),
    "RUN": "/tmp/phoenix_run",
    # Open slots — assign via op:assign
    "Q":  _home, "R":  _home, "S":  _home, "T":  _home,
    "U":  _home, "V":  _home, "W":  _home, "X":  _home,
    "Y":  _home, "Z":  _home,
    "D1": _home, "D2": _home, "D3": _home, "D4": _home,
}

RUN_ALLOWED  = {".py", ".sh", ".js", ".bash"}
CLIENTS: set = set()


# ── Telemetry collectors ──────────────────────────────────────────────────────

def collect_kernel() -> dict:
    shm = KERNEL_SHM / "frank5.shm"
    uptime = int(time.time() - KERNEL_START)
    status = "operational" if shm.exists() else "degraded"
    helix_i = [p for p in [7701,7702,7703,7704] if _port_open(p)]
    helix_e = [p for p in [7805,7806,7807,7808] if _port_open(p)]
    return {
        "status":       status,
        "frank_version":"5.1.0-alpha",
        "uptime_s":     uptime,
        "helix_i":      helix_i,
        "helix_e":      helix_e,
        "channels_up":  len(helix_i) + len(helix_e),
    }

def _port_open(port: int) -> bool:
    import socket
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.1):
            return True
    except OSError:
        return False

def collect_breach_coms() -> dict:
    tiers = {}
    for key, path in BREACH_TIERS.items():
        if path.exists():
            try:
                u = shutil.disk_usage(path)
                tiers[key] = {
                    "path":    str(path),
                    "mounted": True,
                    "total_gb": round(u.total / 1e9, 1),
                    "used_gb":  round(u.used  / 1e9, 1),
                    "free_gb":  round(u.free  / 1e9, 1),
                    "pct":      round(u.used / u.total * 100, 1),
                }
            except OSError:
                tiers[key] = {"path": str(path), "mounted": False}
        else:
            tiers[key] = {"path": str(path), "mounted": False}
    return tiers

def collect_clonepool() -> dict:
    if not CLONEPOOL.exists():
        return {"path": str(CLONEPOOL), "entries": 0, "reachable": False}
    entries = [d for d in CLONEPOOL.iterdir() if d.is_dir()] if CLONEPOOL.exists() else []
    return {
        "path":      str(CLONEPOOL),
        "reachable": True,
        "entries":   len(entries),
    }

def collect_system() -> dict:
    cpu  = psutil.cpu_percent(interval=None)
    ram  = psutil.virtual_memory()
    disk = shutil.disk_usage("/")
    return {
        "cpu_pct":     round(cpu, 1),
        "ram_pct":     round(ram.percent, 1),
        "ram_used_gb": round(ram.used / 1e9, 1),
        "ram_total_gb":round(ram.total / 1e9, 1),
        "disk_pct":    round(disk.used / disk.total * 100, 1),
        "disk_free_gb":round(disk.free / 1e9, 1),
    }

def collect_wg() -> dict:
    try:
        r = subprocess.run(["wg", "show"], capture_output=True, text=True, timeout=2)
        lines = r.stdout.strip().splitlines()
        peers = sum(1 for l in lines if l.strip().startswith("peer:"))
        handshakes = sum(1 for l in lines if "latest handshake" in l)
        return {"peers": peers, "handshakes": handshakes, "raw": r.stdout[:400]}
    except Exception:
        return {"peers": 0, "handshakes": 0, "raw": ""}

def collect_drawers() -> dict:
    """Broadcast metadata only — count + path, no file listings.
    Full directory contents load on-demand via {"op":"ls","path":"..."}.
    Scales to 30+ drawers with no broadcast overhead."""
    out = {}
    for drawer_id, path in DRAWER_ASSIGNMENTS.items():
        p = Path(path)
        if p.exists():
            try:
                count = sum(1 for _ in p.iterdir())
                out[drawer_id] = {
                    "path":    path,
                    "label":   p.name or path,
                    "count":   count,
                    "mounted": True,
                    "run_it":  drawer_id == "RUN",
                }
            except PermissionError:
                out[drawer_id] = {"path": path, "label": Path(path).name, "count": 0, "mounted": True, "error": "permission denied"}
        else:
            out[drawer_id] = {"path": path, "label": Path(path).name, "count": 0, "mounted": False, "run_it": drawer_id == "RUN"}
    return out

def build_frame() -> dict:
    return {
        "ts":          datetime.now(timezone.utc).isoformat(),
        "kernel":      collect_kernel(),
        "breach_coms": collect_breach_coms(),
        "clonepool":   collect_clonepool(),
        "system":      collect_system(),
        "wg":          collect_wg(),
        "drawers":     collect_drawers(),
    }


# ── File operations ───────────────────────────────────────────────────────────

def op_ls(path: str) -> dict:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return {"error": f"not found: {path}"}
    items = []
    try:
        for item in sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
            stat = item.stat()
            items.append({
                "name":     item.name,
                "type":     "dir" if item.is_dir() else "file",
                "size":     stat.st_size if item.is_file() else None,
                "modified": int(stat.st_mtime),
            })
    except PermissionError as e:
        return {"error": str(e)}
    return {"path": str(p), "items": items, "count": len(items)}

def op_mv(src: str, dst: str) -> dict:
    try:
        s, d = Path(src).resolve(), Path(dst).resolve()
        shutil.move(str(s), str(d))
        return {"ok": True, "src": str(s), "dst": str(d)}
    except Exception as e:
        return {"error": str(e)}

def op_assign(drawer: str, path: str) -> dict:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return {"error": f"path not found: {path}"}
    DRAWER_ASSIGNMENTS[drawer.upper()] = str(p)
    return {"ok": True, "drawer": drawer.upper(), "path": str(p)}

async def op_run(path: str, ws) -> None:
    p = Path(path).resolve()
    if p.suffix not in RUN_ALLOWED:
        await ws.send(json.dumps({"op":"run_err","msg":f"not allowed: {p.suffix}"}))
        return
    run_dir = Path("/tmp/phoenix_run")
    run_dir.mkdir(exist_ok=True)
    interp = {"py": sys.executable, "sh": "bash", "bash": "bash", "js": "node"}.get(p.suffix.lstrip("."), "bash")
    await ws.send(json.dumps({"op":"run_start","path":str(p)}))
    try:
        proc = await asyncio.create_subprocess_exec(
            interp, str(p),
            cwd=str(run_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        async for line in proc.stdout:
            await ws.send(json.dumps({"op":"run_out","line":line.decode(errors="replace").rstrip()}))
        await proc.wait()
        await ws.send(json.dumps({"op":"run_done","exit":proc.returncode}))
    except Exception as e:
        await ws.send(json.dumps({"op":"run_err","msg":str(e)}))


# ── WebSocket handler ─────────────────────────────────────────────────────────

async def handler(ws):
    CLIENTS.add(ws)
    print(f"[telemetry] client connected — {len(CLIENTS)} active")
    try:
        # Send immediate frame on connect
        await ws.send(json.dumps(build_frame()))

        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            op = msg.get("op")
            if op == "ls":
                await ws.send(json.dumps({"op":"ls","result": op_ls(msg.get("path","."))}))
            elif op == "mv":
                await ws.send(json.dumps({"op":"mv","result": op_mv(msg.get("src",""), msg.get("dst",""))}))
            elif op == "assign":
                await ws.send(json.dumps({"op":"assign","result": op_assign(msg.get("drawer",""), msg.get("path",""))}))
            elif op == "run":
                await op_run(msg.get("path",""), ws)
            elif op == "ping":
                await ws.send(json.dumps({"op":"pong","ts":datetime.now(timezone.utc).isoformat()}))
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        CLIENTS.discard(ws)
        print(f"[telemetry] client disconnected — {len(CLIENTS)} active")


# ── Broadcast loop ────────────────────────────────────────────────────────────

async def broadcast_loop():
    psutil.cpu_percent()  # prime the CPU meter
    while True:
        await asyncio.sleep(2)
        if not CLIENTS:
            continue
        frame = json.dumps(build_frame())
        dead = set()
        for ws in CLIENTS.copy():
            try:
                await ws.send(frame)
            except Exception:
                dead.add(ws)
        CLIENTS -= dead


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    print(f"[telemetry] Phoenix Telemetry Server — port {PORT}")
    print(f"[telemetry] Clonepool: {CLONEPOOL}")
    print(f"[telemetry] Drawers:   {list(DRAWER_ASSIGNMENTS.keys())}")
    async with websockets.serve(handler, "0.0.0.0", PORT):
        await broadcast_loop()

if __name__ == "__main__":
    asyncio.run(main())
