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
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse
from frank_save import frank_save, frank_status, CATALOG_DB

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
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/save":
            length = int(self.headers.get("Content-Length", 0))
            body   = json.loads(self.rfile.read(length))
            result = frank_save(
                doc_id   = body.get("doc_id", "unnamed"),
                title    = body.get("title",  "Untitled"),
                doc_type = body.get("doc_type","doc"),
                content  = body.get("content",""),
            )
            self._json(200, result)
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
    print("  GET  /status  — drive pressures + tier")
    print("  POST /save    — route a document save")
    print("  GET  /catalog — recent saves")
    srv.serve_forever()
