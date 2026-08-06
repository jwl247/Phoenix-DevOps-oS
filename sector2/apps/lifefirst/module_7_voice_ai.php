<?php
/**
 * ============================================
 * MODULE 7: VOICE COMMANDER AI
 * General conversation handler + command fallback
 * ============================================
 *
 * DEPLOYMENT:
 * 1. Run deploy_lifefirst.sh on phoenix-ext
 * 2. Deployed to: /var/www/html/lifefirst/ai/ai_voice.php
 * 3. API key set via /etc/lifefirst/lifefirst.env (CLAUDE_API_KEY)
 *
 * FEATURES:
 * - General natural language conversation
 * - Command fallback when other AIs don't match
 * - Intent detection — routes to correct specialist AI
 * - "What time is it?", "Remind me...", open-ended queries
 * - Context-aware: knows who is asking (Jerry or Laurie)
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

function handleVoiceRequest($data) {
    $userId  = $data['user_id']  ?? null;
    $message = trim($data['message'] ?? '');
    $context = $data['context']  ?? [];   // optional prior-turn context

    if (!$userId || !$message) {
        return ['status' => 'error', 'message' => 'user_id and message required'];
    }

    $db = getDB();

    // Load user profile
    $stmt = $db->prepare("SELECT display_name, preferences, timezone FROM users WHERE user_id = ?");
    $stmt->bind_param('i', $userId);
    $stmt->execute();
    $user = $stmt->get_result()->fetch_assoc();
    $stmt->close();

    if (!$user) {
        $db->close();
        return ['status' => 'error', 'message' => 'User not found'];
    }

    $displayName = $user['display_name'];
    $timezone    = $user['timezone'] ?? 'America/Chicago';
    $nowLocal    = (new DateTime('now', new DateTimeZone($timezone)))->format('l, F j Y g:i A T');

    // Detect likely intent so the caller can route to specialist if desired
    $intent = detectIntent($message);

    // Build system prompt
    $system = <<<PROMPT
You are the Life First Voice Commander, a personal AI assistant for {$displayName}.
Current time: {$nowLocal}.

You handle open-ended questions and general conversation. When a request clearly belongs to a specialist:
- Schedule questions → tell the user you're checking the calendar
- "Ask Laurie" / "Tell Jerry" messages → tell the user you're relaying it
- Reminder / notification requests → tell the user you're setting it up
- Memory / preference questions → tell the user you're checking memories

Keep replies short and natural — these are spoken or glanced on a phone screen.
Never make up facts. If you don't know something, say so plainly.
PROMPT;

    $messages = [];

    // Inject up to 4 prior turns of context if provided
    if (!empty($context)) {
        foreach (array_slice($context, -4) as $turn) {
            if (isset($turn['role'], $turn['content'])) {
                $messages[] = ['role' => $turn['role'], 'content' => $turn['content']];
            }
        }
    }

    $messages[] = ['role' => 'user', 'content' => $message];

    // Pick model size by intent — memory gets the large model, voice gets medium
    $model    = ollamaModelForIntent($intent);

    // Try Ollama first (local, zero cost, paged-vRAM handles big models), fall back to Claude
    $response = callOllama($system, $messages, $model);
    if (isset($response['error'])) {
        $response = callClaude($system, $messages);
        $response['source'] = 'claude';
    }

    // Log interaction
    $aiResponse = $response['content'] ?? 'No response';
    $logStmt = $db->prepare("
        INSERT INTO ai_interactions (user_id, ai_module, user_message, ai_response, intent, created_at)
        VALUES (?, 'voice_commander', ?, ?, ?, NOW())
    ");
    if ($logStmt) {
        $logStmt->bind_param('isss', $userId, $message, $aiResponse, $intent);
        $logStmt->execute();
        $logStmt->close();
    }

    $db->close();

    return [
        'status'   => 'ok',
        'module'   => 'voice_commander',
        'intent'   => $intent,
        'response' => $aiResponse,
        'user'     => $displayName,
        'ai'       => $response['source'] ?? 'ollama',
    ];
}

// ============================================
// INTENT DETECTION
// Simple keyword-based classifier so the API router
// can decide whether to re-route to a specialist AI.
// ============================================

function detectIntent($message) {
    $msg = strtolower($message);

    $patterns = [
        'schedule'     => ['schedule', 'calendar', 'appointment', 'meeting', 'free', 'busy', 'available', 'block time', 'am i free', 'what time', 'remind me at', 'set a reminder'],
        'messenger'    => ['ask laurie', 'ask jerry', 'tell laurie', 'tell jerry', 'what does laurie', 'what does jerry', 'relay', 'message'],
        'memory'       => ['remember', 'preference', 'what does', 'what did', 'last time', 'favorite', 'usually', 'likes', 'hates', 'recall', 'forget'],
        'notification' => ['remind me', 'alert', 'notify', 'don\'t let me forget', 'ping me', 'notification'],
    ];

    foreach ($patterns as $intent => $keywords) {
        foreach ($keywords as $kw) {
            if (str_contains($msg, $kw)) {
                return $intent;
            }
        }
    }

    return 'general';
}

// ============================================
// CLAUDE API CALL
// ============================================

function callClaude($system, $messages) {
    if (empty(CLAUDE_API_KEY)) {
        return ['error' => 'Claude API key not configured'];
    }

    $payload = json_encode([
        'model'      => CLAUDE_MODEL,
        'max_tokens' => 512,
        'system'     => $system,
        'messages'   => $messages,
    ]);

    $ch = curl_init('https://api.anthropic.com/v1/messages');
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_POST           => true,
        CURLOPT_POSTFIELDS     => $payload,
        CURLOPT_HTTPHEADER     => [
            'Content-Type: application/json',
            'x-api-key: ' . CLAUDE_API_KEY,
            'anthropic-version: 2023-06-01',
        ],
        CURLOPT_TIMEOUT        => 30,
    ]);

    $raw    = curl_exec($ch);
    $status = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    if ($status !== 200) {
        return ['error' => 'Claude API error', 'status' => $status];
    }

    $decoded = json_decode($raw, true);
    return [
        'content' => $decoded['content'][0]['text'] ?? '',
        'usage'   => $decoded['usage'] ?? [],
    ];
}

// ============================================
// ENTRY POINT
// ============================================

$data = json_decode(file_get_contents('php://input'), true) ?? [];
echo json_encode(handleVoiceRequest($data));
