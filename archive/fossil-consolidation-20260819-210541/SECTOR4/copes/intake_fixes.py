#!/usr/bin/env python3
"""
Apply TAV fix to intake.sh:
  - Replaces to_hex() with gen_tav() — SHA3-512 → first 8 bytes → base58
  - Renames all variable uses: hex → tav (where identity-related)
  - Renames sidecar field: hex_name → tav
  - Keeps SCRIPT_HEX constant as-is (it's a fixed label, not a generated identity)
  - No external deps — uses system python3 inline, same pattern already in script
Run: python3 intake_fixes.py ~/Phoenix/intake/intake.sh
"""
import sys, re
from pathlib import Path

if len(sys.argv) < 2:
    print("Usage: python3 intake_fixes.py <path/to/intake.sh>")
    sys.exit(1)

path = Path(sys.argv[1])
src  = path.read_text()
original = src

fixes = 0

# ── Fix 1: Replace to_hex() function definition ───────────────────────────────
old_fn = 'to_hex() { echo -n "$1" | xxd -p | tr -d \'\\n\'; }'

new_fn = r'''# ── TAV address (SHA3-512 → first 8 bytes → base58, max 11 chars) ────────────
gen_tav() {
  [[ -z "${PYTHON_CMD}" ]] && { echo "notav"; return 1; }
  "${PYTHON_CMD}" - "$1" <<'PYEOF'
import hashlib, sys
digest = hashlib.sha3_512(sys.argv[1].encode()).digest()[:8]
alpha  = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
n      = int.from_bytes(digest, 'big')
r      = ''
while n:
    r = alpha[n % 58] + r
    n //= 58
print(r or '1')
PYEOF
}'''

if old_fn in src:
    src = src.replace(old_fn, new_fn)
    fixes += 1
    print("[FIX 1] to_hex() → gen_tav() function replaced")
else:
    print("[WARN 1] to_hex() function pattern not matched — check manually")

# ── Fix 2: All call sites — hex=$(to_hex → tav=$(gen_tav ─────────────────────
# Pattern: local hex;  hex=$(to_hex  or  local hex; hex=$(to_hex
replacements = [
    # intake_file — orig filename
    ('local hex;  hex=$(to_hex "${orig}")',
     'local tav;  tav=$(gen_tav "${orig}")'),
    # intake_file alt spacing
    ('local hex; hex=$(to_hex "${orig}")',
     'local tav; tav=$(gen_tav "${orig}")'),
    # intake_from_backend
    ('local hex; hex=$(to_hex "${pkg_name}")',
     'local tav; tav=$(gen_tav "${pkg_name}")'),
    # intake_clone (file clone out)
    ('local hex; hex=$(to_hex "${name}")',
     'local tav; tav=$(gen_tav "${name}")'),
    # intake_directory — dirname
    ('local hex;     hex=$(to_hex "${dirname}")',
     'local tav;     tav=$(gen_tav "${dirname}")'),
    # intake_directory — file_hex inside loop
    ('local file_hex;  file_hex=$(to_hex "${file_orig}")',
     'local file_tav;  file_tav=$(gen_tav "${file_orig}")'),
    # intake_clone_directory
    ('local hex; hex=$(to_hex "${name}")',
     'local tav; tav=$(gen_tav "${name}")'),
]

for old, new in replacements:
    if old in src:
        src = src.replace(old, new)
        fixes += 1
        print(f"[FIX 2] call site: {old.strip()[:50]}...")

# ── Fix 3: Variable references after call sites ───────────────────────────────
# Only where hex is the TAV identity — not SCRIPT_HEX or checksum vars
# Replace "${hex}" → "${tav}" in identity contexts (pool_dir, sidecar, reports)
# Replace "${file_hex}" → "${file_tav}" throughout

