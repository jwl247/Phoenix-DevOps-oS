#!/usr/bin/env python3
"""
Apply two fixes to package_handler.py:
  1. _gen_tav() — correct base58 implementation (no external lib, matches helix.db)
  2. ph list crash — safe format for None version/backend
Run: python3 ph_fixes.py ~/Phoenix/src/package_handler.py
"""
import sys, re
from pathlib import Path

if len(sys.argv) < 2:
    print("Usage: python3 ph_fixes.py <path/to/package_handler.py>")
    sys.exit(1)

path = Path(sys.argv[1])
src  = path.read_text()

# ── Fix 1: _gen_tav ───────────────────────────────────────────────────────────
old_gen_tav = '''    def _gen_tav(self, name: str) -> str:
        try:
            import base58
            raw = hashlib.sha3_512(name.encode()).digest()[:8]
            return base58.b58encode(raw).decode()
        except ImportError:
            return hashlib.sha3_512(name.encode()).hexdigest()[:16]'''

new_gen_tav = '''    def _gen_tav(self, name: str) -> str:
        """SHA3-512 → first 8 bytes → base58 (max 11 chars). No external deps."""
        digest = hashlib.sha3_512(name.encode()).digest()[:8]
        alpha  = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
        n      = int.from_bytes(digest, 'big')
        result = ''
        while n:
            result = alpha[n % 58] + result
            n //= 58
        return result or '1' '''

if old_gen_tav in src:
    src = src.replace(old_gen_tav, new_gen_tav)
    print("[FIX 1] _gen_tav() — replaced with correct base58 implementation")
else:
    print("[WARN 1] _gen_tav() pattern not matched — check manually")

# ── Fix 2: ph list crash — None version/backend in format string ──────────────
old_list = (
    "        [print(f\"  {p['name']:30} {p['version']:15}"
    " {p['backend']:10} [{p['state']}]\")"
    " for p in pkgs] if pkgs else print(\"[ph] no packages found.\")"
)
new_list = (
    "        [print(f\"  {p['name']:30}"
    " {(p['version'] or 'unknown'):15}"
    " {(p['backend'] or ''):10} [{p['state']}]\")"
    " for p in pkgs] if pkgs else print(\"[ph] no packages found.\")"
)

if old_list in src:
    src = src.replace(old_list, new_list)
    print("[FIX 2] ph list — None-safe format strings applied")
else:
    print("[WARN 2] ph list pattern not matched — check manually")

# ── Write ─────────────────────────────────────────────────────────────────────
path.write_text(src)
print(f"\n[DONE] Written: {path}")
print("[VERIFY] Run: ph list && python3 -c \"from package_handler import PackageRecord; r = PackageRecord('test'); print(r.tav, len(r.tav))\"")
