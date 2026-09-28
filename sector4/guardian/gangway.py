#!/usr/bin/env python3
"""gangway.py — the gangway watch for every Claude Code session on this repo
(.claude/settings.json, PreToolUse on Bash). Reads the hook JSON on stdin,
holds the command against the same never-list the sailors use (sailor.NEVER),
and blocks it (exit 2, reason on stderr) before it runs. Deterministic: no
model in the loop, no network, nothing written.

If the hook input names a sailor subagent (agent_type starting "sailor-"), the
command must also match the sailor allowlist (read/hash/verify only). When the
field is absent the never-list alone applies; that is the honest floor.
"""
import json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sailor import NEVER_RE  # noqa: E402

SAILOR_ALLOW = re.compile(
    r"^\s*(python3?\s+\S*sector4/guardian/sailor\.py\b|bash\s+\S*scripts/verify\.sh\b|\S*scripts/verify\.sh\b"
    r"|git\s+(status|diff|log|show|ls-files|rev-parse|blame)\b|(cat|head|tail|sed\s+-n|grep|rg|find|ls|wc|sha3sum|sha256sum|openssl\s+dgst|stat|file|jq|python3\s+-c\s+.import\s+hashlib)\b)")


def verdict(payload: dict) -> tuple[int, str]:
    if payload.get("tool_name") != "Bash":
        return 0, ""
    cmd = (payload.get("tool_input") or {}).get("command") or ""
    for name, rx, why in NEVER_RE:
        m = rx.search(cmd)
        if m:
            return 2, f"GANGWAY: blocked ({name}) — {why}. Matched: {m.group(0)[:80]!r}. CLAUDE.md AI SAFETY RULES."
    agent = str(payload.get("agent_type") or payload.get("agent_name") or "")
    if agent.startswith("sailor-"):
        for part in re.split(r"\s*(?:&&|\|\||;|\|)\s*", cmd.strip()):
            if part and not SAILOR_ALLOW.match(part):
                return 2, f"GANGWAY: sailors are read-only; not on the allowlist: {part[:80]!r}"
    return 0, ""


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # not for us; never block on a parse error
    code, reason = verdict(payload)
    if code:
        print(reason, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
