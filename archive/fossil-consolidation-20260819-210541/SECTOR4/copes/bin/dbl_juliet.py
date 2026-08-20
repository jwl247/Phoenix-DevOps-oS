#!/usr/bin/env python3
"""
dbl_juliet.py — Sector 3 / CoPES Egress Shim
Phoenix DevOps OS
"""
import sys
from pathlib import Path

# Bridge to canonical sector3 dbl_juliet
SECTOR3 = Path(__file__).resolve().parents[3] / "sector3" / "romeo_juliet"
if SECTOR3.exists():
    sys.path.insert(0, str(SECTOR3))
    try:
        from dbl_juliet import *
    except ImportError:
        pass

if __name__ == "__main__":
    print("[DBL_JULIET] CoPES Egress Shim ready.")
