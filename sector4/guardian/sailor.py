#!/usr/bin/env python3
"""sailor.py — one sailor per sector (Jerry, 2026-09-28: "like one per sector,
only job is to verify and take care of that sector, like sailors on a ship,
you're the captain").

A sailor is a read-only watch. Every cycle it:
  1. hashes every file on its deck (crew.json `watch`) and reports DRIFT against
     the commissioned baseline (or against git when a .git tree is present:
     modified / untracked / missing);
  2. scans its deck for the NEVER-list (the AI safety rules in CLAUDE.md, as
     command shapes: drive readonly, storage-driver blacklists, writes into
     modprobe.d/udev rules.d, mkfs/rm on a breach_coms mount, secrets on disk);
  3. checks its deck's services are active and its heartbeat files fresh
     (box only; skipped where systemd is absent, and a skip is recorded);
  4. optionally runs its deck's checks through scripts/verify.sh --only;
  5. writes the report to the verification ledger
     (verification/<date>/crew-<sector>.log + summary.json) and a heartbeat.

It never writes anywhere but its own home and the ledger: _write() refuses any
other path, and the systemd unit (phoenix-sailor@.service) makes the rest of
the filesystem read-only at the kernel level. Findings go to the captain; a
sailor does not fix, revert, restart or "heal" anything.

  sailor.py <sector> commission        record the baseline for this deck
  sailor.py <sector> watch [--checks]  one cycle, exit = number of findings
  sailor.py <sector> daemon [--checks] watch every PHOENIX_SAILOR_INTERVAL s (600)
  sailor.py <sector> status            last heartbeat
  sailor.py muster [--checks]          every sector, deck report, exit = findings
  sailor.py rules                      print the never-list (used by gangway.py)
"""
from __future__ import annotations
import hashlib, json, os, re, signal, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("PHOENIX_ROOT") or HERE.parent.parent).resolve()
CREW_HOME = Path(os.environ.get("PHOENIX_CREW_HOME") or (Path.home() / ".phoenix" / "crew")).resolve()
VERIFY_DIR = Path(os.environ.get("VERIFY_DIR") or (ROOT / "verification")).resolve()
INTERVAL = int(os.environ.get("PHOENIX_SAILOR_INTERVAL", "600"))
HOST = os.environ.get("VERIFY_HOST") or os.uname().nodename
TEXT_MAX = 2 * 1024 * 1024

# The never-list: CLAUDE.md "AI SAFETY RULES" as command shapes. (name, regex, why)
NEVER = [
    ("drive-readonly", r"\bblockdev\s+--setro\b|\bhdparm\s+(-\S*\s+)*-r\s*1\b|\bmount\b[^\n]*\bremount,ro\b[^\n]*(breach_coms|/mnt/[defg]\b)",
     "rule 3: never set a breach_coms drive readonly"),
    ("storage-blacklist", r"^\s*blacklist\s+(ahci|libata|sd_mod|scsi_mod|nvme|usb_storage|uas|xhci_pci|ext4|vfat|ntfs3?)\b",
     "rule 2: never blacklist a storage driver"),
    ("modprobe-udev-write", r"(>>?|\btee\b(\s+-a)?)\s*/etc/(modprobe\.d|udev/rules\.d)/",
     "rule 4: never inject into /etc/modprobe.d or /etc/udev/rules.d"),
    ("vault-format", r"\bmkfs(\.\w+)?\s+[^\n;&|]*(/dev/disk/by-label/breach_coms|/mnt/[defg]\b|breach_coms[1-4])",
     "rule 8 / AI rule 1: never format a breach_coms drive"),
    ("vault-delete", r"\brm\s+-[a-zA-Z]*[rf][a-zA-Z]*\s+[^\n;&|]*(/mnt/g\b|breach_coms4)",
     "rule 8: never delete from breach_coms4 (master vault)"),
    ("secret-stripe", r"\bsk_(live|test)_[A-Za-z0-9]{20,}", "a Stripe secret key on disk"),
    ("secret-stripe-webhook", r"\bwhsec_[A-Za-z0-9]{20,}", "a Stripe webhook secret on disk"),
    ("secret-aws", r"\bAKIA[0-9A-Z]{16}\b", "an AWS access key on disk"),
    ("secret-private-key", r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----", "a private key on disk"),
]
NEVER_RE = [(n, re.compile(p, re.M), why) for n, p, why in NEVER]


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def roster() -> dict:
    return json.loads((HERE / "crew.json").read_text())


def _write(path: Path, text: str) -> None:
    """The only way a sailor writes. Refuses anything outside its home or the ledger."""
    p = path.resolve()
    if not (str(p).startswith(str(CREW_HOME) + os.sep) or str(p).startswith(str(VERIFY_DIR) + os.sep)):
        raise PermissionError(f"sailor refuses to write outside its home/ledger: {p}")
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, p)


def sha3(path: Path) -> str:
    h = hashlib.sha3_512()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def deck_files(sector: dict, r: dict) -> list[Path]:
    ex = set(r.get("exclude_dirs", []))
    out: list[Path] = []
    for w in sector["watch"]:
        p = ROOT / w
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            for dp, dns, fns in os.walk(p):
                dns[:] = sorted(d for d in dns if d not in ex)
                out.extend(Path(dp) / f for f in sorted(fns))
    return out


