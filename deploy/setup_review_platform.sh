#!/usr/bin/env bash
# setup_review_platform.sh — Deploy Phoenix Review Platform to Apache
# Run: sudo bash ~/phoenix-devops/deploy/setup_review_platform.sh

set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB_ROOT="/var/www/html/review"

mkdir -p "$WEB_ROOT"
cp "$REPO/sector2/review-platform/index.php" "$WEB_ROOT/index.php"
chown -R www-data:www-data "$WEB_ROOT"
chmod 644 "$WEB_ROOT/index.php"
systemctl reload apache2

echo "=== Review Platform LIVE ==="
echo "  http://$(hostname -I | awk '{print $1}')/review/"
