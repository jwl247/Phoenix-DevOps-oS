<?php
/**
 * Life First — Shared Config
 * Reads credentials from environment. Never hardcode secrets here.
 *
 * On phoenix-ext, set via /etc/lifefirst/lifefirst.env (loaded by Apache SetEnv
 * directives in /etc/apache2/sites-available/lifefirst.conf).
 *
 * For Frank dispatch, the same env vars must be exported before calling PHP.
 */

if (!defined('CLAUDE_API_KEY')) {
    define('CLAUDE_API_KEY', getenv('CLAUDE_API_KEY') ?: '');
}
if (!defined('CLAUDE_MODEL')) {
    define('CLAUDE_MODEL', 'claude-sonnet-4-6');
}

// Ollama self-hosted AI — primary for Life First, no API cost, no data egress
if (!defined('OLLAMA_URL')) {
    define('OLLAMA_URL', getenv('OLLAMA_URL') ?: 'http://localhost:11434');
}
if (!defined('OLLAMA_MODEL_LIFEFIRST')) {
    define('OLLAMA_MODEL_LIFEFIRST', getenv('OLLAMA_MODEL_LIFEFIRST') ?: 'llama3.1');
}

if (!function_exists('ollamaModelForIntent')) {
    /**
     * Pick the right model size for the given AI intent.
     * Phoenix LLM engine handles paged-vRAM so large models run even on
     * constrained hardware — this just sets the preference.
     *
     * @param string $intent  schedule|messenger|memory|notification|voice|general
     * @return string  Ollama model name
     */
    function ollamaModelForIntent(string $intent): string {
        $map = [
            'memory'       => OLLAMA_MODEL_LARGE,   // deep recall needs the big model
            'schedule'     => OLLAMA_MODEL_MEDIUM,
            'messenger'    => OLLAMA_MODEL_MEDIUM,
            'voice'        => OLLAMA_MODEL_MEDIUM,
            'notification' => OLLAMA_MODEL_SMALL,
            'general'      => OLLAMA_MODEL_SMALL,
        ];
        return $map[$intent] ?? OLLAMA_MODEL_MEDIUM;
    }
}

if (!function_exists('callOllama')) {
    /**
     * Call Ollama /api/generate.
     * Falls back down the model size ladder automatically if the preferred
     * model is not available (Phoenix paged-vRAM handles oversized models).
     *
     * @param string $system    System prompt
     * @param array  $messages  Conversation turns [{role, content}]
     * @param string $model     Model name (use ollamaModelForIntent() for auto-select)
     * @param int    $maxTokens Max tokens to generate (default 1024)
     * @return array  {content: string, source: 'ollama'} | {error: string}
     */
    function callOllama(string $system, array $messages, string $model = OLLAMA_MODEL_LIFEFIRST, int $maxTokens = 1024): array {
        $context = '';
        foreach (array_slice($messages, 0, -1) as $turn) {
            $role = $turn['role'] === 'assistant' ? 'Assistant' : 'User';
            $context .= "{$role}: {$turn['content']}\n";
        }
        $prompt = end($messages)['content'] ?? '';
        if ($context) {
            $prompt = $context . "User: " . $prompt;
        }

        $payload = json_encode([
            'model'  => $model,
            'prompt' => $prompt,
            'system' => $system,
            'stream' => false,
            'options' => ['temperature' => 0.7, 'num_predict' => $maxTokens],
        ]);

        // Timeout scales with model size — large models need more time to generate
        $timeoutSec = str_contains($model, '70b') ? 300 :
                      (str_contains($model, '8b')  ? 120 : 60);

        $ch = curl_init(OLLAMA_URL . '/api/generate');
        curl_setopt_array($ch, [
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_POST           => true,
            CURLOPT_POSTFIELDS     => $payload,
            CURLOPT_HTTPHEADER     => ['Content-Type: application/json'],
            CURLOPT_TIMEOUT        => $timeoutSec,
            CURLOPT_CONNECTTIMEOUT => 5,
        ]);

        $raw    = curl_exec($ch);
        $status = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        $err    = curl_error($ch);
        curl_close($ch);

        if ($err || $status !== 200) {
            // Try one step down the ladder before giving up
            $fallback = ($model === OLLAMA_MODEL_LARGE)  ? OLLAMA_MODEL_MEDIUM :
                        (($model === OLLAMA_MODEL_MEDIUM) ? OLLAMA_MODEL_SMALL : null);
            if ($fallback && $fallback !== $model) {
                return callOllama($system, $messages, $fallback, $maxTokens);
            }
            return ['error' => $err ?: "Ollama HTTP {$status}", 'model' => $model];
        }

        $data = json_decode($raw, true);
        return ['content' => $data['response'] ?? '', 'source' => 'ollama', 'model' => $model];
    }
}

if (!function_exists('getDB')) {
    function getDB() {
        $host = getenv('LF_DB_HOST') ?: 'localhost';
        $user = getenv('LF_DB_USER') ?: 'lifefirst';
        $pass = getenv('LF_DB_PASS') ?: '';
        $name = getenv('LF_DB_NAME') ?: 'lifefirst';
        $conn = new mysqli($host, $user, $pass, $name);
        if ($conn->connect_error) {
            die(json_encode(['status' => 'error', 'message' => 'Database connection failed']));
        }
        $conn->set_charset('utf8mb4');
        return $conn;
    }
}
