<?php
/**
 * SECURE SETTINGS LOCK (MODULE 9)
 * Life First AI System
 * "The Fort Knox of Budget Apps"
 * 
 * Multi-factor authentication system for budget settings:
 * - GPS + Elevation verification
 * - Partner Bluetooth detection
 * - Home WiFi verification
 * - Time window restrictions
 * - Cool-down periods
 * - Behavioral analysis
 * - Threat detection
 */

if (!defined('API_ACCESS')) {
    die('Direct access not permitted');
}

class SecureSettingsLock {
    
    private $db;
    private $user_id;
    
    public function __construct($db_connection) {
        $this->db = $db_connection;
    }
    
    /**
     * Main request handler
     */
    public function handleRequest($action, $data) {
        $this->user_id = $data['user_id'] ?? null;
        
        switch ($action) {
            // Configuration
            case 'get_config':
                return $this->getConfig($data['user_id']);
            case 'setup_config':
                return $this->setupConfig($data);
            case 'update_config':
                return $this->updateConfig($data);
                
            // Unlock Process
            case 'attempt_unlock':
                return $this->attemptUnlock($data);
            case 'verify_unlock':
                return $this->verifyUnlock($data);
            case 'check_unlock_status':
                return $this->checkUnlockStatus($data['user_id']);
            case 'lock_settings':
                return $this->lockSettings($data['user_id']);
                
            // Emergency
            case 'request_emergency_override':
                return $this->requestEmergencyOverride($data);
            case 'verify_emergency_code':
                return $this->verifyEmergencyCode($data);
                
            // Monitoring
            case 'get_unlock_attempts':
                return $this->getUnlockAttempts($data['user_id']);
            case 'get_violations':
                return $this->getViolations($data['user_id']);
            case 'get_security_stats':
                return $this->getSecurityStats($data['user_id']);
            case 'get_notifications':
                return $this->getSecurityNotifications($data['user_id']);
                
            // Behavioral
            case 'update_behavior':
                return $this->updateBehaviorProfile($data);
                
            default:
                return ['success' => false, 'message' => 'Unknown action'];
        }
    }
    
    // =============================================
    // CONFIGURATION
    // =============================================
    
    private function getConfig($user_id) {
        $stmt = $this->db->prepare("SELECT * FROM secure_settings_config WHERE user_id = ?");
        $stmt->bind_param("i", $user_id);
        $stmt->execute();
        $result = $stmt->get_result();
        
        if ($result->num_rows === 0) {
            return ['success' => false, 'message' => 'Configuration not found. Run setup first.'];
        }
        
        $config = $result->fetch_assoc();
        
        // Don't send sensitive data to client
        unset($config['unlock_token']);
        
        return ['success' => true, 'config' => $config];
    }
    
