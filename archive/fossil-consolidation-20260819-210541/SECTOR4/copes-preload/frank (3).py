#!/usr/bin/env python3
"""
frank.py — Phoenix DevOps OS
Frank: intake authority + immutable audit log + template processor + auto-venv.
Frank does NOT translate. Frank does NOT orchestrate processes.
He intakes. Helix handles everything after.
jwl247 / United Systems / GPL v3
"""

import os
import sys
import json
import hashlib
import sqlite3
import subprocess
import threading
import time
from pathlib import Path
from datetime import datetime, timezone

def _now(): return datetime.now(timezone.utc).isoformat()
from typing import Any

FRANK_VERSION = "1.0.0"

# ── Paths ─────────────────────────────────────────────────────────────────────

PHOENIX_HOME  = Path(os.environ.get("PHOENIX_HOME",  Path.home() / "Phoenix"))
FRANK_LOG_DIR = Path(os.environ.get("FRANK_LOG_DIR", PHOENIX_HOME / "logs"))
FRANK_DB      = Path(os.environ.get("FRANK_DB",      PHOENIX_HOME / "db" / "frank.db"))
TEMPLATE_DIR  = Path(os.environ.get("TEMPLATE_DIR",  PHOENIX_HOME / "templates"))
VENV_PATH     = Path(os.environ.get("VENV_PATH",     PHOENIX_HOME / ".venv"))

# ── Frank never moves ─────────────────────────────────────────────────────────

FRANK_ANCHOR  = str(Path(__file__).resolve())

# ── Audit log entry ───────────────────────────────────────────────────────────

class AuditEntry:
    def __init__(self, action: str, subject: str, meta: dict = None,
                 result: str = "ok", error: str = None):
        self.id        = hashlib.sha256(
            f"{action}{subject}{time.time_ns()}".encode()
        ).hexdigest()[:16]
        self.timestamp = _now()
        self.action    = action
        self.subject   = subject
        self.meta      = meta or {}
        self.result    = result
        self.error     = error

    def to_dict(self) -> dict:
        return {
            "id":        self.id,
            "timestamp": self.timestamp,
            "action":    self.action,
            "subject":   self.subject,
            "meta":      self.meta,
            "result":    self.result,
            "error":     self.error,
        }

# ── Frank ─────────────────────────────────────────────────────────────────────

