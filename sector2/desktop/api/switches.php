<?php
/**
 * switches.php — Phoenix Switches & Settings API
 * GET  /desktop/api/switches.php          → all switch states + dropdown options
 * POST /desktop/api/switches.php          → set a switch or dropdown value
 * POST /desktop/api/switches.php?action=X → fire a one-shot action button
 *
 * Settings stored in /var/phoenix/settings.json
 * Service toggles delegate to service.php
 * Phoenix DevOps OS | jwl247 | GPL v3
 */

header('Content-Type: application/json');
header('X-Content-Type-Options: nosniff');

$SETTINGS_FILE  = '/var/phoenix/settings.json';
$AUDIT_LOG      = '/var/log/phoenix/audit.log';
$GUARDIAN_URL   = 'http://127.0.0.1:7781';
$FRANK_HTTP     = 'http://127.0.0.1:7347';
$OLLAMA_URL     = 'http://127.0.0.1:11434';

// ── Load / save settings ──────────────────────────────────────────────────────
function load_settings(string $file): array {
    if (!file_exists($file)) return default_settings();
    $data = json_decode(file_get_contents($file), true);
    return is_array($data) ? array_merge(default_settings(), $data) : default_settings();
}

function save_settings(array $settings, string $file): void {
    @mkdir(dirname($file), 0755, true);
    file_put_contents($file, json_encode($settings, JSON_PRETTY_PRINT));
}

function default_settings(): array {
    return [
        // Toggles
        'ai_suggestions'      => true,
        'auto_forge'          => false,
        'index_new_docs'      => true,
        'lifefirst_security'  => true,
        'full_audit_log'      => false,
        'quadralingual_vault' => true,
        'witness_required'    => false,
        'bounce_armed'        => false,
        // Dropdowns
        'ollama_model'        => 'llama3.2:3b',
        'lockdown_level'      => 'high',
        'buffer_sensitivity'  => 'standard',
        'threat_response'     => 'auto-block',
    ];
}

// ── Switch definitions ────────────────────────────────────────────────────────
$SWITCHES = [
    'ai_suggestions'      => ['label' => 'AI Suggestions',      'group' => 'ai',       'action' => 'setting'],
    'auto_forge'          => ['label' => 'Auto-Forge',           'group' => 'docs',     'action' => 'setting'],
    'index_new_docs'      => ['label' => 'Index New Docs',       'group' => 'docs',     'action' => 'setting'],
    'lifefirst_security'  => ['label' => 'Life First Security',  'group' => 'security', 'action' => 'setting'],
    'full_audit_log'      => ['label' => 'Full Audit Log',       'group' => 'security', 'action' => 'setting'],
    'quadralingual_vault' => ['label' => 'Quadralingual Vault',  'group' => 'core',     'action' => 'setting'],
    'witness_required'    => ['label' => 'Witness Required',     'group' => 'docs',     'action' => 'setting'],
    'bounce_armed'        => ['label' => 'Bounce Armed',         'group' => 'security', 'action' => 'bounce_arm'],
];

// ── Dropdown definitions ──────────────────────────────────────────────────────
$DROPDOWNS = [
    'ollama_model' => [
        'label'   => 'Ollama Model',
        'group'   => 'ai',
        'options' => ['llama3.1', 'llama3.2:3b', 'deepseek-r1:1.5b', 'phi3.5'],
    ],
    'lockdown_level' => [
        'label'   => 'Lockdown Level',
        'group'   => 'security',
        'options' => ['basic', 'high', 'critical', 'immutable'],
    ],
    'buffer_sensitivity' => [
        'label'   => 'Buffer Sensitivity',
        'group'   => 'security',
        'options' => ['standard', 'elevated', 'paranoid'],
    ],
    'threat_response' => [
        'label'   => 'Threat Response',
        'group'   => 'security',
        'options' => ['log-only', 'auto-block', 'full-lockdown'],
    ],
];

