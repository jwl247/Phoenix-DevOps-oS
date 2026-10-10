<?php
/**
 * ============================================
 * MODULE 3: SCHEDULE AI MANAGER
 * Handles calendar queries and conflict detection
 * ============================================
 * 
 * DEPLOYMENT:
 * 1. Save as: ai_schedule.php
 * 2. Upload to: C:\wamp64\www\lifefirst\ai\ai_schedule.php
 * 3. Add your Claude API key on line 25
 * 
 * FEATURES:
 * - Check availability ("Am I free at 3pm?")
 * - Prevent schedule conflicts
 * - Block time for both users
 * - Smart conflict detection
 * 
 * ============================================
 */

// ============================================
// CONFIGURATION
// ============================================

define('CLAUDE_API_KEY', 'YOUR_CLAUDE_API_KEY_HERE');  // ADD YOUR KEY HERE!
define('CLAUDE_MODEL', 'claude-sonnet-4-5-20250929');

// ============================================
// DATABASE CONNECTION
// ============================================

function getDB() {
    $conn = new mysqli('localhost', 'root', '', 'lifefirst');
    if ($conn->connect_error) {
        die(json_encode(['status' => 'error', 'message' => 'Database connection failed']));
    }
    $conn->set_charset('utf8mb4');
    return $conn;
}

// ============================================
// MAIN HANDLER
// ============================================

function handleScheduleRequest($data) {
    $userId = $data['user_id'];
    $message = $data['message'];
    $action = $data['action'] ?? 'query';
    
    // Determine what the user wants
    if (stripos($message, 'free') !== false || stripos($message, 'available') !== false || stripos($message, 'busy') !== false) {
        return checkAvailability($userId, $message);
    } elseif (stripos($message, 'schedule') !== false || stripos($message, 'book') !== false || stripos($message, 'add') !== false) {
        return scheduleEvent($userId, $message);
    } elseif (stripos($message, 'conflict') !== false) {
        return checkConflicts($userId);
    } else {
        return generalScheduleQuery($userId, $message);
    }
}

// ============================================
// CHECK AVAILABILITY
// ============================================

