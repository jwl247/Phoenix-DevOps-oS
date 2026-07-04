#!/usr/bin/env python3
"""
phoenix_status_server.py — Phoenix Kernel HTTP Status Server
Runs on localhost:8765. Seelen UI toolbar plugins poll these endpoints.

Endpoints:
  GET /status     — Helix + Frank + clone pool combined health
  GET /llm        — LLM engine status (active model, sessions, warmed models)
  GET /clonepool  — Clone pool item counts by state and tier
  GET /lifefirst  — Life First API health + pending notification count

Start automatically from main_kernel.py (already wired in).
Run standalone: python phoenix_status_server.py

jwl247 / Phoenix DevOps LLC / GPL v3
"""

import json
import os
import sys
import sqlite3
import threading
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

PHOENIX_HOME    = Path(os.environ.get("PHOENIX_HOME", Path.home() / "Phoenix"))
HELIX_DB        = Path(os.environ.get("HELIX_DB",     PHOENIX_HOME / "db/helix.db"))
FRANK_DB        = Path(os.environ.get("FRANK_DB",     PHOENIX_HOME / "db/frank.db"))
LIFEFIRST_API   = os.environ.get("LIFEFIRST_API",     "http://localhost/lifefirst/api.php")
LIFEFIRST_SEC   = os.environ.get("LF_API_SECRET",     "")
STATUS_PORT     = int(os.environ.get("PHOENIX_STATUS_PORT", "8765"))

# ── Data collectors ───────────────────────────────────────────────────────────

def _query_db(db_path: Path, sql: str, params=()):
    if not db_path.exists():
        return None
    try:
        with sqlite3.connect(str(db_path), timeout=2) as cx:
            return cx.execute(sql, params).fetchone()
    except Exception:
        return None

def get_helix_status() -> dict:
    row = _query_db(HELIX_DB,
        "SELECT COUNT(*), SUM(CASE WHEN state='active' THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN state='deprecated' THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN state='retired' THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN tier='T1' THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN tier='T2' THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN tier='T3' THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN tier='T4' THEN 1 ELSE 0 END) "
        "FROM clone_pool"
    )
    if not row:
        return {"available": False}
    return {
        "available":   True,
        "total":       row[0] or 0,
        "active":      row[1] or 0,
        "deprecated":  row[2] or 0,
        "retired":     row[3] or 0,
        "t1":          row[4] or 0,
        "t2":          row[5] or 0,
        "t3":          row[6] or 0,
        "t4":          row[7] or 0,
    }

def get_frank_status() -> dict:
    row = _query_db(FRANK_DB,
        "SELECT COUNT(*) FROM ring3_routes WHERE status != 'removed'"
    )
    outputs = _query_db(FRANK_DB, "SELECT COUNT(*) FROM output_log")
    sideloads = _query_db(FRANK_DB, "SELECT COUNT(*) FROM sideloads WHERE status='active'")
    return {
        "available":    row is not None,
        "frank_routes": row[0] if row else 0,
        "output_log":   outputs[0] if outputs else 0,
        "sideloads":    sideloads[0] if sideloads else 0,
    }

def get_llm_status() -> dict:
    """Read LLM engine state from the global engine if it's been booted."""
    try:
        # Import llm_engine from same directory
        _here = Path(__file__).parent
        if str(_here) not in sys.path:
            sys.path.insert(0, str(_here))
        from llm_engine import _engine
        if _engine is None:
            return {"available": False}
        stats = _engine.stats()
        # active_model = first warmed model, or "–"
        active = stats["models_warmed"][0] if stats["models_warmed"] else "–"
        return {
            "available":      True,
            "active_model":   active,
            "active_sessions": stats["active_sessions"],
            "models_warmed":  stats["models_warmed"],
            "available_models": stats["available_models"],
        }
    except Exception:
        return {"available": False}

def get_lifefirst_status() -> dict:
    """Quick health check against the Life First PHP API."""
    try:
        req = urllib.request.Request(
            LIFEFIRST_API + "?action=health",
            headers={"Authorization": f"Bearer {LIFEFIRST_SEC}"},
        )
        with urllib.request.urlopen(req, timeout=3) as r:
            data = json.loads(r.read())
        api_online = data.get("status") == "success"
        checks     = data.get("data", {})
        modules    = checks.get("modules_installed", {})
        return {
            "api_online":            api_online,
            "modules":               modules,
            "active_users":          None,    # not exposed by health endpoint yet
            "pending_notifications": 0,       # TODO: wire Module 6 count endpoint
        }
    except Exception:
        return {"api_online": False, "modules": {}, "pending_notifications": 0}

# ── HTTP handler ──────────────────────────────────────────────────────────────

class PhoenixStatusHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass  # silence access log

    def _send(self, data: dict, code: int = 200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")

        if path == "/status":
            helix = get_helix_status()
            frank = get_frank_status()
            llm   = get_llm_status()
            self._send({
                "helix_ops_per_sec":  None,          # only available from live Helix instance
                "helix_hit_rate":     None,
                "clone_pool_items":   helix.get("active", 0),
                "frank_routes":       frank.get("frank_routes", 0),
                "llm_sessions":       llm.get("active_sessions", 0),
                "helix_available":    helix.get("available", False),
                "frank_available":    frank.get("available", False),
                "llm_available":      llm.get("available", False),
                "uptime_sec":         None,
            })

        elif path == "/clonepool":
            self._send(get_helix_status())

        elif path == "/llm":
            self._send(get_llm_status())

        elif path == "/lifefirst":
            self._send(get_lifefirst_status())

        elif path == "/health":
            self._send({"ok": True, "port": STATUS_PORT})

        else:
            self._send({"error": "not found"}, 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()


# ── Entry point ───────────────────────────────────────────────────────────────

def start(port: int = STATUS_PORT):
    """Start status server in a daemon thread. Safe to call from main_kernel.py."""
    server = HTTPServer(("127.0.0.1", port), PhoenixStatusHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True,
                         name="phoenix-status-server")
    t.start()
    return server


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [status] %(message)s")
    print(f"Phoenix Status Server — http://localhost:{STATUS_PORT}")
    print("Endpoints: /status  /clonepool  /llm  /lifefirst  /health")
    server = HTTPServer(("127.0.0.1", STATUS_PORT), PhoenixStatusHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutdown.")
