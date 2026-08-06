#!/bin/bash

################################################################################
# LIFE FIRST AI - MODULE DEPLOYMENT SCRIPT
################################################################################
#
# This script deploys your AI module PHP files to the server
#
# USAGE:
# 1. Upload this script and your module files to the server
# 2. chmod +x deploy_modules.sh
# 3. sudo ./deploy_modules.sh
#
################################################################################

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PROJECT_DIR="/var/www/html/lifefirst"
AI_DIR="$PROJECT_DIR/ai"
UPLOAD_DIR="/tmp/lifefirst_modules"

print_header() {
    echo -e "\n${BLUE}================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    print_error "Please run as root (use: sudo ./deploy_modules.sh)"
    exit 1
fi

print_header "DEPLOYING AI MODULES"

# Create upload directory if it doesn't exist
mkdir -p "$UPLOAD_DIR"

echo "Please ensure your module files are in: $UPLOAD_DIR"
echo "Expected files:"
echo "  - module_1_database.sql"
echo "  - module_3_schedule_ai.php"
echo "  - module_4_messenger_ai.php"
echo "  - module_6_notification_ai.php"
echo ""

read -p "Have you uploaded the files to $UPLOAD_DIR? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Please upload files first, then run this script again."
    exit 1
fi

# Deploy Module 1 (Database)
print_header "Deploying Module 1: Database Schema"
if [ -f "$UPLOAD_DIR/module_1_database.sql" ]; then
    echo "Enter MySQL root password:"
    read -s MYSQL_ROOT_PASS
    mysql -u root -p"$MYSQL_ROOT_PASS" lifefirst < "$UPLOAD_DIR/module_1_database.sql"
    if [ $? -eq 0 ]; then
        print_success "Database schema imported"
    else
        print_error "Database import failed"
    fi
else
    print_error "module_1_database.sql not found in $UPLOAD_DIR"
fi

# Deploy Module 3 (Schedule AI)
print_header "Deploying Module 3: Schedule AI"
if [ -f "$UPLOAD_DIR/module_3_schedule_ai.php" ]; then
    cp "$UPLOAD_DIR/module_3_schedule_ai.php" "$AI_DIR/ai_schedule.php"
    chown www-data:www-data "$AI_DIR/ai_schedule.php"
    chmod 644 "$AI_DIR/ai_schedule.php"
    print_success "Schedule AI deployed"
else
    print_error "module_3_schedule_ai.php not found"
fi

# Deploy Module 4 (Messenger AI)
print_header "Deploying Module 4: Messenger AI"
if [ -f "$UPLOAD_DIR/module_4_messenger_ai.php" ]; then
    cp "$UPLOAD_DIR/module_4_messenger_ai.php" "$AI_DIR/ai_messenger.php"
    chown www-data:www-data "$AI_DIR/ai_messenger.php"
    chmod 644 "$AI_DIR/ai_messenger.php"
    print_success "Messenger AI deployed"
else
    print_error "module_4_messenger_ai.php not found"
fi

# Deploy Module 6 (Notification AI)
print_header "Deploying Module 6: Notification AI"
if [ -f "$UPLOAD_DIR/module_6_notification_ai.php" ]; then
    cp "$UPLOAD_DIR/module_6_notification_ai.php" "$AI_DIR/ai_notifications.php"
    chown www-data:www-data "$AI_DIR/ai_notifications.php"
    chmod 644 "$AI_DIR/ai_notifications.php"
    print_success "Notification AI deployed"
else
    print_error "module_6_notification_ai.php not found"
fi

print_header "DEPLOYMENT COMPLETE"

echo -e "${YELLOW}⚠️  IMPORTANT: Update Configuration${NC}"
echo ""
echo "1. Add your Claude API key to:"
echo "   - $AI_DIR/ai_schedule.php (line 25)"
echo "   - $AI_DIR/ai_messenger.php (line 18)"
echo "   - $AI_DIR/ai_notifications.php (line 19)"
echo ""
echo "2. Test the API:"
echo "   curl http://YOUR_SERVER_IP/lifefirst/api.php?action=health"
echo ""
echo -e "${GREEN}✓ All modules deployed!${NC}"