class Sailor:
    def __init__(self, name: str, r: dict | None = None):
        r = r or roster()
        if name not in r["sectors"]:
            raise SystemExit(f"no such sector in crew.json: {name}")
        self.name, self.r, self.sector = name, r, r["sectors"][name]
        self.findings: list[dict] = []
        self.notes: list[str] = []

    # ── reporting ──
    def flag(self, kind: str, what: str, why: str = "") -> None:
        self.findings.append({"kind": kind, "what": what, "why": why})

    def note(self, s: str) -> None:
        self.notes.append(s)

    # ── 1. drift ──
    def manifest(self) -> dict[str, str]:
        return {str(p.relative_to(ROOT)): sha3(p) for p in deck_files(self.sector, self.r)}

    def baseline_path(self) -> Path:
        return CREW_HOME / f"{self.name}.baseline.json"

    def commission(self) -> dict:
        m = self.manifest()
        doc = {"sector": self.name, "host": HOST, "utc": utc(), "commit": git_commit(), "files": m}
        _write(self.baseline_path(), json.dumps(doc, indent=1, sort_keys=True))
        return doc

    def drift(self) -> None:
        if (ROOT / ".git").is_dir() and not self.baseline_path().exists():
            rc, out = git("status", "--porcelain", "--", *[w for w in self.sector["watch"] if (ROOT / w).exists()])
            if rc != 0:
                self.flag("drift-unknown", "git status failed", out.strip()[:200]); return
            lines = [l for l in out.splitlines() if l.strip()]
            for l in lines:
                self.flag("drift", l.strip(), "differs from the committed tree")
            self.note(f"drift: git tree, {len(lines)} changed path(s)")
            return
        bp = self.baseline_path()
        if not bp.exists():
            self.flag("uncommissioned", str(bp), "run: sailor.py %s commission (after an approved deploy)" % self.name); return
        base = json.loads(bp.read_text())["files"]
        now = self.manifest()
        for k in sorted(set(base) | set(now)):
            if k not in now: self.flag("drift", f"missing {k}", "in baseline, gone from disk")
            elif k not in base: self.flag("drift", f"new {k}", "on disk, not in baseline")
            elif base[k] != now[k]: self.flag("drift", f"modified {k}", "hash differs from baseline")
        self.note(f"drift: baseline {bp.name} ({len(base)} files) vs disk ({len(now)} files)")

    # ── 2. never-list ──
    def rules(self) -> None:
        exempt = set(self.r.get("rule_exempt", []))
        n = 0
        for p in deck_files(self.sector, self.r):
            rel = str(p.relative_to(ROOT))
            if rel in exempt or p.stat().st_size > TEXT_MAX: continue
            try: text = p.read_text(errors="strict")
            except (UnicodeDecodeError, OSError): continue
            n += 1
            for name, rx, why in NEVER_RE:
                for m in rx.finditer(text):
                    line = text.count("\n", 0, m.start()) + 1
                    self.flag(f"never:{name}", f"{rel}:{line}", why)
        self.note(f"rules: {n} text files scanned against {len(NEVER_RE)} never-list patterns")

    # ── 3. services + heartbeats (box only) ──
    def services(self) -> None:
        svcs = self.sector.get("services", [])
        if not svcs: return
        if not on_box():
            self.note("services: skipped, %s is not a systemd box" % HOST); return
        for s in svcs:
            rc, out = run("systemctl", "is-active", s)
            if rc != 0: self.flag("service-down", s, out.strip() or "inactive")
        self.note(f"services: {len(svcs)} checked")

    def heartbeats(self) -> None:
        for hb in self.sector.get("heartbeats", []):
            p = Path(hb["path"])
            if not on_box():
                self.note(f"heartbeat: {p} not checked ({HOST} is not a systemd box)"); continue
            if not p.exists():
                self.flag("heartbeat-missing", str(p), "expected on a box with the team installed"); continue
            if hb.get("max_age", 0) and time.time() - p.stat().st_mtime > hb["max_age"]:
                self.flag("heartbeat-stale", str(p), f"older than {hb['max_age']}s")

    # ── 4. the deck's checks through the ledger ──
    def checks(self) -> None:
        vs = ROOT / "scripts" / "verify.sh"
        if not vs.exists(): self.note("checks: scripts/verify.sh absent"); return
        for c in self.sector.get("checks", []):
            rc, out = run("bash", str(vs), "--only", c, env={**os.environ, "VERIFY_DIR": str(VERIFY_DIR), "VERIFY_HOST": HOST}, cwd=ROOT)
            last = out.strip().splitlines()[-1] if out.strip() else ""
            if rc != 0: self.flag("check-failed", c, last)
        self.note(f"checks: {len(self.sector.get('checks', []))} through scripts/verify.sh")

    # ── one cycle ──
    def watch(self, with_checks: bool = False) -> dict:
        t0 = time.time()
        self.findings, self.notes = [], []
        self.drift(); self.rules(); self.services(); self.heartbeats()
        if with_checks: self.checks()
        report = {"sector": self.name, "deck": self.sector["deck"], "host": HOST, "commit": git_commit(),
                  "utc": utc(), "seconds": round(time.time() - t0, 3), "findings": self.findings, "notes": self.notes}
        self.ledger(report)
        _write(CREW_HOME / f"{self.name}.heartbeat.json", json.dumps(report, indent=1))
        return report

    def ledger(self, report: dict) -> None:
        day = VERIFY_DIR / report["utc"][:10]
        name = f"crew-{self.name}"
        lines = [f"# {name}", f"# host={HOST} commit={report['commit']} utc={report['utc']}", f"# deck: {report['deck']}", ""]
        for n in report["notes"]: lines.append(f"  {n}")
        lines.append("")
        for f in report["findings"]: lines.append(f"  FINDING {f['kind']:<22} {f['what']}    {f['why']}")
        lines.append(f"\n# findings={len(report['findings'])}  exit={len(report['findings'])}")
        _write(day / f"{name}.log", "\n".join(lines) + "\n")
        sp = day / "summary.json"
        rows = json.loads(sp.read_text()) if sp.exists() else []
        rows = [r for r in rows if r.get("check") != name]
        rows.append({"check": name, "result": str(len(report["findings"])), "seconds": report["seconds"],
                     "command": f"sector4/guardian/sailor.py {self.name} watch", "reason": "", "commit": report["commit"],
                     "dirty": False, "host": HOST, "utc": report["utc"]})
        _write(sp, json.dumps(sorted(rows, key=lambda r: r["check"]), indent=1))

    def daemon(self, with_checks: bool = False) -> None:
        stop = {"v": False}
        signal.signal(signal.SIGTERM, lambda *_: stop.__setitem__("v", True))
        signal.signal(signal.SIGINT, lambda *_: stop.__setitem__("v", True))
        print(f"[{self.name}] on watch: {self.sector['deck']} (every {INTERVAL}s)", flush=True)
        while not stop["v"]:
            rep = self.watch(with_checks)
            print(f"[{self.name}] {rep['utc']} findings={len(rep['findings'])}", flush=True)
            for _ in range(INTERVAL):
                if stop["v"]: break
                time.sleep(1)
        print(f"[{self.name}] stood down", flush=True)


