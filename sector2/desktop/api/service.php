<?php
/**
 * service.php — Phoenix Service Control API
 * Controls systemd services on phoenix-ext via the mixer panel.
 * Runs as www-data; requires /etc/sudoers.d/phoenix-mixer for systemctl calls.
 *
 * POST /desktop/api/service.php  { "service": "wireguard", "action": "start|stop|restart|status" }
 * GET  /desktop/api/service.php?services=all  → status of all services
 *
 * Phoenix DevOps OS | jwl247 | GPL v3
 */

header('Content-Type: application/json');
header('X-Content-Type-Options: nosniff');

// ── Auth ────────────────────────────────────────────────────────────────────
$auth = getenv('PHOENIX_AUTH') ?: '';
$req_auth = $_SERVER['HTTP_X_PHOENIX_AUTH'] ?? '';
if ($auth && $req_auth !== $auth) {
    http_response_code(401);
    echo json_encode(['error' => 'unauthorized']);
    exit;
}

// ── Service registry ────────────────────────────────────────────────────────
// Maps mixer channel name → systemd unit name
// 'venv' channels are handled specially (activate/deactivate Python venvs)
$SERVICES = [
    'ssh'         => ['unit' => 'ssh',                    'label' => 'SSH',          'group' => 'network'],
    'wireguard'   => ['unit' => 'wg-quick@wg0',           'label' => 'WireGuard',    'group' => 'network'],
    'cloudflared' => ['unit' => 'cloudflared',             'label' => 'Cloudflared',  'group' => 'network'],
    'frank'       => ['unit' => 'phoenix-kernel',          'label' => 'Frank Kernel', 'group' => 'core'],
    'ollama'      => ['unit' => 'ollama',                  'label' => 'Ollama AI',    'group' => 'ai'],
    'lifefirst'   => ['unit' => 'apache2',                 'label' => 'Life First',   'group' => 'apps'],
    'nextcloud'   => ['unit' => 'snap.nextcloud.apache',   'label' => 'Nextcloud',    'group' => 'apps'],
    'prometheus'  => ['unit' => 'snap.prometheus.prometheus', 'label' => 'Prometheus', 'group' => 'monitor'],
    'conversion'  => ['unit' => 'phoenix-conversion-agent','label' => 'Conversion',   'group' => 'core'],
    'venv_frank'  => ['unit' => 'venv:frank',              'label' => 'venv/Frank',   'group' => 'venv'],
    'venv_lf'     => ['unit' => 'venv:lifefirst',          'label' => 'venv/LF',      'group' => 'venv'],
    'venv_wt'     => ['unit' => 'venv:warthunder',         'label' => 'venv/WT',      'group' => 'venv'],
];

// venv paths on phoenix-ext
$VENV_PATHS = [
    'venv:frank'      => '/home/jwlef/Phoenix/venv',
    'venv:lifefirst'  => '/home/jwlef/lifefirst/venv',
    'venv:warthunder' => '/home/jwlef/Phoenix/warthunder_venv',
];

// ── Helpers ─────────────────────────────────────────────────────────────────

function run_cmd(string $cmd): array {
    $output = []; $rc = 0;
    exec($cmd . ' 2>&1', $output, $rc);
    return ['out' => implode("\n", $output), 'rc' => $rc];
}

function systemctl_status(string $unit): string {
    $r = run_cmd("sudo systemctl is-active " . escapeshellarg($unit));
    $state = trim($r['out']);
    if ($state === 'active') return 'active';
    if ($state === 'inactive') return 'inactive';
    if ($state === 'failed') return 'failed';
    return 'unknown';
}

function venv_status(string $venv_key, array $venv_paths): string {
    $path = $venv_paths[$venv_key] ?? null;
    if (!$path) return 'unknown';
    // A venv is "active" if pyvenv.cfg exists and the activate script is present
    return (file_exists("$path/bin/activate") && file_exists("$path/pyvenv.cfg"))
        ? 'active' : 'inactive';
}

function service_status(string $name, array $def, array $venv_paths): array {
    $unit = $def['unit'];
    if (str_starts_with($unit, 'venv:')) {
        $state = venv_status($unit, $venv_paths);
        return ['service' => $name, 'unit' => $unit, 'state' => $state, 'label' => $def['label'], 'group' => $def['group']];
    }
    $state = systemctl_status($unit);
    return ['service' => $name, 'unit' => $unit, 'state' => $state, 'label' => $def['label'], 'group' => $def['group']];
}

function do_action(string $name, string $action, array $def, array $venv_paths): array {
    $unit = $def['unit'];

    if (str_starts_with($unit, 'venv:')) {
        $path = $venv_paths[$unit] ?? null;
        if (!$path) return ['ok' => false, 'error' => 'unknown venv'];
        if ($action === 'start') {
            // Ensure venv exists; create if missing
            if (!file_exists("$path/bin/activate")) {
                $r = run_cmd("python3 -m venv " . escapeshellarg($path));
                if ($r['rc'] !== 0) return ['ok' => false, 'error' => $r['out']];
            }
            return ['ok' => true, 'state' => 'active', 'note' => 'venv ready — activate with: source ' . $path . '/bin/activate'];
        }
        if ($action === 'stop') {
            // Deactivate = noop at the process level (venv is just a directory)
            return ['ok' => true, 'state' => 'inactive', 'note' => 'venv deactivated in shell context'];
        }
        if ($action === 'status') {
            return ['ok' => true, 'state' => venv_status($unit, $venv_paths)];
        }
        return ['ok' => false, 'error' => 'unsupported venv action'];
    }

    $allowed = ['start', 'stop', 'restart', 'status'];
    if (!in_array($action, $allowed, true)) {
        return ['ok' => false, 'error' => 'invalid action'];
    }

    if ($action === 'status') {
        return ['ok' => true, 'state' => systemctl_status($unit)];
    }

    $r = run_cmd("sudo systemctl " . escapeshellarg($action) . " " . escapeshellarg($unit));
    $state = systemctl_status($unit);
    return ['ok' => $r['rc'] === 0, 'state' => $state, 'out' => $r['out']];
}

// ── Route ────────────────────────────────────────────────────────────────────

$method = $_SERVER['REQUEST_METHOD'];

// GET /desktop/api/service.php?services=all — poll all service states
if ($method === 'GET') {
    $statuses = [];
    foreach ($SERVICES as $name => $def) {
        $statuses[] = service_status($name, $def, $VENV_PATHS);
    }
    echo json_encode(['ok' => true, 'services' => $statuses]);
    exit;
}

// POST — control a service
if ($method === 'POST') {
    $body = json_decode(file_get_contents('php://input'), true);
    $name   = trim($body['service'] ?? '');
    $action = trim($body['action']  ?? '');

    if (!$name || !isset($SERVICES[$name])) {
        http_response_code(400);
        echo json_encode(['error' => 'unknown service: ' . $name]);
        exit;
    }

    $result = do_action($name, $action, $SERVICES[$name], $VENV_PATHS);
    $log_line = json_encode([
        'ts' => date('c'), 'op' => 'mixer', 'service' => $name,
        'action' => $action, 'ok' => $result['ok'],
    ]);
    @file_put_contents('/var/log/phoenix/audit.log', $log_line . "\n", FILE_APPEND);

    echo json_encode(array_merge(['service' => $name, 'action' => $action], $result));
    exit;
}

http_response_code(405);
echo json_encode(['error' => 'method not allowed']);
