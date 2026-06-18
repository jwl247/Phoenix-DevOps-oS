<?php
/**
 * files.php — Phoenix File Tree API
 * Returns real filesystem listing for the Desktop dropdown file tree.
 * Supports user-assigned groups (pinned/labeled collections).
 *
 * GET  /desktop/api/files.php              → full file tree
 * GET  /desktop/api/files.php?groups=1     → user-defined groups only
 * POST /desktop/api/files.php              → assign file to group
 *   body: { path, group }                  → assign file to named group
 *   body: { path, group: null }            → remove assignment
 *   body: { action: "rename_group", from, to }
 *   body: { action: "delete_group", group }
 *   body: { action: "create_group", group }
 *
 * Phoenix DevOps OS | jwl247 | GPL v3
 */

header('Content-Type: application/json');
header('X-Content-Type-Options: nosniff');
header('Cache-Control: no-store');

$ASSIGNMENTS_FILE = '/var/phoenix/file_assignments.json';
$WORKER_URL       = getenv('DOCS_WORKER_URL') ?: 'https://documents-worker.phoenix-jwl.workers.dev';
$PHOENIX_AUTH     = getenv('PHOENIX_AUTH') ?: '';

// ── Phoenix directories to expose ─────────────────────────────────────────────
// Each entry: [label, path, icon, depth_limit]
$PHOENIX_DIRS = [
    ['Sector 1 — Boot',        '/home/jwlef/phoenix-devops/sector1',  '⚙',  2],
    ['Sector 2 — Packages',    '/home/jwlef/phoenix-devops/sector2',  '📦', 2],
    ['Sector 3 — Comms',       '/home/jwlef/phoenix-devops/sector3',  '📡', 2],
    ['Sector 4 — Core',        '/home/jwlef/phoenix-devops/sector4',  '🔧', 2],
    ['Life First',             '/var/www/html/lifefirst',             '💚', 1],
    ['Desktop Apps',           '/var/www/html',                       '🖥',  1],
    ['Phoenix Vault',          '/breach_coms4',                       '🔒', 1],
    ['Clone Pool',             '/home/jwlef/Phoenix/clonepool',       '🗂',  1],
];

// ── Allowed file extensions ────────────────────────────────────────────────────
$ALLOWED_EXT = [
    'py','js','php','sh','bash','json','yaml','yml','toml','conf','ini',
    'cfg','env','md','txt','sql','c','h','service','target','jmx','csv',
];

// ── Load / save assignments ───────────────────────────────────────────────────
function load_assignments(string $file): array {
    if (!file_exists($file)) return ['groups' => [], 'assignments' => []];
    $data = json_decode(file_get_contents($file), true);
    return is_array($data) ? $data : ['groups' => [], 'assignments' => []];
}

function save_assignments(array $data, string $file): void {
    @mkdir(dirname($file), 0755, true);
    file_put_contents($file, json_encode($data, JSON_PRETTY_PRINT));
}

// ── Scan one directory ────────────────────────────────────────────────────────
function scan_dir(string $label, string $dirpath, string $icon, int $max_depth): array {
    if (!is_dir($dirpath)) return [];
    return [
        'label'    => $label,
        'path'     => $dirpath,
        'icon'     => $icon,
        'type'     => 'sector',
        'children' => scan_children($dirpath, 0, $max_depth),
    ];
}

function scan_children(string $dirpath, int $depth, int $max_depth): array {
    global $ALLOWED_EXT;
    if ($depth >= $max_depth) return [];

    $items = [];
    try {
        $entries = array_diff(scandir($dirpath), ['.','..']);
        sort($entries);
        foreach ($entries as $name) {
            if ($name[0] === '.') continue;
            $full = "$dirpath/$name";
            if (is_dir($full)) {
                $children = scan_children($full, $depth + 1, $max_depth);
                if (count($children) > 0 || $depth < $max_depth - 1) {
                    $items[] = [
                        'label'    => $name,
                        'path'     => $full,
                        'type'     => 'dir',
                        'children' => $children,
                    ];
                }
            } elseif (is_file($full)) {
                $ext = strtolower(pathinfo($name, PATHINFO_EXTENSION));
                if (in_array($ext, $ALLOWED_EXT, true)) {
                    $items[] = [
                        'label' => $name,
                        'path'  => $full,
                        'type'  => 'file',
                        'ext'   => $ext,
                        'size'  => filesize($full),
                        'mtime' => filemtime($full),
                    ];
                }
            }
        }
    } catch (Exception $e) {}
    return $items;
}

// ── Fetch forged docs from documents-worker ────────────────────────────────────
function fetch_worker_docs(string $worker_url, string $auth): array {
    if (!$auth) return [];
    $ctx = stream_context_create(['http' => [
        'timeout' => 4,
        'header'  => "X-Phoenix-Auth: $auth\r\n",
    ]]);
    $raw = @file_get_contents("$worker_url/docs?limit=50&stage=forged", false, $ctx);
    if (!$raw) return [];
    $data = json_decode($raw, true);
    if (!isset($data['documents'])) return [];

    return array_map(fn($doc) => [
        'label' => $doc['title'] ?? $doc['filename'],
        'path'  => "doc://{$doc['tav']}",
        'type'  => 'doc',
        'ext'   => pathinfo($doc['filename'] ?? '', PATHINFO_EXTENSION),
        'tav'   => $doc['tav'],
        'mime'  => $doc['mime_type'] ?? '',
        'size'  => $doc['size_bytes'] ?? 0,
        'mtime' => strtotime($doc['created_at'] ?? '') ?: 0,
    ], $data['documents']);
}

