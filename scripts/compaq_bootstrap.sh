#!/usr/bin/env bash
# =============================================================================
# compaq_bootstrap.sh — Phoenix node bootstrap for Debian
#
# Installs prerequisites, configures rclone for R2, pulls the Phoenix
# pre-deploy tree, then runs the Helix smoke test so you can verify the
# host-detection and cache-tier auto-scaling before anything else starts.
#
# Required env vars (set before running or export in your shell):
#   PHOENIX_R2_ACCOUNT_ID   — Cloudflare account ID
#   PHOENIX_R2_ACCESS_KEY   — R2 access key ID
#   PHOENIX_R2_SECRET_KEY   — R2 secret access key
#   PHOENIX_R2_BUCKET       — R2 bucket name (e.g. phoenix-vault)
#   PHOENIX_R2_PATH         — path inside bucket (e.g. windows/vault/phoenix-predeploy)
#
# Optional:
#   PHOENIX_DEST            — local destination (default: ~/phoenix)
#   PHOENIX_R2_REGION       — rclone region hint (default: auto)
#
# Usage:
#   export PHOENIX_R2_ACCOUNT_ID=xxx
#   export PHOENIX_R2_ACCESS_KEY=xxx
#   export PHOENIX_R2_SECRET_KEY=xxx
#   export PHOENIX_R2_BUCKET=phoenix-vault
#   export PHOENIX_R2_PATH=windows/vault/phoenix-predeploy
#   bash compaq_bootstrap.sh
# =============================================================================

set -euo pipefail

PHOENIX_DEST="${PHOENIX_DEST:-$HOME/phoenix}"
LOG="$PHOENIX_DEST/bootstrap.log"

# ── colour helpers ────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[OK]${NC}    $*" | tee -a "$LOG"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*" | tee -a "$LOG"; }
die()  { echo -e "${RED}[FAIL]${NC}  $*" | tee -a "$LOG"; exit 1; }
info() { echo -e "        $*" | tee -a "$LOG"; }

echo "============================================================"
echo "  Phoenix Node Bootstrap  $(date -u '+%Y-%m-%d %H:%M UTC')"
echo "  Destination: $PHOENIX_DEST"
echo "============================================================"
mkdir -p "$PHOENIX_DEST"

# ── verify required env vars ──────────────────────────────────────────────────
for var in PHOENIX_R2_ACCOUNT_ID PHOENIX_R2_ACCESS_KEY PHOENIX_R2_SECRET_KEY \
           PHOENIX_R2_BUCKET PHOENIX_R2_PATH; do
    [[ -n "${!var:-}" ]] || die "Required env var $var is not set. Aborting."
done
ok "Env vars verified"

# ── system prerequisites ──────────────────────────────────────────────────────
info "Updating package lists..."
sudo apt-get update -qq 2>>"$LOG"

PKGS=(python3 python3-pip git curl unzip)
for pkg in "${PKGS[@]}"; do
    if dpkg -s "$pkg" &>/dev/null; then
        info "  $pkg already installed"
    else
        info "  Installing $pkg..."
        sudo apt-get install -y -qq "$pkg" >>"$LOG" 2>&1
    fi
done
ok "System packages ready"

# Python version check — 3.8 minimum
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJ=$(echo "$PY_VER" | cut -d. -f1)
PY_MIN=$(echo "$PY_VER" | cut -d. -f2)
if [[ $PY_MAJ -lt 3 || ($PY_MAJ -eq 3 && $PY_MIN -lt 8) ]]; then
    die "Python 3.8+ required, found $PY_VER"
fi
ok "Python $PY_VER"

# ── install rclone ────────────────────────────────────────────────────────────
if command -v rclone &>/dev/null; then
    RCLONE_VER=$(rclone version 2>/dev/null | head -1)
    ok "rclone already installed: $RCLONE_VER"
else
    info "Installing rclone..."
    curl -fsSL https://rclone.org/install.sh | sudo bash >>"$LOG" 2>&1
    ok "rclone installed: $(rclone version 2>/dev/null | head -1)"
fi

# ── configure rclone for R2 ───────────────────────────────────────────────────
RCLONE_CFG="$HOME/.config/rclone/rclone.conf"
mkdir -p "$(dirname "$RCLONE_CFG")"

# Write/overwrite the phoenix-r2 remote — env vars are the source of truth
cat > /tmp/phoenix_r2_remote.conf <<EOF
[phoenix-r2]
type = s3
provider = Cloudflare
access_key_id = ${PHOENIX_R2_ACCESS_KEY}
secret_access_key = ${PHOENIX_R2_SECRET_KEY}
endpoint = https://${PHOENIX_R2_ACCOUNT_ID}.r2.cloudflarestorage.com
acl = private
EOF

# Merge: remove existing [phoenix-r2] block if present, append new one
python3 - <<'PYEOF'
import re, os
cfg_path = os.path.expanduser("~/.config/rclone/rclone.conf")
new_block = open("/tmp/phoenix_r2_remote.conf").read()
if os.path.exists(cfg_path):
    existing = open(cfg_path).read()
    # remove old phoenix-r2 block
    existing = re.sub(r'\[phoenix-r2\][^\[]*', '', existing, flags=re.DOTALL)
    existing = existing.rstrip('\n') + '\n'