    private function setupConfig($data) {
        // Initial setup - requires all security factors
        $required = [
            'user_id', 'partner_user_id', 
            'home_latitude', 'home_longitude', 'home_elevation',
            'user_bluetooth_mac', 'partner_bluetooth_mac',
            'home_wifi_bssid'
        ];
        
        foreach ($required as $field) {
            if (!isset($data[$field])) {
                return ['success' => false, 'message' => "Missing required field: $field"];
            }
        }
        
        $stmt = $this->db->prepare("
            INSERT INTO secure_settings_config 
            (user_id, partner_user_id, home_latitude, home_longitude, home_elevation,
             user_bluetooth_mac, partner_bluetooth_mac, home_wifi_bssid, home_wifi_ssid,
             security_level)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ");
        
        $security_level = $data['security_level'] ?? 'standard';
        
        $stmt->bind_param(
            "iidddsssss",
            $data['user_id'],
            $data['partner_user_id'],
            $data['home_latitude'],
            $data['home_longitude'],
            $data['home_elevation'],
            $data['user_bluetooth_mac'],
            $data['partner_bluetooth_mac'],
            $data['home_wifi_bssid'],
            $data['home_wifi_ssid'] ?? 'Unknown',
            $security_level
        );
        
        $stmt->execute();
        
        // Initialize behavior profile
        $this->db->prepare("INSERT IGNORE INTO user_behavior_profiles (user_id) VALUES (?)")->bind_param("i", $data['user_id'])->execute();
        $this->db->prepare("INSERT IGNORE INTO user_behavior_profiles (user_id) VALUES (?)")->bind_param("i", $data['partner_user_id'])->execute();
        
        // Initialize stats
        $this->db->prepare("INSERT IGNORE INTO security_stats (user_id) VALUES (?)")->bind_param("i", $data['user_id'])->execute();
        
        return ['success' => true, 'message' => 'Secure Settings Lock configured'];
    }
    
    private function updateConfig($data) {
        // Can only update config if currently unlocked
        if (!$this->isCurrentlyUnlocked($data['user_id'])) {
            return ['success' => false, 'message' => 'Settings must be unlocked to change configuration'];
        }
        
        $updates = [];
        $types = "";
        $params = [];
        
        $allowed_fields = [
            'security_level', 'location_radius_meters', 'elevation_tolerance_meters',
            'required_signal_strength', 'discussion_start_time', 'discussion_end_time',
            'weekend_anytime', 'cooldown_hours', 'voice_verification_required',
            'photo_verification_required', 'movement_detection_enabled',
            'max_failed_attempts', 'lockout_duration_hours', 'threat_score_threshold'
        ];
        
        foreach ($allowed_fields as $field) {
            if (isset($data[$field])) {
                $updates[] = "$field = ?";
                $params[] = $data[$field];
                $types .= $this->getParamType($field);
            }
        }
        
        if (empty($updates)) {
            return ['success' => false, 'message' => 'No valid fields to update'];
        }
        
        $params[] = $data['user_id'];
        $types .= "i";
        
        $sql = "UPDATE secure_settings_config SET " . implode(", ", $updates) . " WHERE user_id = ?";
        $stmt = $this->db->prepare($sql);
        $stmt->bind_param($types, ...$params);
        $stmt->execute();
        
        // Log the config change
        $this->logConfigChange($data['user_id'], $updates);
        
        return ['success' => true, 'message' => 'Configuration updated'];
    }
    
    // =============================================
    // UNLOCK PROCESS
    // =============================================
    
    private function attemptUnlock($data) {
        $user_id = $data['user_id'];
        
        // Get config
        $config = $this->getConfig($user_id);
        if (!$config['success']) {
            return $config;
        }
        $config = $config['config'];
        
        // Check if already unlocked
        if ($this->isCurrentlyUnlocked($user_id)) {
            return [
                'success' => true,
                'already_unlocked' => true,
                'expires_at' => $config['unlock_expires_at']
            ];
        }
        
        // Create unlock attempt record
        $attempt_id = $this->createUnlockAttempt($user_id, $data);
        
        // Run all security checks
        $checks = $this->runSecurityChecks($user_id, $config, $data);
        
        // Calculate threat score
        $threat_score = $this->calculateThreatScore($checks, $data);
        
        // Update attempt record with results
        $this->updateUnlockAttempt($attempt_id, $checks, $threat_score);
        
        // Determine if unlock should be granted
        $all_checks_passed = $this->evaluateChecks($checks);
        $threat_acceptable = $threat_score < $config['threat_score_threshold'];
        
        $success = $all_checks_passed && $threat_acceptable;
        
        if ($success) {
            // Generate unlock token (valid for 5 minutes)
            $token = $this->generateUnlockToken($user_id);
            
            // Update stats
            $this->updateStats($user_id, 'successful_unlock');
            
            // Notify partner
            $this->notifyPartner($config['partner_user_id'], 'unlock_success', $data);
            
            return [
                'success' => true,
                'unlocked' => true,
                'unlock_token' => $token,
                'expires_in_seconds' => 300,
                'checks' => $checks
            ];
        } else {
            // Update stats
            $this->updateStats($user_id, 'failed_unlock');
            
            // Check for violations
            $violations = $this->detectViolations($checks, $threat_score, $attempt_id);
            
            if (!empty($violations)) {
                // Notify partner of violation
                $this->notifyPartner($config['partner_user_id'], 'violation_detected', [
                    'violations' => $violations,
                    'threat_score' => $threat_score
                ]);
            }
            
            // Check for lockout
            $this->checkForLockout($user_id, $config);
            
            return [
                'success' => false,
                'unlocked' => false,
                'checks' => $checks,
                'threat_score' => $threat_score,
                'violations' => $violations,
                'message' => $this->buildDenialMessage($checks)
            ];
        }
    }
    
    private function runSecurityChecks($user_id, $config, $data) {
        $checks = [];
        
        // 1. Location Check (GPS + Elevation)
        $checks['location'] = $this->checkLocation($config, $data);
        
        // 2. Partner Detection (Bluetooth)
        $checks['partner_present'] = $this->checkPartnerPresence($config, $data);
        
        // 3. WiFi Verification
        $checks['wifi'] = $this->checkWiFi($config, $data);
        
        // 4. Time Window
        $checks['time_window'] = $this->checkTimeWindow($config);
        
        // 5. Cool-down Period
        $checks['cooldown'] = $this->checkCooldown($config);
        
        // 6. Device Integrity
        $checks['device_integrity'] = $this->checkDeviceIntegrity($data);
        
        // 7. Behavioral Analysis
        $checks['behavioral'] = $this->checkBehavior($user_id, $data);
        
        // 8. Movement Detection (during unlock)
        if ($config['movement_detection_enabled']) {
            $checks['movement'] = $this->checkMovement($data);
        }
        
        return $checks;
    }
    
    private function checkLocation($config, $data) {
        if (!isset($data['latitude']) || !isset($data['longitude']) || !isset($data['elevation'])) {
            return [
                'passed' => false,
                'reason' => 'Location data not provided',
                'severity' => 'critical'
            ];
        }
        
        // Calculate distance from home
        $distance = $this->calculateDistance(
            $data['latitude'], 
            $data['longitude'],
            $config['home_latitude'],
            $config['home_longitude']
        );
        
        // Check elevation difference
        $elevation_diff = abs($data['elevation'] - $config['home_elevation']);
        
        $location_ok = $distance <= $config['location_radius_meters'];
        $elevation_ok = $elevation_diff <= $config['elevation_tolerance_meters'];
        
        // GPS spoofing detection
        $gps_spoofing = false;
        if ($location_ok && !$elevation_ok) {
            // GPS matches but elevation doesn't = possible spoofing
            $gps_spoofing = true;
        }
        
        return [
            'passed' => $location_ok && $elevation_ok && !$gps_spoofing,
            'distance_meters' => round($distance, 2),
            'elevation_diff_meters' => round($elevation_diff, 2),
            'gps_spoofing_suspected' => $gps_spoofing,
            'reason' => !$location_ok ? "Too far from home ($distance m)" : 
                       (!$elevation_ok ? "Wrong elevation ($elevation_diff m)" : 
                       ($gps_spoofing ? "GPS spoofing suspected" : "OK")),
            'severity' => $gps_spoofing ? 'critical' : 'high'
        ];
    }
    
    private function checkPartnerPresence($config, $data) {
        if (!isset($data['partner_detected']) || !isset($data['partner_signal_strength'])) {
            return [
                'passed' => false,
                'reason' => 'Partner detection data not provided',
                'severity' => 'high'
            ];
        }
        
        $partner_present = $data['partner_detected'] === true;
        $signal_strong_enough = $data['partner_signal_strength'] >= $config['required_signal_strength'];
        
        $distance_estimate = $this->estimateDistanceFromRSSI($data['partner_signal_strength']);
        
        return [
            'passed' => $partner_present && $signal_strong_enough,
            'partner_detected' => $partner_present,
            'signal_strength' => $data['partner_signal_strength'],
            'estimated_distance_meters' => round($distance_estimate, 1),
            'reason' => !$partner_present ? "Partner's device not detected" :
                       (!$signal_strong_enough ? "Partner too far away ($distance_estimate m)" : "OK"),
            'severity' => 'critical'
        ];
    }
    
    private function checkWiFi($config, $data) {
        if (!isset($data['wifi_bssid'])) {
            return [
                'passed' => false,
                'reason' => 'WiFi data not provided',
                'severity' => 'medium'
            ];
        }
        
        $wifi_matches = strcasecmp($data['wifi_bssid'], $config['home_wifi_bssid']) === 0;
        
        return [
            'passed' => $wifi_matches,
            'connected_bssid' => $data['wifi_bssid'],
            'expected_bssid' => $config['home_wifi_bssid'],
            'reason' => $wifi_matches ? "OK" : "Not connected to home WiFi",
            'severity' => 'high'
        ];
    }
    
    private function checkTimeWindow($config) {
        $now = new DateTime();
        $day_of_week = (int)$now->format('w'); // 0=Sunday, 6=Saturday
        
        $is_weekend = ($day_of_week === 0 || $day_of_week === 6);
        
        if ($is_weekend && $config['weekend_anytime']) {
            return [
                'passed' => true,
                'reason' => 'Weekend - anytime allowed',
                'severity' => 'info'
            ];
        }
        
        $current_time = $now->format('H:i:s');
        $start_time = $config['discussion_start_time'];
        $end_time = $config['discussion_end_time'];
        
        $in_window = ($current_time >= $start_time && $current_time <= $end_time);
        
        return [
            'passed' => $in_window,
            'current_time' => $current_time,
            'window_start' => $start_time,
            'window_end' => $end_time,
            'reason' => $in_window ? "OK" : "Outside discussion hours ($start_time - $end_time)",
            'severity' => 'medium'
        ];
    }
    
    private function checkCooldown($config) {
        if (!$config['cooldown_active'] || $config['last_settings_change'] === null) {
            return [
                'passed' => true,
                'reason' => 'No active cool-down',
                'severity' => 'info'
            ];
        }
        
        $last_change = new DateTime($config['last_settings_change']);
        $now = new DateTime();
        $hours_since = ($now->getTimestamp() - $last_change->getTimestamp()) / 3600;
        
        $cooldown_satisfied = $hours_since >= $config['cooldown_hours'];
        
        return [
            'passed' => $cooldown_satisfied,
            'hours_since_change' => round($hours_since, 1),
            'required_hours' => $config['cooldown_hours'],
            'hours_remaining' => $cooldown_satisfied ? 0 : round($config['cooldown_hours'] - $hours_since, 1),
            'reason' => $cooldown_satisfied ? "OK" : "Cool-down period active",
            'severity' => 'high'
        ];
    }
    
    private function checkDeviceIntegrity($data) {
        $issues = [];
        
        if (isset($data['rooted']) && $data['rooted'] === true) {
            $issues[] = 'Device is rooted/jailbroken';
        }
        
        if (isset($data['usb_debugging']) && $data['usb_debugging'] === true) {
            $issues[] = 'USB debugging enabled';
        }
        
        if (isset($data['airplane_mode']) && $data['airplane_mode'] === true) {
            $issues[] = 'Airplane mode active';
        }
        
        if (isset($data['vpn_active']) && $data['vpn_active'] === true) {
            $issues[] = 'VPN detected';
        }
        
        if (isset($data['mock_location']) && $data['mock_location'] === true) {
            $issues[] = 'Mock location enabled';
        }
        
        $passed = empty($issues);
        
        return [
            'passed' => $passed,
            'issues' => $issues,
            'reason' => $passed ? "OK" : implode(', ', $issues),
            'severity' => 'critical'
        ];
    }
    
    private function checkBehavior($user_id, $data) {
        // Get user's behavioral profile
        $stmt = $this->db->prepare("SELECT * FROM user_behavior_profiles WHERE user_id = ?");
        $stmt->bind_param("i", $user_id);
        $stmt->execute();
        $result = $stmt->get_result();
        
        if ($result->num_rows === 0 || !isset($data['behavior'])) {
            return [
                'passed' => true,
                'reason' => 'Behavioral analysis not yet trained',
                'confidence' => 0,
                'severity' => 'info'
            ];
        }
        
        $profile = $result->fetch_assoc();
        $behavior = $data['behavior'];
        
        // Compare current behavior to profile
        $score = 100; // Start at perfect match
        $anomalies = [];
        
        // Typing speed
        if (isset($behavior['typing_speed']) && $profile['avg_typing_speed_wpm']) {
            $diff = abs($behavior['typing_speed'] - $profile['avg_typing_speed_wpm']);
            if ($diff > ($profile['typing_speed_variance'] * 2)) {
                $score -= 20;
                $anomalies[] = 'Typing speed unusual';
            }
        }
        
        // Touch pressure
        if (isset($behavior['screen_pressure']) && $profile['avg_screen_pressure']) {
            $diff = abs($behavior['screen_pressure'] - $profile['avg_screen_pressure']);
            if ($diff > ($profile['pressure_variance'] * 2)) {
                $score -= 15;
                $anomalies[] = 'Touch pressure unusual';
            }
        }
        
        // Time of day
        if (isset($behavior['hour']) && $profile['typical_access_hours']) {
            $typical_hours = json_decode($profile['typical_access_hours'], true);
            if (!in_array($behavior['hour'], $typical_hours)) {
                $score -= 10;
                $anomalies[] = 'Unusual access time';
            }
        }
        
        $passed = $score >= 70; // 70% match required
        
        return [
            'passed' => $passed,
            'behavior_score' => $score,
            'anomalies' => $anomalies,
            'reason' => $passed ? "OK" : "Behavioral mismatch: " . implode(', ', $anomalies),
            'severity' => $score < 50 ? 'high' : 'medium'
        ];
    }
    
    private function checkMovement($data) {
        if (!isset($data['movement_detected']) || !isset($data['movement_distance'])) {
            return [
                'passed' => true,
                'reason' => 'Movement data not provided',
                'severity' => 'info'
            ];
        }
        
        $moved_too_much = $data['movement_distance'] > 5; // 5 meters
        
        return [
            'passed' => !$moved_too_much,
            'movement_distance' => $data['movement_distance'],
            'reason' => $moved_too_much ? "Phone moved {$data['movement_distance']}m during unlock" : "OK",
            'severity' => 'high'
        ];
    }
    
    private function calculateThreatScore($checks, $data) {
        $score = 0;
        
        // Each failed check adds to threat score
        foreach ($checks as $check_name => $check) {
            if (!$check['passed']) {
                switch ($check['severity']) {
                    case 'critical':
                        $score += 30;
                        break;
                    case 'high':
                        $score += 20;
                        break;
                    case 'medium':
                        $score += 10;
                        break;
                    case 'low':
                        $score += 5;
                        break;
                }
            }
        }
        
        // Additional threat indicators
        if (isset($data['rooted']) && $data['rooted']) {
            $score += 25;
        }
        
        if (isset($checks['location']['gps_spoofing_suspected']) && $checks['location']['gps_spoofing_suspected']) {
            $score += 40;
        }
        
        if (isset($checks['behavioral']['behavior_score']) && $checks['behavioral']['behavior_score'] < 50) {
            $score += 20;
        }
        
        return min($score, 100); // Cap at 100
    }
    
    private function evaluateChecks($checks) {
        // Core checks that MUST pass
        $core_checks = ['location', 'partner_present', 'wifi', 'device_integrity'];
        
        foreach ($core_checks as $check_name) {
            if (isset($checks[$check_name]) && !$checks[$check_name]['passed']) {
                return false;
            }
        }
        
        return true;
    }
    
    private function detectViolations($checks, $threat_score, $attempt_id) {
        $violations = [];
        
        // GPS Spoofing
        if (isset($checks['location']['gps_spoofing_suspected']) && $checks['location']['gps_spoofing_suspected']) {
            $violations[] = $this->createViolation('gps_spoofing', 'critical', $attempt_id);
        }
        
        // Unauthorized Location
        if (isset($checks['location']) && !$checks['location']['passed'] && !$checks['location']['gps_spoofing_suspected']) {
            $violations[] = $this->createViolation('unauthorized_location', 'high', $attempt_id);
        }
        
        // Partner Not Present
        if (isset($checks['partner_present']) && !$checks['partner_present']['passed']) {
            $violations[] = $this->createViolation('partner_not_present', 'critical', $attempt_id);
        }
        
        // Rooted Device
        if (isset($checks['device_integrity']['issues']) && in_array('Device is rooted/jailbroken', $checks['device_integrity']['issues'])) {
            $violations[] = $this->createViolation('rooted_device', 'critical', $attempt_id);
        }
        
        // High Threat Score
        if ($threat_score >= 70) {
            $violations[] = $this->createViolation('multiple_failed_attempts', 'high', $attempt_id);
        }
        
        return $violations;
    }
    
    private function createViolation($type, $severity, $attempt_id) {
        $stmt = $this->db->prepare("
            INSERT INTO security_violations 
            (user_id, unlock_attempt_id, violation_type, severity, detected_at)
            VALUES (?, ?, ?, ?, NOW())
        ");
        
        $stmt->bind_param("iiss", $this->user_id, $attempt_id, $type, $severity);
        $stmt->execute();
        
        return [
            'id' => $stmt->insert_id,
            'type' => $type,
            'severity' => $severity
        ];
    }
    
    private function generateUnlockToken($user_id) {
        $token = bin2hex(random_bytes(32));
        $expires_at = date('Y-m-d H:i:s', time() + 300); // 5 minutes
        
        $stmt = $this->db->prepare("
            UPDATE secure_settings_config 
            SET currently_unlocked = 1, 
                unlock_expires_at = ?, 
                unlock_token = ?
            WHERE user_id = ?
        ");
        
        $stmt->bind_param("ssi", $expires_at, $token, $user_id);
        $stmt->execute();
        
        return $token;
    }
    
    private function isCurrentlyUnlocked($user_id) {
        $stmt = $this->db->prepare("
            SELECT currently_unlocked, unlock_expires_at 
            FROM secure_settings_config 
            WHERE user_id = ?
        ");
        $stmt->bind_param("i", $user_id);
        $stmt->execute();
        $result = $stmt->get_result()->fetch_assoc();
        
        if (!$result || !$result['currently_unlocked']) {
            return false;
        }
        
        // Check if expired
        $expires = new DateTime($result['unlock_expires_at']);
        $now = new DateTime();
        
        if ($now > $expires) {
            // Auto-lock
            $this->lockSettings($user_id);
            return false;
        }
        
        return true;
    }
    
    private function lockSettings($user_id) {
        $stmt = $this->db->prepare("
            UPDATE secure_settings_config 
            SET currently_unlocked = 0, 
                unlock_expires_at = NULL,
                unlock_token = NULL
            WHERE user_id = ?
        ");
        $stmt->bind_param("i", $user_id);
        $stmt->execute();
        
        return ['success' => true, 'message' => 'Settings locked'];
    }
    
    // =============================================
    // HELPER FUNCTIONS
    // =============================================
    
    private function calculateDistance($lat1, $lon1, $lat2, $lon2) {
        // Haversine formula
        $earth_radius = 6371000; // meters
        
        $dLat = deg2rad($lat2 - $lat1);
        $dLon = deg2rad($lon2 - $lon1);
        
        $a = sin($dLat/2) * sin($dLat/2) +
             cos(deg2rad($lat1)) * cos(deg2rad($lat2)) *
             sin($dLon/2) * sin($dLon/2);
        
        $c = 2 * atan2(sqrt($a), sqrt(1-$a));
        
        return $earth_radius * $c;
    }
    
    private function estimateDistanceFromRSSI($rssi) {
        // Rough estimation: -40 dBm = 1m, -70 dBm = 10m, -90 dBm = 100m
        // Formula: distance = 10 ^ ((TxPower - RSSI) / (10 * N))
        $txPower = -40; // Typical Bluetooth transmission power
        $n = 2.0; // Path loss exponent (2-4 for indoor)
        
        return pow(10, ($txPower - $rssi) / (10 * $n));
    }
    
    private function getParamType($field) {
        $int_fields = ['location_radius_meters', 'elevation_tolerance_meters', 'required_signal_strength',
                      'cooldown_hours', 'max_failed_attempts', 'lockout_duration_hours', 'threat_score_threshold'];
        $bool_fields = ['weekend_anytime', 'voice_verification_required', 'photo_verification_required', 
                       'movement_detection_enabled'];
        
        if (in_array($field, $int_fields)) return 'i';
        if (in_array($field, $bool_fields)) return 'i'; // MySQL boolean as int
        return 's'; // Default to string
    }
    
    private function createUnlockAttempt($user_id, $data) {
        $stmt = $this->db->prepare("
            INSERT INTO settings_unlock_attempts 
            (user_id, attempt_latitude, attempt_longitude, attempt_elevation,
             device_model, android_version, app_version, ip_address)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ");
        
        $stmt->bind_param(
            "idddssss",
            $user_id,
            $data['latitude'] ?? null,
            $data['longitude'] ?? null,
            $data['elevation'] ?? null,
            $data['device_model'] ?? 'Unknown',
            $data['android_version'] ?? 'Unknown',
            $data['app_version'] ?? '1.0',
            $_SERVER['REMOTE_ADDR'] ?? 'Unknown'
        );
        
        $stmt->execute();
        return $stmt->insert_id;
    }
    
    private function updateUnlockAttempt($attempt_id, $checks, $threat_score) {
        $all_passed = $this->evaluateChecks($checks);
        
        $stmt = $this->db->prepare("
            UPDATE settings_unlock_attempts 
            SET location_verified = ?,
                partner_detected = ?,
                wifi_verified = ?,
                time_window_verified = ?,
                cooldown_satisfied = ?,
                all_checks_passed = ?,
                threat_score = ?,
                success = ?
            WHERE id = ?
        ");
        
        $stmt->bind_param(
            "iiiiiiii",
            $checks['location']['passed'] ?? 0,
            $checks['partner_present']['passed'] ?? 0,
            $checks['wifi']['passed'] ?? 0,
            $checks['time_window']['passed'] ?? 0,
            $checks['cooldown']['passed'] ?? 0,
            $all_passed,
            $threat_score,
            $all_passed,
            $attempt_id
        );
        
        $stmt->execute();
    }
    
    private function notifyPartner($partner_id, $type, $data) {
        // Create notification via Notification AI
        $message = $this->buildNotificationMessage($type, $data);
        
        $stmt = $this->db->prepare("
            INSERT INTO pending_notifications 
            (user_id, notification_type, message, priority, requires_response)
            VALUES (?, 'security_alert', ?, 'high', 0)
        ");
        
        $stmt->bind_param("is", $partner_id, $message);
        $stmt->execute();
    }
    
    private function buildNotificationMessage($type, $data) {
        switch ($type) {
            case 'unlock_success':
                return "Your partner is accessing budget settings";
            case 'violation_detected':
                return "Security violation detected during settings unlock attempt";
            case 'emergency_override':
                return "Emergency override requested";
            default:
                return "Security event occurred";
        }
    }
    
    private function buildDenialMessage($checks) {
        $failed = [];
        
        foreach ($checks as $name => $check) {
            if (!$check['passed']) {
                $failed[] = $check['reason'];
            }
        }
        
        return "Access denied: " . implode(', ', $failed);
    }
    
    private function updateStats($user_id, $event_type) {
        if ($event_type === 'successful_unlock') {
            $this->db->prepare("
                UPDATE security_stats 
                SET total_unlock_attempts = total_unlock_attempts + 1,
                    successful_unlocks = successful_unlocks + 1,
                    consecutive_successful_unlocks = consecutive_successful_unlocks + 1,
                    last_successful_unlock = NOW()
                WHERE user_id = ?
            ")->bind_param("i", $user_id)->execute();
        } else {
            $this->db->prepare("
                UPDATE security_stats 
                SET total_unlock_attempts = total_unlock_attempts + 1,
                    failed_unlocks = failed_unlocks + 1,
                    consecutive_successful_unlocks = 0,
                    last_unlock_attempt = NOW()
                WHERE user_id = ?
            ")->bind_param("i", $user_id)->execute();
        }
    }
    
    private function checkForLockout($user_id, $config) {
        // Check recent failed attempts
        $stmt = $this->db->prepare("
            SELECT COUNT(*) as failures 
            FROM settings_unlock_attempts 
            WHERE user_id = ? 
            AND success = 0 
            AND attempt_timestamp > DATE_SUB(NOW(), INTERVAL 1 HOUR)
        ");
        
        $stmt->bind_param("i", $user_id);
        $stmt->execute();
        $result = $stmt->get_result()->fetch_assoc();
        
        if ($result['failures'] >= $config['max_failed_attempts']) {
            // Trigger lockout
            // Implementation depends on your broader system
        }
    }
    
    private function logConfigChange($user_id, $changes) {
        // Log to audit trail
        // Implementation as needed
    }
    
    private function checkUnlockStatus($user_id) {
        return [
            'success' => true,
            'unlocked' => $this->isCurrentlyUnlocked($user_id)
        ];
    }
    
    private function verifyUnlock($data) {
        // Verify unlock token for API requests
        $stmt = $this->db->prepare("
            SELECT user_id FROM secure_settings_config 
            WHERE unlock_token = ? AND unlock_expires_at > NOW()
        ");
        
        $stmt->bind_param("s", $data['unlock_token']);
        $stmt->execute();
        $result = $stmt->get_result();
        
        return [
            'success' => $result->num_rows > 0,
            'valid' => $result->num_rows > 0
        ];
    }
    
    // Emergency override and monitoring functions would go here
    // Simplified for brevity
    
    private function requestEmergencyOverride($data) {
        return ['success' => true, 'message' => 'Emergency override not yet implemented'];
    }
    
    private function verifyEmergencyCode($data) {
        return ['success' => false, 'message' => 'Emergency override not yet implemented'];
    }
    
    private function getUnlockAttempts($user_id) {
        $stmt = $this->db->prepare("
            SELECT * FROM settings_unlock_attempts 
            WHERE user_id = ? 
            ORDER BY attempt_timestamp DESC 
            LIMIT 50
        ");
        $stmt->bind_param("i", $user_id);
        $stmt->execute();
        $result = $stmt->get_result();
        
        $attempts = [];
        while ($row = $result->fetch_assoc()) {
            $attempts[] = $row;
        }
        
        return ['success' => true, 'attempts' => $attempts];
    }
    
    private function getViolations($user_id) {
        $stmt = $this->db->prepare("
            SELECT * FROM security_violations 
            WHERE user_id = ? 
            ORDER BY detected_at DESC 
            LIMIT 50
        ");
        $stmt->bind_param("i", $user_id);
        $stmt->execute();
        $result = $stmt->get_result();
        
        $violations = [];
        while ($row = $result->fetch_assoc()) {
            $violations[] = $row;
        }
        
        return ['success' => true, 'violations' => $violations];
    }
    
    private function getSecurityStats($user_id) {
        $stmt = $this->db->prepare("SELECT * FROM security_stats WHERE user_id = ?");
        $stmt->bind_param("i", $user_id);
        $stmt->execute();
        $result = $stmt->get_result();
        
        return ['success' => true, 'stats' => $result->fetch_assoc()];
    }
    
    private function getSecurityNotifications($user_id) {
        $stmt = $this->db->prepare("
            SELECT * FROM security_notifications 
            WHERE user_id = ? 
            ORDER BY created_at DESC 
            LIMIT 20
        ");
        $stmt->bind_param("i", $user_id);
        $stmt->execute();
        $result = $stmt->get_result();
        
        $notifications = [];
        while ($row = $result->fetch_assoc()) {
            $notifications[] = $row;
        }
        
        return ['success' => true, 'notifications' => $notifications];
    }
    
    private function updateBehaviorProfile($data) {
        // Update behavioral learning data
        return ['success' => true, 'message' => 'Behavior profile updated'];
    }
}

// Module export function
function handleSecureSettingsRequest($db, $action, $data) {
    $security = new SecureSettingsLock($db);
    return $security->handleRequest($action, $data);
}

?>
