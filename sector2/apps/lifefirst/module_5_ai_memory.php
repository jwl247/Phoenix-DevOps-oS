<?php
/**
 * ============================================
 * MODULE 5: MEMORY KEEPER AI
 * WITH TEMPERATURE CONTROL
 * ============================================
 * 
 * DEPLOYMENT:
 * 1. Save as: ai_memory.php
 * 2. Upload to: /var/www/html/lifefirst/ai/ai_memory.php
 * 3. Add your Claude API key on line 29
 * 
 * FEATURES:
 * - Remember user preferences
 * - Learn from conversations
 * - Recall past interactions
 * - "What does Laurie like?" queries
 * - Temperature control for AI responses (0.0-1.0)
 * 
 * TEMPERATURE LEVELS:
 * - 0.0-0.3: Precise, factual (recall exact preferences)
 * - 0.4-0.6: Balanced (default, natural responses)
 * - 0.7-1.0: Creative, exploratory (suggestions)
 * ============================================
 */

// ============================================
// CONFIGURATION — credentials + model from config.php
// ============================================

require_once __DIR__ . '/config.php';

// Temperature presets
define('TEMP_PRECISE', 0.2);    // Exact recall
define('TEMP_BALANCED', 0.5);   // Natural conversation
define('TEMP_CREATIVE', 0.8);   // Suggestions & ideas

// ============================================
// MAIN HANDLER
// ============================================

function handleMemoryRequest($data) {
    $userId = $data['user_id'];
    $message = $data['message'];
    $action = $data['action'] ?? 'query';
    
    // Detect what user wants
    if (stripos($message, 'remember') !== false || stripos($message, 'save') !== false) {
        return storeMemory($userId, $message, $data);
    } elseif (stripos($message, 'forget') !== false || stripos($message, 'delete') !== false) {
        return forgetMemory($userId, $message);
    } elseif (stripos($message, 'what does') !== false || stripos($message, 'does ') !== false) {
        return recallPreference($userId, $message);
    } elseif (stripos($message, 'suggest') !== false || stripos($message, 'recommend') !== false) {
        return getSuggestions($userId, $message);
    } else {
        return queryMemory($userId, $message);
    }
}

// ============================================
// STORE MEMORY (Temperature: Precise)
// ============================================

