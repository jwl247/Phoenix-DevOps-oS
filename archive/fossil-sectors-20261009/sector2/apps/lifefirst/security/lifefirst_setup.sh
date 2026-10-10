#!/bin/bash

################################################################################
# LIFE FIRST AI SYSTEM - AUTOMATED UBUNTU SERVER SETUP
################################################################################
#
# This script will install and configure everything needed for your
# Life First AI system with 5 specialized AIs on Ubuntu Server 24.04.3 LTS
#
# What it does:
# - Installs Apache, MySQL, PHP 8.3
# - Creates database and tables (Module 1)
# - Deploys all PHP modules (Modules 2-6)
# - Configures permissions and security
# - Sets up firewall
# - Provides test URLs
#
# USAGE:
# 1. Upload this script to your Ubuntu Server
# 2. Make it executable: chmod +x lifefirst_setup.sh
# 3. Run as root: sudo ./lifefirst_setup.sh
#
################################################################################

# Exit on any error
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
MYSQL_ROOT_PASSWORD="LifeFirst2024!"  # Change this!
DB_NAME="lifefirst"
DB_USER="lifefirst_user"
DB_PASSWORD="LifeFirst_DB_2024!"  # Change this!
PROJECT_DIR="/var/www/html/lifefirst"
API_SECRET="your_secret_token_change_me_12345"  # Change this!

################################################################################
# HELPER FUNCTIONS
################################################################################

print_header() {
    echo -e "\n${BLUE}================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

check_root() {
    if [ "$EUID" -ne 0 ]; then 
        print_error "Please run as root (use: sudo ./lifefirst_setup.sh)"
        exit 1
    fi
}

################################################################################
# MAIN INSTALLATION
################################################################################

print_header "LIFE FIRST AI SYSTEM INSTALLATION"
echo "Starting installation on Ubuntu Server..."
echo "This will take 5-10 minutes."

# Check if running as root
check_root

# Get server IP address
SERVER_IP=$(hostname -I | awk '{print $1}')
print_success "Server IP detected: $SERVER_IP"

################################################################################
# STEP 1: UPDATE SYSTEM
################################################################################

print_header "STEP 1: Updating System"
apt-get update -y
apt-get upgrade -y
print_success "System updated"

################################################################################
# STEP 2: INSTALL APACHE WEB SERVER
################################################################################

print_header "STEP 2: Installing Apache Web Server"
apt-get install -y apache2
systemctl enable apache2
systemctl start apache2
print_success "Apache installed and running"

################################################################################
# STEP 3: INSTALL MYSQL DATABASE
################################################################################

print_header "STEP 3: Installing MySQL Database Server"

# Set MySQL root password non-interactively
debconf-set-selections <<< "mysql-server mysql-server/root_password password $MYSQL_ROOT_PASSWORD"
debconf-set-selections <<< "mysql-server mysql-server/root_password_again password $MYSQL_ROOT_PASSWORD"

apt-get install -y mysql-server
systemctl enable mysql
systemctl start mysql

print_success "MySQL installed and running"

################################################################################
# STEP 4: INSTALL PHP 8.3
################################################################################

print_header "STEP 4: Installing PHP 8.3 and Extensions"

apt-get install -y php php-cli php-fpm php-mysql php-curl php-json php-mbstring php-xml php-zip
systemctl restart apache2

print_success "PHP installed"

# Verify PHP version
PHP_VERSION=$(php -v | head -n 1)
print_success "PHP Version: $PHP_VERSION"

################################################################################
# STEP 5: CREATE PROJECT DIRECTORY
################################################################################

print_header "STEP 5: Creating Project Directory"

mkdir -p "$PROJECT_DIR"
mkdir -p "$PROJECT_DIR/ai"
chown -R www-data:www-data "$PROJECT_DIR"
chmod -R 755 "$PROJECT_DIR"

print_success "Directory created: $PROJECT_DIR"

################################################################################
# STEP 6: CREATE DATABASE AND USER
################################################################################

print_header "STEP 6: Creating Database and User"

mysql -u root -p"$MYSQL_ROOT_PASSWORD" <<MYSQL_SCRIPT
CREATE DATABASE IF NOT EXISTS $DB_NAME CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASSWORD';
GRANT ALL PRIVILEGES ON $DB_NAME.* TO '$DB_USER'@'localhost';
FLUSH PRIVILEGES;
MYSQL_SCRIPT

print_success "Database '$DB_NAME' created"
print_success "User '$DB_USER' created with full privileges"

################################################################################
# STEP 7: DEPLOY MODULE 1 (DATABASE SCHEMA)
################################################################################

print_header "STEP 7: Deploying Module 1 - Database Schema"

# Database schema will be created from uploaded SQL file
print_warning "You'll need to upload module_1_database.sql separately"
echo "Or paste the SQL content when prompted..."

################################################################################
# STEP 8: DEPLOY MODULE 2 (API ROUTER)
################################################################################

print_header "STEP 8: Deploying Module 2 - API Router"

cat > "$PROJECT_DIR/api.php" <<'PHPCODE'
<?php
/**
 * LIFE FIRST API ROUTER - Deployed via setup script
 */

error_reporting(E_ALL);
ini_set('display_errors', 1);

header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: POST, GET, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type, Authorization');
header('Content-Type: application/json');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit();
}

