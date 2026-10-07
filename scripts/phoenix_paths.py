"""phoenix_paths.py - slash-insensitive paths for Phoenix (Python side).
Phoenix DevOps OS | jwl247 | GPL v3

Jerry 2026-10-07: "make all our system slash insensitive, seeing how we are Windows and Linux".
Same rule as scripts/phoenix-paths.ps1 and bin/phoenix-paths.sh (tested together).
    from phoenix_paths import to_native, native_args
    to_native('/f/Phoenix/x')   -> 'F:\\Phoenix\\x' on Windows, '/mnt/f/Phoenix/x' on Linux if /mnt/f exists
Only path-looking strings change: URLs, flags and words pass through.
"""
import os
import re
import sys

_URL = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]+://")
_LIKE = re.compile(r"^([a-zA-Z]:([\\/]|$)|/mnt/[a-zA-Z](/|$)|/[a-zA-Z]/|~[\\/]|\.{1,2}[\\/])")


def path_like(a: str) -> bool:
    if not a or a.startswith("-") or _URL.match(a):
        return False
    return bool(_LIKE.match(a)) or "\\" in a


def to_native(text: str) -> str:
    t = text.strip().strip("`\"'").strip()
    if _URL.match(t):
        return t
    t = t.replace("\\", "/")
    if t == "~" or t.startswith("~/"):
        t = os.path.expanduser("~") + t[1:]
    m = (re.match(r"^([a-zA-Z]):(/.*)?$", t) or re.match(r"^/mnt/([a-zA-Z])(/.*)?$", t)
         or (re.match(r"^/([a-zA-Z])(/.*)$", t) if sys.platform == "win32" else None))
    if not m:
        return t.replace("/", "\\") if sys.platform == "win32" else t
    drive, rest = m.group(1).lower(), m.group(2) or "/"
    if sys.platform == "win32":
        return f"{drive.upper()}:{rest}".replace("/", "\\")
    return f"/mnt/{drive}{rest if rest != '/' else ''}" if os.path.isdir(f"/mnt/{drive}") else t


def native_args(argv):
    return [to_native(a) if path_like(a) else a for a in argv]
