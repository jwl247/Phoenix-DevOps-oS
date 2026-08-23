#!/usr/bin/env bash
# =============================================================================
# persist-smb-mount.sh -- Make /phoenix SMB mount survive Debian reboots
#
# Idempotent. Safe to run multiple times.
#
# What it does:
#   1. Writes /etc/phoenix-cifs.creds  (root-only, 600)
#   2. Adds the fstab entry if not already present
#   3. Reloads systemd so the fstab change takes effect
#   4. Mounts /phoenix right now (if not already mounted)
#   5. Verifies the mount is live and /phoenix/helix-pages/ is reachable
#   6. Prints current fstab state and mount status
#
# Usage (inside Debian as root or phoenix with sudo):
#   bash /phoenix/helix-pages/persist-smb-mount.sh
#   -- OR (if repo is on share) --
#   bash /phoenix/Phoenix-DevOps-oS/tools/poc/persist-smb-mount.sh
#
# After this script runs, /phoenix will mount automatically on every boot.
# No manual mount needed. No password in /proc/mounts or ps output.
# =============================================================================

set -uo pipefail

# ---------------------------------------------------------------------------
# Config — edit these if your credentials change
# ---------------------------------------------------------------------------
SHARE_HOST="10.0.2.2"
SHARE_NAME="Phoenix"
MOUNT_POINT="/phoenix"
CREDS_FILE="/etc/phoenix-cifs.creds"
SMB_USER="jwlef"
SMB_PASS="wtfover1A?"
SMB_DOMAIN=""
FSTAB_OPTS="credentials=${CREDS_FILE},uid=1000,gid=1000,iocharset=utf8,vers=3.0,nofail,_netdev"
FSTAB_ENTRY="//${SHARE_HOST}/${SHARE_NAME}  ${MOUNT_POINT}  cifs  ${FSTAB_OPTS}  0  0"

pass() { echo "  [OK]   $1"; }
fail() { echo "  [FAIL] $1"; }
info() { echo "  [INFO] $1"; }
warn() { echo "  [WARN] $1"; }

echo ""
echo "  Phoenix SMB persistent mount setup"
echo "  ===================================="
echo ""

# ---------------------------------------------------------------------------
# Must run as root
# ---------------------------------------------------------------------------
if [[ $EUID -ne 0 ]]; then
    echo "  Requires root. Re-running with sudo..."
    exec sudo bash "$0" "$@"
fi

# ---------------------------------------------------------------------------
# STEP 1: Install cifs-utils if missing
# ---------------------------------------------------------------------------
if ! command -v mount.cifs &>/dev/null; then
    info "Installing cifs-utils..."
    apt-get install -y cifs-utils 2>&1 | tail -3
fi

if command -v mount.cifs &>/dev/null; then
    pass "mount.cifs available"
else
    fail "mount.cifs not found after install attempt"
    exit 1
fi

# ---------------------------------------------------------------------------
# STEP 2: Write credentials file
# ---------------------------------------------------------------------------
mkdir -p "$(dirname "$CREDS_FILE")"

if [[ -f "$CREDS_FILE" ]]; then
    # Check if it already has the right content
    EXISTING=$(cat "$CREDS_FILE" 2>/dev/null)
    if echo "$EXISTING" | grep -q "username=${SMB_USER}"; then
        pass "Credentials file already exists: $CREDS_FILE"
    else
        warn "Credentials file exists but may be stale — overwriting"
        write_creds=1
    fi
else
    write_creds=1
fi

if [[ "${write_creds:-0}" == "1" ]]; then
    cat > "$CREDS_FILE" << EOF
username=${SMB_USER}
password=${SMB_PASS}
domain=${SMB_DOMAIN}
EOF
    chmod 600 "$CREDS_FILE"
    pass "Credentials written to $CREDS_FILE (mode 600)"
fi

# ---------------------------------------------------------------------------
# STEP 3: Create mount point
# ---------------------------------------------------------------------------
mkdir -p "$MOUNT_POINT"
pass "Mount point exists: $MOUNT_POINT"

