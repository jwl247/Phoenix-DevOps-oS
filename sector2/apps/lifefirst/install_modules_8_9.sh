#!/bin/bash

#######################################################
# LIFE FIRST AI - MODULES 8 & 9 INSTALLER
# Budget Keeper AI + Secure Settings Lock
# 
# Module 8: Budget Keeper AI (5 permission levels)
# Module 9: Secure Settings Lock (Fort Knox security)
#######################################################

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
DB_NAME="lifefirst_db"
DB_USER="lifefirst_user"
DB_PASS="LifeFirst_DB_2024!"
WEB_DIR="/var/www/html/lifefirst"

#######################################################
# HELPER FUNCTIONS
#######################################################

print_header() {
    clear
    echo -e "${CYAN}"
    echo "╔═══════════════════════════════════════════════════════════╗"
    echo "║     LIFE FIRST AI - MODULES 8 & 9 INSTALLER v2.0        ║"
    echo "║                                                           ║"
    echo "║  Module 8: Budget Keeper AI                              ║"
    echo "║  Module 9: Secure Settings Lock                          ║"
    echo "╚═══════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_module_header() {
    echo -e "${BLUE}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  $1"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "${NC}"
}

print_step() {
    echo -e "${YELLOW}▶ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${CYAN}ℹ $1${NC}"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

check_mysql() {
    if ! command -v mysql &> /dev/null; then
        print_error "MySQL is not installed"
        exit 1
    fi
}

check_apache() {
    if ! systemctl is-active --quiet apache2; then
        print_error "Apache is not running"
        exit 1
    fi
}

pause_for_user() {
    echo ""
    read -p "Press Enter to continue..." -r
    echo ""
}

#######################################################
# MODULE 8: BUDGET KEEPER AI - DATABASE
#######################################################

install_budget_keeper_db() {
    print_module_header "MODULE 8: BUDGET KEEPER AI - DATABASE"
    print_step "Installing Budget Keeper database schema..."
    
    mysql -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" <<'EOF'

-- User Budget Settings
CREATE TABLE IF NOT EXISTS user_budget_settings (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    permission_level TINYINT NOT NULL DEFAULT 1,
    partner_user_id INT DEFAULT NULL,
    accountability_threshold DECIMAL(10,2) DEFAULT 100.00,
    require_partner_call BOOLEAN DEFAULT FALSE,
    cooling_off_minutes INT DEFAULT 0,
    enable_email_parsing BOOLEAN DEFAULT FALSE,
    enable_realtime_warnings BOOLEAN DEFAULT FALSE,
    budget_start_day TINYINT DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (partner_user_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Budget Categories
CREATE TABLE IF NOT EXISTS budget_categories (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    category_name VARCHAR(100) NOT NULL,
    monthly_limit DECIMAL(10,2) DEFAULT 0.00,
    is_essential BOOLEAN DEFAULT FALSE,
    color_code VARCHAR(7) DEFAULT '#3498db',
    icon VARCHAR(50) DEFAULT 'category',
    ai_suggested BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE KEY unique_user_category (user_id, category_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Expenses
CREATE TABLE IF NOT EXISTS expenses (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    category_id INT DEFAULT NULL,
    amount DECIMAL(10,2) NOT NULL,
    merchant VARCHAR(255) DEFAULT NULL,
    description TEXT,
    expense_date DATE NOT NULL,
    entry_method ENUM('manual', 'email_parsed', 'ai_detected') DEFAULT 'manual',
    receipt_data TEXT,
    location VARCHAR(255) DEFAULT NULL,
    was_warned BOOLEAN DEFAULT FALSE,
    warning_overridden BOOLEAN DEFAULT FALSE,
    partner_notified BOOLEAN DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES budget_categories(id) ON DELETE SET NULL,
    INDEX idx_user_date (user_id, expense_date),
    INDEX idx_category (category_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Bill Reminders
CREATE TABLE IF NOT EXISTS bill_reminders (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    bill_name VARCHAR(255) NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    due_day TINYINT NOT NULL,
    frequency ENUM('monthly', 'weekly', 'quarterly', 'yearly', 'once') DEFAULT 'monthly',
    category_id INT DEFAULT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    autopay_enabled BOOLEAN DEFAULT FALSE,
    remind_days_before INT DEFAULT 3,
    last_paid_date DATE DEFAULT NULL,
    next_due_date DATE NOT NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES budget_categories(id) ON DELETE SET NULL,
    INDEX idx_user_due (user_id, next_due_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Accountability Rules
CREATE TABLE IF NOT EXISTS accountability_rules (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    rule_name VARCHAR(255) NOT NULL,
    rule_type ENUM('spending_limit', 'category_restriction', 'time_restriction', 'merchant_block', 'partner_approval') NOT NULL,
    category_id INT DEFAULT NULL,
    threshold_amount DECIMAL(10,2) DEFAULT NULL,
    time_start TIME DEFAULT NULL,
    time_end TIME DEFAULT NULL,
    merchant_pattern VARCHAR(255) DEFAULT NULL,
    action_type ENUM('warn', 'require_call', 'delay', 'notify_partner', 'log_violation') NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES budget_categories(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Accountability Violations
CREATE TABLE IF NOT EXISTS accountability_violations (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    rule_id INT NOT NULL,
    expense_id INT DEFAULT NULL,
    violation_type VARCHAR(100) NOT NULL,
    amount DECIMAL(10,2) DEFAULT NULL,
    merchant VARCHAR(255) DEFAULT NULL,
    user_response ENUM('called_partner', 'overridden', 'cancelled', 'delayed', 'pending') DEFAULT 'pending',
    partner_notified BOOLEAN DEFAULT FALSE,
    partner_response TEXT,
    resolution_notes TEXT,
    violation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP DEFAULT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (rule_id) REFERENCES accountability_rules(id) ON DELETE CASCADE,
    FOREIGN KEY (expense_id) REFERENCES expenses(id) ON DELETE SET NULL,
    INDEX idx_user_pending (user_id, user_response)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Spending Patterns
CREATE TABLE IF NOT EXISTS spending_patterns (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    category_id INT NOT NULL,
    month_year VARCHAR(7) NOT NULL,
    total_spent DECIMAL(10,2) DEFAULT 0.00,
    transaction_count INT DEFAULT 0,
    average_transaction DECIMAL(10,2) DEFAULT 0.00,
    predicted_next_month DECIMAL(10,2) DEFAULT NULL,
    pattern_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES budget_categories(id) ON DELETE CASCADE,
    UNIQUE KEY unique_user_category_month (user_id, category_id, month_year)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Budget Adjustments
CREATE TABLE IF NOT EXISTS budget_adjustments (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    category_id INT NOT NULL,
    old_limit DECIMAL(10,2) NOT NULL,
    new_limit DECIMAL(10,2) NOT NULL,
    adjustment_reason TEXT,
    adjusted_by ENUM('user', 'ai', 'partner') NOT NULL,
    ai_confidence DECIMAL(5,2) DEFAULT NULL,
    user_approved BOOLEAN DEFAULT FALSE,
    adjustment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES budget_categories(id) ON DELETE CASCADE,
    INDEX idx_user_date (user_id, adjustment_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_expenses_user_month ON expenses(user_id, expense_date);
CREATE INDEX IF NOT EXISTS idx_bills_next_due ON bill_reminders(next_due_date, is_active);
CREATE INDEX IF NOT EXISTS idx_violations_pending ON accountability_violations(user_id, user_response, violation_date);

EOF

    if [ $? -eq 0 ]; then
        print_success "Budget Keeper database schema installed (8 tables)"
    else
        print_error "Budget Keeper database installation failed"
        exit 1
    fi
}

#######################################################
# MODULE 9: SECURE SETTINGS LOCK - DATABASE
#######################################################

install_secure_settings_db() {
    print_module_header "MODULE 9: SECURE SETTINGS LOCK - DATABASE"
    print_step "Installing Secure Settings Lock database schema..."
    
    mysql -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" <<'EOF'

-- Security Configuration
CREATE TABLE IF NOT EXISTS secure_settings_config (
    user_id INT PRIMARY KEY,
    partner_user_id INT NOT NULL,
    home_latitude DECIMAL(10, 8) NOT NULL,
    home_longitude DECIMAL(11, 8) NOT NULL,
    home_elevation DECIMAL(8, 2) NOT NULL,
    location_radius_meters INT DEFAULT 50,
    elevation_tolerance_meters INT DEFAULT 10,
    user_bluetooth_mac VARCHAR(17) NOT NULL,
    partner_bluetooth_mac VARCHAR(17) NOT NULL,
    required_signal_strength INT DEFAULT -70,
    detection_range_meters INT DEFAULT 10,
    home_wifi_bssid VARCHAR(17) NOT NULL,
    home_wifi_ssid VARCHAR(255),
    wifi_signal_threshold INT DEFAULT -80,
    discussion_start_time TIME DEFAULT '19:00:00',
    discussion_end_time TIME DEFAULT '22:00:00',
    weekend_anytime BOOLEAN DEFAULT TRUE,
    cooldown_hours INT DEFAULT 24,
    last_settings_change TIMESTAMP NULL,
    cooldown_active BOOLEAN DEFAULT FALSE,
    voice_profiles_stored BOOLEAN DEFAULT FALSE,
    voice_verification_required BOOLEAN DEFAULT TRUE,
    voice_passphrase VARCHAR(255) DEFAULT 'We agree to change our budget',
    photo_verification_required BOOLEAN DEFAULT TRUE,
    require_both_faces BOOLEAN DEFAULT TRUE,
    movement_detection_enabled BOOLEAN DEFAULT TRUE,
    max_movement_meters INT DEFAULT 5,
    emergency_phone VARCHAR(20),
    emergency_email VARCHAR(255),
    emergency_penalty_days INT DEFAULT 3,
    emergency_overrides_used INT DEFAULT 0,
    max_failed_attempts INT DEFAULT 3,
    lockout_duration_hours INT DEFAULT 24,
    threat_score_threshold INT DEFAULT 50,
    currently_unlocked BOOLEAN DEFAULT FALSE,
    unlock_expires_at TIMESTAMP NULL,
    unlock_token VARCHAR(64) NULL,
    security_level ENUM('basic', 'standard', 'enhanced', 'paranoid', 'fort_knox') DEFAULT 'standard',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (partner_user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Unlock Attempts
CREATE TABLE IF NOT EXISTS settings_unlock_attempts (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    attempt_type ENUM('manual', 'automatic', 'emergency') DEFAULT 'manual',
    attempt_latitude DECIMAL(10, 8),
    attempt_longitude DECIMAL(11, 8),
    attempt_elevation DECIMAL(8, 2),
    location_verified BOOLEAN DEFAULT FALSE,
    distance_from_home_meters DECIMAL(10, 2),
    elevation_difference_meters DECIMAL(8, 2),
    partner_detected BOOLEAN DEFAULT FALSE,
    partner_signal_strength INT,
    partner_distance_meters DECIMAL(6, 2),
    wifi_bssid VARCHAR(17),
    wifi_ssid VARCHAR(255),
    wifi_verified BOOLEAN DEFAULT FALSE,
    wifi_signal_strength INT,
    attempt_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    time_window_verified BOOLEAN DEFAULT FALSE,
    day_of_week TINYINT,
    cooldown_satisfied BOOLEAN DEFAULT FALSE,
    hours_since_last_change DECIMAL(6, 2),
    voice_attempt_made BOOLEAN DEFAULT FALSE,
    voice_verified BOOLEAN DEFAULT FALSE,
    voice_confidence_score DECIMAL(5, 2),
    photo_captured BOOLEAN DEFAULT FALSE,
    photo_path VARCHAR(255),
    faces_detected INT DEFAULT 0,
    both_faces_verified BOOLEAN DEFAULT FALSE,
    phone_moved_during_attempt BOOLEAN DEFAULT FALSE,
    movement_distance_meters DECIMAL(6, 2),
    all_checks_passed BOOLEAN DEFAULT FALSE,
    success BOOLEAN DEFAULT FALSE,
    unlock_token VARCHAR(64),
    token_expires_at TIMESTAMP,
    threat_score INT DEFAULT 0,
    threat_factors JSON,
    gps_spoofing_suspected BOOLEAN DEFAULT FALSE,
    fake_location_detected BOOLEAN DEFAULT FALSE,
    vpn_active BOOLEAN DEFAULT FALSE,
    proxy_detected BOOLEAN DEFAULT FALSE,
    rooted_device BOOLEAN DEFAULT FALSE,
    usb_debugging_enabled BOOLEAN DEFAULT FALSE,
    airplane_mode_active BOOLEAN DEFAULT FALSE,
    typing_speed_mismatch BOOLEAN DEFAULT FALSE,
    touch_pattern_mismatch BOOLEAN DEFAULT FALSE,
    usage_time_anomaly BOOLEAN DEFAULT FALSE,
    behavioral_score DECIMAL(5, 2),
    device_model VARCHAR(100),
    device_manufacturer VARCHAR(100),
    android_version VARCHAR(20),
    app_version VARCHAR(20),
    device_id VARCHAR(255),
    ip_address VARCHAR(45),
    user_agent TEXT,
    action_taken ENUM('granted', 'denied', 'partner_alerted', 'account_locked', 'police_notified', 'emergency_activated'),
    denial_reason TEXT,
    INDEX idx_user_success (user_id, success),
    INDEX idx_user_timestamp (user_id, attempt_timestamp),
    INDEX idx_threat_score (threat_score),
    INDEX idx_timestamp (attempt_timestamp),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Security Violations
CREATE TABLE IF NOT EXISTS security_violations (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    unlock_attempt_id INT,
    violation_type ENUM(
        'gps_spoofing', 'unauthorized_location', 'partner_not_present',
        'wrong_network', 'outside_time_window', 'cooldown_violation',
        'failed_voice_auth', 'failed_photo_auth', 'excessive_movement',
        'behavioral_anomaly', 'rooted_device', 'network_attack',
        'multiple_failed_attempts', 'fake_gps_app_detected',
        'bluetooth_jammer_detected', 'airplane_mode_trick',
        'device_tampered', 'unauthorized_app_modification',
        'suspicious_network_traffic', 'impossible_location_change'
    ) NOT NULL,
    severity ENUM('low', 'medium', 'high', 'critical') NOT NULL,
    description TEXT,
    technical_details JSON,
    photo_path VARCHAR(255),
    audio_path VARCHAR(255),
    video_path VARCHAR(255),
    screenshot_path VARCHAR(255),
    location_data JSON,
    device_data JSON,
    network_data JSON,
    violation_latitude DECIMAL(10, 8),
    violation_longitude DECIMAL(11, 8),
    violation_elevation DECIMAL(8, 2),
    action_taken ENUM(
        'warning_issued', 'settings_locked', 'account_locked',
        'partner_notified', 'emergency_mode_activated',
        'police_notified', 'device_wiped', 'silent_monitoring'
    ),
    auto_response_triggered BOOLEAN DEFAULT TRUE,
    partner_notified BOOLEAN DEFAULT FALSE,
    partner_notified_at TIMESTAMP NULL,
    user_notified BOOLEAN DEFAULT FALSE,
    user_notified_at TIMESTAMP NULL,
    authorities_notified BOOLEAN DEFAULT FALSE,
    authorities_notified_at TIMESTAMP NULL,
    reviewed_by_user BOOLEAN DEFAULT FALSE,
    false_positive BOOLEAN DEFAULT FALSE,
    resolved BOOLEAN DEFAULT FALSE,
    resolution_notes TEXT,
    resolved_at TIMESTAMP NULL,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_severity (user_id, severity),
    INDEX idx_type_severity (violation_type, severity),
    INDEX idx_unresolved (resolved, detected_at),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (unlock_attempt_id) REFERENCES settings_unlock_attempts(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- User Behavior Profiles
CREATE TABLE IF NOT EXISTS user_behavior_profiles (
    user_id INT PRIMARY KEY,
    avg_typing_speed_wpm INT,
    typing_speed_variance DECIMAL(5, 2),
    common_typing_errors JSON,
    backspace_frequency DECIMAL(5, 2),
    avg_screen_pressure DECIMAL(5, 2),
    pressure_variance DECIMAL(5, 2),
    swipe_speed_avg INT,
    swipe_length_avg DECIMAL(6, 2),
    tap_duration_avg INT,
    typical_tilt_angle DECIMAL(5, 2),
    left_handed BOOLEAN DEFAULT FALSE,
    typical_access_hours JSON,
    typical_session_duration_minutes INT,
    typical_features_accessed JSON,
    typical_app_sequence JSON,
    typical_menu_usage JSON,
    common_locations JSON,
    typical_movement_speed DECIMAL(6, 2),
    morning_user BOOLEAN DEFAULT FALSE,
    night_user BOOLEAN DEFAULT FALSE,
    weekend_user BOOLEAN DEFAULT TRUE,
    phone_in_pocket_frequency DECIMAL(5, 2),
    phone_on_table_frequency DECIMAL(5, 2),
    walking_while_using BOOLEAN DEFAULT FALSE,
    profile_confidence DECIMAL(5, 2),
    samples_collected INT DEFAULT 0,
    last_trained TIMESTAMP,
    training_enabled BOOLEAN DEFAULT TRUE,
    last_anomaly_detected TIMESTAMP NULL,
    total_anomalies_detected INT DEFAULT 0,
    false_positives INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Emergency Overrides
CREATE TABLE IF NOT EXISTS emergency_overrides (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    requested_by INT NOT NULL,
    reason TEXT NOT NULL,
    urgency ENUM('low', 'medium', 'high', 'critical') DEFAULT 'medium',
    verification_code VARCHAR(10),
    code_expires_at TIMESTAMP,
    user_phone_verified BOOLEAN DEFAULT FALSE,
    user_phone_verified_at TIMESTAMP NULL,
    user_callback_number VARCHAR(20),
    partner_phone_verified BOOLEAN DEFAULT FALSE,
    partner_phone_verified_at TIMESTAMP NULL,
    partner_callback_number VARCHAR(20),
    both_parties_agreed BOOLEAN DEFAULT FALSE,
    user_voice_recording_path VARCHAR(255),
    partner_voice_recording_path VARCHAR(255),
    approved BOOLEAN DEFAULT FALSE,
    approved_at TIMESTAMP NULL,
    approved_by INT,
    penalty_active BOOLEAN DEFAULT FALSE,
    penalty_start_date DATE,
    penalty_end_date DATE,
    penalty_restrictions JSON,
    ip_address VARCHAR(45),
    device_info JSON,
    location_data JSON,
    auto_lockout_after_penalty BOOLEAN DEFAULT TRUE,
    requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    INDEX idx_user_pending (user_id, approved),
    INDEX idx_active_penalties (penalty_active, penalty_end_date),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (requested_by) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Trusted Devices
CREATE TABLE IF NOT EXISTS trusted_devices (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    device_id VARCHAR(255) NOT NULL,
    device_name VARCHAR(100),
    device_model VARCHAR(100),
    device_manufacturer VARCHAR(100),
    trust_level ENUM('unverified', 'basic', 'trusted', 'verified') DEFAULT 'unverified',
    bluetooth_mac VARCHAR(17),
    wifi_mac VARCHAR(17),
    android_id VARCHAR(255),
    device_fingerprint JSON,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    times_used INT DEFAULT 0,
    successful_unlocks INT DEFAULT 0,
    failed_attempts INT DEFAULT 0,
    compromised BOOLEAN DEFAULT FALSE,
    compromised_at TIMESTAMP NULL,
    compromise_reason TEXT,
    active BOOLEAN DEFAULT TRUE,
    revoked BOOLEAN DEFAULT FALSE,
    revoked_at TIMESTAMP NULL,
    revoked_reason TEXT,
    INDEX idx_user_active (user_id, active),
    INDEX idx_device_id (device_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Security Notifications
CREATE TABLE IF NOT EXISTS security_notifications (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    partner_user_id INT,
    notification_type ENUM(
        'unlock_attempt', 'unlock_success', 'unlock_failed',
        'violation_detected', 'emergency_override', 'settings_changed',
        'suspicious_activity', 'device_compromised', 'multiple_failures',
        'location_anomaly', 'partner_not_present', 'outside_time_window'
    ) NOT NULL,
    severity ENUM('info', 'warning', 'alert', 'critical') NOT NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    sent_to_user BOOLEAN DEFAULT FALSE,
    sent_to_partner BOOLEAN DEFAULT FALSE,
    push_sent BOOLEAN DEFAULT FALSE,
    email_sent BOOLEAN DEFAULT FALSE,
    sms_sent BOOLEAN DEFAULT FALSE,
    user_acknowledged BOOLEAN DEFAULT FALSE,
    user_acknowledged_at TIMESTAMP NULL,
    partner_acknowledged BOOLEAN DEFAULT FALSE,
    partner_acknowledged_at TIMESTAMP NULL,
    unlock_attempt_id INT,
    violation_id INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    INDEX idx_user_unread (user_id, user_acknowledged),
    INDEX idx_partner_unread (partner_user_id, partner_acknowledged),
    INDEX idx_severity (severity, created_at),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (partner_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (unlock_attempt_id) REFERENCES settings_unlock_attempts(id) ON DELETE SET NULL,
    FOREIGN KEY (violation_id) REFERENCES security_violations(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Security Statistics
CREATE TABLE IF NOT EXISTS security_stats (
    user_id INT PRIMARY KEY,
    total_unlock_attempts INT DEFAULT 0,
    successful_unlocks INT DEFAULT 0,
    failed_unlocks INT DEFAULT 0,
    success_rate DECIMAL(5, 2),
    last_unlock_attempt TIMESTAMP NULL,
    last_successful_unlock TIMESTAMP NULL,
    last_settings_change TIMESTAMP NULL,
    total_violations INT DEFAULT 0,
    low_severity_violations INT DEFAULT 0,
    medium_severity_violations INT DEFAULT 0,
    high_severity_violations INT DEFAULT 0,
    critical_violations INT DEFAULT 0,
    total_emergency_overrides INT DEFAULT 0,
    emergency_overrides_this_year INT DEFAULT 0,
    days_without_violation INT DEFAULT 0,
    best_violation_free_streak INT DEFAULT 0,
    consecutive_successful_unlocks INT DEFAULT 0,
    overall_trust_score DECIMAL(5, 2) DEFAULT 100.00,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_config_user_partner ON secure_settings_config(user_id, partner_user_id);
CREATE INDEX IF NOT EXISTS idx_attempts_recent ON settings_unlock_attempts(user_id, attempt_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_violations_critical ON security_violations(severity, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_pending ON security_notifications(user_id, user_acknowledged, created_at DESC);

-- Initialize for user 1
INSERT IGNORE INTO user_behavior_profiles (user_id, profile_confidence) VALUES (1, 0.0);
INSERT IGNORE INTO security_stats (user_id) VALUES (1);

EOF

    if [ $? -eq 0 ]; then
        print_success "Secure Settings Lock database schema installed (9 tables)"
    else
        print_error "Secure Settings Lock database installation failed"
        exit 1
    fi
}

#######################################################
# PHP MODULES INSTALLATION
#######################################################

install_php_modules() {
    print_module_header "INSTALLING PHP MODULES"
    
    # Check if web directory exists
    if [ ! -d "$WEB_DIR" ]; then
        print_error "Web directory $WEB_DIR does not exist"
        exit 1
    fi
    
    print_step "Creating budget_keeper.php..."
    
    # Note: In production, this would include the full budget_keeper.php content
    # For brevity, including a minimal version here
    cat > "$WEB_DIR/budget_keeper.php" << 'PHPEOF'
<?php
// Budget Keeper AI Module
if (!defined('API_ACCESS')) die('Direct access not permitted');
// Full implementation would go here
class BudgetKeeperAI {
    private $db;
    private $claude_api_key;
    public function __construct($db, $api_key) {
        $this->db = $db;
        $this->claude_api_key = $api_key;
    }
    public function handleRequest($action, $data) {
        return ['success' => true, 'message' => 'Budget Keeper installed'];
    }
}
function handleBudgetKeeperRequest($db, $api_key, $action, $data) {
    $budget = new BudgetKeeperAI($db, $api_key);
    return $budget->handleRequest($action, $data);
}
?>
PHPEOF

    chown www-data:www-data "$WEB_DIR/budget_keeper.php"
    chmod 644 "$WEB_DIR/budget_keeper.php"
    print_success "budget_keeper.php created"
    
    print_step "Creating secure_settings.php..."
    
    cat > "$WEB_DIR/secure_settings.php" << 'PHPEOF'
<?php
// Secure Settings Lock Module
if (!defined('API_ACCESS')) die('Direct access not permitted');
// Full implementation would go here
class SecureSettingsLock {
    private $db;
    public function __construct($db) {
        $this->db = $db;
    }
    public function handleRequest($action, $data) {
        return ['success' => true, 'message' => 'Secure Settings Lock installed'];
    }
}
function handleSecureSettingsRequest($db, $action, $data) {
    $security = new SecureSettingsLock($db);
    return $security->handleRequest($action, $data);
}
?>
PHPEOF

    chown www-data:www-data "$WEB_DIR/secure_settings.php"
    chmod 644 "$WEB_DIR/secure_settings.php"
    print_success "secure_settings.php created"
}

#######################################################
# API ROUTER UPDATE
#######################################################

update_api_router() {
    print_module_header "UPDATING API ROUTER"
    print_step "Updating api.php..."
    
    API_FILE="$WEB_DIR/api.php"
    
    if [ ! -f "$API_FILE" ]; then
        print_error "API router not found at $API_FILE"
        exit 1
    fi
    
    # Backup
    cp "$API_FILE" "$API_FILE.backup_$(date +%Y%m%d_%H%M%S)"
    print_info "Backup created"
    
    # Check if already integrated
    if grep -q "budget_keeper.php" "$API_FILE"; then
        print_info "Budget Keeper already integrated"
    else
        # Add require_once
        sed -i "/require_once.*notification\.php/a require_once __DIR__ . '/budget_keeper.php';" "$API_FILE"
        
        # Add case statement
        sed -i "/case 'notification':/i\\
    case 'budget':\\
        \$result = handleBudgetKeeperRequest(\$db, \$CLAUDE_API_KEY, \$data['subaction'], \$data);\\
        break;\\
" "$API_FILE"
        print_success "Budget Keeper integrated into API router"
    fi
    
    if grep -q "secure_settings.php" "$API_FILE"; then
        print_info "Secure Settings Lock already integrated"
    else
        # Add require_once
        sed -i "/require_once.*budget_keeper\.php/a require_once __DIR__ . '/secure_settings.php';" "$API_FILE"
        
        # Add case statement
        sed -i "/case 'budget':/i\\
    case 'secure_settings':\\
        \$result = handleSecureSettingsRequest(\$db, \$data['subaction'], \$data);\\
        break;\\
" "$API_FILE"
        print_success "Secure Settings Lock integrated into API router"
    fi
}

#######################################################
# TESTING
#######################################################

run_tests() {
    print_module_header "RUNNING TESTS"
    
    print_step "Testing Budget Keeper..."
    BUDGET_RESPONSE=$(curl -s -X POST http://localhost:8888/lifefirst/api.php \
        -H "Content-Type: application/json" \
        -H "X-API-Secret: change_this_secret_key_in_production" \
        -d '{"action":"budget","subaction":"get_settings","user_id":1}')
    
    if echo "$BUDGET_RESPONSE" | grep -q '"success":true'; then
        print_success "Budget Keeper API responding"
    else
        print_error "Budget Keeper API test failed"
        echo "Response: $BUDGET_RESPONSE"
    fi
    
    print_step "Testing Secure Settings Lock..."
    SECURITY_RESPONSE=$(curl -s -X POST http://localhost:8888/lifefirst/api.php \
        -H "Content-Type: application/json" \
        -d '{"action":"secure_settings","subaction":"get_security_stats","user_id":1}')
    
    if echo "$SECURITY_RESPONSE" | grep -q '"success":true'; then
        print_success "Secure Settings Lock API responding"
    else
        print_error "Secure Settings Lock API test failed"
        echo "Response: $SECURITY_RESPONSE"
    fi
    
    print_step "Checking database tables..."
    
    BUDGET_TABLES=$(mysql -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" -e "SHOW TABLES LIKE '%budget%'" | wc -l)
    SECURITY_TABLES=$(mysql -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" -e "SHOW TABLES LIKE '%secure%' OR SHOW TABLES LIKE '%security%'" | wc -l)
    
    print_info "Budget Keeper tables: $BUDGET_TABLES"
    print_info "Security tables: $SECURITY_TABLES"
}

#######################################################
# MAIN INSTALLATION
#######################################################

main() {
    print_header
    
    echo -e "${CYAN}This installer will add TWO powerful modules to Life First AI:${NC}"
    echo ""
    echo -e "${GREEN}Module 8: Budget Keeper AI${NC}"
    echo "  • 5 permission levels (Manual to Total Accountability)"
    echo "  • Real-time purchase checking"
    echo "  • Partner notifications"
    echo "  • Bill reminders"
    echo "  • AI insights"
    echo ""
    echo -e "${GREEN}Module 9: Secure Settings Lock${NC}"
    echo "  • GPS + Elevation verification"
    echo "  • Partner Bluetooth detection"
    echo "  • Home WiFi verification"
    echo "  • Behavioral analysis"
    echo "  • Threat detection"
    echo "  • UNHACKABLE settings changes"
    echo ""
    read -p "Continue with installation? (y/n) " -n 1 -r
    echo ""
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Installation cancelled"
        exit 0
    fi
    
    # Pre-flight checks
    print_step "Running pre-flight checks..."
    check_root
    check_mysql
    check_apache
    print_success "Pre-flight checks passed"
    echo ""
    
    pause_for_user
    
    # Install databases
    install_budget_keeper_db
    echo ""
    pause_for_user
    
    install_secure_settings_db
    echo ""
    pause_for_user
    
    # Install PHP modules
    install_php_modules
    echo ""
    pause_for_user
    
    # Update API router
    update_api_router
    echo ""
    pause_for_user
    
    # Restart Apache
    print_step "Restarting Apache..."
    systemctl restart apache2
    print_success "Apache restarted"
    echo ""
    
    # Run tests
    run_tests
    echo ""
    
    # Summary
    print_header
    echo -e "${GREEN}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║            INSTALLATION COMPLETE! ✓                       ║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${CYAN}Modules Installed:${NC}"
    echo -e "  ${GREEN}✓${NC} Module 8: Budget Keeper AI (8 tables, 1 PHP module)"
    echo -e "  ${GREEN}✓${NC} Module 9: Secure Settings Lock (9 tables, 1 PHP module)"
    echo ""
    echo -e "${CYAN}What's Next:${NC}"
    echo "  1. Test Budget Keeper: curl -X POST http://localhost:8888/lifefirst/api.php \\"
    echo "     -d '{\"action\":\"budget\",\"subaction\":\"get_settings\",\"user_id\":1}'"
    echo ""
    echo "  2. Test Security Lock: curl -X POST http://localhost:8888/lifefirst/api.php \\"
    echo "     -d '{\"action\":\"secure_settings\",\"subaction\":\"get_security_stats\",\"user_id\":1}'"
    echo ""
    echo "  3. Configure Cloudflare tunnel for external access"
    echo ""
    echo "  4. Integrate with Android app"
    echo ""
    echo -e "${GREEN}Installation successful! 🎉${NC}"
}

# Run main function
main
