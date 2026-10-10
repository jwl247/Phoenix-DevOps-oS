<?php
/**
 * ============================================
 * MODULE 4: CROSS-PHONE MESSENGER AI
 * Handles questions between you and Laurie
 * ============================================
 * 
 * DEPLOYMENT:
 * 1. Run deploy_lifefirst.sh on phoenix-ext
 * 2. Deployed to: /var/www/html/lifefirst/ai/ai_messenger.php
 * 3. API key set via /etc/lifefirst/lifefirst.env (CLAUDE_API_KEY)
 * 
 * FEATURES:
 * - Ask questions to other person
 * - Send urgent notifications
 * - Get answers back automatically
 * - "What pickles does Laurie want?" workflow
 * 
 * ============================================
 */

// ============================================
// CONFIGURATION — credentials + model from config.php
// ============================================

require_once __DIR__ . '/config.php';

// ============================================
// MAIN HANDLER
// ============================================

function handleMessengerRequest($data) {
    $userId = $data['user_id'];
    $username = $data['username'];
    $message = $data['message'];
    $action = $data['action'] ?? 'ask';
    
    // Determine action
    if ($action === 'answer') {
        return answerQuestion($userId, $data);
    } elseif ($action === 'check') {
        return checkForQuestions($userId);
    } else {
        return askOtherPerson($userId, $username, $message);
    }
}

// ============================================
// ASK OTHER PERSON A QUESTION
// ============================================

