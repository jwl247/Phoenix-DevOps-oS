#!/usr/bin/env bash
# setup_glossary.sh — Deploy Phoenix Glossary to Apache on phoenix-ext
# Run: sudo bash ~/phoenix-devops/deploy/setup_glossary.sh

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REAL_USER="${SUDO_USER:-$USER}"
WEB_ROOT="/var/www/html/glossary"

echo "[Glossary] Deploying from: $REPO"

mkdir -p "$WEB_ROOT"
cp "$REPO/sector2/glossary/glossary.php" "$WEB_ROOT/index.php"
chown -R www-data:www-data "$WEB_ROOT"
chmod 644 "$WEB_ROOT/index.php"

# Wire Phoenix env into Apache for this vhost
ENV_FILE="/etc/apache2/conf-available/phoenix-env.conf"
if [[ ! -f "$ENV_FILE" ]]; then
    ENV_SOURCE="/home/${REAL_USER}/.phoenix_env"
    PHOENIX_AUTH=$(grep 'PHOENIX_AUTH' "$ENV_SOURCE" 2>/dev/null | head -1 | sed 's/.*="\(.*\)"/\1/' | tr -d '"')
    WORKER_URL=$(grep 'PHOENIX_WORKER_URL' "$ENV_SOURCE" 2>/dev/null | head -1 | sed 's/.*="\(.*\)"/\1/' | tr -d '"')
    cat > "$ENV_FILE" << EOF
# Phoenix environment for Apache/PHP
SetEnv PHOENIX_AUTH "${PHOENIX_AUTH}"
SetEnv PHOENIX_WORKER_URL "${WORKER_URL:-https://packages-worker.phoenix-jwl.workers.dev}"
EOF
    a2enconf phoenix-env
    echo "[Glossary] Phoenix env wired into Apache"
else
    echo "[Glossary] Apache phoenix-env already present"
fi

systemctl reload apache2
echo ""
echo "=== Glossary LIVE ==="
echo "  http://$(hostname -I | awk '{print $1}')/glossary/"
echo "  http://localhost/glossary/"