function storeMemory($userId, $message, $data) {
    // Extract what to remember using Claude with low temperature (precise)
    $parsed = extractMemoryFromMessage($message, TEMP_PRECISE);
    
    if (!$parsed['success']) {
        return [
            'status' => 'error',
            'message' => 'Could not understand what to remember. Try: "Remember that I like dill pickles"'
        ];
    }
    
    $conn = getDB();
    
    // Check if this memory already exists
    $stmt = $conn->prepare("
        SELECT memory_id, memory_value 
        FROM memory_storage 
        WHERE user_id = ? 
        AND memory_key = ?
    ");
    $stmt->bind_param("is", $userId, $parsed['key']);
    $stmt->execute();
    $result = $stmt->get_result();
    
    if ($result->num_rows > 0) {
        // Update existing memory
        $existing = $result->fetch_assoc();
        $stmt->close();
        
        $stmt = $conn->prepare("
            UPDATE memory_storage 
            SET memory_value = ?, 
                last_accessed = NOW(),
                access_count = access_count + 1
            WHERE memory_id = ?
        ");
        $stmt->bind_param("si", $parsed['value'], $existing['memory_id']);
        $stmt->execute();
        $memoryId = $existing['memory_id'];
        
        $message_text = "Updated: " . $parsed['key'] . " = " . $parsed['value'];
    } else {
        // Create new memory
        $stmt->close();
        
        $stmt = $conn->prepare("
            INSERT INTO memory_storage 
            (user_id, memory_key, memory_value, memory_type, confidence, source)
            VALUES (?, ?, ?, ?, ?, 'user_stated')
        ");
        
        $stmt->bind_param(
            "isssd",
            $userId,
            $parsed['key'],
            $parsed['value'],
            $parsed['type'],
            $parsed['confidence']
        );
        $stmt->execute();
        $memoryId = $stmt->insert_id();
        
        $message_text = "Remembered: " . $parsed['key'] . " = " . $parsed['value'];
    }
    
    $stmt->close();
    $conn->close();
    
    return [
        'status' => 'success',
        'message' => $message_text,
        'memory_id' => $memoryId,
        'key' => $parsed['key'],
        'value' => $parsed['value']
    ];
}

// ============================================
// RECALL PREFERENCE (Temperature: Precise)
// ============================================

function recallPreference($userId, $message) {
    // Extract what they're asking about
    $query = extractQueryFromMessage($message);
    
    $conn = getDB();
    
    // Search for relevant memories
    $stmt = $conn->prepare("
        SELECT memory_key, memory_value, memory_type, confidence, last_accessed
        FROM memory_storage
        WHERE user_id = ?
        AND (
            memory_key LIKE ?
            OR memory_value LIKE ?
        )
        ORDER BY confidence DESC, last_accessed DESC
        LIMIT 5
    ");
    
    $searchTerm = "%{$query}%";
    $stmt->bind_param("iss", $userId, $searchTerm, $searchTerm);
    $stmt->execute();
    $result = $stmt->get_result();
    
    $memories = [];
    while ($row = $result->fetch_assoc()) {
        $memories[] = $row;
        
        // Update access count
        $updateStmt = $conn->prepare("
            UPDATE memory_storage 
            SET last_accessed = NOW(), 
                access_count = access_count + 1
            WHERE user_id = ? AND memory_key = ?
        ");
        $updateStmt->bind_param("is", $userId, $row['memory_key']);
        $updateStmt->execute();
        $updateStmt->close();
    }
    
    $stmt->close();
    $conn->close();
    
    if (empty($memories)) {
        return [
            'status' => 'success',
            'message' => "I don't have any memories about that. Would you like to tell me?",
            'memories' => [],
            'found' => false
        ];
    }
    
    // Build natural response using Claude with precise temperature
    $response = buildMemoryResponse($memories, $message, TEMP_PRECISE);
    
    return [
        'status' => 'success',
        'message' => $response,
        'memories' => $memories,
        'found' => true
    ];
}

// ============================================
// QUERY MEMORY (Temperature: Balanced)
// ============================================

function queryMemory($userId, $message) {
    $conn = getDB();
    
    // Get recent relevant memories
    $stmt = $conn->prepare("
        SELECT memory_key, memory_value, memory_type, confidence
        FROM memory_storage
        WHERE user_id = ?
        ORDER BY last_accessed DESC
        LIMIT 10
    ");
    $stmt->bind_param("i", $userId);
    $stmt->execute();
    $result = $stmt->get_result();
    
    $memories = [];
    while ($row = $result->fetch_assoc()) {
        $memories[] = $row;
    }
    $stmt->close();
    $conn->close();
    
    if (empty($memories)) {
        return [
            'status' => 'success',
            'message' => "I don't have any memories stored yet. Tell me things to remember!"
        ];
    }
    
    // Use Claude with balanced temperature for natural conversation
    $context = "User's known preferences:\n";
    foreach ($memories as $mem) {
        $context .= "- {$mem['memory_key']}: {$mem['memory_value']}\n";
    }
    
    $response = callClaudeAPI($message, $context, TEMP_BALANCED);
    
    return [
        'status' => 'success',
        'message' => $response,
        'memories_used' => count($memories)
    ];
}

// ============================================
// GET SUGGESTIONS (Temperature: Creative)
// ============================================

function getSuggestions($userId, $message) {
    $conn = getDB();
    
    // Get all user memories
    $stmt = $conn->prepare("
        SELECT memory_key, memory_value, memory_type
        FROM memory_storage
        WHERE user_id = ?
        ORDER BY confidence DESC, access_count DESC
    ");
    $stmt->bind_param("i", $userId);
    $stmt->execute();
    $result = $stmt->get_result();
    
    $memories = [];
    while ($row = $result->fetch_assoc()) {
        $memories[] = $row;
    }
    $stmt->close();
    $conn->close();
    
    if (empty($memories)) {
        return [
            'status' => 'success',
            'message' => "I don't know enough about your preferences yet to make suggestions. Tell me what you like!"
        ];
    }
    
    // Build context for creative suggestions
    $context = "User's preferences:\n";
    foreach ($memories as $mem) {
        $context .= "- {$mem['memory_key']}: {$mem['memory_value']}\n";
    }
    
    $prompt = "Based on these preferences, suggest something related to: " . $message;
    
    // Use HIGH temperature for creative suggestions
    $response = callClaudeAPI($prompt, $context, TEMP_CREATIVE);
    
    return [
        'status' => 'success',
        'message' => $response,
        'suggestion_type' => 'creative',
        'temperature_used' => TEMP_CREATIVE
    ];
}

// ============================================
// FORGET MEMORY
// ============================================

function forgetMemory($userId, $message) {
    // Extract what to forget
    $toForget = extractForgetFromMessage($message);
    
    $conn = getDB();
    $stmt = $conn->prepare("
        DELETE FROM memory_storage
        WHERE user_id = ?
        AND (
            memory_key LIKE ?
            OR memory_value LIKE ?
        )
    ");
    
    $searchTerm = "%{$toForget}%";
    $stmt->bind_param("iss", $userId, $searchTerm, $searchTerm);
    $stmt->execute();
    $deleted = $stmt->affected_rows;
    $stmt->close();
    $conn->close();
    
    if ($deleted > 0) {
        return [
            'status' => 'success',
            'message' => "Forgot {$deleted} memory/memories about {$toForget}",
            'deleted_count' => $deleted
        ];
    } else {
        return [
            'status' => 'success',
            'message' => "I didn't have any memories about that anyway",
            'deleted_count' => 0
        ];
    }
}

// ============================================
// LEARN FROM CONVERSATION (Background task)
// ============================================

function learnFromConversation($userId, $conversation) {
    // Analyze conversation for implicit preferences
    $learned = extractLearningsFromConversation($conversation);
    
    if (empty($learned)) {
        return ['learned' => 0];
    }
    
    $conn = getDB();
    $count = 0;
    
    foreach ($learned as $learning) {
        // Store as inferred memory (lower confidence)
        $stmt = $conn->prepare("
            INSERT INTO memory_storage 
            (user_id, memory_key, memory_value, memory_type, confidence, source)
            VALUES (?, ?, ?, ?, 0.7, 'inferred')
            ON DUPLICATE KEY UPDATE
                memory_value = VALUES(memory_value),
                confidence = GREATEST(confidence, 0.7)
        ");
        
        $stmt->bind_param(
            "isss",
            $userId,
            $learning['key'],
            $learning['value'],
            $learning['type']
        );
        $stmt->execute();
        $stmt->close();
        $count++;
    }
    
    $conn->close();
    
    return ['learned' => $count, 'items' => $learned];
}

// ============================================
// CLAUDE API INTEGRATION WITH TEMPERATURE
// ============================================

function callClaudeAPI($userMessage, $context = '', $temperature = TEMP_BALANCED) {
    if (CLAUDE_API_KEY === 'YOUR_CLAUDE_API_KEY_HERE') {
        return "ERROR: Claude API key not configured. Add your key to line 29 of ai_memory.php";
    }
    
    $systemPrompt = "You are a memory assistant. You help users remember and recall their preferences and past conversations. ";
    $systemPrompt .= "Be conversational and natural. Today is " . date('l, F j, Y') . ".";
    
    if ($context) {
        $systemPrompt .= "\n\n" . $context;
    }
    
    $payload = [
        'model' => CLAUDE_MODEL,
        'max_tokens' => 1024,
        'temperature' => $temperature,  // KEY FEATURE: Temperature control!
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
// HELPER: EXTRACT MEMORY FROM MESSAGE
// ============================================

function extractMemoryFromMessage($message, $temperature = TEMP_PRECISE) {
    // Use Claude to parse what to remember
    $prompt = "Extract a preference or fact to remember from this message.\n\n";
    $prompt .= "Message: \"$message\"\n\n";
    $prompt .= "Return ONLY a JSON object with these fields:\n";
    $prompt .= "{\n";
    $prompt .= '  "key": "short description of what this is about",'."\n";
    $prompt .= '  "value": "the actual preference or fact",'."\n";
    $prompt .= '  "type": "preference|fact|opinion",'."\n";
    $prompt .= '  "confidence": 0.0-1.0'."\n";
    $prompt .= "}\n\n";
    $prompt .= "Examples:\n";
    $prompt .= '"Remember I like dill pickles" -> {"key":"pickle_preference","value":"dill pickles","type":"preference","confidence":1.0}\n';
    $prompt .= '"I usually wake up at 6am" -> {"key":"wake_time","value":"6:00 AM","type":"fact","confidence":0.9}\n';
    
    $response = callClaudeAPI($prompt, '', $temperature);
    
    // Try to parse JSON
    $response = trim($response);
    $response = preg_replace('/```json|```/i', '', $response);
    $response = trim($response);
    
    $parsed = json_decode($response, true);
    
    if ($parsed && isset($parsed['key']) && isset($parsed['value'])) {
        return [
            'success' => true,
            'key' => $parsed['key'],
            'value' => $parsed['value'],
            'type' => $parsed['type'] ?? 'preference',
            'confidence' => $parsed['confidence'] ?? 0.8
        ];
    }
    
    return ['success' => false];
}

// ============================================
// HELPER: BUILD MEMORY RESPONSE
// ============================================

function buildMemoryResponse($memories, $originalQuestion, $temperature = TEMP_PRECISE) {
    $context = "Relevant memories found:\n";
    foreach ($memories as $mem) {
        $context .= "- {$mem['memory_key']}: {$mem['memory_value']} (confidence: {$mem['confidence']})\n";
    }
    
    $prompt = "Answer this question using the memories: \"$originalQuestion\"\n\n";
    $prompt .= "Be direct and factual. Don't say 'according to my memories' - just answer naturally.";
    
    return callClaudeAPI($prompt, $context, $temperature);
}

// ============================================
// HELPER: EXTRACT QUERY FROM MESSAGE
// ============================================

function extractQueryFromMessage($message) {
    // Simple extraction - remove common question words
    $query = strtolower($message);
    $query = preg_replace('/^(what does|does|do|is|are|when does|where does)\s+/i', '', $query);
    $query = preg_replace('/\s+(like|prefer|want|need)\?*$/i', '', $query);
    $query = trim($query);
    
    return $query;
}

// ============================================
// HELPER: EXTRACT FORGET FROM MESSAGE
// ============================================

function extractForgetFromMessage($message) {
    $toForget = preg_replace('/^(forget|delete|remove)\s+(that|about|the)?\s*/i', '', $message);
    $toForget = trim($toForget);
    return $toForget;
}

// ============================================
// HELPER: LEARN FROM CONVERSATION
// ============================================

function extractLearningsFromConversation($conversation) {
    // Use Claude with balanced temperature to find implicit preferences
    $prompt = "Analyze this conversation and extract any preferences or facts that should be remembered.\n\n";
    $prompt .= "Conversation:\n" . $conversation . "\n\n";
    $prompt .= "Return ONLY a JSON array of learnings. Each learning should have: key, value, type.\n";
    $prompt .= "Only include clear preferences or facts. Don't speculate.\n";
    $prompt .= "Example: [{\"key\":\"preferred_time\",\"value\":\"evening\",\"type\":\"preference\"}]";
    
    $response = callClaudeAPI($prompt, '', TEMP_BALANCED);
    
    // Clean and parse
    $response = trim($response);
    $response = preg_replace('/```json|```/i', '', $response);
    $response = trim($response);
    
    $learned = json_decode($response, true);
    
    return is_array($learned) ? $learned : [];
}

// ============================================
// GET ALL MEMORIES (For debugging/export)
// ============================================

function getAllMemories($userId) {
    $conn = getDB();
    $stmt = $conn->prepare("
        SELECT memory_key, memory_value, memory_type, confidence, 
               source, access_count, created_at, last_accessed
        FROM memory_storage
        WHERE user_id = ?
        ORDER BY confidence DESC, access_count DESC
    ");
    $stmt->bind_param("i", $userId);
    $stmt->execute();
    $result = $stmt->get_result();
    
    $memories = [];
    while ($row = $result->fetch_assoc()) {
        $memories[] = $row;
    }
    $stmt->close();
    $conn->close();
    
    return [
        'status' => 'success',
        'count' => count($memories),
        'memories' => $memories
    ];
}

// ============================================
// TEMPERATURE EXAMPLES
// ============================================

/*
TEMPERATURE USAGE EXAMPLES:

1. PRECISE (0.2) - For exact recall:
   "What pickles does Laurie like?"
   -> "Dill pickles" (exact, no creativity)

2. BALANCED (0.5) - For natural conversation:
   "What should I get Laurie?"
   -> "Based on her preferences, she likes dill pickles. 
       You could get her favorite brand."

3. CREATIVE (0.8) - For suggestions:
   "Suggest a gift for Laurie"
   -> "Since she loves dill pickles, how about a gourmet 
       pickle sampler set? Or a pickle-making kit so she 
       can make her own custom flavors?"
*/

// ============================================
// MODULE 5 COMPLETE WITH TEMPERATURE! ✅
// ============================================
?>
