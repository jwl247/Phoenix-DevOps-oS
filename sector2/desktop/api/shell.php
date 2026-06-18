<?php
/**
 * shell.php — Global Shell API
 * Executes a shell command on phoenix-ext and returns stdout + stderr.
 * Called by the Global Shell toggle (backtick/F12) in index.php.
 *
 * POST { cmd: string }  →  { ok, out, err, exit_code }
 *
 * Safety:
 *  - Requires PHOENIX_AUTH header match
 *  - Blocklist of destructive patterns
 *  - 30s timeout, 256KB output cap
 *  - All commands logged to /var/log/phoenix/shell.log
 *
 * Phoenix DevOps OS | jwl247 | GPL v3
 */

header('Content-Type: application/json');
header('X-Content-Type-Options: nosniff');
header('Cache-Control: no-store');

$PHOENIX_AUTH = getenv('PHOENIX_AUTH') ?: '';
$SHELL_LOG    = '/var/log/phoenix/shell.log';
$TIMEOUT      = 30;
$MAX_BYTES    = 256 * 1024;

// ── Auth ──────────────────────────────────────────────────────────────────────
// Allow same-origin (no auth header needed) but require token when present.
$sent_auth = $_SERVER['HTTP_X_PHOENIX_AUTH'] ?? '';
if ($sent_auth && $PHOENIX_AUTH && $sent_auth !== $PHOENIX_AUTH) {
    http_response_code(403);
    echo json_encode(['error' => 'unauthorized']);
    exit;
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['error' => 'POST only']);
    exit;
}

$body = json_decode(file_get_contents('php://input'), true) ?? [];
$cmd  = trim($body['cmd'] ?? '');

if (!$cmd || strlen($cmd) > 1024) {
    http_response_code(400);
    echo json_encode(['error' => 'missing or oversized cmd']);
    exit;
}

// ── Blocklist — patterns that must never execute ──────────────────────────────
$BLOCKLIST = [
    '/rm\s+-rf\s+\//',           // rm -rf /
    '/mkfs/',                     // format
    '/dd\s+if=.*of=\/dev/',      // dd wipe
    '/>\s*\/dev\/[sh]d[a-z]/',   // overwrite block device
    '/shred\s+.*\/dev/',
    '/chmod\s+-R\s+000\s+\//',
    '/:\(\)\s*\{/',              // fork bomb
];
foreach ($BLOCKLIST as $pattern) {
    if (preg_match($pattern, $cmd)) {
        audit($SHELL_LOG, $cmd, 'BLOCKED', 0);
        http_response_code(403);
        echo json_encode(['error' => 'command blocked by Phoenix shell policy', 'out' => '', 'err' => '']);
        exit;
    }
}

// ── Execute ───────────────────────────────────────────────────────────────────
$desc = [
    0 => ['pipe', 'r'],
    1 => ['pipe', 'w'],
    2 => ['pipe', 'w'],
];

// Run as the www-data user — same user Apache runs as.
// PATH includes /usr/local/sbin and /opt/phoenix so Phoenix tools are reachable.
$env = [
    'PATH'  => '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/opt/phoenix',
    'HOME'  => '/var/www',
    'SHELL' => '/bin/bash',
];

$proc = proc_open("bash -c " . escapeshellarg($cmd), $desc, $pipes, '/tmp', $env);

if (!is_resource($proc)) {
    audit($SHELL_LOG, $cmd, 'FAILED', -1);
    echo json_encode(['ok' => false, 'out' => '', 'err' => 'proc_open failed', 'exit_code' => -1]);
    exit;
}

fclose($pipes[0]);

// Non-blocking read with timeout
stream_set_blocking($pipes[1], false);
stream_set_blocking($pipes[2], false);

$out     = '';
$err     = '';
$start   = microtime(true);
$running = true;

while ($running) {
    $elapsed = microtime(true) - $start;
    if ($elapsed > $TIMEOUT) {
        proc_terminate($proc, 15);
        $err .= "\n[shell: timeout after {$TIMEOUT}s]";
        break;
    }

    $status = proc_get_status($proc);
    if (!$status['running']) $running = false;

    $chunk = fread($pipes[1], 8192);
    if ($chunk !== false) $out .= $chunk;
    $chunk = fread($pipes[2], 8192);
    if ($chunk !== false) $err .= $chunk;

    if (strlen($out) + strlen($err) > $MAX_BYTES) {
        proc_terminate($proc, 15);
        $out = substr($out, 0, $MAX_BYTES);
        $err .= "\n[shell: output truncated at {$MAX_BYTES}B]";
        break;
    }

    if ($running) usleep(50000); // 50ms poll
}

// Drain any remaining
$out .= stream_get_contents($pipes[1]);
$err .= stream_get_contents($pipes[2]);
fclose($pipes[1]);
fclose($pipes[2]);

$exit_code = proc_close($proc);

audit($SHELL_LOG, $cmd, $exit_code === 0 ? 'OK' : "EXIT:$exit_code", $exit_code);

echo json_encode([
    'ok'        => $exit_code === 0,
    'out'       => $out,
    'err'       => $err,
    'exit_code' => $exit_code,
]);

// ── Audit log ─────────────────────────────────────────────────────────────────
function audit(string $log, string $cmd, string $result, int $code): void {
    @mkdir(dirname($log), 0755, true);
    $ts   = date('Y-m-d H:i:s');
    $user = get_current_user();
    $ip   = $_SERVER['REMOTE_ADDR'] ?? '?';
    @file_put_contents($log,
        "[$ts] [$ip] [$user] [$result] $cmd\n",
        FILE_APPEND | LOCK_EX
    );
}