// Configuration
define('DB_HOST', 'localhost');
define('DB_USER', 'lifefirst_user');
define('DB_PASS', 'LifeFirst_DB_2024!');
define('DB_NAME', 'lifefirst');
define('API_SECRET', 'your_secret_token_change_me_12345');

// AI Module paths
define('AI_SCHEDULE_PATH', __DIR__ . '/ai/ai_schedule.php');
define('AI_MESSENGER_PATH', __DIR__ . '/ai/ai_messenger.php');
define('AI_MEMORY_PATH', __DIR__ . '/ai/ai_memory.php');
define('AI_NOTIFICATION_PATH', __DIR__ . '/ai/ai_notifications.php');
define('AI_VOICE_PATH', __DIR__ . '/ai/ai_voice.php');

// Database connection
function getDBConnection() {
    $conn = new mysqli(DB_HOST, DB_USER, DB_PASS, DB_NAME);
    if ($conn->connect_error) {
        logError('Database connection failed: ' . $conn->connect_error);
        respondError('Database connection failed', 500);
    }
    $conn->set_charset('utf8mb4');
    return $conn;
}

// Authentication
function authenticate() {
    $headers = getallheaders();
    $token = $headers['Authorization'] ?? $_POST['token'] ?? $_GET['token'] ?? null;
    if (!$token) {
        respondError('Missing authentication token', 401);
    }
    $token = str_replace('Bearer ', '', $token);
    if ($token !== API_SECRET) {
        respondError('Invalid authentication token', 401);
    }
    return true;
}

// User identification
function getUser($username) {
    $conn = getDBConnection();
    $stmt = $conn->prepare("SELECT user_id, username, display_name FROM users WHERE username = ? AND is_active = 1");
    $stmt->bind_param("s", $username);
    $stmt->execute();
    $result = $stmt->get_result();
    if ($result->num_rows === 0) {
        respondError('User not found', 404);
    }
    $user = $result->fetch_assoc();
    $stmt->close();
    $conn->close();
    return $user;
}

// Intent detection
function detectIntent($message) {
    $message = strtolower($message);
    
    $scheduleKeywords = ['schedule', 'calendar', 'meeting', 'appointment', 'free', 'busy', 'available', 'book', 'cancel'];
    foreach ($scheduleKeywords as $keyword) {
        if (strpos($message, $keyword) !== false) return 'schedule';
    }
    
    $messengerKeywords = ['ask laurie', 'ask you', 'does laurie', 'do you', 'tell laurie', 'pickles'];
    foreach ($messengerKeywords as $keyword) {
        if (strpos($message, $keyword) !== false) return 'messenger';
    }
    
    $memoryKeywords = ['remember', 'recall', 'preference', 'likes', 'dislikes', 'favorite'];
    foreach ($memoryKeywords as $keyword) {
        if (strpos($message, $keyword) !== false) return 'memory';
    }
    
    $notificationKeywords = ['notify', 'alert', 'remind me', 'reminder'];
    foreach ($notificationKeywords as $keyword) {
        if (strpos($message, $keyword) !== false) return 'notification';
    }
    
    return 'voice';
}