// ── One-shot action buttons ───────────────────────────────────────────────────
function run_action(string $action, string $audit_log, string $guardian_url, string $frank_http): array {
    switch ($action) {
        case 'guardian_scan':
            $out = shell_exec('python3 /opt/phoenix/guardian.py scan 2>&1') ?? '';
            return ['ok' => true, 'action' => 'guardian_scan', 'out' => trim($out)];

        case 'guardian_conflicts':
            $out = shell_exec('python3 /opt/phoenix/guardian.py conflicts 2>&1') ?? '';
            return ['ok' => true, 'action' => 'guardian_conflicts', 'out' => trim($out)];

        case 'clear_audit_log':
            file_put_contents($audit_log, '');
            return ['ok' => true, 'action' => 'clear_audit_log'];

        case 'frank_heartbeat':
            $ctx = stream_context_create(['http' => ['method' => 'POST', 'timeout' => 5,
                'header' => 'Content-Type: application/json', 'content' => '{}']]);
            @file_get_contents("$frank_http/heartbeat", false, $ctx);
            return ['ok' => true, 'action' => 'frank_heartbeat'];

        case 'reload_apache':
            $r = shell_exec('sudo systemctl reload apache2 2>&1') ?? '';
            return ['ok' => true, 'action' => 'reload_apache', 'out' => trim($r)];

        case 'reload_wireguard':
            $r = shell_exec('sudo systemctl restart wg-quick@wg0 2>&1') ?? '';
            return ['ok' => true, 'action' => 'reload_wireguard', 'out' => trim($r)];

        case 'pull_ollama_model':
            // Non-blocking pull — starts in background
            $model = $_POST['model'] ?? 'phi3.5';
            $safe  = escapeshellarg($model);
            shell_exec("nohup ollama pull $safe > /tmp/ollama_pull.log 2>&1 &");
            return ['ok' => true, 'action' => 'pull_ollama_model', 'model' => $model, 'note' => 'Pull started in background'];

        case 'security_status':
            $ctx = stream_context_create(['http' => ['method' => 'GET', 'timeout' => 3]]);
            $raw = @file_get_contents("$guardian_url/status", false, $ctx);
            return ['ok' => true, 'action' => 'security_status', 'guardian' => $raw ? json_decode($raw, true) : null];

        default:
            return ['ok' => false, 'error' => "unknown action: $action"];
    }
}

// ── Apply switch side-effect ──────────────────────────────────────────────────
function apply_switch_action(string $key, bool $value, string $frank_http): void {
    switch ($key) {
        case 'bounce_armed':
            // Notify security stack — it reads settings.json directly
            $ctx = stream_context_create(['http' => ['method' => 'POST', 'timeout' => 3,
                'header' => 'Content-Type: application/json',
                'content' => json_encode(['bounce_armed' => $value])]]);
            @file_get_contents("$frank_http/security/bounce", false, $ctx);
            break;
        case 'full_audit_log':
            $ctx = stream_context_create(['http' => ['method' => 'POST', 'timeout' => 3,
                'header' => 'Content-Type: application/json',
                'content' => json_encode(['verbose' => $value])]]);
            @file_get_contents("$frank_http/audit/verbose", false, $ctx);
            break;
    }
}

// ── Route ─────────────────────────────────────────────────────────────────────
$method   = $_SERVER['REQUEST_METHOD'];
$settings = load_settings($SETTINGS_FILE);

// One-shot action
if ($method === 'POST' && isset($_GET['action'])) {
    $result = run_action($_GET['action'], $AUDIT_LOG, $GUARDIAN_URL, $FRANK_HTTP);
    $line   = json_encode(['ts' => date('c'), 'op' => 'switch_action', 'action' => $_GET['action']]);
    @file_put_contents($AUDIT_LOG, $line . "\n", FILE_APPEND);
    echo json_encode($result);
    exit;
}

// GET — return all states + options
if ($method === 'GET') {
    $switches_out  = [];
    foreach ($SWITCHES as $key => $def) {
        $switches_out[] = array_merge($def, ['key' => $key, 'value' => (bool)($settings[$key] ?? false)]);
    }
    $dropdowns_out = [];
    foreach ($DROPDOWNS as $key => $def) {
        $dropdowns_out[] = array_merge($def, ['key' => $key, 'value' => $settings[$key] ?? $def['options'][0]]);
    }
    echo json_encode(['ok' => true, 'switches' => $switches_out, 'dropdowns' => $dropdowns_out]);
    exit;
}

// POST — set switch or dropdown value
if ($method === 'POST') {
    $body = json_decode(file_get_contents('php://input'), true) ?? [];
    $key  = trim($body['key']  ?? '');
    $val  = $body['value'] ?? null;

    if (!$key) { http_response_code(400); echo json_encode(['error' => 'missing key']); exit; }

    if (isset($SWITCHES[$key])) {
        $settings[$key] = (bool)$val;
        apply_switch_action($key, (bool)$val, $FRANK_HTTP);
    } elseif (isset($DROPDOWNS[$key])) {
        $allowed = $DROPDOWNS[$key]['options'];
        if (!in_array($val, $allowed, true)) {
            http_response_code(400); echo json_encode(['error' => "invalid value for $key"]); exit;
        }
        $settings[$key] = $val;
    } else {
        http_response_code(400); echo json_encode(['error' => "unknown key: $key"]); exit;
    }

    save_settings($settings, $SETTINGS_FILE);
    $line = json_encode(['ts' => date('c'), 'op' => 'switch_set', 'key' => $key, 'value' => $val]);
    @file_put_contents($AUDIT_LOG, $line . "\n", FILE_APPEND);

    echo json_encode(['ok' => true, 'key' => $key, 'value' => $settings[$key]]);
    exit;
}

http_response_code(405);
echo json_encode(['error' => 'method not allowed']);
