<?php
/**
 * ============================================
 * MODULE 6: NOTIFICATION ENFORCER AI
 * Relentless notifications (MUST ANSWER)
 * ============================================
 * 
 * DEPLOYMENT:
 * 1. Run deploy_lifefirst.sh on phoenix-ext
 * 2. Deployed to: /var/www/html/lifefirst/ai/ai_notifications.php
 * 3. API key set via /etc/lifefirst/lifefirst.env (CLAUDE_API_KEY)
 * 
 * FEATURES:
 * - Send urgent notifications
 * - Escalate if ignored (louder, repeat)
 * - Track acknowledgment
 * - Priority-based delivery
 * 
 * ============================================
 */

// ============================================
// CONFIGURATION — credentials + model from config.php
// ============================================

require_once __DIR__ . '/config.php';

// Escalation settings
define('MAX_ESCALATION_LEVEL', 5);
define('ESCALATION_INTERVAL_SECONDS', 30);  // Repeat every 30 seconds if not answered

// ============================================
// MAIN HANDLER
// ============================================

function handleNotificationRequest($data) {
    $userId = $data['user_id'];
    $message = $data['message'];
    $action = $data['action'] ?? 'send';
    
    switch ($action) {
        case 'send':
            return sendNotification($userId, $data);
        case 'acknowledge':
            return acknowledgeNotification($userId, $data);
        case 'check':
            return checkPendingNotifications($userId);
        case 'escalate':
            return escalateNotifications($userId);
        default:
            return sendNotification($userId, $data);
    }
}

// ============================================
// SEND NOTIFICATION
// ============================================