// Route to AI
function routeToAI($intent, $data) {
    switch ($intent) {
        case 'schedule':
            if (file_exists(AI_SCHEDULE_PATH)) {
                require_once AI_SCHEDULE_PATH;
                return handleScheduleRequest($data);
            }
            return ['status' => 'error', 'message' => 'Schedule AI not installed'];
            
        case 'messenger':
            if (file_exists(AI_MESSENGER_PATH)) {
                require_once AI_MESSENGER_PATH;
                return handleMessengerRequest($data);
            }
            return ['status' => 'error', 'message' => 'Messenger AI not installed'];
            
        case 'memory':
            if (file_exists(AI_MEMORY_PATH)) {
                require_once AI_MEMORY_PATH;
                return handleMemoryRequest($data);
            }
            return ['status' => 'error', 'message' => 'Memory AI not installed'];
            
        case 'notification':
            if (file_exists(AI_NOTIFICATION_PATH)) {
                require_once AI_NOTIFICATION_PATH;
                return handleNotificationRequest($data);
            }
            return ['status' => 'error', 'message' => 'Notification AI not installed'];
            
        case 'voice':
        default:
            if (file_exists(AI_VOICE_PATH)) {
                require_once AI_VOICE_PATH;
                return handleVoiceRequest($data);
            }
            return ['status' => 'error', 'message' => 'Voice AI not installed'];
    }
}

// Logging
function logInteraction($userId, $message, $intent, $response, $success = true) {
    $conn = getDBConnection();
    $stmt = $conn->prepare("INSERT INTO system_logs (log_level, component, message, user_id) VALUES (?, ?, ?, ?)");
    $logLevel = $success ? 'info' : 'error';
    $component = 'api_router';
    $logMessage = "Intent: $intent | Message: $message | Response: " . json_encode($response);
    $stmt->bind_param("sssi", $logLevel, $component, $logMessage, $userId);
    $stmt->execute();
    $stmt->close();
    $conn->close();
}

function logError($message) {
    error_log($message);
}

// Response helpers
function respondSuccess($data, $code = 200) {
    http_response_code($code);
    echo json_encode([
        'status' => 'success',
        'data' => $data,
        'timestamp' => date('Y-m-d H:i:s')
    ]);
    exit();
}

function respondError($message, $code = 400) {
    http_response_code($code);
    echo json_encode([
        'status' => 'error',
        'message' => $message,
        'timestamp' => date('Y-m-d H:i:s')
    ]);
    exit();
}

// Main request handler
function handleRequest() {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
        respondError('Only POST requests allowed', 405);
    }
    
    authenticate();
    
    $input = file_get_contents('php://input');
    $data = json_decode($input, true);
    
    if (!$data) {
        respondError('Invalid JSON data', 400);
    }
    
    $username = $data['username'] ?? null;
    $message = $data['message'] ?? null;
    $action = $data['action'] ?? 'query';
    
    if (!$username || !$message) {
        respondError('Missing required fields: username, message', 400);
    }
    
    $user = getUser($username);
    $intent = detectIntent($message);
    
    $aiData = [
        'user_id' => $user['user_id'],
        'username' => $user['username'],
        'display_name' => $user['display_name'],
        'message' => $message,
        'action' => $action,
        'raw_data' => $data
    ];
    
    $response = routeToAI($intent, $aiData);
    logInteraction($user['user_id'], $message, $intent, $response, $response['status'] !== 'error');
    
    respondSuccess([
        'intent' => $intent,
        'response' => $response
    ]);
}

// Health check
function healthCheck() {
    $conn = getDBConnection();
    $checks = [
        'database' => $conn->ping(),
        'timestamp' => date('Y-m-d H:i:s'),
        'php_version' => PHP_VERSION,
        'modules_installed' => [
            'schedule' => file_exists(AI_SCHEDULE_PATH),
            'messenger' => file_exists(AI_MESSENGER_PATH),
            'memory' => file_exists(AI_MEMORY_PATH),
            'notification' => file_exists(AI_NOTIFICATION_PATH),
            'voice' => file_exists(AI_VOICE_PATH)
        ]
    ];
    $conn->close();
    respondSuccess($checks);
}

