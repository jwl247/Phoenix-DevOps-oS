#!/usr/bin/env python3
"""
integrated_guardian.py — the ring guardian (jwl247 / Phoenix DevOps LLC, GPL v3)

Restored 2026-09-28 from archive/fossil-consolidation-20260819-210541/SECTOR4/
coms4/integrated_guardian.py (the four ring copies were byte-identical) and
made a real service. What it does, unchanged in spirit:

  InstallerGuardian  scans config files, records every port and path each
                     service claims, and flags two services claiming the same
                     port or path — unless they are registered friends.
  FileGuardian       the guardian instance: config, shared intel, threat
                     scores, heartbeat, and the `query()` face the ring uses.

What changed to make it run persistently and correctly on a real box:
  * state files live under PHOENIX_GUARDIAN_HOME (default
    /var/lib/phoenix/guardian), never next to the script;
  * the scan list is PHOENIX_GUARDIAN_SCAN_DIRS (colon-separated; default:
    the Phoenix unit dir, /etc/systemd/system, /etc/default) instead of a
    hardcoded WAMP/XAMPP/apache list;
  * port detection no longer matches every "12:34" in a file (the old
    ":(\\d{2,5})" pattern reported clock times and dates as ports);
  * the team is registered as friends on first run (helix, phoenix-paging,
    helix-vram, helix-guardian, phoenix-mesh) so their shared paths are not
    reported as conflicts;
  * `daemon` writes heartbeat.json every cycle (verify-team.sh reads its age),
    honours PHOENIX_GUARDIAN_INTERVAL, exits cleanly on SIGTERM, and `--once`
    runs one cycle;
  * silent `except: pass` replaced with logged errors.

    integrated_guardian.py [guardian_N] daemon [--once]
    integrated_guardian.py status | heartbeat | installer scan|conflicts|ports
"""
import getpass
import hashlib
import json
import os
import re
import signal
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HOME = Path(os.environ.get("PHOENIX_GUARDIAN_HOME") or "/var/lib/phoenix/guardian")
SCAN_DIRS = [d for d in os.environ.get(
    "PHOENIX_GUARDIAN_SCAN_DIRS",
    "/opt/phoenix/sector3/services:/etc/systemd/system:/etc/default").split(":") if d]
INTERVAL = int(os.environ.get("PHOENIX_GUARDIAN_INTERVAL", "300"))
CONFIG_EXT = (".conf", ".ini", ".cfg", ".env", ".service", ".socket", ".timer", ".yaml", ".yml", ".toml", ".json")
TEAM = ["helix", "phoenix-paging", "helix-vram", "helix-guardian", "phoenix-mesh", "phoenix-hands"]

_PORT_PATTERNS = [
    re.compile(r"\b[Pp]ort\s*[:=]\s*(\d{2,5})\b"),
    re.compile(r"\bListen\s+(?:[\w.:]+:)?(\d{2,5})\b"),
    re.compile(r"\bPORT\s*[:=]\s*(\d{2,5})\b"),
    re.compile(r"\b(?:localhost|0\.0\.0\.0|127\.0\.0\.1|\[::\]|\[::1\]|\d{1,3}(?:\.\d{1,3}){3}):(\d{2,5})\b"),
    re.compile(r"hostfwd=tcp:[^-]*:(\d{2,5})-"),
]
_PATH_PATTERNS = [
    re.compile(r"\b[Pp]ath\s*[:=]\s*\"?(/[\w/.-]+)\"?"),
    re.compile(r"\bDocumentRoot\s+\"?(/[\w/.-]+)\"?"),
    re.compile(r"\b(?:Exec(?:Start|Stop|Reload)|WorkingDirectory|EnvironmentFile|StateDirectory|ReadWritePaths)\s*=\s*-?\"?(/[\w/.-]+)"),
    re.compile(r"\b(?:HELIX_ORIGIN|HELIX_B_IMG|HELIX_B_DEV|HELIX_MOUNT|HELIX_VRAM_STRAND_B|HELIX_VRAM_SOCK)\s*=\s*(/[\w/.-]+)"),
]


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(msg):
    print(f"[{_now()}] guardian: {msg}", flush=True)


