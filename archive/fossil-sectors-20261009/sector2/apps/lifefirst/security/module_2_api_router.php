<?php
/**
 * ============================================
 * MODULE 2: LIFE FIRST API ROUTER
 * Main Entry Point for All Phone Requests
 * ============================================
 * 
 * DEPLOYMENT INSTRUCTIONS:
 * 1. Save this file as: api.php
 * 2. Upload to: C:\wamp64\www\lifefirst\api.php
 * 3. Set permissions: Read/Write for PHP
 * 4. Test URL: http://YOUR_SERVER_IP/lifefirst/api.php
 * 
 * REQUIRED:
 * - Module 1 (Database) must be installed first
 * - PHP 7.4+ with mysqli extension
 * - Claude API key (you'll add in Module 3+)
 * 
 * ============================================
 */

// Error reporting (turn off in production)
error_reporting(E_ALL);
ini_set('display_errors', 1);

// Allow cross-origin requests (for your phones)
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: POST, GET, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type, Authorization');
header('Content-Type: application/json');

// Handle preflight OPTIONS request
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit();
}

// ============================================
// CONFIGURATION
// ============================================

define('DB_HOST', 'localhost');
define('DB_USER', 'root');  // Change if you have different MySQL user
define('DB_PASS', '');      // Add your MySQL password if you have one
define('DB_NAME', 'lifefirst');

// Simple authentication token (change this!)
define('API_SECRET', 'your_secret_token_change_me_12345');

// AI Module paths (we'll create these in modules 3-7)
define('AI_SCHEDULE_PATH', __DIR__ . '/ai/ai_schedule.php');
define('AI_MESSENGER_PATH', __DIR__ . '/ai/ai_messenger.php');
define('AI_MEMORY_PATH', __DIR__ . '/ai/ai_memory.php');
define('AI_NOTIFICATION_PATH', __DIR__ . '/ai/ai_notifications.php');
define('AI_VOICE_PATH', __DIR__ . '/ai/ai_voice.php');

// ============================================
// DATABASE CONNECTION
// ============================================

function getDBConnection() {
    $conn = new mysqli(DB_HOST, DB_USER, DB_PASS, DB_NAME);
    
    if ($conn->connect_error) {
        logError('Database connection failed: ' . $conn->connect_error);
        respondError('Database connection failed', 500);
    }
    
    $conn->set_charset('utf8mb4');
    return $conn;
}

// ============================================
// AUTHENTICATION
// ============================================

function authenticate() {
    $headers = getallheaders();
    $token = $headers['Authorization'] ?? $_POST['token'] ?? $_GET['token'] ?? null;
    
    if (!$token) {
        respondError('Missing authentication token', 401);
    }
    
    // Remove "Bearer " prefix if present
    $token = str_replace('Bearer ', '', $token);
    
    if ($token !== API_SECRET) {
        respondError('Invalid authentication token', 401);
    }
    
    return true;
}

// ============================================
// USER IDENTIFICATION
// ============================================

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

// ============================================
// INTENT DETECTION (Routes to correct AI)
// ============================================

function detectIntent($message) {
    $message = strtolower($message);
    
    // AI #1: Schedule Manager
    $scheduleKeywords = ['schedule', 'calendar', 'meeting', 'appointment', 'free', 'busy', 'available', 'book', 'cancel', 'when am i', 'am i free', 'conflict'];
    foreach ($scheduleKeywords as $keyword) {
        if (strpos($message, $keyword) !== false) {
            return 'schedule';
        }
    }
    
    // AI #2: Cross-Phone Messenger
    $messengerKeywords = ['ask laurie', 'ask you', 'does laurie', 'do you', 'tell laurie', 'tell you', 'what does', 'send message', 'pickles'];
    foreach ($messengerKeywords as $keyword) {
        if (strpos($message, $keyword) !== false) {
            return 'messenger';
        }
    }
    
    // AI #3: Memory Keeper
    $memoryKeywords = ['remember', 'recall', 'what does', 'preference', 'likes', 'dislikes', 'favorite', 'prefers', 'usually', 'always', 'never'];
    foreach ($memoryKeywords as $keyword) {
        if (strpos($message, $keyword) !== false) {
            return 'memory';
        }
    }
    
    // AI #4: Notification (usually triggered internally, not by user)
    $notificationKeywords = ['notify', 'alert', 'remind me', 'reminder', 'notification'];
    foreach ($notificationKeywords as $keyword) {
        if (strpos($message, $keyword) !== false) {
            return 'notification';
        }
    }
    
    // Default: AI #5 Voice Commander (general conversation)
    return 'voice';
}