function sendNotification($userId, $data) {
    $message = $data['raw_data']['notification_text'] ?? $data['message'];
    $type = $data['raw_data']['notification_type'] ?? 'info';
    $priority = $data['raw_data']['priority'] ?? 5;
    $relatedMessageId = $data['raw_data']['related_message_id'] ?? null;
    
    // Determine urgency
    $maxEscalation = ($type === 'must_answer') ? MAX_ESCALATION_LEVEL : 1;
    
    $conn = getDB();
    $stmt = $conn->prepare("
        INSERT INTO notification_queue
        (user_id, message_text, notification_type, priority_level, max_escalation, related_message_id, scheduled_for)
        VALUES (?, ?, ?, ?, ?, ?, NOW())
    ");
    
    $stmt->bind_param("issiii", 
        $userId, 
        $message, 
        $type, 
        $priority, 
        $maxEscalation, 
        $relatedMessageId
    );
    
    if ($stmt->execute()) {
        $notificationId = $stmt->insert_id;
        $stmt->close();
        
        // Immediately mark as sent
        markNotificationAsSent($notificationId);
        
        $conn->close();
        
        return [
            'status' => 'success',
            'message' => 'Notification sent',
            'notification_id' => $notificationId,
            'type' => $type,
            'priority' => $priority,
            'will_escalate' => ($maxEscalation > 1)
        ];
    } else {
        $error = $stmt->error;
        $stmt->close();
        $conn->close();
        
        return [
            'status' => 'error',
            'message' => 'Failed to queue notification: ' . $error
        ];
    }
}

// ============================================
// ACKNOWLEDGE NOTIFICATION
// ============================================

function acknowledgeNotification($userId, $data) {
    $notificationId = $data['raw_data']['notification_id'] ?? null;
    
    if (!$notificationId) {
        return [
            'status' => 'error',
            'message' => 'No notification ID provided'
        ];
    }
    
    $conn = getDB();
    $stmt = $conn->prepare("
        UPDATE notification_queue
        SET status = 'acknowledged',
            acknowledged_at = NOW()
        WHERE notification_id = ?
        AND user_id = ?
        AND status != 'acknowledged'
    ");
    $stmt->bind_param("ii", $notificationId, $userId);
    
    if ($stmt->execute() && $stmt->affected_rows > 0) {
        $stmt->close();
        $conn->close();
        
        return [
            'status' => 'success',
            'message' => 'Notification acknowledged',
            'notification_id' => $notificationId
        ];
    } else {
        $stmt->close();
        $conn->close();
        
        return [
            'status' => 'error',
            'message' => 'Notification not found or already acknowledged'
        ];
    }
}

// ============================================
// CHECK PENDING NOTIFICATIONS
// ============================================

function checkPendingNotifications($userId) {
    $conn = getDB();
    $stmt = $conn->prepare("
        SELECT 
            notification_id,
            message_text,
            notification_type,
            priority_level,
            escalation_level,
            delivery_attempts,
            scheduled_for,
            sent_at
        FROM notification_queue
        WHERE user_id = ?
        AND status IN ('queued', 'sent', 'delivered')
        AND (expires_at IS NULL OR expires_at > NOW())
        ORDER BY priority_level DESC, escalation_level DESC, scheduled_for ASC
    ");
    $stmt->bind_param("i", $userId);
    $stmt->execute();
    $result = $stmt->get_result();
    
    $notifications = [];
    while ($row = $result->fetch_assoc()) {
        $notifications[] = $row;
    }
    $stmt->close();
    $conn->close();
    
    if (empty($notifications)) {
        return [
            'status' => 'success',
            'has_notifications' => false,
            'count' => 0,
            'message' => 'No pending notifications',
            'notifications' => []
        ];
    } else {
        // Get highest priority one
        $urgent = $notifications[0];
        
        return [
            'status' => 'success',
            'has_notifications' => true,
            'count' => count($notifications),
            'message' => 'You have ' . count($notifications) . ' notification(s)',
            'most_urgent' => $urgent,
            'notifications' => $notifications
        ];
    }
}

// ============================================
// ESCALATE NOTIFICATIONS (Called periodically)
// ============================================

function escalateNotifications($userId = null) {
    $conn = getDB();
    
    // Find notifications that need escalation
    $query = "
        SELECT notification_id, user_id, escalation_level, max_escalation, delivery_attempts
        FROM notification_queue
        WHERE status IN ('sent', 'delivered')
        AND escalation_level < max_escalation
        AND (expires_at IS NULL OR expires_at > NOW())
        AND sent_at < DATE_SUB(NOW(), INTERVAL " . ESCALATION_INTERVAL_SECONDS . " SECOND)
    ";
    
    if ($userId) {
        $query .= " AND user_id = $userId";
    }
    
    $result = $conn->query($query);
    
    $escalated = [];
    while ($row = $result->fetch_assoc()) {
        // Increment escalation level
        $newLevel = $row['escalation_level'] + 1;
        $newAttempts = $row['delivery_attempts'] + 1;
        
        $stmt = $conn->prepare("
            UPDATE notification_queue
            SET escalation_level = ?,
                delivery_attempts = ?,
                sent_at = NOW()
            WHERE notification_id = ?
        ");
        $stmt->bind_param("iii", $newLevel, $newAttempts, $row['notification_id']);
        $stmt->execute();
        $stmt->close();
        
        $escalated[] = [
            'notification_id' => $row['notification_id'],
            'user_id' => $row['user_id'],
            'new_escalation_level' => $newLevel,
            'attempts' => $newAttempts
        ];
    }
    
    $conn->close();
    
    return [
        'status' => 'success',
        'escalated_count' => count($escalated),
        'notifications' => $escalated
    ];
}

// ============================================
// MARK NOTIFICATION AS SENT
// ============================================

function markNotificationAsSent($notificationId) {
    $conn = getDB();
    $stmt = $conn->prepare("
        UPDATE notification_queue
        SET status = 'sent',
            sent_at = NOW(),
            delivery_attempts = delivery_attempts + 1
        WHERE notification_id = ?
    ");
    $stmt->bind_param("i", $notificationId);
    $stmt->execute();
    $stmt->close();
    $conn->close();
}

// ============================================
// GET NOTIFICATION SETTINGS FOR USER
// ============================================

function getNotificationSettings($userId) {
    $conn = getDB();
    $stmt = $conn->prepare("
        SELECT preferences
        FROM users
        WHERE user_id = ?
    ");
    $stmt->bind_param("i", $userId);
    $stmt->execute();
    $result = $stmt->get_result();
    $user = $result->fetch_assoc();
    $stmt->close();
    $conn->close();
    
    if ($user && $user['preferences']) {
        $prefs = json_decode($user['preferences'], true);
        return [
            'sound_level' => $prefs['notification_sound'] ?? 'normal',
            'vibrate' => $prefs['vibrate'] ?? true,
            'led_color' => $prefs['led_color'] ?? 'blue'
        ];
    }
    
    return [
        'sound_level' => 'normal',
        'vibrate' => true,
        'led_color' => 'blue'
    ];
}

// ============================================
// CREATE ESCALATION MESSAGE (Makes it more urgent)
// ============================================

function createEscalationMessage($originalMessage, $escalationLevel) {
    $prefixes = [
        1 => '',
        2 => '⚠️ REMINDER: ',
        3 => '🔴 URGENT: ',
        4 => '🚨 VERY URGENT: ',
        5 => '❗❗ CRITICAL - ANSWER NOW: '
    ];
    
    $prefix = $prefixes[$escalationLevel] ?? $prefixes[5];
    return $prefix . $originalMessage;
}

// ============================================
// SEND NOTIFICATION TO ANDROID (Called by Android)
// ============================================

function getNextNotificationForDevice($userId) {
    $conn = getDB();
    $stmt = $conn->prepare("
        SELECT 
            notification_id,
            message_text,
            notification_type,
            priority_level,
            escalation_level,
            delivery_attempts
        FROM notification_queue
        WHERE user_id = ?
        AND status IN ('queued', 'sent')
        AND (expires_at IS NULL OR expires_at > NOW())
        AND scheduled_for <= NOW()
        ORDER BY priority_level DESC, escalation_level DESC
        LIMIT 1
    ");
    $stmt->bind_param("i", $userId);
    $stmt->execute();
    $result = $stmt->get_result();
    
    if ($result->num_rows > 0) {
        $notification = $result->fetch_assoc();
        
        // Enhance message based on escalation
        $notification['message_text'] = createEscalationMessage(
            $notification['message_text'],
            $notification['escalation_level']
        );
        
        // Get notification settings
        $notification['settings'] = getNotificationSettings($userId);
        
        // Mark as delivered
        $stmt->close();
        $updateStmt = $conn->prepare("
            UPDATE notification_queue
            SET status = 'delivered'
            WHERE notification_id = ?
        ");
        $updateStmt->bind_param("i", $notification['notification_id']);
        $updateStmt->execute();
        $updateStmt->close();
        $conn->close();
        
        return [
            'status' => 'success',
            'has_notification' => true,
            'notification' => $notification
        ];
    } else {
        $stmt->close();
        $conn->close();
        
        return [
            'status' => 'success',
            'has_notification' => false
        ];
    }
}

// ============================================
// CLEANUP EXPIRED NOTIFICATIONS
// ============================================

function cleanupExpiredNotifications() {
    $conn = getDB();
    $stmt = $conn->prepare("
        UPDATE notification_queue
        SET status = 'failed'
        WHERE status IN ('queued', 'sent', 'delivered')
        AND expires_at IS NOT NULL
        AND expires_at < NOW()
    ");
    $stmt->execute();
    $affected = $stmt->affected_rows;
    $stmt->close();
    $conn->close();
    
    return $affected;
}

// ============================================
// GET NOTIFICATION STATISTICS
// ============================================

function getNotificationStats($userId) {
    $conn = getDB();
    $stmt = $conn->prepare("
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN status = 'acknowledged' THEN 1 ELSE 0 END) as acknowledged,
            SUM(CASE WHEN status IN ('queued', 'sent', 'delivered') THEN 1 ELSE 0 END) as pending,
            AVG(TIMESTAMPDIFF(SECOND, sent_at, acknowledged_at)) as avg_response_time
        FROM notification_queue
        WHERE user_id = ?
        AND created_at > DATE_SUB(NOW(), INTERVAL 7 DAY)
    ");
    $stmt->bind_param("i", $userId);
    $stmt->execute();
    $result = $stmt->get_result();
    $stats = $result->fetch_assoc();
    $stmt->close();
    $conn->close();
    
    return $stats;
}

// ============================================
// MODULE 6 COMPLETE! ✅
// ============================================
?>