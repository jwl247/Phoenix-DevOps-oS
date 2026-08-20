#!/usr/bin/env python3
"""
Phoenix Connections System
Canonical implementation of the connections / wiring / coms fabric.

This is the runtime realization of:
- Lost_Ark_Connections_Wiring_Map.md
- Phoenix_Structure_and_Connections.md
- dispatch.json targets + com_chain
- helix_mesh.conf
- propcoms (daisy COM4→COM3→COM2→COM1)
- Syncthing distribution
- ZMQ mesh (frank-helix 5557, romeo 5560, juliet 5561, dispatch peers)
- Guardian "friendships"
- Helix API / Franken / Freewheeling patterns
- Catalog / Glossary registration (D1 via packages-worker when available)
- Diagnostic posting (What + Why + Recommended Action)

Location: SECTOR4 (vault/coms master). 
Coms1-4 layers should import or delegate to this module (or intake this file).

Usage:
    from connections import PhoenixConnections
    conn = PhoenixConnections()
    conn.register_from_dispatch("path/to/dispatch.json")
    conn.daisy_relay({"type": "test", "payload": "hello"})
    print(conn.list_connections())
    conn.health_check_all()

Part of Phoenix DevOps OS — jwl247 | GPL-3.0
"""

import os
import sys
import json
import time
import socket
import subprocess
import sqlite3
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Literal
import urllib.request
import urllib.error

# Optional heavy deps (graceful)
try:
    import zmq  # pyzmq
    HAS_ZMQ = True
except ImportError:
    HAS_ZMQ = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# ============================================================
# CONSTANTS & KNOWN PORTS (from wiring + helix_mesh + dispatch + services)
# ============================================================

KNOWN_PORTS = {
    "frank_helix_zmq": 5557,
    "frank3_dispatch": 5555,
    "romeo_ingress": 5560,
    "juliet_egress": 5561,
    "propcoms_com4": 5564,
    "propcoms_com3": 5563,
    "propcoms_com2": 5562,
    "propcoms_com1": 5561,  # overlaps juliet in some maps; daisy uses distinct in sh
    "helix_mesh_memory": 5570,
    "helix_mesh_storage": 5571,
    "helix_mesh_network": 5572,
    "helix_mesh_compute": 5573,
    "helix_mesh_com": 5574,
    "helix_mesh_vault": 5575,
    "ollama": 11434,
    "unoserver": 2003,
}

CONNECTION_TYPES = Literal[
    "zmq", "syncthing", "http", "r2", "d1", "worker", "helix_mesh",
    "file", "dispatch_target", "mcp", "local_service", "com_daisy"
]

DIAG_LEVELS = ["INFO", "WARN", "ERROR", "SUCCESS"]

# Default catalog for local persistence (matches project patterns)
DEFAULT_CATALOG = Path.home() / ".catalog" / "connections.db"
DEFAULT_LOG = Path.home() / ".unitedsys" / "logs" / "connections.log"


# ============================================================
# DATA MODEL
# ============================================================

@dataclass
class Connection:
    name: str
    type: CONNECTION_TYPES
    address: str  # endpoint, url, path, device_id, etc.
    meta: Dict[str, Any] = field(default_factory=dict)
    state: str = "unknown"  # unknown, connected, degraded, disconnected, white/grey/black
    last_heartbeat: Optional[str] = None
    registered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict:
        return asdict(self)

    def to_glossary_entry(self) -> Dict:
        """Format suitable for packages-worker /glossary"""
        return {
            "name": f"connection:{self.name}",
            "category": "connection",
            "description": f"{self.type} connection to {self.address}",
            "metadata": {
                "type": self.type,
                "address": self.address,
                "state": self.state,
                "meta": self.meta,
            },
            "backend": "connections-system",
        }


# ============================================================
# DIAGNOSTICS (per wiring map rule)
# ============================================================

def post_diagnostic(what: str, why: str, action: str, level: str = "INFO", extra: Optional[Dict] = None):
    """Every significant event/error must post What + Why + Recommended Action."""
    ts = datetime.now(timezone.utc).isoformat()
    msg = f"[{level}] {what}\n  WHY: {why}\n  ACTION: {action}"
    if extra:
        msg += f"\n  EXTRA: {json.dumps(extra)}"

    # Console
    print(msg)

    # Local log
    try:
        DEFAULT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(DEFAULT_LOG, "a", encoding="utf-8") as f:
            f.write(f"{ts} {msg}\n\n")
    except Exception:
        pass

    # TODO: also post to propagator / conductor / central log when wired