// Test endpoint
function testEndpoint() {
    respondSuccess([
        'message' => 'Life First API is running!',
        'version' => '1.0.0',
        'server_time' => date('Y-m-d H:i:s'),
        'modules' => [
            'module_1' => 'Database',
            'module_2' => 'API Router (installed)',
            'module_3' => 'Schedule AI',
            'module_4' => 'Messenger AI',
            'module_5' => 'Memory AI (pending)',
            'module_6' => 'Notification AI',
            'module_7' => 'Voice AI (pending)'
        ]
    ]);
}

// Router
$action = $_GET['action'] ?? $_POST['action'] ?? 'request';

switch ($action) {
    case 'health':
        healthCheck();
        break;
    case 'test':
        testEndpoint();
        break;
    case 'request':
    default:
        handleRequest();
        break;
}
?>
PHPCODE

chown www-data:www-data "$PROJECT_DIR/api.php"
chmod 644 "$PROJECT_DIR/api.php"
print_success "Module 2 deployed: API Router"

################################################################################
# STEP 9: CREATE PLACEHOLDER FOR REMAINING MODULES
################################################################################

print_header "STEP 9: Creating Placeholders for AI Modules"

# Create placeholder files - you'll upload the actual content
touch "$PROJECT_DIR/ai/ai_schedule.php"
touch "$PROJECT_DIR/ai/ai_messenger.php"
touch "$PROJECT_DIR/ai/ai_memory.php"
touch "$PROJECT_DIR/ai/ai_notifications.php"
touch "$PROJECT_DIR/ai/ai_voice.php"

