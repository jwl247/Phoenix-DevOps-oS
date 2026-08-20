#!/bim/bash
################################################################################
# LIFE FIRST AI - MODULE DEPLOYMENT SCRIPT
# Run from: ~/phoenix-workspace/lifefirst_modules/
# Usage: sudo ./deploy_modules.sh
################################################################################

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="/var/www/html/lifefirst"
AI_DIR="$PROJECT_DIR/ai"

print_header() { echo -e "\n${BLUE}================================${NC}\n${BLUE}$1${NC}\n${BLUE}================================${NC}\n"; }
print_success() { echo -e "${GREEN}✓ $1${NC}"; }
print_error()   { echo -e "${RED}✗ $1${NC}"; }
print_warn()    { echo -e "${YELLOW}⚠ $1${NC}"; }

if [ "$EUID" -ne 0 ]; then
    print_error "Run as root: sudo ./deploy_modules.sh"
    exit 1
fi

print_header "LIFE FIRST AI — FULL DEPLOYMENT"
echo "From: $SCRIPT_DIR"
echo "To:   $PROJECT_DIR"

mkdir -p "$AI_DIR"

deploy_php() {
    local src="$1" dst="$2" label="$3"
    print_header "$label"
    if [ -f "$SCRIPT_DIR/$src" ]; then
        cp "$SCRIPT_DIR/$src" "$dst"
        chown www-data:www-data "$dst"
        chmod 644 "$dst"
        print_success "$label deployed"
    else
        print_warn "$src not found — skipping"
    fi
}

# Module 1 Database
print_header "Module 1: Database Schema"
if [ -f "$SCRIPT_DIR/module_1_database.sql" ]; then
    echo "MySQL root password:"
    read -s MYSQL_ROOT_PASS
    mysql -u root -p"$MYSQL_ROOT_PASS" lifefirst < "$SCRIPT_DIR/module_1_database.sql" \
        && print_success "Database imported" \
        || print_error "Database import failed"
else
    print_warn "module_1_database.sql not found — skipping"
fi

deploy_php "module_2_api_router.php"      "$PROJECT_DIR/api.php"            "Module 2: API Router"
deploy_php "module_3_schedule_ai.php"     "$AI_DIR/ai_schedule.php"         "Module 3: Schedule AI"
deploy_php "module_4_messenger_ai.php"    "$AI_DIR/ai_messenger.php"        "Module 4: Messenger AI"
deploy_php "module_5_ai_memory.php"       "$AI_DIR/ai_memory.php"           "Module 5: Memory AI"
deploy_php "module_6_notification_ai.php" "$AI_DIR/ai_notifications.php"    "Module 6: Notification AI"

# Module 7 needs capturing from server first
print_header "Module 7: Voice AI"
if [ -f "$SCRIPT_DIR/module_7_ai_voice.php" ]; then
    deploy_php "module_7_ai_voice.php" "$AI_DIR/ai_voice.php" "Module 7: Voice AI"
else
    print_warn "module_7 not in repo yet — capture it first:"
    echo "  sudo cp $AI_DIR/ai_voice.php $SCRIPT_DIR/module_7_ai_voice.php"
fi

chown -R www-data:www-data "$AI_DIR"
chmod -R 644 "$AI_DIR"
find "$AI_DIR" -type d -exec chmod 755 {} \;

print_header "DONE"
print_warn "Add Claude API key when available to all files in $AI_DIR"
echo "Test: curl http://YOUR_SERVER_IP/lifefirst/api.php?action=health"
EOF

chmod +x ~/phoenix-workspace/lifefirst_modules/deploy_modules.sh