function askOtherPerson($fromUserId, $fromUsername, $message) {
    // Determine who to ask
    $otherUserId = ($fromUserId == 1) ? 2 : 1;
    
    // Get other person's name
    $conn = getDB();
    $stmt = $conn->prepare("SELECT display_name FROM users WHERE user_id = ?");
    $stmt->bind_param("i", $otherUserId);
    $stmt->execute();
    $result = $stmt->get_result();
    $otherUser = $result->fetch_assoc();
    $stmt->close();
    
    $otherName = $otherUser['display_name'];
    
    // Parse the question using Claude
    $parsedQuestion = parseQuestion($message, $fromUsername, $otherName);
    
    // Create pending message
    $stmt = $conn->prepare("
        INSERT INTO pending_messages 
        (from_user_id, to_user_id, question, message_type, priority, status, expires_at)
        VALUES (?, ?, ?, 'question', 'must_answer', 'pending', DATE_ADD(NOW(), INTERVAL 1 HOUR))
    ");
    $stmt->bind_param("iis", $fromUserId, $otherUserId, $parsedQuestion['question']);
    
    if ($stmt->execute()) {
        $messageId = $stmt->insert_id;
        $stmt->close();
        
        // Create notification for other person
        createNotificationForQuestion($messageId, $otherUserId, $parsedQuestion['question']);
        
        $conn->close();
        
        return [
            'status' => 'success',
            'message' => "Question sent to $otherName! You'll get the answer shortly.",
            'question_sent' => $parsedQuestion['question'],
            'to_user' => $otherName,
            'message_id' => $messageId,
            'notification_created' => true
        ];
    } else {
        $error = $stmt->error;
        $stmt->close();
        $conn->close();
        
        return [
            'status' => 'error',
            'message' => 'Failed to send question: ' . $error
        ];
    }
}

// ============================================
// ANSWER A QUESTION
// ============================================

function answerQuestion($userId, $data) {
    $answer = $data['raw_data']['answer'] ?? $data['message'];
    $messageId = $data['raw_data']['message_id'] ?? null;
    
    if (!$messageId) {
        return [
            'status' => 'error',
            'message' => 'No message ID provided'
        ];
    }
    
    $conn = getDB();
    
    // Update the message with answer
    $stmt = $conn->prepare("
        UPDATE pending_messages 
        SET answer = ?, status = 'answered', answered_at = NOW()
        WHERE message_id = ? AND to_user_id = ?
    ");
    $stmt->bind_param("sii", $answer, $messageId, $userId);
    
    if ($stmt->execute() && $stmt->affected_rows > 0) {
        $stmt->close();
        
        // Get the original question details
        $stmt = $conn->prepare("
            SELECT pm.question, pm.from_user_id, u.display_name
            FROM pending_messages pm
            JOIN users u ON pm.from_user_id = u.user_id
            WHERE pm.message_id = ?
        ");
        $stmt->bind_param("i", $messageId);
        $stmt->execute();
        $result = $stmt->get_result();
        $questionData = $result->fetch_assoc();
        $stmt->close();
        
        // Notify the original asker
        notifyWithAnswer($questionData['from_user_id'], $questionData['question'], $answer);
        
        $conn->close();
        
        return [
            'status' => 'success',
            'message' => "Answer sent to " . $questionData['display_name'],
            'question' => $questionData['question'],
            'answer' => $answer
        ];
    } else {
        $stmt->close();
        $conn->close();
        
        return [
            'status' => 'error',
            'message' => 'Question not found or already answered'
        ];
    }
}

// ============================================
// CHECK FOR PENDING QUESTIONS
// ============================================

function checkForQuestions($userId) {
    $conn = getDB();
    $stmt = $conn->prepare("
        SELECT 
            pm.message_id,
            pm.question,
            pm.priority,
            pm.created_at,
            u.display_name as from_user
        FROM pending_messages pm
        JOIN users u ON pm.from_user_id = u.user_id
        WHERE pm.to_user_id = ?
        AND pm.status = 'pending'
        ORDER BY pm.priority DESC, pm.created_at ASC
    ");
    $stmt->bind_param("i", $userId);
    $stmt->execute();
    $result = $stmt->get_result();
    
    $questions = [];
    while ($row = $result->fetch_assoc()) {
        $questions[] = $row;
    }
    $stmt->close();
    $conn->close();
    
    if (empty($questions)) {
        return [
            'status' => 'success',
            'has_questions' => false,
            'message' => 'No pending questions',
            'questions' => []
        ];
    } else {
        return [
            'status' => 'success',
            'has_questions' => true,
            'count' => count($questions),
            'message' => "You have " . count($questions) . " question(s) waiting",
            'questions' => $questions
        ];
    }
}

// ============================================
// CREATE NOTIFICATION FOR QUESTION
// ============================================

function createNotificationForQuestion($messageId, $toUserId, $question) {
    $conn = getDB();
    $stmt = $conn->prepare("
        INSERT INTO notification_queue
        (user_id, message_text, notification_type, priority_level, related_message_id, max_escalation)
        VALUES (?, ?, 'must_answer', 10, ?, 5)
    ");
    
    $notificationText = "QUESTION: " . $question . "\n\nPlease answer!";
    $stmt->bind_param("isi", $toUserId, $notificationText, $messageId);
    $stmt->execute();
    $stmt->close();
    $conn->close();
}

// ============================================
// NOTIFY WITH ANSWER
// ============================================

function notifyWithAnswer($toUserId, $question, $answer) {
    $conn = getDB();
    $stmt = $conn->prepare("
        INSERT INTO notification_queue
        (user_id, message_text, notification_type, priority_level)
        VALUES (?, ?, 'info', 5)
    ");
    
    $notificationText = "ANSWER to: \"$question\"\n\n$answer";
    $stmt->bind_param("is", $toUserId, $notificationText);
    $stmt->execute();
    $stmt->close();
    $conn->close();
}

// ============================================
// PARSE QUESTION USING CLAUDE AI
// ============================================

function parseQuestion($message, $fromName, $toName) {
    if (CLAUDE_API_KEY === 'YOUR_CLAUDE_API_KEY_HERE') {
        // Fallback if no API key
        $cleanQuestion = str_replace(['ask laurie', 'ask you', 'does laurie', 'do you'], '', strtolower($message));
        $cleanQuestion = ucfirst(trim($cleanQuestion));
        return ['question' => $cleanQuestion];
    }
    
    $systemPrompt = "You are helping format questions between two people. Extract the core question from the message and make it clear and direct. Remove phrases like 'ask Laurie' or 'tell them'. Just return the question itself.";
    
    $payload = [
        'model' => CLAUDE_MODEL,
        'max_tokens' => 256,
        'messages' => [
            [
                'role' => 'user',
                'content' => "$systemPrompt\n\nOriginal message from $fromName: \"$message\"\n\nExtract the question to ask $toName:"
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
    
    if ($httpCode === 200) {
        $data = json_decode($response, true);
        $question = $data['content'][0]['text'] ?? $message;
    } else {
        $question = $message;
    }
    
    return ['question' => $question];
}

// ============================================
// GET CONVERSATION HISTORY (for context)
// ============================================

function getRecentConversations($userId, $limit = 5) {
    $conn = getDB();
    $stmt = $conn->prepare("
        SELECT question, answer, created_at, answered_at
        FROM pending_messages
        WHERE (from_user_id = ? OR to_user_id = ?)
        AND status = 'answered'
        ORDER BY answered_at DESC
        LIMIT ?
    ");
    $stmt->bind_param("iii", $userId, $userId, $limit);
    $stmt->execute();
    $result = $stmt->get_result();
    
    $history = [];
    while ($row = $result->fetch_assoc()) {
        $history[] = $row;
    }
    $stmt->close();
    $conn->close();
    
    return $history;
}

// ============================================
// CLEANUP EXPIRED QUESTIONS
// ============================================

function cleanupExpiredQuestions() {
    $conn = getDB();
    $stmt = $conn->prepare("
        UPDATE pending_messages 
        SET status = 'expired'
        WHERE status = 'pending'
        AND expires_at < NOW()
    ");
    $stmt->execute();
    $affected = $stmt->affected_rows;
    $stmt->close();
    $conn->close();
    
    return $affected;
}

// ============================================
// MODULE 4 COMPLETE! ✅
// ============================================
?>