class InstallerGuardian:
    """The tag-along who knows everyone in every department: who claims which
    port and path, and which pairs are friends."""

    def __init__(self, registry_file=None):
        HOME.mkdir(parents=True, exist_ok=True)
        self.registry_file = Path(registry_file) if registry_file else HOME / "installer_registry.json"
        self.registry = self.load_registry()
        self.conflicts = []
        self.suggestions = []
        for i, a in enumerate(TEAM):
            for b in TEAM[i + 1:]:
                self._befriend(a, b)

    def load_registry(self):
        if self.registry_file.exists():
            try:
                with open(self.registry_file) as f:
                    return json.load(f)
            except (OSError, ValueError) as e:
                _log(f"registry unreadable ({e}); starting a fresh one")
        return {"configs": {}, "ports": {}, "paths": {}, "services": {}, "conflicts_log": [], "friendships": {}}

    def save_registry(self):
        tmp = self.registry_file.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(self.registry, f, indent=2)
        os.replace(tmp, self.registry_file)

    # ---------------------------------------------------------- friends
    def _befriend(self, a, b):
        fr = self.registry["friendships"]
        fr.setdefault(a, [])
        fr.setdefault(b, [])
        if b not in fr[a]:
            fr[a].append(b)
        if a not in fr[b]:
            fr[b].append(a)

    def make_friends(self, service1, service2):
        self._befriend(service1, service2)
        self.save_registry()
        _log(f"{service1} and {service2} are now friends")

    def are_friends(self, service1, service2):
        return service2 in self.registry["friendships"].get(service1, [])

    def all_friends(self, services):
        """True when every pair in `services` is registered friends."""
        s = list(dict.fromkeys(services))
        return len(s) >= 1 and all(self.are_friends(a, b) for i, a in enumerate(s) for b in s[i + 1:])

    # ---------------------------------------------------------- scanning
    @staticmethod
    def service_name_for(filepath):
        """A stable service name for a config file: the unit name for
        systemd units, the file stem otherwise."""
        p = Path(filepath)
        if p.suffix in (".service", ".socket", ".timer"):
            return p.stem
        return p.stem.lower()

    def scan_config_file(self, filepath):
        config_data = {"filepath": str(filepath), "filename": Path(filepath).name,
                       "type": self.detect_config_type(filepath), "ports": [], "paths": [],
                       "settings": {}, "scanned": _now()}
        try:
            with open(filepath, "r", errors="replace") as f:
                content = f.read()
            ports = set()
            for pat in _PORT_PATTERNS:
                for m in pat.findall(content):
                    n = int(m)
                    if 1 <= n <= 65535:
                        ports.add(n)
            paths = set()
            for pat in _PATH_PATTERNS:
                paths.update(pat.findall(content))
            config_data["ports"] = sorted(ports)
            config_data["paths"] = sorted(paths)
        except OSError as e:
            config_data["error"] = str(e)
        return config_data

    @staticmethod
    def detect_config_type(filepath):
        name = Path(filepath).name.lower()
        path_str = str(filepath).lower()
        for needle, kind in (("apache", "Apache"), ("httpd", "Apache"), ("nginx", "Nginx"), ("php", "PHP"),
                             ("mysql", "MySQL/MariaDB"), ("mariadb", "MySQL/MariaDB"), ("docker", "Docker")):
            if needle in name:
                return kind
        if name.endswith(".service"):
            return "systemd"
        if ".env" in name or name.startswith("helix") or name.startswith("phoenix"):
            return "Environment"
        for needle, kind in (("helix", "Helix"), ("lifefirst", "LifeFirst"), ("ollama", "Ollama"), ("phoenix", "Phoenix")):
            if needle in path_str:
                return kind
        return "Generic"

    def register_config(self, filepath, service_name=None):
        config_data = self.scan_config_file(filepath)
        config_hash = hashlib.sha256(str(filepath).encode()).hexdigest()
        service = service_name or self.service_name_for(filepath)
        # re-registering the same file replaces its old claims instead of stacking them
        self._unclaim(config_hash)
        self.registry["configs"][config_hash] = config_data
        for port in config_data["ports"]:
            self.registry["ports"].setdefault(str(port), [])
            self.registry["ports"][str(port)].append({"config": config_hash, "service": service, "file": str(filepath)})
        for path in config_data["paths"]:
            self.registry["paths"].setdefault(path, [])
            self.registry["paths"][path].append({"config": config_hash, "service": service, "file": str(filepath)})
        conflicts = self.check_conflicts(config_hash)
        return config_hash, conflicts

    def _unclaim(self, config_hash):
        for table in ("ports", "paths"):
            for k in list(self.registry[table]):
                self.registry[table][k] = [u for u in self.registry[table][k] if u["config"] != config_hash]
                if not self.registry[table][k]:
                    del self.registry[table][k]

    def check_conflicts(self, config_hash):
        conflicts = []
        config = self.registry["configs"][config_hash]
        for port in config["ports"]:
            users = self.registry["ports"].get(str(port), [])
            services = sorted({u["service"] for u in users})
            if len(services) > 1:
                conflicts.append({"type": "port", "value": port, "services": services,
                                  "files": sorted({u["file"] for u in users}), "friends": self.all_friends(services)})
        for path in config["paths"]:
            users = self.registry["paths"].get(path, [])
            services = sorted({u["service"] for u in users})
            if len(services) > 1:
                conflicts.append({"type": "path", "value": path, "services": services,
                                  "files": sorted({u["file"] for u in users}), "friends": self.all_friends(services)})
        return conflicts

    def suggest_alternatives(self, conflict):
        suggestions = []
        if conflict["type"] == "port":
            port = int(conflict["value"])
            for offset in (1, 10, 100, 1000):
                alt = port + offset
                if str(alt) not in self.registry["ports"] and alt < 65535:
                    suggestions.append({"type": "port", "original": port, "alternative": alt, "reason": f"Port {port} + {offset}"})
                    if len(suggestions) >= 3:
                        break
        else:
            base = Path(conflict["value"])
            for i in range(1, 4):
                alt = f"{base.parent}/{base.stem}_{i}{base.suffix}"
                if alt not in self.registry["paths"]:
                    suggestions.append({"type": "path", "original": str(base), "alternative": alt, "reason": f"Numbered variant {i}"})
        return suggestions

    def resolve_conflicts(self, quiet=False):
        """Every real conflict (different services, not all friends) with
        suggestions. Friend conflicts are listed but not counted."""
        real, friendly = [], []
        for table, kind in (("ports", "port"), ("paths", "path")):
            for value, users in self.registry[table].items():
                services = sorted({u["service"] for u in users})
                if len(services) < 2:
                    continue
                c = {"type": kind, "value": value, "services": services,
                     "files": sorted({u["file"] for u in users}), "friends": self.all_friends(services)}
                (friendly if c["friends"] else real).append(c)
        self.registry["conflicts_log"] = self.registry["conflicts_log"][-200:] + [
            {"at": _now(), "real": len(real), "friendly": len(friendly)}]
        if not quiet:
            if not real:
                _log(f"no conflicts ({len(friendly)} shared by friends)")
            for i, c in enumerate(real, 1):
                _log(f"conflict #{i} {c['type']} {c['value']}: {', '.join(c['services'])} <- {', '.join(c['files'])}")
                for s in self.suggest_alternatives(c):
                    _log(f"    alternative: {s['alternative']} ({s['reason']})")
        return [{"conflict": c, "suggestions": self.suggest_alternatives(c)} for c in real]

    def auto_scan(self, directories=None):
        directories = directories if directories is not None else SCAN_DIRS
        found = []
        for directory in directories:
            d = Path(directory)
            if not d.is_dir():
                continue
            for root, dirs, files in os.walk(d):
                dirs[:] = [x for x in dirs if not x.startswith(".")]
                for file in files:
                    if file.lower().endswith(CONFIG_EXT):
                        fp = Path(root) / file
                        if fp.is_symlink() and not fp.exists():
                            continue
                        try:
                            self.register_config(fp)
                            found.append(str(fp))
                        except OSError as e:
                            _log(f"could not read {fp}: {e}")
        self.save_registry()
        return found

    def introduce_to_port_guardian(self, port_guardian):
        configs = self.auto_scan()
        reg = port_guardian.config.setdefault("registered_services", {})
        for port, users in self.registry["ports"].items():
            for user in users:
                svc = user["service"]
                entry = reg.setdefault(svc, {"ports": [], "config_file": user["file"],
                                             "registered_by": "installer_guardian", "registered_at": _now()})
                if int(port) not in entry["ports"]:
                    entry["ports"].append(int(port))
        port_guardian.save_config()
        return configs


