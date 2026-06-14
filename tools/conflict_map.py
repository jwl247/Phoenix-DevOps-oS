#!/usr/bin/env python3
"""
conflict_map.py — Phoenix DevOps Phase 1 duplicate resolver
Shows every file that exists in multiple locations with line counts,
clonepool version comparison, and canonical designation.
Run read-only. Nothing moves. Nothing deletes. Just the map.

Usage:
    python3 ~/projects/phoenix-devops/tools/conflict_map.py
    python3 ~/projects/phoenix-devops/tools/conflict_map.py --json > conflicts.json
"""

import os
import sys
import json
import hashlib
import sqlite3
from collections import defaultdict
from pathlib import Path

# ── Search roots — add/remove as needed ──────────────────────────────────────
SEARCH_ROOTS = [
    "~/projects/phoenix-devops",
    "~/projects/CoPES",
    "~/projects/unitedsys",
    "~/projects/Helix_lightning_kernel",
    "~/projects/Phoenix_Universal_Kernel",
    "~/projects/Phoenix-Package_handler",
    "~/projects/lifefirst_modules",
    "~/Phoenix/bin",
]

SKIP_DIRS = {
    "__pycache__", "site-packages", ".venv", "dist-packages",
    "node_modules", "clonepool", ".git", "helix_legacy",
}

EXTENSIONS = {
    ".py", ".sh", ".php", ".js", ".c", ".jsonc", ".sql", ".kt",
}

# Files whose canonical location we've already decided
CANONICAL = {
    "frank.py":       "~/projects/CoPES/src/kernel/frank.py",
    "helix.py":       "~/projects/phoenix-devops/sector4/helix/helix.py",
    "main_kernel.py": "~/projects/Helix_lightning_kernel/main_kernel.py",
}

CATALOG_DB = "~/.catalog/catalog.db"


def expand(p):
    return os.path.expanduser(p)


def sha3_file(path):
    h = hashlib.sha3_512()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def line_count(path):
    try:
        with open(path, "rb") as f:
            return sum(1 for _ in f)
    except Exception:
        return -1


def load_catalog():
    """Returns dict of name → (sha3, pool_path, version)"""
    db = expand(CATALOG_DB)
    if not os.path.exists(db):
        return {}
    conn = sqlite3.connect(db)
    c = conn.cursor()
    try:
        c.execute("SELECT name, sha3, pool_path, version FROM packages ORDER BY name, version DESC")
        seen = {}
        for name, sha3, pool_path, version in c.fetchall():
            if name not in seen:
                seen[name] = (sha3, pool_path, version)
        return seen
    finally:
        conn.close()


def collect_files():
    """Walk roots and return dict of basename → [full_path, ...]"""
    found = defaultdict(list)
    for root in SEARCH_ROOTS:
        root = expand(root)
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fname in filenames:
                if Path(fname).suffix in EXTENSIONS or fname in ("lol", "us"):
                    found[fname].append(os.path.join(dirpath, fname))
    return found


def shorten(path):
    home = os.path.expanduser("~")
    return path.replace(home, "~")


def run(as_json=False):
    catalog = load_catalog()
    all_files = collect_files()

    # Only duplicates
    conflicts = {k: v for k, v in all_files.items() if len(v) > 1}
    unique    = {k: v for k, v in all_files.items() if len(v) == 1}

    if as_json:
        out = {}
        for name, paths in sorted(conflicts.items()):
            canonical_raw = CANONICAL.get(name)
            canonical_exp = expand(canonical_raw) if canonical_raw else None
            cat = catalog.get(name)
            entries = []
            for p in sorted(paths):
                lc   = line_count(p)
                sha3 = sha3_file(p)
                is_canon = (p == canonical_exp) if canonical_exp else None
                matches_catalog = (sha3 == cat[0]) if (cat and sha3) else None
                entries.append({
                    "path":            shorten(p),
                    "lines":           lc,
                    "is_canonical":    is_canon,
                    "matches_catalog": matches_catalog,
                })
            out[name] = {
                "copies":    len(paths),
                "canonical": shorten(canonical_raw) if canonical_raw else "UNDECIDED",
                "in_catalog": cat is not None,
                "catalog_version": cat[2] if cat else None,
                "entries":   entries,
            }
        print(json.dumps(out, indent=2))
        return

    # ── Human-readable output ─────────────────────────────────────────────────
    W = 90
    print("=" * W)
    print("  PHOENIX CONFLICT MAP — Phase 1")
    print(f"  {len(conflicts)} files with duplicates | {len(unique)} unique | {len(catalog)} catalogued")
    print("=" * W)

    DECIDED   = []
    UNDECIDED = []

    for name in sorted(conflicts):
        paths = sorted(conflicts[name])
        canonical_raw = CANONICAL.get(name)
        canonical_exp = expand(canonical_raw) if canonical_raw else None
        cat = catalog.get(name)

        entry = {"name": name, "paths": paths, "canonical": canonical_raw, "cat": cat}
        if canonical_raw:
            DECIDED.append(entry)
        else:
            UNDECIDED.append(entry)

    # Print undecided first — these need a decision
    if UNDECIDED:
        print(f"\n{'─'*W}")
        print("  !! UNDECIDED — needs your call")
        print(f"{'─'*W}")
        for e in UNDECIDED:
            name = e["name"]
            cat  = e["cat"]
            print(f"\n  {name}  {'[in catalog v'+str(cat[2])+']' if cat else '[NOT CATALOGUED]'}")
            sizes = []
            for p in e["paths"]:
                lc = line_count(p)
                sha3 = sha3_file(p)
                match = ""
                if cat and sha3:
                    match = "  ← matches catalog" if sha3 == cat[0] else ""
                sizes.append((lc, p, match))
            sizes.sort(reverse=True)
            for lc, p, match in sizes:
                print(f"    {lc:>5} lines   {shorten(p)}{match}")

    # Print decided — for confirmation
    if DECIDED:
        print(f"\n{'─'*W}")
        print("  ✓ DECIDED — canonical already set")
        print(f"{'─'*W}")
        for e in DECIDED:
            name = e["name"]
            cat  = e["cat"]
            canon = expand(e["canonical"])
            print(f"\n  {name}  {'[catalog v'+str(cat[2])+']' if cat else '[NOT CATALOGUED]'}")
            print(f"  CANONICAL → {e['canonical']}")
            for p in sorted(e["paths"]):
                lc = line_count(p)
                sha3 = sha3_file(p)
                tag = "  ← WINNER" if p == canon else ""
                match = ""
                if cat and sha3:
                    match = "  [matches catalog]" if sha3 == cat[0] else "  [differs from catalog]"
                print(f"    {lc:>5} lines   {shorten(p)}{tag}{match}")

    # Summary of what's NOT duplicated but also not in catalog
    not_catalogued_unique = [
        (name, paths[0]) for name, paths in unique.items()
        if name not in catalog
    ]
    if not_catalogued_unique:
        print(f"\n{'─'*W}")
        print(f"  ℹ  {len(not_catalogued_unique)} unique files not yet in catalog")
        print(f"{'─'*W}")
        for name, path in sorted(not_catalogued_unique):
            print(f"    {shorten(path)}")

    print(f"\n{'='*W}")
    print("  Nothing was moved or deleted. This is read-only.")
    print(f"  To mark a canonical: edit CANONICAL dict in this script.")
    print(f"{'='*W}\n")


if __name__ == "__main__":
    run(as_json="--json" in sys.argv)
