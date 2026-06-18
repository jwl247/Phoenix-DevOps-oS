#!/usr/bin/env bash
# setup_desktop.sh — Deploy Phoenix Desktop + Mixer to Apache on phoenix-ext
# Run: sudo bash ~/phoenix-devops/deploy/setup_desktop.sh

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB_ROOT="/var/www/html/desktop"

echo "[Desktop] Deploying from: $REPO"

mkdir -p "$WEB_ROOT/api"
cp "$REPO/sector2/desktop/index.php"        "$WEB_ROOT/index.php"
cp "$REPO/sector2/desktop/mixer.php"        "$WEB_ROOT/mixer.php"
cp "$REPO/sector2/desktop/switches.php"     "$WEB_ROOT/switches.php"
cp "$REPO/sector2/desktop/filetree.php"     "$WEB_ROOT/filetree.php"
cp "$REPO/sector2/desktop/api/service.php"  "$WEB_ROOT/api/service.php"
cp "$REPO/sector2/desktop/api/sysinfo.php"  "$WEB_ROOT/api/sysinfo.php"
cp "$REPO/sector2/desktop/api/switches.php" "$WEB_ROOT/api/switches.php"
cp "$REPO/sector2/desktop/api/files.php"    "$WEB_ROOT/api/files.php"
cp "$REPO/sector2/desktop/api/shell.php"    "$WEB_ROOT/api/shell.php"

# Phoenix state dirs
mkdir -p /var/phoenix /var/log/phoenix
chown www-data:www-data /var/phoenix /var/log/phoenix

chown -R www-data:www-data "$WEB_ROOT"
chmod 644 "$WEB_ROOT"/*.php "$WEB_ROOT/api"/*.php

# ── sudoers: allow www-data to run systemctl for mixer service control ────────
SUDOERS="/etc/sudoers.d/phoenix-mixer"
if [[ ! -f "$SUDOERS" ]]; then
    cat > "$SUDOERS" <<'EOF'
www-data ALL=(ALL) NOPASSWD: \
  /bin/systemctl start ssh, \
  /bin/systemctl stop ssh, \
  /bin/systemctl restart ssh, \
  /bin/systemctl is-active ssh, \
  /bin/systemctl start wg-quick@wg0, \
  /bin/systemctl stop wg-quick@wg0, \
  /bin/systemctl restart wg-quick@wg0, \
  /bin/systemctl is-active wg-quick@wg0, \
  /bin/systemctl start cloudflared, \
  /bin/systemctl stop cloudflared, \
  /bin/systemctl restart cloudflared, \
  /bin/systemctl is-active cloudflared, \
  /bin/systemctl start phoenix-kernel, \
  /bin/systemctl stop phoenix-kernel, \
  /bin/systemctl restart phoenix-kernel, \
  /bin/systemctl is-active phoenix-kernel, \
  /bin/systemctl start phoenix-conversion-agent, \
  /bin/systemctl stop phoenix-conversion-agent, \
  /bin/systemctl restart phoenix-conversion-agent, \
  /bin/systemctl is-active phoenix-conversion-agent, \
  /bin/systemctl start ollama, \
  /bin/systemctl stop ollama, \
  /bin/systemctl restart ollama, \
  /bin/systemctl is-active ollama, \
  /bin/systemctl start apache2, \
  /bin/systemctl stop apache2, \
  /bin/systemctl restart apache2, \
  /bin/systemctl is-active apache2, \
  /bin/systemctl start snap.nextcloud.apache, \
  /bin/systemctl stop snap.nextcloud.apache, \
  /bin/systemctl restart snap.nextcloud.apache, \
  /bin/systemctl is-active snap.nextcloud.apache, \
  /bin/systemctl start snap.prometheus.prometheus, \
  /bin/systemctl stop snap.prometheus.prometheus, \
  /bin/systemctl restart snap.prometheus.prometheus, \
  /bin/systemctl is-active snap.prometheus.prometheus
EOF
    chmod 440 "$SUDOERS"
    echo "[Desktop] sudoers written: $SUDOERS"
else
    echo "[Desktop] sudoers already exists: $SUDOERS"
fi

systemctl reload apache2

IP=$(hostname -I | awk '{print $1}')
echo ""
echo "=== Phoenix Desktop LIVE ==="
echo "  Desktop:  http://$IP/desktop/"
echo "  Mixer:    http://$IP/desktop/mixer.php"
echo "  Switches: http://$IP/desktop/switches.php"
echo "  Files:    http://$IP/desktop/filetree.php"
echo ""
echo "  Global Shell: backtick (\`) or F12 from anywhere in the Desktop"
