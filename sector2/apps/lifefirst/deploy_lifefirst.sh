#!/usr/bin/env bash
# deploy_lifefirst.sh — Life First AI System deployment for phoenix-ext
# Phoenix DevOps OS — jwl247
#
# Run on phoenix-ext (Ubuntu, Apache2 + MySQL already running):
#   bash ~/phoenix-devops/lifefirst_modules/deploy_lifefirst.sh
#
# What this does:
#   1. Creates /etc/lifefirst/lifefirst.env  (credentials — ask for values interactively)
#   2. Sets up MySQL: lifefirst user + lifefirst database
#   3. Installs PHP modules to /var/www/html/lifefirst/
#   4. Writes Apache vhost config with SetEnv for credentials
#   5. Prints test URL

set -euo pipefail

WEB_ROOT="/var/www/html/lifefirst"
AI_DIR="$WEB_ROOT/ai"
ENV_DIR="/etc/lifefirst"
ENV_FILE="$ENV_DIR/lifefirst.env"
MODULE_SRC="$(cd "$(dirname "$0")" && pwd)"

# ── colours ──────────────────────────────────────────────────────────────────
G='\033[0;32m'; R='\033[0;31m'; C='\033[0;36m'; B='\033[1m'; N='\033[0m'
ok()  { echo -e "${G}[OK]${N} $*"; }
bad() { echo -e "${R}[FAIL]${N} $*"; exit 1; }
hdr() { echo -e "\n${C}${B}── $* ──${N}"; }

# ── must run as root ──────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    echo "Re-running with sudo..."
    exec sudo bash "$0" "$@"
fi

# ─────────────────────────────────────────────────────────────────────────────
hdr "Step 1 — Credentials"
# ─────────────────────────────────────────────────────────────────────────────

mkdir -p "$ENV_DIR"
chmod 750 "$ENV_DIR"

if [[ -f "$ENV_FILE" ]]; then
    ok "lifefirst.env already exists — loading existing values"
    # shellcheck disable=SC1090
    source "$ENV_FILE"
else
    echo ""
    echo "  You'll need your Claude API key and a MySQL password for the lifefirst user."
    echo "  The API key is at: console.anthropic.com → API Keys"
    echo ""

    read -rsp "  Claude API key: " CLAUDE_API_KEY; echo
    read -rsp "  MySQL password for 'lifefirst' user: " LF_DB_PASS; echo

    # Generate a random API secret for phone auth
    LF_API_SECRET=$(head -c 32 /dev/urandom | base58 2>/dev/null || openssl rand -hex 24)

    cat > "$ENV_FILE" <<EOF
CLAUDE_API_KEY=${CLAUDE_API_KEY}
LF_DB_HOST=localhost
LF_DB_USER=lifefirst
LF_DB_PASS=${LF_DB_PASS}
LF_DB_NAME=lifefirst
LF_API_SECRET=${LF_API_SECRET}
EOF
    chmod 640 "$ENV_FILE"
    chown root:www-data "$ENV_FILE"
    ok "Credentials saved to $ENV_FILE"
fi

# source for use below
# shellcheck disable=SC1090
source "$ENV_FILE"

# ─────────────────────────────────────────────────────────────────────────────
hdr "Step 2 — PHP extensions"
# ─────────────────────────────────────────────────────────────────────────────

PHP_VER=$(php -r 'echo PHP_MAJOR_VERSION.".".PHP_MINOR_VERSION;')
apt-get install -y -q "php${PHP_VER}-mysqli" "php${PHP_VER}-curl" 2>/dev/null || true
phpenmod mysqli curl 2>/dev/null || true
ok "PHP mysqli + curl enabled"

# ─────────────────────────────────────────────────────────────────────────────
hdr "Step 3 — MySQL: lifefirst user + database"
# ─────────────────────────────────────────────────────────────────────────────

mysql -u root <<SQL
CREATE USER IF NOT EXISTS 'lifefirst'@'localhost' IDENTIFIED BY '${LF_DB_PASS}';
CREATE DATABASE IF NOT EXISTS lifefirst CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL PRIVILEGES ON lifefirst.* TO 'lifefirst'@'localhost';
FLUSH PRIVILEGES;
SQL
ok "MySQL user + database ready"

