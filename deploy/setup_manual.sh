#!/usr/bin/env bash
# setup_manual.sh — Deploy Phoenix Operator Manual to Apache
# Run: sudo bash ~/phoenix-devops/deploy/setup_manual.sh

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB="/var/www/html/manual"

mkdir -p "$WEB"
cp "${REPO}/sector2/manual/index.php" "$WEB/index.php"
chown -R www-data:www-data "$WEB"
chmod -R 750 "$WEB"

# Ensure Phoenix env is wired (glossary conf covers it, but make sure)
if [ -f /etc/apache2/conf-available/phoenix-env.conf ]; then
    a2enconf phoenix-env 2>/dev/null || true
    systemctl reload apache2
fi

echo ""
echo "=== Operator Manual LIVE ==="
echo "  http://$(hostname -I | awk '{print $1}')/manual/"
echo "  http://localhost/manual/"
