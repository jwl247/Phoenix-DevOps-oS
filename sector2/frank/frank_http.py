"""
frank_http.py — tiny HTTP bridge
Serves frank_status() as JSON so the Phoenix Office worker
can poll it from the browser without touching the filesystem.

Run once, stays resident:
    python3 frank_http.py &

Endpoints:
    GET  /status          → frank_status()
    POST /save            → frank_save(doc_id, title, doc_type, content)
    GET  /catalog         → last 50 catalog entries
"""

import json
import sqlite3
import sys
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse
from pathlib import Path

# Frank save (local Office bridge)
from frank_save import frank_save, frank_status, CATALOG_DB

# Frank × Life First bridge (sector4)
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "sector4" / "frank"))
from frank_lifefirst import dispatch as lf_dispatch, health as lf_health, frank_lf_status, uk_resolve

PORT = 7347   # F=6 R=17 A=1 N=13 K=10 → 7347 is just a clean unused port

class FrankHandler(BaseHTTPRequestHandler):

    def log_message(self, *a): pass   # silent — Frank doesn't chatter

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "http://localhost")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "http://localhost")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/status":
            self._json(200, frank_status())
        elif path == "/catalog":
            self._json(200, recent_catalog())
        elif path == "/lifefirst/health":
            self._json(200, lf_health())
        elif path == "/lifefirst/status":
            self._json(200, frank_lf_status())
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        path   = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        body   = json.loads(self.rfile.read(length)) if length else {}

        if path == "/save":
            result = frank_save(
                doc_id   = body.get("doc_id",   "unnamed"),
                title    = body.get("title",    "Untitled"),
                doc_type = body.get("doc_type", "doc"),
                content  = body.get("content",  ""),
            )
            self._json(200, result)

        elif path == "/lifefirst":
            user_id = body.get("user_id", "laurie")
            message = body.get("message", "")
            if not message:
                self._json(400, {"error": "message required"})
                return
            result = lf_dispatch(user_id=user_id, message=message)
            self._json(200, result)

        elif path == "/lifefirst/uk":
            command = body.get("command", "")
            channel = int(body.get("channel", 1))
            if not command:
                self._json(400, {"error": "command required"})
                return
            result = uk_resolve(command, channel=channel)
            self._json(200, {"response": result})

        else:
            self._json(404, {"error": "not found"})

def recent_catalog(n=50):
    try:
        con = sqlite3.connect(CATALOG_DB)
        rows = con.execute(
            "SELECT id,title,doc_type,saved_at,drive,version,size_bytes "
            "FROM documents ORDER BY saved_at DESC LIMIT ?", (n,)
        ).fetchall()
        con.close()
        return [{"id":r[0],"title":r[1],"type":r[2],"saved":r[3],
                 "drive":r[4],"v":r[5],"size":r[6]} for r in rows]
    except Exception:
        return []

if __name__ == "__main__":
    srv = HTTPServer(("127.0.0.1", PORT), FrankHandler)
    print(f"Frank3 HTTP bridge running on 127.0.0.1:{PORT}")
    print("  GET  /status             — drive pressures + tier")
    print("  POST /save               — route a document save")
    print("  GET  /catalog            — recent saves")
    print("  GET  /lifefirst/health   — Life First API health")
    print("  GET  /lifefirst/status   — Frank + LF combined status")
    print("  POST /lifefirst          — dispatch message to Life First via Frank")
    print("  POST /lifefirst/uk       — send command to Universal Kernel")
    srv.serve_forever()