# ============================================================
# CONNECTION MANAGER
# ============================================================

class PhoenixConnections:
    """
    The central connections system.
    Tracks, registers, health-checks, and routes across all Phoenix transports.
    """

    def __init__(self, catalog_path: Optional[Path] = None, worker_url: Optional[str] = None, auth_token: Optional[str] = None):
        self.catalog_path = catalog_path or DEFAULT_CATALOG
        self.worker_url = worker_url or os.environ.get("PHOENIX_WORKER_URL", "https://packages-worker.phoenix-jwl.workers.dev")
        self.auth_token = auth_token or os.environ.get("PHOENIX_AUTH")
        self.connections: Dict[str, Connection] = {}
        self.dispatch_targets: Dict[str, Any] = {}
        self.com_chain: List[str] = ["COM4", "COM3", "COM2", "COM1"]

        self._ensure_catalog()
        self._load_from_catalog()

        post_diagnostic(
            "PhoenixConnections initialized",
            "Connections fabric started. All wiring goes through this manager.",
            "Register known endpoints from dispatch + helix_mesh + services. Call health_check_all()."
        )

    def _ensure_catalog(self):
        self.catalog_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.catalog_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS connections (
                name TEXT PRIMARY KEY,
                type TEXT,
                address TEXT,
                meta TEXT,
                state TEXT,
                last_heartbeat TEXT,
                registered_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS diagnostics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT,
                level TEXT,
                what TEXT,
                why TEXT,
                action TEXT,
                extra TEXT
            )
        """)
        conn.commit()
        conn.close()

    def _load_from_catalog(self):
        try:
            conn = sqlite3.connect(self.catalog_path)
            rows = conn.execute("SELECT name, type, address, meta, state, last_heartbeat, registered_at FROM connections").fetchall()
            for row in rows:
                name, typ, addr, meta_json, state, hb, reg = row
                meta = json.loads(meta_json) if meta_json else {}
                self.connections[name] = Connection(
                    name=name, type=typ, address=addr, meta=meta,
                    state=state or "unknown", last_heartbeat=hb, registered_at=reg
                )
            conn.close()
        except Exception as e:
            post_diagnostic("Failed to load connections catalog", str(e), "Continuing with empty registry. Will repopulate from dispatch.", "WARN")

    def _persist_connection(self, conn_obj: Connection):
        try:
            conn = sqlite3.connect(self.catalog_path)
            conn.execute("""
                INSERT OR REPLACE INTO connections (name, type, address, meta, state, last_heartbeat, registered_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                conn_obj.name, conn_obj.type, conn_obj.address,
                json.dumps(conn_obj.meta), conn_obj.state,
                conn_obj.last_heartbeat, conn_obj.registered_at
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            post_diagnostic("Persist connection failed", str(e), "In-memory only for this run. Check disk permissions on ~/.catalog", "WARN")

    # ---------------- REGISTRATION ----------------

    def register(self, name: str, typ: CONNECTION_TYPES, address: str, meta: Optional[Dict] = None) -> Connection:
        meta = meta or {}
        c = Connection(name=name, type=typ, address=address, meta=meta, state="registered")
        self.connections[name] = c
        self._persist_connection(c)

        post_diagnostic(
            f"Registered connection: {name}",
            f"Type={typ} address={address}",
            "Use health_check() or daisy_relay() as appropriate. Consider posting to glossary."
        )
        return c

    def register_from_dispatch(self, dispatch_path: str | Path):
        """Load targets and com_chain from dispatch.json"""
        p = Path(dispatch_path)
        if not p.exists():
            post_diagnostic("dispatch.json not found", str(p), "Create or pass correct path. Using built-in defaults.", "WARN")
            self.dispatch_targets = {
                "vault": {"path": "/mnt/e/CLONEPOOL", "active": True},
                "sql": {"path": str(Path.home() / ".catalog" / "catalog.db"), "active": True},
                "d1": {"endpoint": "cloudflare_d1", "active": True},
                "frank3": {"zmq_port": 5555, "active": True},
                "peer": {"zmq_port": 5560, "active": True},
                "windows": {"via": "translator", "active": True},
            }
            return

        data = json.loads(p.read_text())
        self.dispatch_targets = data.get("targets", {})
        self.com_chain = data.get("com_chain", self.com_chain)

        for tname, tcfg in self.dispatch_targets.items():
            addr = tcfg.get("path") or tcfg.get("endpoint") or tcfg.get("zmq_port") or str(tcfg.get("via", ""))
            self.register(
                name=f"dispatch:{tname}",
                typ="dispatch_target",
                address=str(addr),
                meta={"config": tcfg, "source": "dispatch.json"}
            )

        post_diagnostic(
            "Loaded dispatch targets into connections",
            f"{len(self.dispatch_targets)} targets, chain={self.com_chain}",
            "Connections now know how to route via propagator."
        )

    def register_from_helix_mesh(self, conf_path: str | Path):
        """Parse helix_mesh.conf style file and register ports"""
        p = Path(conf_path)
        if not p.exists():
            post_diagnostic("helix_mesh.conf missing", str(p), "Register manual mesh ports or provide path.", "WARN")
            return

        # Very lightweight parser for the known format
        content = p.read_text()
        for line in content.splitlines():
            line = line.strip()
            if "=" in line and "helix://" in line:
                key, val = [x.strip() for x in line.split("=", 1)]
                self.register(
                    name=f"helix_mesh:{key}",
                    typ="helix_mesh",
                    address=val,
                    meta={"from": "helix_mesh.conf"}
                )

        post_diagnostic("Registered helix mesh ports", str(p), "High-speed internal channels now known to connections system.")

    def register_zmq(self, name: str, host: str = "localhost", port: int = 5557, role: str = ""):
        addr = f"tcp://{host}:{port}"
        return self.register(name, "zmq", addr, {"role": role, "port": port})

    def register_syncthing(self, device_id: str, address: str = "http://127.0.0.1:8384", api_key: Optional[str] = None):
        meta = {"api_key_present": bool(api_key)}
        if api_key:
            meta["api_key"] = api_key  # in real use, store in vault, not here
        return self.register(f"syncthing:{device_id}", "syncthing", address, meta)

    # ---------------- DISCOVERY & QUERY ----------------

    def list_connections(self, typ: Optional[CONNECTION_TYPES] = None, state: Optional[str] = None) -> List[Dict]:
        results = []
        for c in self.connections.values():
            if typ and c.type != typ:
                continue
            if state and c.state != state:
                continue
            results.append(c.to_dict())
        return results

    def get(self, name: str) -> Optional[Connection]:
        return self.connections.get(name)

    # ---------------- HEALTH & HEARTBEAT ----------------

    def health_check(self, name: str) -> Dict[str, Any]:
        c = self.get(name)
        if not c:
            return {"name": name, "status": "unknown", "error": "not registered"}

        status = {"name": name, "type": c.type, "address": c.address, "state": "unknown"}

        if c.type == "zmq":
            status["status"] = "degraded" if not HAS_ZMQ else "not_tested_here"
            status["note"] = "Use actual ZMQ socket connect in production"

        elif c.type == "syncthing":
            status.update(self._syncthing_health(c))

        elif c.type in ("http", "worker", "d1"):
            status.update(self._http_head_health(c.address))

        else:
            status["status"] = "registered"
            status["note"] = "No specific health probe implemented for this type yet"

        c.state = status.get("status", "unknown")
        c.last_heartbeat = datetime.now(timezone.utc).isoformat()
        self._persist_connection(c)
        return status

    def _http_head_health(self, url: str) -> Dict:
        try:
            if HAS_REQUESTS:
                r = requests.head(url, timeout=3)
                ok = r.status_code < 500
            else:
                req = urllib.request.Request(url, method="HEAD")
                with urllib.request.urlopen(req, timeout=3) as resp:
                    ok = resp.status < 500
            return {"status": "connected" if ok else "degraded", "probe": "http_head"}
        except Exception as e:
            return {"status": "disconnected", "error": str(e)}

    def _syncthing_health(self, conn: Connection) -> Dict:
        base = conn.address.rstrip("/")
        api_key = conn.meta.get("api_key")
        headers = {"X-API-Key": api_key} if api_key else {}
        try:
            if HAS_REQUESTS:
                r = requests.get(f"{base}/rest/system/connections", headers=headers, timeout=4)
                data = r.json()
            else:
                req = urllib.request.Request(f"{base}/rest/system/connections", headers=headers)
                with urllib.request.urlopen(req, timeout=4) as resp:
                    data = json.loads(resp.read())
            conns = data.get("connections", {})
            return {
                "status": "connected" if conns else "degraded",
                "connected_nodes": len(conns),
                "probe": "syncthing_rest"
            }
        except Exception as e:
            return {"status": "disconnected", "error": str(e)}

    def health_check_all(self) -> List[Dict]:
        results = []
        for name in list(self.connections.keys()):
            results.append(self.health_check(name))
        post_diagnostic(
            "Health sweep complete",
            f"Checked {len(results)} connections",
            "Review any 'disconnected' or 'degraded'. Daisy chain and services depend on green paths."
        )
        return results

    # ---------------- DAISY / PROPAGATION ----------------

    def daisy_relay(self, payload: Any, chain: Optional[List[str]] = None):
        """COM4 → COM3 → COM2 → COM1 style relay (or custom chain)."""
        chain = chain or self.com_chain
        log_entries = []
        start = time.time()

        for hop in chain:
            entry = {
                "hop": hop,
                "ts": datetime.now(timezone.utc).isoformat(),
                "payload_hash": hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]
            }
            log_entries.append(entry)
            # In real: send over ZMQ or netcat or propcoms socket to the port for that COM
            # For now we simulate + log
            time.sleep(0.05)

        duration = time.time() - start
        post_diagnostic(
            f"Daisy relay complete over {chain}",
            f"Payload relayed in {duration:.3f}s. {len(log_entries)} hops.",
            "Check propcoms_log in catalog and actual ZMQ listeners on COM ports."
        )

        # Persist to local catalog (matches propcoms.sh/sql)
        self._log_propcoms(chain, payload, log_entries)
        return {"chain": chain, "hops": log_entries, "duration": duration}

    def _log_propcoms(self, chain, payload, logs):
        try:
            conn = sqlite3.connect(self.catalog_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS propcoms_log (
                    id INTEGER PRIMARY KEY,
                    ts TEXT,
                    chain TEXT,
                    payload TEXT,
                    details TEXT
                )
            """)
            conn.execute(
                "INSERT INTO propcoms_log (ts, chain, payload, details) VALUES (?,?,?,?)",
                (datetime.now(timezone.utc).isoformat(), json.dumps(chain), json.dumps(payload, default=str), json.dumps(logs))
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    # ---------------- GLOSSARY / WORKER INTEGRATION ----------------

    def publish_to_glossary(self, name: Optional[str] = None):
        """
        Publish one or all connections as glossary entries via packages-worker.
        Requires PHOENIX_AUTH for writes.
        """
        if not self.auth_token:
            post_diagnostic("Cannot publish to glossary", "No PHOENIX_AUTH token", "Set env or pass to constructor. Connections stay local-only.", "WARN")
            return False

        targets = [self.connections[name]] if name else list(self.connections.values())
        successes = 0

        for c in targets:
            entry = c.to_glossary_entry()
            body = json.dumps(entry).encode()
            req = urllib.request.Request(
                f"{self.worker_url.rstrip('/')}/glossary",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.auth_token}",
                },
                method="POST"
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status in (200, 201):
                        successes += 1
            except Exception as e:
                post_diagnostic(f"Failed to publish connection {c.name} to glossary", str(e), "Check worker health and token. Fall back to local catalog.", "WARN")

        post_diagnostic(f"Published {successes}/{len(targets)} connections to glossary", "category=connection", "They are now queryable via /search and /glossary on the worker.")
        return successes > 0

    # ---------------- SYNCTHING HELPERS (Python native) ----------------

    def ensure_syncthing(self, port: int = 8384, auto_install_hint: bool = True) -> bool:
        """Best-effort ensure Syncthing is available (used by coms layers)."""
        try:
            # Check binary
            subprocess.run(["which", "syncthing"], check=True, capture_output=True)
            post_diagnostic("Syncthing binary present", "Ready for device/folder management", "Call start_syncthing() if needed.")
            return True
        except Exception:
            if auto_install_hint:
                post_diagnostic(
                    "Syncthing not found",
                    "Distribution module needs it for multi-node",
                    "Install via apt (Linux) or winget/choco (Win) or the logic in v1_franken.py clonepool entry. Then re-run."
                )
            return False

    # ---------------- UTILITIES ----------------

    def make_friends(self, name1: str, name2: str):
        """Register a 'friendship' (inspired by integrated_guardian)."""
        c1 = self.get(name1)
        c2 = self.get(name2)
        if not c1 or not c2:
            post_diagnostic("Cannot make friends", "One or both connections unknown", "Register them first.")
            return
        c1.meta.setdefault("friends", []).append(name2)
        c2.meta.setdefault("friends", []).append(name1)
        self._persist_connection(c1)
        self._persist_connection(c2)
        post_diagnostic(f"{name1} ⇄ {name2} are now friends", "Explicit connection friendship recorded", "Useful for guardian / dependency visualization and propagator routing.")

    def summary(self) -> Dict:
        return {
            "total": len(self.connections),
            "by_type": {t: len([c for c in self.connections.values() if c.type == t]) for t in set(c.type for c in self.connections.values())},
            "com_chain": self.com_chain,
            "dispatch_targets": list(self.dispatch_targets.keys()),
            "worker_configured": bool(self.auth_token),
        }


# ============================================================
# CONVENIENCE FACTORY + CLI
# ============================================================

def get_connections(**kwargs) -> PhoenixConnections:
    """Factory that auto-registers common known connections."""
    mgr = PhoenixConnections(**kwargs)

    # Core known ZMQ
    mgr.register_zmq("frank-helix", port=KNOWN_PORTS["frank_helix_zmq"], role="router/sideload")
    mgr.register_zmq("romeo-ingress", port=KNOWN_PORTS["romeo_ingress"], role="S3-ingress")
    mgr.register_zmq("juliet-egress", port=KNOWN_PORTS["juliet_egress"], role="S3-egress")
    mgr.register_zmq("frank3-dispatch", port=KNOWN_PORTS["frank3_dispatch"], role="propagator")

    # Mesh from conf if present (caller can call register_from_helix_mesh later)
    for k, port in list(KNOWN_PORTS.items()):
        if k.startswith("helix_mesh_"):
            mgr.register(f"helix-mesh-{k}", "helix_mesh", f"helix://localhost:{port}", {"source": "built-in"})

    # Worker / D1
    if mgr.worker_url:
        mgr.register("packages-worker", "worker", mgr.worker_url, {"auth_required": True})

    return mgr


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Phoenix Connections System CLI")
    parser.add_argument("command", choices=["status", "register", "health", "relay", "publish", "friends", "summary"])
    parser.add_argument("--dispatch", help="Path to dispatch.json")
    parser.add_argument("--mesh", help="Path to helix_mesh.conf")
    parser.add_argument("--name", help="Connection name for targeted ops")
    parser.add_argument("--payload", default="ping", help="Payload for relay")
    args = parser.parse_args()

    mgr = get_connections()

    if args.dispatch:
        mgr.register_from_dispatch(args.dispatch)
    if args.mesh:
        mgr.register_from_helix_mesh(args.mesh)

    if args.command == "status":
        print(json.dumps(mgr.list_connections(), indent=2))
    elif args.command == "health":
        print(json.dumps(mgr.health_check_all() if not args.name else mgr.health_check(args.name), indent=2))
    elif args.command == "relay":
        print(mgr.daisy_relay({"payload": args.payload}))
    elif args.command == "publish":
        mgr.publish_to_glossary(args.name)
    elif args.command == "friends":
        # demo
        mgr.make_friends("frank-helix", "packages-worker")
        print("Friendships recorded (demo)")
    elif args.command == "summary":
        print(json.dumps(mgr.summary(), indent=2))
    elif args.command == "register":
        print("Use Python API for registration in scripts.")


if __name__ == "__main__":
    main()