class Frank:
    """
    Frank — intake authority and immutable audit logger.
    Frank brings things in and writes everything down.
    Frank never moves. Frank is where Frank is.
    """

    def __init__(self):
        FRANK_LOG_DIR.mkdir(parents=True, exist_ok=True)
        FRANK_DB.parent.mkdir(parents=True, exist_ok=True)
        TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
        self._lock    = threading.RLock()
        self._helix   = None   # lazy — imported after init to avoid circular
        self._init_db()
        self._log(AuditEntry("frank.init", FRANK_ANCHOR, {
            "version": FRANK_VERSION,
            "phoenix_home": str(PHOENIX_HOME),
        }))

    # ── DB ────────────────────────────────────────────────────────────────────

    def _init_db(self):
        with sqlite3.connect(FRANK_DB) as cx:
            cx.executescript("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id        TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    action    TEXT NOT NULL,
                    subject   TEXT NOT NULL,
                    meta      TEXT,
                    result    TEXT NOT NULL DEFAULT 'ok',
                    error     TEXT
                );
                CREATE TABLE IF NOT EXISTS intakes (
                    id         TEXT PRIMARY KEY,
                    timestamp  TEXT NOT NULL,
                    name       TEXT NOT NULL,
                    tav        TEXT,
                    template   TEXT,
                    source     TEXT,
                    status     TEXT NOT NULL DEFAULT 'pending',
                    meta       TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_action  ON audit_log(action);
                CREATE INDEX IF NOT EXISTS idx_ts      ON audit_log(timestamp);
                CREATE INDEX IF NOT EXISTS idx_subject ON audit_log(subject);
            """)

    # ── Audit log — IMMUTABLE ─────────────────────────────────────────────────

    def _log(self, entry: AuditEntry):
        """Write to immutable audit log. Never delete. Never update."""
        with self._lock:
            with sqlite3.connect(FRANK_DB) as cx:
                cx.execute(
                    "INSERT OR IGNORE INTO audit_log "
                    "(id, timestamp, action, subject, meta, result, error) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (entry.id, entry.timestamp, entry.action, entry.subject,
                     json.dumps(entry.meta), entry.result, entry.error)
                )
            log_file = FRANK_LOG_DIR / f"frank_{datetime.now(timezone.utc).strftime('%Y%m%d')}.log"
            with open(log_file, "a") as f:
                f.write(json.dumps(entry.to_dict()) + "\n")

    # ── Helix lazy loader ─────────────────────────────────────────────────────

    def _get_helix(self):
        if self._helix is None:
            try:
                import helix as helix_mod
                self._helix = helix_mod._get_global_helix()
            except ImportError:
                pass
        return self._helix

    # ── Template loader ───────────────────────────────────────────────────────

    def load_template(self, name: str) -> dict | None:
        path = TEMPLATE_DIR / f"{name}.json"
        if not path.exists():
            self._log(AuditEntry("frank.template.missing", name, result="error",
                                  error=f"Template not found: {path}"))
            return None
        with open(path) as f:
            tpl = json.load(f)
        self._log(AuditEntry("frank.template.load", name, {"path": str(path)}))
        return tpl

    def list_templates(self) -> list:
        return [p.stem for p in TEMPLATE_DIR.glob("*.json")]

    # ── Core intake ───────────────────────────────────────────────────────────

    def intake(self, name: str, data: Any, template_name: str = None,
               source: str = None, meta: dict = None) -> dict:
        """
        Frank's primary job — bring something in.
        Validates against template if provided, then hands to Helix.
        Returns intake receipt.
        """
        intake_id = hashlib.sha256(
            f"{name}{time.time_ns()}".encode()
        ).hexdigest()[:16]

        self._log(AuditEntry("frank.intake.start", name, {
            "id": intake_id, "template": template_name, "source": source
        }))

        template = None
        if template_name:
            template = self.load_template(template_name)
            if template is None:
                self._log(AuditEntry("frank.intake.failed", name,
                                      {"reason": "template missing"},
                                      result="error"))
                return {"ok": False, "error": f"Template not found: {template_name}"}

            valid, err = self._validate(data, template)
            if not valid:
                self._log(AuditEntry("frank.intake.validation_failed", name,
                                      {"error": err}, result="error", error=err))
                return {"ok": False, "error": err}

        helix = self._get_helix()
        tav   = None
        if helix:
            rec = helix.store(name, data, meta=meta or {}, note=f"intake:{intake_id}")
            tav = rec.tav

        with sqlite3.connect(FRANK_DB) as cx:
            cx.execute(
                "INSERT INTO intakes (id, timestamp, name, tav, template, source, status, meta) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (intake_id, _now(), name, tav,
                 template_name, source, "complete", json.dumps(meta or {}))
            )

        receipt = {
            "ok":        True,
            "id":        intake_id,
            "name":      name,
            "tav":       tav,
            "template":  template_name,
            "timestamp": _now(),
        }

        self._log(AuditEntry("frank.intake.complete", name, receipt))
        return receipt

    def intake_file(self, filepath: str, template_name: str = None) -> dict:
        """Intake a file from disk."""
        path = Path(filepath)
        if not path.exists():
            return {"ok": False, "error": f"File not found: {filepath}"}

        with open(path, "rb") as f:
            raw = f.read()

        try:
            data = json.loads(raw)
        except Exception:
            data = raw.decode(errors="replace")

        companions = self._find_companions(path)
        meta = {
            "filepath":   str(path.resolve()),
            "size":       path.stat().st_size,
            "companions": companions,
        }

        result = self.intake(path.name, data, template_name, str(path), meta)

        for companion in companions:
            self.intake_file(companion, template_name)

        return result

    def _find_companions(self, path: Path) -> list:
        """Files that belong together travel together."""
        stem = path.stem
        companion_exts = [".service", ".conf", ".env", ".yaml", ".yml", ".toml"]
        companions = []
        for ext in companion_exts:
            c = path.parent / f"{stem}{ext}"
            if c.exists() and c != path:
                companions.append(str(c))
        return companions

    # ── Template validation ───────────────────────────────────────────────────

    def _validate(self, data: Any, template: dict) -> tuple[bool, str | None]:
        required = template.get("required_fields", [])
        if required and not isinstance(data, dict):
            return False, "Data must be a dict for field validation"
        for field in required:
            if field not in data:
                return False, f"Missing required field: {field}"
        allowed_types = template.get("type")
        if allowed_types:
            type_map = {"str": str, "dict": dict, "list": list,
                        "int": int, "float": float, "bool": bool}
            expected = type_map.get(allowed_types)
            if expected and not isinstance(data, expected):
                return False, f"Expected type {allowed_types}, got {type(data).__name__}"
        return True, None

    # ── Auto-venv ─────────────────────────────────────────────────────────────

    def ensure_venv(self, requirements: list = None) -> dict:
        """
        Frank standard — auto-venv. Called on bootstrap.
        Creates .venv if missing, installs requirements if provided.
        """
        result = {"ok": True, "created": False, "installed": [], "errors": []}

        self._log(AuditEntry("frank.venv.check", str(VENV_PATH)))

        if not VENV_PATH.exists():
            self._log(AuditEntry("frank.venv.create", str(VENV_PATH)))
            ret = subprocess.run(
                [sys.executable, "-m", "venv", str(VENV_PATH)],
                capture_output=True, text=True
            )
            if ret.returncode != 0:
                err = ret.stderr.strip()
                self._log(AuditEntry("frank.venv.create.failed", str(VENV_PATH),
                                      result="error", error=err))
                return {"ok": False, "error": err}
            result["created"] = True
            self._log(AuditEntry("frank.venv.created", str(VENV_PATH)))

        if requirements:
            pip = VENV_PATH / "bin" / "pip"
            if not pip.exists():
                pip = VENV_PATH / "Scripts" / "pip.exe"
            for pkg in requirements:
                ret = subprocess.run(
                    [str(pip), "install", pkg],
                    capture_output=True, text=True
                )
                if ret.returncode == 0:
                    result["installed"].append(pkg)
                    self._log(AuditEntry("frank.venv.install", pkg))
                else:
                    err = ret.stderr.strip()
                    result["errors"].append({"pkg": pkg, "error": err})
                    self._log(AuditEntry("frank.venv.install.failed", pkg,
                                          result="error", error=err))

        return result

    # ── Audit queries (read-only) ─────────────────────────────────────────────

    def audit_tail(self, n: int = 20) -> list:
        with sqlite3.connect(FRANK_DB) as cx:
            rows = cx.execute(
                "SELECT id, timestamp, action, subject, result, error "
                "FROM audit_log ORDER BY timestamp DESC LIMIT ?", (n,)
            ).fetchall()
        return [{"id": r[0], "ts": r[1], "action": r[2],
                 "subject": r[3], "result": r[4], "error": r[5]}
                for r in rows]

    def audit_search(self, action: str = None, subject: str = None) -> list:
        query  = "SELECT * FROM audit_log WHERE 1=1"
        params = []
        if action:
            query += " AND action LIKE ?"
            params.append(f"%{action}%")
        if subject:
            query += " AND subject LIKE ?"
            params.append(f"%{subject}%")
        query += " ORDER BY timestamp DESC LIMIT 100"
        with sqlite3.connect(FRANK_DB) as cx:
            rows = cx.execute(query, params).fetchall()
        cols = ["id","timestamp","action","subject","meta","result","error"]
        return [dict(zip(cols, r)) for r in rows]

    def intake_history(self, name: str = None) -> list:
        query  = "SELECT * FROM intakes WHERE 1=1"
        params = []
        if name:
            query += " AND name LIKE ?"
            params.append(f"%{name}%")
        query += " ORDER BY timestamp DESC LIMIT 100"
        with sqlite3.connect(FRANK_DB) as cx:
            rows = cx.execute(query, params).fetchall()
        cols = ["id","timestamp","name","tav","template","source","status","meta"]
        return [dict(zip(cols, r)) for r in rows]

    def status(self) -> dict:
        with sqlite3.connect(FRANK_DB) as cx:
            audit_count  = cx.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
            intake_count = cx.execute("SELECT COUNT(*) FROM intakes").fetchone()[0]
            recent       = cx.execute(
                "SELECT action, timestamp FROM audit_log ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()
        helix = self._get_helix()
        return {
            "frank_version":  FRANK_VERSION,
            "anchor":         FRANK_ANCHOR,
            "phoenix_home":   str(PHOENIX_HOME),
            "audit_entries":  audit_count,
            "intake_entries": intake_count,
            "last_action":    recent[0] if recent else None,
            "last_action_ts": recent[1] if recent else None,
            "templates":      self.list_templates(),
            "venv_exists":    VENV_PATH.exists(),
            "helix_online":   helix is not None,
            "helix_stats":    helix.stats() if helix else None,
        }


# ── Global Frank instance ─────────────────────────────────────────────────────

_frank: Frank | None = None

def get_frank() -> Frank:
    global _frank
    if _frank is None:
        _frank = Frank()
    return _frank


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Frank — Phoenix intake authority")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("status",    help="Frank status")
    sub.add_parser("templates", help="List templates")

    si = sub.add_parser("intake", help="Intake data")
    si.add_argument("name")
    si.add_argument("data")
    si.add_argument("--template", default=None)

    sf = sub.add_parser("intake-file", help="Intake a file")
    sf.add_argument("filepath")
    sf.add_argument("--template", default=None)

    sv = sub.add_parser("venv", help="Ensure venv")
    sv.add_argument("--install", nargs="*", default=None)

    sa = sub.add_parser("audit", help="Show audit tail")
    sa.add_argument("--n", type=int, default=20)

    ss = sub.add_parser("search", help="Search audit log")
    ss.add_argument("--action",  default=None)
    ss.add_argument("--subject", default=None)

    args = parser.parse_args()
    f = get_frank()

    if args.cmd == "status":
        print(json.dumps(f.status(), indent=2))

    elif args.cmd == "templates":
        print(json.dumps(f.list_templates(), indent=2))

    elif args.cmd == "intake":
        try:
            data = json.loads(args.data)
        except Exception:
            data = args.data
        print(json.dumps(f.intake(args.name, data, args.template), indent=2))

    elif args.cmd == "intake-file":
        print(json.dumps(f.intake_file(args.filepath, args.template), indent=2))

    elif args.cmd == "venv":
        print(json.dumps(f.ensure_venv(args.install), indent=2))

    elif args.cmd == "audit":
        entries = f.audit_tail(args.n)
        for e in entries:
            print(f"[{e['ts']}] {e['action']} → {e['subject']} ({e['result']})")

    elif args.cmd == "search":
        entries = f.audit_search(args.action, args.subject)
        for e in entries:
            print(json.dumps(e, indent=2))

    else:
        parser.print_help()