identity_subs = [
    # pool_dir and sidecar construction
    ('local pool_dir="${CLONEPOOL_DIR}/${hex}"',
     'local pool_dir="${CLONEPOOL_DIR}/${tav}"'),
    ('local sidecar="${pool_dir}/${hex}.sidecar.json"',
     'local sidecar="${pool_dir}/${tav}.sidecar.json"'),
    # directory sidecar
    ('local dir_sidecar="${pool_dir}/${hex}.sidecar.json"',
     'local dir_sidecar="${pool_dir}/${tav}.sidecar.json"'),
    # sidecar field name
    ('"hex_name": "${hex}"',   '"tav": "${tav}"'),
    ('"hex_name": "${file_hex}"', '"tav": "${file_tav}"'),
    # report calls with hex
    ('report_clonepool "${hex}"', 'report_clonepool "${tav}"'),
    ('report_custody "${hex}"',   'report_custody "${tav}"'),
    ('report_glossary "${hex}"',  'report_glossary "${tav}"'),
    # custody log calls
    ('custody_log_local "${hex}"', 'custody_log_local "${tav}"'),
    # file_hex → file_tav in report/custody calls
    ('report_clonepool "${file_hex}"', 'report_clonepool "${file_tav}"'),
    ('report_custody "${file_hex}"',   'report_custody "${file_tav}"'),
    ('custody_log_local "${file_hex}"','custody_log_local "${file_tav}"'),
    # sidecar write calls
    ('write_sidecar_basic "${sidecar}" "${hex}"',
     'write_sidecar_basic "${sidecar}" "${tav}"'),
    ('write_sidecar_basic "${sidecar}" "${file_hex}"',
     'write_sidecar_basic "${sidecar}" "${file_tav}"'),
    # dir sidecar content
    ('"hex_name": "${hex}"',   '"tav": "${tav}"'),
    # D1 payload fields — hex_id and b58 both become tav
    ('"hex_id\":\"${1}\",\"b58\":\"${1}\"',
     '"tav\":\"${1}\"'),
    ('"hex_id\":\"${hex}\"',   '"tav\":\"${tav}\"'),
    # pool path references
    ('${CLONEPOOL_DIR}/${file_hex}', '${CLONEPOOL_DIR}/${file_tav}'),
    # evict call
    ('evict_old_versions "${file_pool}" "${file_orig}"',
     'evict_old_versions "${file_pool}" "${file_orig}"'),  # unchanged, file_pool already updated
    # manifest entry
    ('"hex\":\"${file_hex}\"', '"tav\":\"${file_tav}\"'),
    # echo output
    ('echo "[intake:OK] hex: ${hex}"',  'echo "[intake:OK] tav: ${tav}"'),
    ('echo "  Hex       : ${hex}"',     'echo "  TAV       : ${tav}"'),
]

for old, new in identity_subs:
    if old in src and old != new:
        count = src.count(old)
        src = src.replace(old, new)
        fixes += 1
        print(f"[FIX 3] {old.strip()[:55]}... ({count}x)")

# ── Fix 4: SCRIPT_HEX stays — it's a fixed constant label, not generated ─────
# (no change needed — SCRIPT_HEX is never passed to to_hex)

# ── Fix 5: D1 payload in report_clonepool / report_custody functions ──────────
# These use positional $1 $2 etc — the field name fix in payload strings
old_clonepool_payload = (
    '"{\\\"hex_id\\\":\\\"${1}\\\",\\\"b58\\\":\\\"${1}\\\","'
)
# Already handled above via the hex_id/b58 replacement

# ── Summary ───────────────────────────────────────────────────────────────────
changed = src != original

if changed:
    # Backup
    backup = path.with_suffix('.sh.pre_tav')
    backup.write_text(original)
    print(f"\n[BACKUP] Original saved: {backup}")
    path.write_text(src)
    print(f"[DONE] {fixes} fixes applied → {path}")
else:
    print(f"\n[WARN] No changes made — patterns may have already been applied or differ")

print("\n[VERIFY] Run on copes:")
print("  intake.sh status")
print("  intake.sh ./src/helix.py")
print("  # TAV should be 11 chars max, base58 chars only")