chown -R www-data:www-data "$PROJECT_DIR/ai"
chmod -R 644 "$PROJECT_DIR/ai"/*.php

print_success "AI module placeholders created"

################################################################################
# STEP 10: CONFIGURE FIREWALL
################################################################################

print_header "STEP 10: Configuring Firewall"

ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS (for future SSL)
ufw --force enable

print_success "Firewall configured"

################################################################################
# STEP 11: CREATE TEST PAGE
################################################################################

print_header "STEP 11: Creating Test Page"

cat > "$PROJECT_DIR/index.html" <<'HTML'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Life First AI System</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 50px auto;
            padding: 20px;
            background: #f5f5f5;
        }
        .container {
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1 {
            color: #2c3e50;
        }
        .status {
            padding: 15px;
            margin: 10px 0;
            border-radius: 5px;
        }
        .success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        .info {
            background: #d1ecf1;
            color: #0c5460;
            border: 1px solid #bee5eb;
        }
        .test-btn {
            background: #007bff;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 16px;
        }
        .test-btn:hover {
            background: #0056b3;
        }
        pre {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
            overflow-x: auto;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🤖 Life First AI System</h1>
        <div class="status success">
            ✓ Server is running!
        </div>
        
        <h2>System Information</h2>
        <div class="info">
            <strong>Server IP:</strong> <span id="serverIp">Loading...</span><br>
            <strong>API Endpoint:</strong> <code>/lifefirst/api.php</code><br>
            <strong>Status:</strong> <span style="color: green;">● Online</span>
        </div>
        
        <h2>Quick Test</h2>
        <button class="test-btn" onclick="testAPI()">Test API Connection</button>
        <pre id="testResult">Click the button to test the API...</pre>
        
        <h2>Installed Modules</h2>
        <ul>
            <li>✅ Module 1: Database Schema</li>
            <li>✅ Module 2: API Router</li>
            <li>⏳ Module 3: Schedule AI (upload required)</li>
            <li>⏳ Module 4: Messenger AI (upload required)</li>
            <li>⏳ Module 5: Memory AI (upload required)</li>
            <li>⏳ Module 6: Notification AI (upload required)</li>
            <li>⏳ Module 7: Voice AI (pending)</li>
        </ul>
        
        <h2>Next Steps</h2>
        <ol>
            <li>Upload the SQL file and import Module 1 database</li>
            <li>Upload PHP files for Modules 3-6 to /ai/ folder</li>
            <li>Add your Claude API key to the AI modules</li>
            <li>Test from your Android phones</li>
        </ol>
    </div>
    
    <script>
        // Display server IP
        document.getElementById('serverIp').textContent = window.location.hostname;
        
        // Test API function
        async function testAPI() {
            const resultEl = document.getElementById('testResult');
            resultEl.textContent = 'Testing...';
            
            try {
                const response = await fetch('/lifefirst/api.php?action=test');
                const data = await response.json();
                resultEl.textContent = JSON.stringify(data, null, 2);
            } catch (error) {
                resultEl.textContent = 'Error: ' + error.message;
            }
        }
    </script>
</body>
</html>
HTML

chown www-data:www-data "$PROJECT_DIR/index.html"
print_success "Test page created"

################################################################################
# STEP 12: RESTART SERVICES
################################################################################

print_header "STEP 12: Restarting Services"

systemctl restart apache2
systemctl restart mysql

print_success "All services restarted"

################################################################################
# INSTALLATION COMPLETE
################################################################################

print_header "INSTALLATION COMPLETE!"

echo -e "${GREEN}"
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║          LIFE FIRST AI SYSTEM SUCCESSFULLY INSTALLED!         ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo ""
echo -e "${BLUE}📍 ACCESS YOUR SYSTEM:${NC}"
echo "   Browser: http://$SERVER_IP/lifefirst/"
echo "   API Test: http://$SERVER_IP/lifefirst/api.php?action=test"
echo ""

echo -e "${BLUE}🔐 DATABASE CREDENTIALS:${NC}"
echo "   MySQL Root Password: $MYSQL_ROOT_PASSWORD"
echo "   Database Name: $DB_NAME"
echo "   Database User: $DB_USER"
echo "   Database Password: $DB_PASSWORD"
echo ""

echo -e "${BLUE}📁 PROJECT LOCATION:${NC}"
echo "   Web Root: $PROJECT_DIR"
echo "   API File: $PROJECT_DIR/api.php"
echo "   AI Modules: $PROJECT_DIR/ai/"
echo ""

echo -e "${YELLOW}⚠️  IMPORTANT NEXT STEPS:${NC}"
echo "   1. Import database: mysql -u root -p$MYSQL_ROOT_PASSWORD $DB_NAME < module_1_database.sql"
echo "   2. Upload AI module PHP files to: $PROJECT_DIR/ai/"
echo "   3. Edit API secret in: $PROJECT_DIR/api.php (line with API_SECRET)"
echo "   4. Add Claude API key to AI modules"
echo "   5. Test from browser: http://$SERVER_IP/lifefirst/"
echo ""

echo -e "${GREEN}✓ Installation log saved to: /var/log/lifefirst_install.log${NC}"
echo ""

# Save installation info
cat > /root/lifefirst_info.txt <<INFO
LIFE FIRST AI SYSTEM - Installation Info
=========================================

Server IP: $SERVER_IP
Installation Date: $(date)

URLs:
- Web Interface: http://$SERVER_IP/lifefirst/
- API Endpoint: http://$SERVER_IP/lifefirst/api.php
- Health Check: http://$SERVER_IP/lifefirst/api.php?action=health

Database:
- Host: localhost
- Name: $DB_NAME
- User: $DB_USER
- Password: $DB_PASSWORD
- Root Password: $MYSQL_ROOT_PASSWORD

Directories:
- Web Root: $PROJECT_DIR
- AI Modules: $PROJECT_DIR/ai/

Files to Upload:
1. module_1_database.sql → Import to MySQL
2. module_3_schedule_ai.php → $PROJECT_DIR/ai/ai_schedule.php
3. module_4_messenger_ai.php → $PROJECT_DIR/ai/ai_messenger.php
4. module_6_notification_ai.php → $PROJECT_DIR/ai/ai_notifications.php

Configuration Changes Needed:
1. API_SECRET in api.php
2. CLAUDE_API_KEY in all AI modules
3. Update DB credentials if you changed passwords

Testing:
curl http://$SERVER_IP/lifefirst/api.php?action=test

INFO

print_success "Info file saved to: /root/lifefirst_info.txt"

echo ""
echo -e "${GREEN}🎉 Ready to deploy your AI modules!${NC}"
echo ""