function checkAvailability($userId, $message) {
    // Extract time from message using Claude
    $timeData = extractTimeFromMessage($message);
    
    if (!$timeData['success']) {
        return [
            'status' => 'error',
            'message' => 'Could not understand the time. Try: "Am I free at 3pm today?"'
        ];
    }
    
    $startTime = $timeData['start_time'];
    $endTime = $timeData['end_time'];
    
    // Check user's schedule
    $conn = getDB();
    $stmt = $conn->prepare("
        SELECT title, start_time, end_time, priority 
        FROM schedule_events 
        WHERE user_id = ? 
        AND ((start_time <= ? AND end_time > ?) 
             OR (start_time < ? AND end_time >= ?))
        ORDER BY start_time
    ");
    $stmt->bind_param("issss", $userId, $startTime, $startTime, $endTime, $endTime);
    $stmt->execute();
    $result = $stmt->get_result();
    
    $conflicts = [];
    while ($row = $result->fetch_assoc()) {
        $conflicts[] = $row;
    }
    $stmt->close();
    
    // Check other user's schedule (for blocking)
    $otherUserId = ($userId == 1) ? 2 : 1;
    $stmt = $conn->prepare("
        SELECT u.display_name, s.title, s.start_time, s.end_time 
        FROM schedule_events s
        JOIN users u ON s.user_id = u.user_id
        WHERE s.user_id = ? 
        AND s.is_blocking = 1
        AND ((s.start_time <= ? AND s.end_time > ?) 
             OR (s.start_time < ? AND s.end_time >= ?))
    ");
    $stmt->bind_param("issss", $otherUserId, $startTime, $startTime, $endTime, $endTime);
    $stmt->execute();
    $otherResult = $stmt->get_result();
    
    $otherConflicts = [];
    while ($row = $otherResult->fetch_assoc()) {
        $otherConflicts[] = $row;
    }
    $stmt->close();
    $conn->close();
    
    // Build response
    if (empty($conflicts) && empty($otherConflicts)) {
        return [
            'status' => 'success',
            'available' => true,
            'message' => "Yes, you're free at that time!",
            'time_checked' => [
                'start' => $startTime,
                'end' => $endTime
            ]
        ];
    } else {
        $conflictMessages = [];
        foreach ($conflicts as $c) {
            $conflictMessages[] = "You have: " . $c['title'] . " (" . date('g:ia', strtotime($c['start_time'])) . " - " . date('g:ia', strtotime($c['end_time'])) . ")";
        }
        foreach ($otherConflicts as $c) {
            $conflictMessages[] = $c['display_name'] . " has: " . $c['title'] . " (blocking time)";
        }
        
        return [
            'status' => 'success',
            'available' => false,
            'message' => "No, you have conflicts:\n" . implode("\n", $conflictMessages),
            'conflicts' => array_merge($conflicts, $otherConflicts)
        ];
    }
}

// ============================================
// SCHEDULE NEW EVENT
// ============================================

function scheduleEvent($userId, $message) {
    // Extract event details using Claude
    $eventData = extractEventFromMessage($message);
    
    if (!$eventData['success']) {
        return [
            'status' => 'error',
            'message' => 'Could not understand the event. Try: "Schedule a meeting at 3pm for 1 hour"'
        ];
    }
    
    // Check for conflicts first
    $availability = checkAvailability($userId, "Am I free from " . $eventData['start_time'] . " to " . $eventData['end_time']);
    
    if (!$availability['available']) {
        return [
            'status' => 'conflict',
            'message' => 'Cannot schedule - you have conflicts at that time',
            'conflicts' => $availability['conflicts']
        ];
    }
    
    // Schedule the event
    $conn = getDB();
    $stmt = $conn->prepare("
        INSERT INTO schedule_events 
        (user_id, title, description, start_time, end_time, priority, is_blocking, created_by_ai)
        VALUES (?, ?, ?, ?, ?, ?, 1, 1)
    ");
    $stmt->bind_param("isssss", 
        $userId, 
        $eventData['title'], 
        $eventData['description'], 
        $eventData['start_time'], 
        $eventData['end_time'], 
        $eventData['priority']
    );
    
    if ($stmt->execute()) {
        $eventId = $stmt->insert_id;
        $stmt->close();
        $conn->close();
        
        return [
            'status' => 'success',
            'message' => "Event scheduled: " . $eventData['title'],
            'event' => [
                'id' => $eventId,
                'title' => $eventData['title'],
                'start' => $eventData['start_time'],
                'end' => $eventData['end_time']
            ]
        ];
    } else {
        $error = $stmt->error;
        $stmt->close();
        $conn->close();
        return [
            'status' => 'error',
            'message' => 'Failed to schedule event: ' . $error
        ];
    }
}

// ============================================
// CHECK ALL CONFLICTS
// ============================================

function checkConflicts($userId) {
    $conn = getDB();
    $stmt = $conn->prepare("
        SELECT 
            s1.title as event1,
            s1.start_time as start1,
            s1.end_time as end1,
            s2.title as event2,
            s2.start_time as start2,
            s2.end_time as end2
        FROM schedule_events s1
        JOIN schedule_events s2 ON s1.user_id = s2.user_id
        WHERE s1.user_id = ?
        AND s1.event_id < s2.event_id
        AND ((s1.start_time <= s2.start_time AND s1.end_time > s2.start_time)
             OR (s2.start_time <= s1.start_time AND s2.end_time > s1.start_time))
        AND s1.end_time >= NOW()
    ");
    $stmt->bind_param("i", $userId);
    $stmt->execute();
    $result = $stmt->get_result();
    
    $conflicts = [];
    while ($row = $result->fetch_assoc()) {
        $conflicts[] = $row;
    }
    $stmt->close();
    $conn->close();
    
    if (empty($conflicts)) {
        return [
            'status' => 'success',
            'conflicts' => [],
            'message' => 'No schedule conflicts found!'
        ];
    } else {
        return [
            'status' => 'success',
            'conflicts' => $conflicts,
            'message' => 'Found ' . count($conflicts) . ' conflict(s) in your schedule'
        ];
    }
}

// ============================================
// GENERAL SCHEDULE QUERY (Uses Claude AI)
// ============================================

function generalScheduleQuery($userId, $message) {
    // Get user's upcoming schedule
    $conn = getDB();
    $stmt = $conn->prepare("
        SELECT title, start_time, end_time, priority, description
        FROM schedule_events
        WHERE user_id = ?
        AND end_time >= NOW()
        ORDER BY start_time
        LIMIT 10
    ");
    $stmt->bind_param("i", $userId);
    $stmt->execute();
    $result = $stmt->get_result();
    
    $schedule = [];
    while ($row = $result->fetch_assoc()) {
        $schedule[] = $row;
    }
    $stmt->close();
    $conn->close();
    
    // Build context for Claude
    $scheduleContext = "User's upcoming schedule:\n";
    foreach ($schedule as $event) {
        $scheduleContext .= "- " . $event['title'] . " on " . date('M j, Y g:ia', strtotime($event['start_time'])) . " - " . date('g:ia', strtotime($event['end_time'])) . "\n";
    }
    
    // Call Claude API
    $response = callClaudeAPI($message, $scheduleContext);
    
    return [
        'status' => 'success',
        'message' => $response,
        'schedule' => $schedule
    ];
}

// ============================================
// CLAUDE API INTEGRATION
// ============================================

function callClaudeAPI($userMessage, $context = '') {
    if (CLAUDE_API_KEY === 'YOUR_CLAUDE_API_KEY_HERE') {
        return "ERROR: Claude API key not configured. Add your key to line 25 of ai_schedule.php";
    }
    
    $systemPrompt = "You are a schedule management assistant. You help users understand their calendar and find available times. Be concise and helpful. Today is " . date('l, F j, Y') . ".";
    
    if ($context) {
        $systemPrompt .= "\n\n" . $context;
    }
    
    $payload = [
        'model' => CLAUDE_MODEL,
        'max_tokens' => 1024,
        'messages' => [
            [
                'role' => 'user',
                'content' => $systemPrompt . "\n\nUser question: " . $userMessage
            ]
        ]
    ];
    
    $ch = curl_init('https://api.anthropic.com/v1/messages');
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_POST, true);
    curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($payload));
    curl_setopt($ch, CURLOPT_HTTPHEADER, [
        'Content-Type: application/json',
        'x-api-key: ' . CLAUDE_API_KEY,
        'anthropic-version: 2023-06-01'
    ]);
    
    $response = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    
    if ($httpCode !== 200) {
        return "Error calling Claude API (HTTP $httpCode)";
    }
    
    $data = json_decode($response, true);
    return $data['content'][0]['text'] ?? 'No response from AI';
}

// ============================================
// HELPER: EXTRACT TIME FROM MESSAGE
// ============================================

function extractTimeFromMessage($message) {
    // Simple time extraction (you can enhance this with Claude)
    $message = strtolower($message);
    
    // Try to find "at Xpm" or "at X:XXpm"
    if (preg_match('/at (\d{1,2})(?::(\d{2}))?\s*(am|pm)?/i', $message, $matches)) {
        $hour = (int)$matches[1];
        $minute = isset($matches[2]) ? (int)$matches[2] : 0;
        $ampm = $matches[3] ?? 'pm';
        
        if ($ampm === 'pm' && $hour < 12) $hour += 12;
        if ($ampm === 'am' && $hour === 12) $hour = 0;
        
        $today = date('Y-m-d');
        $startTime = $today . ' ' . sprintf('%02d:%02d:00', $hour, $minute);
        $endTime = date('Y-m-d H:i:s', strtotime($startTime . ' +1 hour'));
        
        return [
            'success' => true,
            'start_time' => $startTime,
            'end_time' => $endTime
        ];
    }
    
    return ['success' => false];
}

// ============================================
// HELPER: EXTRACT EVENT FROM MESSAGE
// ============================================

function extractEventFromMessage($message) {
    // Simple event extraction
    $timeData = extractTimeFromMessage($message);
    
    if (!$timeData['success']) {
        return ['success' => false];
    }
    
    // Extract title (simple version - everything before "at")
    $title = preg_replace('/\s+at\s+.*/i', '', $message);
    $title = preg_replace('/^(schedule|book|add)\s+/i', '', $title);
    $title = ucfirst(trim($title));
    
    if (empty($title)) {
        $title = 'Event';
    }
    
    return [
        'success' => true,
        'title' => $title,
        'description' => 'Created by AI',
        'start_time' => $timeData['start_time'],
        'end_time' => $timeData['end_time'],
        'priority' => 'medium'
    ];
}

// ============================================
// MODULE 3 COMPLETE! ✅
// ============================================
?>