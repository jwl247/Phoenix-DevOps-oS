#!/usr/bin/env python3
"""
x4_foundations.py — Frank Suit: X4 Foundations (GOG)
Save manager, session logger, mod loader integration.
Frank logs every session to D1 custody. Save files backed to clonepool.

GOG install path (Windows): C:/GOG Games/X4 Foundations/
Save path:  %USERPROFILE%/Documents/Egosoft/X4/<player_id>/save/
Via WSL:    /mnt/c/Users/jwlef/Documents/Egosoft/X4/

SUIT_ID:  x4_foundations
CHANNEL:  game_rt

Phoenix DevOps OS | jwl247 | GPL v3
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

SUIT_ID  = "x4_foundations"
CHANNEL  = "game_rt"

# GOG install on Windows — accessible via WireGuard SSH or /mnt/c
GOG_WIN_PATH    = Path("/mnt/c/GOG Games/X4 Foundations")
SAVE_BASE       = Path("/mnt/c/Users/jwlef/Documents/Egosoft/X4")
WINDOWS_INSTALL = Path("/mnt/c/Program Files (x86)/GOG Galaxy")

D1_WORKER    = os.environ.get("D1_WORKER_URL", "https://packages-worker.phoenix-jwl.workers.dev")
PHOENIX_AUTH = os.environ.get("PHOENIX_AUTH", "")
CLONEPOOL    = Path(os.environ.get("CLONEPOOL_DIR", str(Path.home() / "Phoenix" / "clonepool")))
AUDIT_LOG    = Path(os.environ.get("PHOENIX_AUDIT", "/var/log/phoenix/audit.log"))

INTAKE_PY = Path(os.environ.get("PHOENIX_INSTALL_DIR",
    str(Path.home() / "phoenix-devops"))) / "unitedsys" / "core" / "intake.py"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _audit(msg: str):
    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        entry = json.dumps({"ts": datetime.now(timezone.utc).isoformat(),
                            "op": SUIT_ID, "msg": msg})
        with open(str(AUDIT_LOG), "a") as f:
            f.write(entry + "\n")
    except Exception:
        pass


def _post_d1(endpoint: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    headers = {
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {PHOENIX_AUTH}",
    }
    req = urllib.request.Request(
        f"{D1_WORKER}/{endpoint}", data=data, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}


def _find_save_dirs() -> list[Path]:
    """Find X4 save directories under Documents/Egosoft/X4/<player_id>/save/"""
    if not SAVE_BASE.exists():
        return []
    saves = []
    for player_dir in SAVE_BASE.iterdir():
        save_dir = player_dir / "save"
        if save_dir.exists():
            saves.append(save_dir)
    return saves


def _save_files(save_dir: Path) -> list[Path]:
    """List save files sorted newest first."""
    files = sorted(save_dir.glob("*.xml.gz"), key=lambda f: f.stat().st_mtime, reverse=True)
    files += sorted(save_dir.glob("*.xml"),   key=lambda f: f.stat().st_mtime, reverse=True)
    return files


def _intake_file(path: Path) -> bool:
    """Push a file into Phoenix clonepool + D1 via intake.py."""
    if not INTAKE_PY.exists():
        return False
    result = subprocess.run(
        [sys.executable, str(INTAKE_PY), str(path)],
        capture_output=True, timeout=30
    )
    return result.returncode == 0


# ── X4 Suit ───────────────────────────────────────────────────────────────────

class X4Suit:

    def status(self) -> dict:
        save_dirs = _find_save_dirs()
        saves = []
        for sd in save_dirs:
            files = _save_files(sd)
            saves.append({
                "player_dir": sd.parent.name,
                "save_dir":   str(sd),
                "save_count": len(files),
                "latest":     files[0].name if files else None,
                "latest_ts":  datetime.fromtimestamp(
                    files[0].stat().st_mtime, tz=timezone.utc
                ).isoformat() if files else None,
            })

        return {
            "suit":         SUIT_ID,
            "gog_path":     str(GOG_WIN_PATH),
            "gog_exists":   GOG_WIN_PATH.exists(),
            "save_base":    str(SAVE_BASE),
            "save_base_exists": SAVE_BASE.exists(),
            "players":      saves,
        }

    def backup_saves(self, dry_run: bool = False) -> dict:
        """
        Intake all X4 save files into Phoenix clonepool + D1.
        Each save file gets a TAV hex address and full custody receipt.
        """
        save_dirs = _find_save_dirs()
        if not save_dirs:
            return {"error": f"No X4 save directories found under {SAVE_BASE}"}

        results = []
        total_backed = 0

        for save_dir in save_dirs:
            files = _save_files(save_dir)
            player = save_dir.parent.name
            print(f"\n  Player: {player}  ({len(files)} saves)")

            for f in files:
                ts = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
                size_kb = f.stat().st_size // 1024
                print(f"    {f.name:<40} {size_kb:>6} KB  {ts.strftime('%Y-%m-%d %H:%M')}", end="")

                if dry_run:
                    print("  [dry-run]")
                    results.append({"file": str(f), "status": "dry-run"})
                    continue

                ok = _intake_file(f)
                status = "OK" if ok else "FAIL"
                print(f"  [{status}]")
                results.append({"file": str(f), "status": status})
                if ok:
                    total_backed += 1

        if not dry_run:
            _post_d1("custody", {
                "hex_id":  f"x4_backup_{int(time.time())}",
                "name":    "x4_saves_backup",
                "action":  "save_backup",
                "actor":   SUIT_ID,
                "state":   "complete",
                "qr_top":  f"USYS:X4:SAVE:HEADER",
                "qr_bottom": f"USYS:X4:SAVE:FOOTER",
            })
            _audit(f"save backup — {total_backed} files intaked")

        return {
            "files_backed": total_backed,
            "dry_run":      dry_run,
            "results":      results,
        }

    def log_session(self, duration_min: float = 0, notes: str = "") -> dict:
        """Log a game session to D1."""
        session_id = f"x4_{int(time.time())}"
        save_dirs  = _find_save_dirs()
        latest_save = None

        for sd in save_dirs:
            files = _save_files(sd)
            if files:
                latest_save = files[0].name
                break

        payload = {
            "hex_id":  session_id,
            "name":    "x4_session",
            "action":  "game_session",
            "actor":   SUIT_ID,
            "state":   "complete",
            "qr_top":  f"USYS:X4:SESSION:{session_id}:HEADER",
            "qr_bottom": f"USYS:X4:SESSION:{session_id}:FOOTER",
        }
        r = _post_d1("custody", payload)
        _audit(f"session logged — {session_id} duration={duration_min}min latest_save={latest_save} notes={notes}")

        print(f"  Session logged — {session_id}")
        print(f"  Latest save:    {latest_save}")
        print(f"  D1:             {r}")

        return {"session_id": session_id, "d1": r, "latest_save": latest_save}

    def mods(self) -> list[dict]:
        """List installed mods from X4 extensions directory."""
        mod_dirs = []
        for player_dir in SAVE_BASE.iterdir() if SAVE_BASE.exists() else []:
            ext_dir = player_dir.parent / "extensions"
            if ext_dir.exists():
                for mod in ext_dir.iterdir():
                    if mod.is_dir():
                        content_xml = mod / "content.xml"
                        mod_dirs.append({
                            "name": mod.name,
                            "has_content_xml": content_xml.exists(),
                            "path": str(mod),
                        })
        return mod_dirs


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Frank Suit: X4 Foundations (GOG)")
    parser.add_argument("--status",       action="store_true", help="show install + save status")
    parser.add_argument("--backup",       action="store_true", help="intake all save files → clonepool + D1")
    parser.add_argument("--backup-dry",   action="store_true", help="dry run — list saves without intaking")
    parser.add_argument("--log-session",  action="store_true", help="log current session to D1")
    parser.add_argument("--duration",     type=float, default=0, help="session duration in minutes")
    parser.add_argument("--notes",        type=str, default="",  help="session notes")
    parser.add_argument("--mods",         action="store_true", help="list installed mods")
    args = parser.parse_args()

    suit = X4Suit()

    print(f"\n{'='*65}")
    print(f"FRANK SUIT — X4 FOUNDATIONS  [{SUIT_ID}]")
    print(f"GOG path: {GOG_WIN_PATH}")
    print(f"Saves:    {SAVE_BASE}")
    print(f"{'='*65}\n")

    if args.status:
        s = suit.status()
        print(json.dumps(s, indent=2, default=str))

    elif args.backup:
        print("Intaking all X4 save files into Phoenix clonepool + D1...\n")
        r = suit.backup_saves(dry_run=False)
        print(f"\n  Backed up: {r['files_backed']} files")

    elif args.backup_dry:
        print("DRY RUN — save files that would be intaked:\n")
        r = suit.backup_saves(dry_run=True)

    elif args.log_session:
        suit.log_session(duration_min=args.duration, notes=args.notes)

    elif args.mods:
        mods = suit.mods()
        if mods:
            print("Installed mods:")
            for m in mods:
                print(f"  {m['name']:<40} content.xml: {'yes' if m['has_content_xml'] else 'no'}")
        else:
            print("No mods found (or extensions dir not accessible from WSL)")

    else:
        parser.print_help()
        print("\nExamples:")
        print("  python3 x4_foundations.py --status")
        print("  python3 x4_foundations.py --backup-dry      # see what would be backed up")
        print("  python3 x4_foundations.py --backup          # intake all saves → clonepool + D1")
        print("  python3 x4_foundations.py --log-session --duration 90 --notes 'completed PHQ'")
        print("  python3 x4_foundations.py --mods")


if __name__ == "__main__":
    main()