// ============================================
// ROUTE REQUEST TO CORRECT AI MODULE
// ============================================

function routeToAI($intent, $data) {
    switch ($intent) {
        case 'schedule':
            if (file_exists(AI_SCHEDULE_PATH)) {
                require_once AI_SCHEDULE_PATH;
                return handleScheduleRequest($data);
            } else {
                return ['status' => 'error', 'message' => 'Schedule AI module not yet installed (Module 3)', 'fallback' => true];
            }
            
        case 'messenger':
            if (file_exists(AI_MESSENGER_PATH)) {
                require_once AI_MESSENGER_PATH;
                return handleMessengerRequest($data);
            } else {
                return ['status' => 'error', 'message' => 'Messenger AI module not yet installed (Module 4)', 'fallback' => true];
            }
            
        case 'memory':
            if (file_exists(AI_MEMORY_PATH)) {
                require_once AI_MEMORY_PATH;
                return handleMemoryRequest($data);
            } else {
                return ['status' => 'error', 'message' => 'Memory AI module not yet installed (Module 5)', 'fallback' => true];
            }
            
        case 'notification':
            if (file_exists(AI_NOTIFICATION_PATH)) {
                require_once AI_NOTIFICATION_PATH;
                return handleNotificationRequest($data);
            } else {
                return ['status' => 'error', 'message' => 'Notification AI module not yet installed (Module 6)', 'fallback' => true];
            }
            
        case 'voice':
        default:
            if (file_exists(AI_VOICE_PATH)) {
                require_once AI_VOICE_PATH;
                return handleVoiceRequest($data);
            } else {
                return ['status' => 'error', 'message' => 'Voice AI module not yet installed (Module 7)', 'fallback' => true];
            }
    }
}

// ============================================
// LOGGING
// ============================================

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
    $conn = getDBConnection();
    $stmt = $conn->prepare("INSERT INTO system_logs (log_level, component, message) VALUES ('error', 'api_router', ?)");
    $stmt->bind_param("s", $message);
    $stmt->execute();
    $stmt->close();
    $conn->close();
}

// ============================================
// RESPONSE HELPERS
// ============================================

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

// ============================================
// MAIN REQUEST HANDLER
// ============================================

function handleRequest() {
    // Only accept POST requests
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
        respondError('Only POST requests are allowed', 405);
    }
    
    // Authenticate request
    authenticate();
    
    // Get request data
    $input = file_get_contents('php://input');
    $data = json_decode($input, true);
    
    if (!$data) {
        respondError('Invalid JSON data', 400);
    }
    
    // Required fields
    $username = $data['username'] ?? null;
    $message = $data['message'] ?? null;
    $action = $data['action'] ?? 'query';  // query, notify, schedule, etc.
    
    if (!$username || !$message) {
        respondError('Missing required fields: username, message', 400);
    }
    
    // Get user info
    $user = getUser($username);
    
    // Detect intent from message
    $intent = detectIntent($message);
    
    // Prepare data for AI module
    $aiData = [
        'user_id' => $user['user_id'],
        'username' => $user['username'],
        'display_name' => $user['display_name'],
        'message' => $message,
        'action' => $action,
        'raw_data' => $data
    ];
    
    // Route to appropriate AI
    $response = routeToAI($intent, $aiData);
    
    // Log the interaction
    logInteraction($user['user_id'], $message, $intent, $response, $response['status'] !== 'error');
    
    // Return response
    respondSuccess([
        'intent' => $intent,
        'response' => $response
    ]);
}

// ============================================
// HEALTH CHECK ENDPOINT
// ============================================

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

// ============================================
// TEST ENDPOINT
// ============================================

function testEndpoint() {
    respondSuccess([
        'message' => 'Life First API is running!',
        'version' => '1.0.0',
        'modules' => [
            'module_1' => 'Database (installed)',
            'module_2' => 'API Router (you are here)',
            'module_3' => 'Schedule AI (coming next)',
            'module_4' => 'Messenger AI (coming next)',
            'module_5' => 'Memory AI (coming next)',
            'module_6' => 'Notification AI (coming next)',
            'module_7' => 'Voice AI (coming next)'
        ],
        'next_steps' => [
            '1. Create ai/ directory in /lifefirst/',
            '2. Build Module 3 (Schedule AI)',
            '3. Test with Android app (Module 8)'
        ]
    ]);
}

// ============================================
// ROUTER - Determine which function to call
// ============================================

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

// ============================================
// MODULE 2 COMPLETE! ✅
// ============================================
?>