// ── Build groups tree from assignments ────────────────────────────────────────
function build_groups(array $assignments_data): array {
    $groups      = $assignments_data['groups'] ?? [];
    $assignments = $assignments_data['assignments'] ?? [];
    $result      = [];

    foreach ($groups as $group_name) {
        $files = [];
        foreach ($assignments as $path => $grp) {
            if ($grp !== $group_name) continue;
            $label = basename($path);
            $ext   = strtolower(pathinfo($label, PATHINFO_EXTENSION));
            $files[] = [
                'label' => $label,
                'path'  => $path,
                'type'  => str_starts_with($path, 'doc://') ? 'doc' : 'file',
                'ext'   => $ext,
            ];
        }
        $result[] = [
            'label'     => $group_name,
            'type'      => 'group',
            'icon'      => '📌',
            'children'  => $files,
            'assignable'=> true,
        ];
    }
    return $result;
}

// ── Route ─────────────────────────────────────────────────────────────────────
$method      = $_SERVER['REQUEST_METHOD'];
$assignments = load_assignments($ASSIGNMENTS_FILE);

if ($method === 'GET') {
    $groups_only = isset($_GET['groups']);

    $groups_tree = build_groups($assignments);

    if ($groups_only) {
        echo json_encode(['ok' => true, 'groups' => $groups_tree,
                          'group_names' => $assignments['groups'] ?? []]);
        exit;
    }

    // Build sector tree
    global $PHOENIX_DIRS;
    $sectors = [];
    foreach ($PHOENIX_DIRS as [$label, $path, $icon, $depth]) {
        $node = scan_dir($label, $path, $icon, $depth);
        if ($node) $sectors[] = $node;
    }

    // Documents from worker
    $docs = fetch_worker_docs($WORKER_URL, $PHOENIX_AUTH);
    if ($docs) {
        $sectors[] = [
            'label'    => 'Forged Documents',
            'path'     => 'doc://all',
            'icon'     => '📄',
            'type'     => 'sector',
            'children' => $docs,
        ];
    }

    echo json_encode([
        'ok'          => true,
        'groups'      => $groups_tree,
        'group_names' => $assignments['groups'] ?? [],
        'sectors'     => $sectors,
        'ts'          => time(),
    ]);
    exit;
}

if ($method === 'POST') {
    $body = json_decode(file_get_contents('php://input'), true) ?? [];

    // ── Group management actions ──────────────────────────────────────────────
    $action = $body['action'] ?? null;

    if ($action === 'create_group') {
        $group = trim($body['group'] ?? '');
        if (!$group || strlen($group) > 40) {
            http_response_code(400); echo json_encode(['error' => 'invalid group name']); exit;
        }
        if (!in_array($group, $assignments['groups'], true)) {
            $assignments['groups'][] = $group;
            save_assignments($assignments, $ASSIGNMENTS_FILE);
        }
        echo json_encode(['ok' => true, 'group' => $group, 'groups' => $assignments['groups']]);
        exit;
    }

    if ($action === 'delete_group') {
        $group = $body['group'] ?? '';
        $assignments['groups'] = array_values(array_filter($assignments['groups'], fn($g) => $g !== $group));
        // Remove all assignments for this group
        foreach ($assignments['assignments'] as $path => $grp) {
            if ($grp === $group) unset($assignments['assignments'][$path]);
        }
        save_assignments($assignments, $ASSIGNMENTS_FILE);
        echo json_encode(['ok' => true, 'deleted' => $group, 'groups' => $assignments['groups']]);
        exit;
    }

    if ($action === 'rename_group') {
        $from = $body['from'] ?? '';
        $to   = trim($body['to'] ?? '');
        if (!$from || !$to || strlen($to) > 40) {
            http_response_code(400); echo json_encode(['error' => 'invalid names']); exit;
        }
        $assignments['groups'] = array_map(fn($g) => $g === $from ? $to : $g, $assignments['groups']);
        foreach ($assignments['assignments'] as $path => &$grp) {
            if ($grp === $from) $grp = $to;
        }
        save_assignments($assignments, $ASSIGNMENTS_FILE);
        echo json_encode(['ok' => true, 'renamed' => ['from' => $from, 'to' => $to]]);
        exit;
    }

    if ($action === 'reorder_groups') {
        $order = $body['order'] ?? [];
        $valid = array_filter($order, fn($g) => in_array($g, $assignments['groups'], true));
        $assignments['groups'] = array_values($valid);
        save_assignments($assignments, $ASSIGNMENTS_FILE);
        echo json_encode(['ok' => true, 'groups' => $assignments['groups']]);
        exit;
    }

    // ── Assign / unassign file ─────────────────────────────────────────────────
    $path  = $body['path']  ?? '';
    $group = $body['group'] ?? null;  // null = remove assignment

    if (!$path) { http_response_code(400); echo json_encode(['error' => 'missing path']); exit; }

    if ($group === null || $group === '') {
        unset($assignments['assignments'][$path]);
        save_assignments($assignments, $ASSIGNMENTS_FILE);
        echo json_encode(['ok' => true, 'unassigned' => $path]);
        exit;
    }

    // Auto-create group if it doesn't exist
    if (!in_array($group, $assignments['groups'], true)) {
        $assignments['groups'][] = $group;
    }
    $assignments['assignments'][$path] = $group;
    save_assignments($assignments, $ASSIGNMENTS_FILE);

    echo json_encode(['ok' => true, 'path' => $path, 'group' => $group,
                      'groups' => $assignments['groups']]);
    exit;
}

http_response_code(405);
echo json_encode(['error' => 'method not allowed']);
