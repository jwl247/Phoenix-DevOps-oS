-- ============================================
-- SECURE SETTINGS LOCK (MODULE 9)
-- Life First AI System
-- "The Fort Knox of Budget Apps"
-- ============================================

-- Security Configuration (Per User)
CREATE TABLE IF NOT EXISTS secure_settings_config (
    user_id INT PRIMARY KEY,
    partner_user_id INT NOT NULL,
    
    -- Location Lock (GPS + Elevation)
    home_latitude DECIMAL(10, 8) NOT NULL,
    home_longitude DECIMAL(11, 8) NOT NULL,
    home_elevation DECIMAL(8, 2) NOT NULL,
    location_radius_meters INT DEFAULT 50,
    elevation_tolerance_meters INT DEFAULT 10,
    
    -- Device Pairing (Bluetooth Detection)
    user_bluetooth_mac VARCHAR(17) NOT NULL,
    partner_bluetooth_mac VARCHAR(17) NOT NULL,
    required_signal_strength INT DEFAULT -70, -- dBm (stronger = closer)
    detection_range_meters INT DEFAULT 10,
    
    -- Network Lock (WiFi BSSID)
    home_wifi_bssid VARCHAR(17) NOT NULL,
    home_wifi_ssid VARCHAR(255),
    wifi_signal_threshold INT DEFAULT -80,
    
    -- Time Restrictions
    discussion_start_time TIME DEFAULT '19:00:00', -- 7 PM
    discussion_end_time TIME DEFAULT '22:00:00',   -- 10 PM
    weekend_anytime BOOLEAN DEFAULT TRUE,
    
    -- Cool-down Period
    cooldown_hours INT DEFAULT 24,
    last_settings_change TIMESTAMP NULL,
    cooldown_active BOOLEAN DEFAULT FALSE,
    
    -- Voice Authentication
    voice_profiles_stored BOOLEAN DEFAULT FALSE,
    voice_verification_required BOOLEAN DEFAULT TRUE,
    voice_passphrase VARCHAR(255) DEFAULT 'We agree to change our budget',
    
    -- Photo Verification
    photo_verification_required BOOLEAN DEFAULT TRUE,
    require_both_faces BOOLEAN DEFAULT TRUE,
    
    -- Movement Detection
    movement_detection_enabled BOOLEAN DEFAULT TRUE,
    max_movement_meters INT DEFAULT 5,
    
    -- Emergency Override
    emergency_phone VARCHAR(20),
    emergency_email VARCHAR(255),
    emergency_penalty_days INT DEFAULT 3,
    emergency_overrides_used INT DEFAULT 0,
    
    -- Threat Detection Thresholds
    max_failed_attempts INT DEFAULT 3,
    lockout_duration_hours INT DEFAULT 24,
    threat_score_threshold INT DEFAULT 50, -- 0-100 scale
    
    -- Current Status
    currently_unlocked BOOLEAN DEFAULT FALSE,
    unlock_expires_at TIMESTAMP NULL,
    unlock_token VARCHAR(64) NULL,
    
    -- Security Level
    security_level ENUM('basic', 'standard', 'enhanced', 'paranoid', 'fort_knox') DEFAULT 'standard',
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (partner_user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Unlock Attempts (Complete Audit Trail)
CREATE TABLE IF NOT EXISTS settings_unlock_attempts (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    attempt_type ENUM('manual', 'automatic', 'emergency') DEFAULT 'manual',
    
    -- Location Data
    attempt_latitude DECIMAL(10, 8),
    attempt_longitude DECIMAL(11, 8),
    attempt_elevation DECIMAL(8, 2),
    location_verified BOOLEAN DEFAULT FALSE,
    distance_from_home_meters DECIMAL(10, 2),
    elevation_difference_meters DECIMAL(8, 2),
    
    -- Device Detection
    partner_detected BOOLEAN DEFAULT FALSE,
    partner_signal_strength INT,
    partner_distance_meters DECIMAL(6, 2),
    
    -- Network Verification
    wifi_bssid VARCHAR(17),
    wifi_ssid VARCHAR(255),
    wifi_verified BOOLEAN DEFAULT FALSE,
    wifi_signal_strength INT,
    
    -- Time Verification
    attempt_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    time_window_verified BOOLEAN DEFAULT FALSE,
    day_of_week TINYINT, -- 0=Sunday, 6=Saturday
    
    -- Cooldown Check
    cooldown_satisfied BOOLEAN DEFAULT FALSE,
    hours_since_last_change DECIMAL(6, 2),
    
    -- Voice Authentication
    voice_attempt_made BOOLEAN DEFAULT FALSE,
    voice_verified BOOLEAN DEFAULT FALSE,
    voice_confidence_score DECIMAL(5, 2),
    
    -- Photo Verification
    photo_captured BOOLEAN DEFAULT FALSE,
    photo_path VARCHAR(255),
    faces_detected INT DEFAULT 0,
    both_faces_verified BOOLEAN DEFAULT FALSE,
    
    -- Movement Detection
    phone_moved_during_attempt BOOLEAN DEFAULT FALSE,
    movement_distance_meters DECIMAL(6, 2),
    
    -- Overall Result
    all_checks_passed BOOLEAN DEFAULT FALSE,
    success BOOLEAN DEFAULT FALSE,
    unlock_token VARCHAR(64),
    token_expires_at TIMESTAMP,
    
    -- Threat Analysis
    threat_score INT DEFAULT 0, -- 0=safe, 100=critical threat
    threat_factors JSON, -- Detailed breakdown
    
    -- Suspicious Indicators
    gps_spoofing_suspected BOOLEAN DEFAULT FALSE,
    fake_location_detected BOOLEAN DEFAULT FALSE,
    vpn_active BOOLEAN DEFAULT FALSE,
    proxy_detected BOOLEAN DEFAULT FALSE,
    rooted_device BOOLEAN DEFAULT FALSE,
    usb_debugging_enabled BOOLEAN DEFAULT FALSE,
    airplane_mode_active BOOLEAN DEFAULT FALSE,
    
    -- Behavioral Analysis
    typing_speed_mismatch BOOLEAN DEFAULT FALSE,
    touch_pattern_mismatch BOOLEAN DEFAULT FALSE,
    usage_time_anomaly BOOLEAN DEFAULT FALSE,
    behavioral_score DECIMAL(5, 2), -- How much it matches normal behavior
    
    -- Device Information
    device_model VARCHAR(100),
    device_manufacturer VARCHAR(100),
    android_version VARCHAR(20),
    app_version VARCHAR(20),
    device_id VARCHAR(255), -- Hashed
    ip_address VARCHAR(45),
    user_agent TEXT,
    
    -- Response Actions
    action_taken ENUM(
        'granted',
        'denied',
        'partner_alerted',
        'account_locked',
        'police_notified',
        'emergency_activated'
    ),
    
    denial_reason TEXT,
    
    INDEX idx_user_success (user_id, success),
    INDEX idx_user_timestamp (user_id, attempt_timestamp),
    INDEX idx_threat_score (threat_score),
    INDEX idx_timestamp (attempt_timestamp),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Security Violations (Serious Threats)
CREATE TABLE IF NOT EXISTS security_violations (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    unlock_attempt_id INT, -- Link to the attempt that triggered it
    
    violation_type ENUM(
        'gps_spoofing',
        'unauthorized_location',
        'partner_not_present',
        'wrong_network',
        'outside_time_window',
        'cooldown_violation',
        'failed_voice_auth',
        'failed_photo_auth',
        'excessive_movement',
        'behavioral_anomaly',
        'rooted_device',
        'network_attack',
        'multiple_failed_attempts',
        'fake_gps_app_detected',
        'bluetooth_jammer_detected',
        'airplane_mode_trick',
        'device_tampered',
        'unauthorized_app_modification',
        'suspicious_network_traffic',
        'impossible_location_change'
    ) NOT NULL,
    
    severity ENUM('low', 'medium', 'high', 'critical') NOT NULL,
    
    description TEXT,
    technical_details JSON,
    
    -- Evidence Collection
    photo_path VARCHAR(255),
    audio_path VARCHAR(255),
    video_path VARCHAR(255),
    screenshot_path VARCHAR(255),
    location_data JSON,
    device_data JSON,
    network_data JSON,
    
    -- Geolocation at time of violation
    violation_latitude DECIMAL(10, 8),
    violation_longitude DECIMAL(11, 8),
    violation_elevation DECIMAL(8, 2),
    
    -- Automated Response
    action_taken ENUM(
        'warning_issued',
        'settings_locked',
        'account_locked',
        'partner_notified',
        'emergency_mode_activated',
        'police_notified',
        'device_wiped',
        'silent_monitoring'
    ),
    
    auto_response_triggered BOOLEAN DEFAULT TRUE,
    
    -- Notifications
    partner_notified BOOLEAN DEFAULT FALSE,
    partner_notified_at TIMESTAMP NULL,
    user_notified BOOLEAN DEFAULT FALSE,
    user_notified_at TIMESTAMP NULL,
    authorities_notified BOOLEAN DEFAULT FALSE,
    authorities_notified_at TIMESTAMP NULL,
    
    -- Resolution
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

-- User Behavioral Profiles (AI Learning)
CREATE TABLE IF NOT EXISTS user_behavior_profiles (
    user_id INT PRIMARY KEY,
    
    -- Typing Patterns
    avg_typing_speed_wpm INT,
    typing_speed_variance DECIMAL(5, 2),
    common_typing_errors JSON, -- Patterns of mistakes
    backspace_frequency DECIMAL(5, 2),
    
    -- Touch Patterns
    avg_screen_pressure DECIMAL(5, 2),
    pressure_variance DECIMAL(5, 2),
    swipe_speed_avg INT,
    swipe_length_avg DECIMAL(6, 2),
    tap_duration_avg INT, -- milliseconds
    
    -- Phone Orientation
    typical_tilt_angle DECIMAL(5, 2),
    left_handed BOOLEAN DEFAULT FALSE,
    
    -- Usage Patterns
    typical_access_hours JSON, -- {"weekday": [19,20,21], "weekend": [10,11,12]}
    typical_session_duration_minutes INT,
    typical_features_accessed JSON,
    
    -- App Navigation Flow
    typical_app_sequence JSON, -- Common paths through app
    typical_menu_usage JSON,
    
    -- Location Patterns
    common_locations JSON, -- Places user frequently accesses app
    typical_movement_speed DECIMAL(6, 2), -- km/h when using app
    
    -- Time Patterns
    morning_user BOOLEAN DEFAULT FALSE,
    night_user BOOLEAN DEFAULT FALSE,
    weekend_user BOOLEAN DEFAULT TRUE,
    
    -- Device Handling
    phone_in_pocket_frequency DECIMAL(5, 2),
    phone_on_table_frequency DECIMAL(5, 2),
    walking_while_using BOOLEAN DEFAULT FALSE,
    
    -- Profile Quality
    profile_confidence DECIMAL(5, 2), -- 0-100, how much data we have
    samples_collected INT DEFAULT 0,
    last_trained TIMESTAMP,
    training_enabled BOOLEAN DEFAULT TRUE,
    
    -- Anomaly Detection
    last_anomaly_detected TIMESTAMP NULL,
    total_anomalies_detected INT DEFAULT 0,
    false_positives INT DEFAULT 0,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Emergency Overrides (Last Resort)
CREATE TABLE IF NOT EXISTS emergency_overrides (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    requested_by INT NOT NULL, -- Which user initiated
    
    reason TEXT NOT NULL,
    urgency ENUM('low', 'medium', 'high', 'critical') DEFAULT 'medium',
    
    -- Verification Process
    verification_code VARCHAR(10),
    code_expires_at TIMESTAMP,
    
    user_phone_verified BOOLEAN DEFAULT FALSE,
    user_phone_verified_at TIMESTAMP NULL,
    user_callback_number VARCHAR(20),
    
    partner_phone_verified BOOLEAN DEFAULT FALSE,
    partner_phone_verified_at TIMESTAMP NULL,
    partner_callback_number VARCHAR(20),
    
    both_parties_agreed BOOLEAN DEFAULT FALSE,
    
    -- Voice Recording
    user_voice_recording_path VARCHAR(255),
    partner_voice_recording_path VARCHAR(255),
    
    -- Approval
    approved BOOLEAN DEFAULT FALSE,
    approved_at TIMESTAMP NULL,
    approved_by INT, -- Which admin or system approved
    
    -- Penalty Period
    penalty_active BOOLEAN DEFAULT FALSE,
    penalty_start_date DATE,
    penalty_end_date DATE,
    penalty_restrictions JSON, -- What's limited during penalty
    
    -- Audit Trail
    ip_address VARCHAR(45),
    device_info JSON,
    location_data JSON,
    
    -- Auto-Lockout After Penalty
    auto_lockout_after_penalty BOOLEAN DEFAULT TRUE,
    
    requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP, -- Request expires if not completed
    
    INDEX idx_user_pending (user_id, approved),
    INDEX idx_active_penalties (penalty_active, penalty_end_date),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (requested_by) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Trusted Devices (For Reduced Security Checks)
CREATE TABLE IF NOT EXISTS trusted_devices (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    
    device_id VARCHAR(255) NOT NULL, -- Hashed device identifier
    device_name VARCHAR(100),
    device_model VARCHAR(100),
    device_manufacturer VARCHAR(100),
    
    -- Trust Level
    trust_level ENUM('unverified', 'basic', 'trusted', 'verified') DEFAULT 'unverified',
    
    -- Device Fingerprint
    bluetooth_mac VARCHAR(17),
    wifi_mac VARCHAR(17),
    android_id VARCHAR(255),
    device_fingerprint JSON, -- Multiple identifying factors
    
    -- Usage Stats
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    times_used INT DEFAULT 0,
    successful_unlocks INT DEFAULT 0,
    failed_attempts INT DEFAULT 0,
    
    -- Security
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

-- Security Notifications Log
CREATE TABLE IF NOT EXISTS security_notifications (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    partner_user_id INT,
    
    notification_type ENUM(
        'unlock_attempt',
        'unlock_success',
        'unlock_failed',
        'violation_detected',
        'emergency_override',
        'settings_changed',
        'suspicious_activity',
        'device_compromised',
        'multiple_failures',
        'location_anomaly',
        'partner_not_present',
        'outside_time_window'
    ) NOT NULL,
    
    severity ENUM('info', 'warning', 'alert', 'critical') NOT NULL,
    
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    
    -- Delivery
    sent_to_user BOOLEAN DEFAULT FALSE,
    sent_to_partner BOOLEAN DEFAULT FALSE,
    push_sent BOOLEAN DEFAULT FALSE,
    email_sent BOOLEAN DEFAULT FALSE,
    sms_sent BOOLEAN DEFAULT FALSE,
    
    -- User Response
    user_acknowledged BOOLEAN DEFAULT FALSE,
    user_acknowledged_at TIMESTAMP NULL,
    partner_acknowledged BOOLEAN DEFAULT FALSE,
    partner_acknowledged_at TIMESTAMP NULL,
    
    -- Related Records
    unlock_attempt_id INT,
    violation_id INT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP, -- Auto-dismiss after X time
    
    INDEX idx_user_unread (user_id, user_acknowledged),
    INDEX idx_partner_unread (partner_user_id, partner_acknowledged),
    INDEX idx_severity (severity, created_at),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (partner_user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (unlock_attempt_id) REFERENCES settings_unlock_attempts(id) ON DELETE SET NULL,
    FOREIGN KEY (violation_id) REFERENCES security_violations(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Security Statistics (For Dashboard)
CREATE TABLE IF NOT EXISTS security_stats (
    user_id INT PRIMARY KEY,
    
    -- Unlock History
    total_unlock_attempts INT DEFAULT 0,
    successful_unlocks INT DEFAULT 0,
    failed_unlocks INT DEFAULT 0,
    success_rate DECIMAL(5, 2),
    
    -- Last Activity
    last_unlock_attempt TIMESTAMP NULL,
    last_successful_unlock TIMESTAMP NULL,
    last_settings_change TIMESTAMP NULL,
    
    -- Violations
    total_violations INT DEFAULT 0,
    low_severity_violations INT DEFAULT 0,
    medium_severity_violations INT DEFAULT 0,
    high_severity_violations INT DEFAULT 0,
    critical_violations INT DEFAULT 0,
    
    -- Emergency Overrides
    total_emergency_overrides INT DEFAULT 0,
    emergency_overrides_this_year INT DEFAULT 0,
    
    -- Streaks
    days_without_violation INT DEFAULT 0,
    best_violation_free_streak INT DEFAULT 0,
    consecutive_successful_unlocks INT DEFAULT 0,
    
    -- Trust Score
    overall_trust_score DECIMAL(5, 2) DEFAULT 100.00, -- 0-100
    
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================
-- SAMPLE DATA (For Testing)
-- ============================================

-- Example secure config for user 1
INSERT IGNORE INTO secure_settings_config 
(user_id, partner_user_id, home_latitude, home_longitude, home_elevation, 
 user_bluetooth_mac, partner_bluetooth_mac, home_wifi_bssid) 
VALUES 
(1, 2, 33.1581, -117.3506, 28.5, 
 '00:00:00:00:00:01', '00:00:00:00:00:02', '00:11:22:33:44:55');

-- Initialize behavior profile
INSERT IGNORE INTO user_behavior_profiles (user_id, profile_confidence) 
VALUES (1, 0.0);

-- Initialize stats
INSERT IGNORE INTO security_stats (user_id) 
VALUES (1);

-- ============================================
-- INDEXES FOR PERFORMANCE
-- ============================================

CREATE INDEX idx_config_user_partner ON secure_settings_config(user_id, partner_user_id);
CREATE INDEX idx_attempts_recent ON settings_unlock_attempts(user_id, attempt_timestamp DESC);
CREATE INDEX idx_violations_critical ON security_violations(severity, detected_at DESC);
CREATE INDEX idx_notifications_pending ON security_notifications(user_id, user_acknowledged, created_at DESC);

-- ============================================
-- END OF SECURE SETTINGS LOCK SCHEMA
-- ============================================