class FileGuardian:
    """The guardian instance for this ring."""

    def __init__(self, config_file=None, instance_id="guardian_1"):
        HOME.mkdir(parents=True, exist_ok=True)
        self.config_file = Path(config_file) if config_file else HOME / "file_guardian.json"
        self.instance_id = instance_id
        self.shared_intel_file = HOME / "guardian_shared_intel.json"
        self.heartbeat_file = HOME / "heartbeat.json"
        self.config = self.load_config()
        self.access_log = []
        self.violations = []
        self.threat_score = {}
        self.auto_block_list = []
        self.approved_patterns = []
        self.load_shared_intel()
        self.system_alive = True
        self.in_failsafe = False
        self.installer = InstallerGuardian()
        self.installer.introduce_to_port_guardian(self)

    def load_config(self):
        if self.config_file.exists():
            try:
                with open(self.config_file) as f:
                    return json.load(f)
            except (OSError, ValueError) as e:
                _log(f"config unreadable ({e}); using defaults")
        try:
            own_ip = socket.gethostbyname(socket.gethostname())
        except OSError:
            own_ip = "127.0.0.1"
        return {
            "protected_paths": [], "allowed_users": [getpass.getuser()],
            "allowed_ips": sorted({"127.0.0.1", own_ip}),
            "allowed_hours": {"start": "06:00", "end": "23:00"},
            "suspicious_patterns": [".exe", ".bat", ".sh", ".dll"],
            "max_access_per_minute": 10, "alert_on_delete": True, "alert_on_copy": True,
            "lockdown_mode": False, "auto_block_threshold": 3, "threat_decay_minutes": 30,
            "proactive_mode": True, "mirror_attack": True, "mirror_multiplier": 3,
            "interactive_mode": False, "auto_approve_known": True, "peer_mode": True,
            "trust_levels": {}, "bcm_mode": False, "log_only_violations": False,
            "mesh_network": True, "consensus_required": 2, "vote_on_threats": True,
            "component_registry": {}, "require_component_auth": True, "autonomous_mode": True,
            "failsafe_lockdown": True, "heartbeat_timeout": 30, "last_system_heartbeat": None,
            "registered_services": {},
        }

    def save_config(self):
        tmp = self.config_file.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(self.config, f, indent=2)
        os.replace(tmp, self.config_file)

    def load_shared_intel(self):
        if not self.shared_intel_file.exists():
            return
        try:
            with open(self.shared_intel_file) as f:
                shared = json.load(f)
        except (OSError, ValueError) as e:
            _log(f"shared intel unreadable ({e})")
            return
        need = self.config.get("consensus_required", 2)
        for blocked in shared.get("global_blocks", []):
            votes = shared.get("block_votes", {}).get(blocked, [])
            if len(votes) >= need and blocked not in self.auto_block_list:
                self.auto_block_list.append(blocked)
        for ident, score_data in shared.get("global_threats", {}).items():
            if ident not in self.threat_score:
                self.threat_score[ident] = score_data
            else:
                mine = self.threat_score[ident]["score"]
                self.threat_score[ident]["score"] = int((score_data["score"] + mine) / 2)

    def system_heartbeat(self, conflicts=0):
        now = _now()
        self.config["last_system_heartbeat"] = now
        self.save_config()
        beat = {"instance": self.instance_id, "at": now, "host": socket.gethostname(), "pid": os.getpid(),
                "configs": len(self.installer.registry["configs"]), "ports": len(self.installer.registry["ports"]),
                "conflicts": conflicts, "failsafe": self.in_failsafe}
        tmp = self.heartbeat_file.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(beat, f)
        os.replace(tmp, self.heartbeat_file)
        self.system_alive = True
        self.in_failsafe = False
        return beat

    def query(self, question):
        q = question.lower()
        if "violation" in q or "attack" in q:
            return {"status": "success", "total_violations": len(self.violations),
                    "recent": self.violations[-5:], "message": f"Found {len(self.violations)} violations"}
        if "access" in q or "log" in q:
            return {"status": "success", "total_accesses": len(self.access_log),
                    "recent": self.access_log[-10:], "message": f"Total accesses: {len(self.access_log)}"}
        if "protected" in q:
            return {"status": "success", "protected_files": self.config["protected_paths"],
                    "count": len(self.config["protected_paths"])}
        if "installer" in q or "config" in q or "conflict" in q:
            return {"status": "success", "configs": len(self.installer.registry["configs"]),
                    "ports": len(self.installer.registry["ports"]), "paths": len(self.installer.registry["paths"]),
                    "conflicts": len(self.installer.resolve_conflicts(quiet=True))}
        if "heartbeat" in q or "alive" in q:
            return {"status": "success", "last_heartbeat": self.config.get("last_system_heartbeat"),
                    "alive": self.system_alive}
        return {"status": "error", "message": "Query not recognized"}

    # ------------------------------------------------------------- daemon
    def cycle(self):
        self.installer.auto_scan()
        real = self.installer.resolve_conflicts()
        beat = self.system_heartbeat(conflicts=len(real))
        return real, beat

    def daemon(self, once=False):
        stop = {"now": False}

        def _stop(*_):
            stop["now"] = True

        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)
        _log(f"[{self.instance_id}] daemon: scanning {', '.join(SCAN_DIRS)} every {INTERVAL}s; state {HOME}")
        while not stop["now"]:
            real, beat = self.cycle()
            _log(f"cycle: {beat['configs']} configs, {beat['ports']} ports, {len(real)} conflicts")
            if once:
                break
            for _ in range(INTERVAL):
                if stop["now"]:
                    break
                time.sleep(1)
        self.save_config()
        self.installer.save_registry()
        _log(f"[{self.instance_id}] down")