# ---------------------------------------------------------------------------
# STEP 4: Add fstab entry if missing
# ---------------------------------------------------------------------------
if grep -q "${SHARE_HOST}/${SHARE_NAME}" /etc/fstab 2>/dev/null; then
    EXISTING_LINE=$(grep "${SHARE_HOST}/${SHARE_NAME}" /etc/fstab)
    pass "fstab entry already present:"
    echo ""
    echo "    $EXISTING_LINE"
    echo ""

    # Check if it has _netdev (required for boot-time mount ordering)
    if ! echo "$EXISTING_LINE" | grep -q "_netdev"; then
        warn "fstab entry missing _netdev — updating it"
        # Remove old entry, add correct one
        sed -i "\\|${SHARE_HOST}/${SHARE_NAME}|d" /etc/fstab
        echo "$FSTAB_ENTRY" >> /etc/fstab
        pass "fstab entry updated with _netdev"
    fi

    # Check if it has nofail (prevents boot stall if share unreachable)
    CURRENT=$(grep "${SHARE_HOST}/${SHARE_NAME}" /etc/fstab)
    if ! echo "$CURRENT" | grep -q "nofail"; then
        warn "fstab entry missing nofail — updating it"
        sed -i "\\|${SHARE_HOST}/${SHARE_NAME}|d" /etc/fstab
        echo "$FSTAB_ENTRY" >> /etc/fstab
        pass "fstab entry updated with nofail"
    fi
else
    echo "$FSTAB_ENTRY" >> /etc/fstab
    pass "fstab entry added"
    echo ""
    echo "    $FSTAB_ENTRY"
    echo ""
fi

# ---------------------------------------------------------------------------
# STEP 5: systemd-networkd-wait-online / remote-fs target check
# ---------------------------------------------------------------------------
# _netdev mounts are handled by remote-fs.target. Make sure it's enabled.
if systemctl is-enabled remote-fs.target &>/dev/null; then
    pass "remote-fs.target is enabled"
else
    systemctl enable remote-fs.target 2>/dev/null || true
    pass "remote-fs.target enabled"
fi

# Reload systemd so it picks up the fstab change
systemctl daemon-reload
pass "systemd daemon reloaded"

# ---------------------------------------------------------------------------
# STEP 6: Mount /phoenix right now (if not already mounted)
# ---------------------------------------------------------------------------
if mountpoint -q "$MOUNT_POINT" 2>/dev/null || mount | grep -q "on ${MOUNT_POINT} "; then
    pass "$MOUNT_POINT already mounted"
else
    info "Mounting $MOUNT_POINT now..."
    if mount "$MOUNT_POINT" 2>&1; then
        pass "$MOUNT_POINT mounted successfully"
    else
        # Try explicit mount in case fstab parse fails
        mount -t cifs "//${SHARE_HOST}/${SHARE_NAME}" "$MOUNT_POINT" \
            -o "$(echo "$FSTAB_OPTS" | sed 's/_netdev,\?//' | sed 's/,nofail//')" \
            && pass "$MOUNT_POINT mounted (explicit)" \
            || { fail "Mount failed — is QEMU running with user-net? Is Windows SMB share active?"; }
    fi
fi

# ---------------------------------------------------------------------------
# STEP 7: Verify helix-pages/ is reachable
# ---------------------------------------------------------------------------
HELIX_DIR="$MOUNT_POINT/helix-pages"
if [[ -d "$HELIX_DIR" ]]; then
    SNAP="$HELIX_DIR/windows_snapshot.json"
    if [[ -f "$SNAP" ]]; then
        SIZE=$(stat -c%s "$SNAP" 2>/dev/null || echo "?")
        pass "helix-pages/ reachable — windows_snapshot.json present ($SIZE bytes)"
    else
        pass "helix-pages/ reachable (no snapshot yet — run test-double-helix.cmd on Windows)"
    fi
else
    warn "helix-pages/ not found — Windows side may not have created it yet"
    info "Run test-double-helix.cmd on Windows to create it"
fi

# ---------------------------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------------------------
echo ""
echo "  Current fstab entry:"
echo ""
grep "${SHARE_HOST}/${SHARE_NAME}" /etc/fstab | sed 's/^/    /'
echo ""

echo "  Mount status:"
mount | grep "$MOUNT_POINT" | sed 's/^/    /' || echo "    (not currently mounted)"
echo ""

echo "  ===================================="
echo "  /phoenix will now mount automatically on every boot."
echo ""
echo "  Test it: sudo umount /phoenix && sudo mount /phoenix"
echo ""
echo "  To run the full end-to-end test:"
echo "    bash /phoenix/helix-pages/test-double-helix.sh"
echo ""
