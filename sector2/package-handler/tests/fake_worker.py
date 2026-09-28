#!/usr/bin/env python3
"""A stand-in for packages-worker, for testing intake.sh without Cloudflare.

It answers the routes intake.sh actually calls, with the same shapes the real
worker (sector2/package-handler/worker/index.js) returns, and records every
request to a JSON-lines log so a test can assert what the client did:

  GET  /whoami                                  -> 200 {"ok":true}
  POST /clonepool                               -> {"ok":true,"version_logged":{...}|null}
       (a versions row is "logged" when hash_sha3 is new for that hex_id,
        exactly as index.js does; store_path = <hex>/versions/<sha3[0:16]>)
  PUT  /clonepool/<hex>                         -> stores current bytes
  PUT  /clonepool/<hex>/versions/<prefix>       -> stores immutable version bytes
  GET  /clonepool/<hex>?meta=true               -> the D1-style row (hash_sha3 ...)
  GET  /clonepool/<hex>                         -> current bytes (404 if none)
  GET  /clonepool/<hex>/versions/<prefix>       -> version bytes (404 if none)
  POST /clonepool/<hex>/validate                -> {"ok":true,"valid":bool}
  PATCH /clonepool/<hex>/tier                   -> {"ok":true}
  POST /custody, /glossary, /deps               -> {"ok":true}

Auth: Bearer must equal FAKE_PHOENIX_AUTH (default "test-token"); anything
else is 401, like the real worker.

Usage: fake_worker.py <port> <state-dir>
  <state-dir>/requests.jsonl   one line per request
  <state-dir>/objects/         stored R2 objects (path = key with / -> __)
  <state-dir>/rows.json        the clonepool rows by hex_id
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

PORT = int(sys.argv[1])
STATE = sys.argv[2]
TOKEN = os.environ.get("FAKE_PHOENIX_AUTH", "test-token")
os.makedirs(os.path.join(STATE, "objects"), exist_ok=True)
LOCK = threading.Lock()
ROWS_PATH = os.path.join(STATE, "rows.json")
VERSIONS_PATH = os.path.join(STATE, "versions.json")


def _load(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def _save(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=1)


def _objpath(key):
    return os.path.join(STATE, "objects", key.replace("/", "__"))


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _record(self, body_len):
        with LOCK:
            with open(os.path.join(STATE, "requests.jsonl"), "a") as f:
                f.write(json.dumps({"method": self.command, "path": self.path, "bytes": body_len}) + "\n")

    def _json(self, status, obj):
        data = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _bytes(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authed(self):
        return self.headers.get("Authorization", "") == f"Bearer {TOKEN}"

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def do_GET(self):
        u = urlparse(self.path)
        self._record(0)
        if u.path == "/whoami":
            return self._json(200 if self._authed() else 401, {"ok": self._authed()})
        if not self._authed():
            return self._json(401, {"error": "unauthorized"})
        if u.path == "/versions":
            pkg = parse_qs(u.query).get("package", [None])[0]
            vs = _load(VERSIONS_PATH, [])
            if pkg:
                vs = [v for v in vs if v["package"] == pkg]
            return self._json(200, {"versions": vs, "count": len(vs)})
        if u.path.startswith("/clonepool/"):
            key = u.path[len("/clonepool/"):]
            if "/versions/" in key:
                p = _objpath(key)
                if os.path.exists(p):
                    return self._bytes(200, open(p, "rb").read())
                return self._json(404, {"error": "not found"})
            wants_meta = parse_qs(u.query).get("meta", [""])[0] == "true"
            if not wants_meta:
                p = _objpath(key)
                if os.path.exists(p):
                    return self._bytes(200, open(p, "rb").read())
            rows = _load(ROWS_PATH, {})
            row = rows.get(key) or next((r for r in rows.values() if r.get("name") == key), None)
            return self._json(200, row) if row else self._json(404, {"error": "not found"})
        return self._json(404, {"error": "no route"})

    def do_PUT(self):
        u = urlparse(self.path)
        body = self._body()
        self._record(len(body))
        if not self._authed():
            return self._json(401, {"error": "unauthorized"})
        if u.path.startswith("/clonepool/"):
            key = u.path[len("/clonepool/"):]
            with open(_objpath(key), "wb") as f:
                f.write(body)
            return self._json(200, {"ok": True, "key": key, "bytes": len(body)})
        return self._json(404, {"error": "no route"})

    def do_PATCH(self):
        u = urlparse(self.path)
        body = self._body()
        self._record(len(body))
        if not self._authed():
            return self._json(401, {"error": "unauthorized"})
        if u.path.startswith("/clonepool/") and u.path.endswith("/tier"):
            hex_id = u.path[len("/clonepool/"):-len("/tier")]
            b = json.loads(body or b"{}")
            with LOCK:
                rows = _load(ROWS_PATH, {})
                if hex_id in rows:
                    rows[hex_id]["tier"] = b.get("tier")
                    if b.get("pool_path"):
                        rows[hex_id]["pool_path"] = b["pool_path"]
                    if b.get("state"):
                        rows[hex_id]["state"] = b["state"]
                    _save(ROWS_PATH, rows)
            return self._json(200, {"ok": True, "hex_id": hex_id, "tier": b.get("tier")})
        return self._json(404, {"error": "no route"})

    def do_POST(self):
        u = urlparse(self.path)
        body = self._body()
        self._record(len(body))
        if not self._authed():
            return self._json(401, {"error": "unauthorized"})
        try:
            b = json.loads(body or b"{}")
        except json.JSONDecodeError as e:
            return self._json(400, {"error": f"invalid json: {e}"})
        if u.path == "/clonepool":
            if not b.get("hex_id") or not b.get("name"):
                return self._json(400, {"error": "hex_id and name required"})
            with LOCK:
                rows = _load(ROWS_PATH, {})
                prior = rows.get(b["hex_id"])
                row = dict(prior or {})
                row.update({k: v for k, v in b.items() if v not in ("", None)})
                row["hex_id"] = b["hex_id"]
                rows[b["hex_id"]] = row
                _save(ROWS_PATH, rows)
                logged = None
                if b.get("hash_sha3") and (not prior or prior.get("hash_sha3") != b["hash_sha3"]):
                    vs = _load(VERSIONS_PATH, [])
                    n = sum(1 for v in vs if v["package"] == b["name"])
                    logged = {"version": f"v{n + 1}", "store_path": f"{b['hex_id']}/versions/{b['hash_sha3'][:16]}"}
                    vs.append({"package": b["name"], "version": logged["version"], "store_path": logged["store_path"],
                               "hash_sha3": b["hash_sha3"], "size": b.get("size", 0)})
                    _save(VERSIONS_PATH, vs)
            return self._json(200, {"ok": True, "hex_id": b["hex_id"], "name": b["name"], "version_logged": logged})
        if u.path.startswith("/clonepool/") and u.path.endswith("/validate"):
            hex_id = u.path[len("/clonepool/"):-len("/validate")]
            rows = _load(ROWS_PATH, {})
            row = rows.get(hex_id)
            valid = bool(row and row.get("hash_sha3") == b.get("hash_sha3"))
            return self._json(200, {"ok": True, "hex_id": hex_id, "valid": valid})
        if u.path in ("/custody", "/glossary", "/deps"):
            return self._json(200, {"ok": True})
        return self._json(404, {"error": "no route"})


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    srv.serve_forever()