# ── helpers ──
def have(cmd: str) -> bool:
    from shutil import which
    return which(cmd) is not None


def on_box() -> bool:
    """systemd is PID 1 here (a deployed box), not merely installed (a container, CI)."""
    v = os.environ.get("PHOENIX_SAILOR_BOX")
    if v in ("0", "1"): return v == "1"
    return Path("/run/systemd/system").is_dir() and have("systemctl")


def run(*argv, env=None, cwd=None) -> tuple[int, str]:
    try:
        p = subprocess.run(argv, capture_output=True, text=True, env=env, cwd=cwd, timeout=1800)
        return p.returncode, p.stdout + p.stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)


def git(*args) -> tuple[int, str]:
    return run("git", "-C", str(ROOT), *args)


def git_commit() -> str:
    rc, out = git("rev-parse", "--short", "HEAD")
    if rc == 0: return out.strip()
    dc = ROOT / ".deployed-commit"
    return dc.read_text().strip() if dc.exists() else "unknown"


def print_report(rep: dict) -> None:
    n = len(rep["findings"])
    print(f"{rep['sector']:<8} {'clear' if n == 0 else f'{n} finding(s)':<14} {rep['deck']}")
    for f in rep["findings"]: print(f"    {f['kind']:<22} {f['what']}    {f['why']}")


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"): print(__doc__); return 0
    with_checks = "--checks" in argv
    argv = [a for a in argv if a != "--checks"]
    if argv[0] == "rules":
        for n, p, why in NEVER: print(json.dumps({"name": n, "pattern": p, "why": why}))
        return 0
    r = roster()
    if argv[0] == "muster":
        total = 0
        print(f"# muster  host={HOST} commit={git_commit()} utc={utc()}")
        for name in r["sectors"]:
            rep = Sailor(name, r).watch(with_checks); print_report(rep); total += len(rep["findings"])
        print(f"# {total} finding(s) across {len(r['sectors'])} decks -> {VERIFY_DIR}")
        return min(total, 125)
    if len(argv) < 2: print(__doc__); return 2
    s, cmd = Sailor(argv[0], r), argv[1]
    if cmd == "commission":
        d = s.commission(); print(f"{s.name} commissioned: {len(d['files'])} files, commit {d['commit']} -> {s.baseline_path()}"); return 0
    if cmd == "watch":
        rep = s.watch(with_checks); print_report(rep); return min(len(rep["findings"]), 125)
    if cmd == "daemon":
        s.daemon(with_checks); return 0
    if cmd == "status":
        hb = CREW_HOME / f"{s.name}.heartbeat.json"
        if not hb.exists(): print(f"{s.name}: no heartbeat at {hb}"); return 1
        print_report(json.loads(hb.read_text())); return 0
    print(__doc__); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
