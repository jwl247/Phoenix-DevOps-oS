#!/usr/bin/env python3
"""
romeo.py — Sector 3 / CoPES Romeo Ingress Shim
Phoenix DevOps OS
"""
import sys
from pathlib import Path

SECTOR3 = Path(__file__).resolve().parents[3] / "sector3" / "romeo_juliet"
if SECTOR3.exists():
    sys.path.insert(0, str(SECTOR3))
    try:
        from romeo import *
    except ImportError:
        pass

if __name__ == "__main__":
    print("[ROMEO] CoPES Ingress Shim ready.")