def main(argv):
    args = list(argv[1:])
    instance_id = "guardian_1"
    if args and args[0].startswith("guardian"):
        instance_id = args.pop(0)
    guardian = FileGuardian(instance_id=instance_id)
    cmd = args[0] if args else "help"
    if cmd == "daemon":
        guardian.daemon(once="--once" in args)
        return 0
    if cmd == "shutdown":
        guardian.save_config(); guardian.installer.save_registry(); return 0
    if cmd == "heartbeat":
        print(json.dumps(guardian.system_heartbeat())); return 0
    if cmd == "status":
        r = guardian.installer.registry
        real = guardian.installer.resolve_conflicts(quiet=True)
        print(f"guardian [{guardian.instance_id}] state {HOME}")
        print(f"  alive {guardian.system_alive}  failsafe {guardian.in_failsafe}  last heartbeat {guardian.config.get('last_system_heartbeat')}")
        print(f"  configs {len(r['configs'])}  ports {len(r['ports'])}  paths {len(r['paths'])}  conflicts {len(real)}")
        return 0 if not real else 1
    if cmd == "installer":
        sub = args[1] if len(args) > 1 else "help"
        if sub == "scan":
            print(f"scanned {len(guardian.installer.auto_scan())} config files"); return 0
        if sub == "conflicts":
            return 0 if not guardian.installer.resolve_conflicts() else 1
        if sub == "ports":
            for port, users in sorted(guardian.installer.registry["ports"].items(), key=lambda kv: int(kv[0])):
                print(f"  {port}: {', '.join(sorted({u['service'] for u in users}))}")
            return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