# Import schema (idempotent — uses CREATE TABLE IF NOT EXISTS)
mysql -u lifefirst -p"${LF_DB_PASS}" lifefirst < "${MODULE_SRC}/module_1_database.sql"
ok "Schema imported (module_1_database.sql)"

# ─────────────────────────────────────────────────────────────────────────────
hdr "Step 4 — Deploy PHP modules"
# ─────────────────────────────────────────────────────────────────────────────

mkdir -p "$WEB_ROOT" "$AI_DIR"

# API router
cp "${MODULE_SRC}/module_2_api_router.php"   "$WEB_ROOT/api.php"
cp "${MODULE_SRC}/config.php"                "$WEB_ROOT/ai/config.php"

# AI modules → ai/ sub-directory
cp "${MODULE_SRC}/module_3_schedule_ai.php"   "$AI_DIR/ai_schedule.php"
cp "${MODULE_SRC}/module_4_messenger_ai.php"  "$AI_DIR/ai_messenger.php"
cp "${MODULE_SRC}/module_5_ai_memory.php"     "$AI_DIR/ai_memory.php"
cp "${MODULE_SRC}/module_6_notification_ai.php" "$AI_DIR/ai_notifications.php"
cp "${MODULE_SRC}/module_7_voice_ai.php"      "$AI_DIR/ai_voice.php"

chown -R www-data:www-data "$WEB_ROOT"
chmod -R 750 "$WEB_ROOT"
ok "Modules deployed to $WEB_ROOT"

# ─────────────────────────────────────────────────────────────────────────────
hdr "Step 5 — Apache vhost with SetEnv"
# ─────────────────────────────────────────────────────────────────────────────

VHOST_FILE="/etc/apache2/sites-available/lifefirst.conf"

# Read env file into SetEnv directives
ENV_DIRECTIVES=""
while IFS='=' read -r key val; do
    [[ "$key" =~ ^# ]] && continue
    [[ -z "$key" ]] && continue
    ENV_DIRECTIVES+="    SetEnv ${key} ${val}\n"
done < "$ENV_FILE"

cat > "$VHOST_FILE" <<VHOST
<VirtualHost *:80>
    ServerName lifefirst.local
    DocumentRoot ${WEB_ROOT}

    # Credentials injected into PHP environment
$(echo -e "$ENV_DIRECTIVES")

    <Directory ${WEB_ROOT}>
        Options -Indexes
        AllowOverride None
        Require all granted
    </Directory>

    # Block direct browser access to ai/ sub-modules
    <Directory ${AI_DIR}>
        Require all denied
    </Directory>

    # Allow api.php to include from ai/ internally
    php_admin_value open_basedir "${WEB_ROOT}:/etc/lifefirst"

    ErrorLog \${APACHE_LOG_DIR}/lifefirst_error.log
    CustomLog \${APACHE_LOG_DIR}/lifefirst_access.log combined
</VirtualHost>
VHOST

a2ensite lifefirst.conf
a2enmod php"${PHP_VER}" 2>/dev/null || true
systemctl reload apache2
ok "Apache vhost configured and reloaded"

# ─────────────────────────────────────────────────────────────────────────────
hdr "Step 6 — Smoke test"
# ─────────────────────────────────────────────────────────────────────────────

sleep 1
RESULT=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "http://localhost/lifefirst/api.php" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${LF_API_SECRET}" \
    -d '{"action":"health"}' 2>/dev/null || echo "000")

if [[ "$RESULT" == "200" ]]; then
    ok "API responded HTTP 200"
else
    echo -e "${R}[WARN]${N} API returned HTTP $RESULT — check Apache logs"
fi

# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo -e "${G}${B}Life First deployed.${N}"
echo ""
echo "  API endpoint:  http://$(hostname -I | awk '{print $1}')/lifefirst/api.php"
echo "  API secret:    ${LF_API_SECRET}"
echo "  From WSL:      http://192.168.1.133/lifefirst/api.php"
echo ""
echo "  Test query:"
echo "    curl -s -X POST http://192.168.1.133/lifefirst/api.php \\"
echo "      -H 'Content-Type: application/json' \\"
echo "      -H 'Authorization: Bearer \${LF_API_SECRET}' \\"
echo "      -d '{\"action\":\"voice\",\"user_id\":1,\"message\":\"What time is it?\"}'"
echo ""