else:
    existing = ''
with open(cfg_path, 'w') as f:
    f.write(existing + new_block)
print("rclone config written")
PYEOF

ok "rclone remote 'phoenix-r2' configured"

# ── test R2 connectivity before pulling ──────────────────────────────────────
info "Testing R2 connection..."
if rclone lsd "phoenix-r2:${PHOENIX_R2_BUCKET}" --max-depth 1 >>"$LOG" 2>&1; then
    ok "R2 bucket accessible: ${PHOENIX_R2_BUCKET}"
else
    die "Cannot reach R2 bucket '${PHOENIX_R2_BUCKET}'. Check credentials."
fi

# ── pull Phoenix from R2 ──────────────────────────────────────────────────────
info "Pulling from R2: ${PHOENIX_R2_BUCKET}/${PHOENIX_R2_PATH} → ${PHOENIX_DEST}"
info "This may take a minute..."

rclone copy \
    "phoenix-r2:${PHOENIX_R2_BUCKET}/${PHOENIX_R2_PATH}" \
    "${PHOENIX_DEST}" \
    --progress \
    --transfers 8 \
    --checkers 16 \
    --exclude "*.exe" \
    --exclude "*.dll" \
    --exclude "*.msi" \
    --exclude "*.ps1" \
    --exclude "node_modules/**" \
    --exclude ".wrangler/**" \
    --log-file="$LOG" \
    --log-level INFO

ok "Phoenix pulled to ${PHOENIX_DEST}"

# file count check
FILE_COUNT=$(find "$PHOENIX_DEST" -type f | wc -l)
info "Files on disk: $FILE_COUNT"
if [[ $FILE_COUNT -lt 10 ]]; then
    warn "Suspiciously few files ($FILE_COUNT). Verify R2 path: ${PHOENIX_R2_PATH}"
fi

# ── verify helix is present ───────────────────────────────────────────────────
HELIX_PATH="$PHOENIX_DEST/sector1/helix/helix_complete_stack.py"
if [[ ! -f "$HELIX_PATH" ]]; then
    # try alternate paths from the pre-deploy tree layout
    ALT=$(find "$PHOENIX_DEST" -name "helix_complete_stack.py" 2>/dev/null | head -1)
    if [[ -n "$ALT" ]]; then
        HELIX_PATH="$ALT"
        warn "helix_complete_stack.py found at non-standard path: $ALT"
    else
        die "helix_complete_stack.py not found under $PHOENIX_DEST — check R2 path"
    fi
fi
ok "Helix stack found: $HELIX_PATH"

# ── run Helix smoke test ──────────────────────────────────────────────────────
info ""
info "Running Helix smoke test..."
info "(This is a controlled first run — benchmark only, no Frank stack, no network)"
info ""

python3 - <<PYEOF
import sys, os
sys.path.insert(0, os.path.dirname("${HELIX_PATH}"))

# import and exercise just the host-detection + benchmark
from helix_complete_stack import HelixHostProfile, HelixSystem

print("── Host Detection ──────────────────────────────────────")
profile = HelixHostProfile()
info = profile.info()
cfg  = profile.config()
for k, v in info.items():
    print(f"  {k:<18} {v}")
print()

print("── Cache Tier Config (auto-scaled to this hardware) ────")
for k, v in cfg.items():
    print(f"  {k:<18} {v}")
print()

# spin up with auto-detected config
helix = HelixSystem(
    l1_cache_mb=cfg['l1_cache_mb'],
    l2_cache_mb=cfg['l2_cache_mb'],
    l3_cache_mb=cfg['l3_cache_mb'],
    virtual_ram_mb=cfg['virtual_ram_mb'],
    page_dir=cfg['page_dir'],
)
helix._host_profile = info  # attach for get_stats

# small allocation test — not the full benchmark, just enough to prove it works
BLOCKS = 50
BLOCK_B = 4096
for i in range(BLOCKS):
    helix.memory.malloc(f'smoke_{i}', b'x' * BLOCK_B)
reads = sum(1 for i in range(BLOCKS) if helix.memory.read(f'smoke_{i}') is not None)

print("── Smoke Test ──────────────────────────────────────────")
print(f"  Blocks written : {BLOCKS}")
print(f"  Blocks readable: {reads}  ({'PASS' if reads == BLOCKS else 'FAIL'})")
snap = helix.get_tier_snapshot()
print(f"  L1 hot_mb      : {snap['hot_mb']:.3f}")
print(f"  Hit rate       : {snap['hit_rate']:.1f}%")
print()

if reads != BLOCKS:
    print("SMOKE TEST FAILED — do not proceed to full Phoenix startup")
    sys.exit(1)
print("SMOKE TEST PASSED — Helix is operational on this hardware")
PYEOF

echo ""
ok "Bootstrap complete. Phoenix is at: ${PHOENIX_DEST}"
ok "Helix verified on this node."
echo ""
echo "Next step: review the smoke test output above, then run the"
echo "full startup only if everything looks right."
echo "Log: $LOG"
