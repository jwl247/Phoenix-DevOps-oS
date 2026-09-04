<?php
/**
 * proxy.php — Laurie's front door talks to this, never to api.php directly.
 *
 * The API secret lives here (server-side, via Apache SetEnv) and never
 * reaches her browser. This file only allows the handful of actions her
 * page actually needs — it is not a general passthrough.
 */

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: same-origin');

$secret = getenv('LF_API_SECRET') ?: '';
if (!$secret) {
    http_response_code(500);
    echo json_encode(['status' => 'error', 'message' => 'Life First is not configured yet — tell Jerry.']);
    exit;
}

$allowed = ['today', 'check_notifications', 'acknowledge'];
$op = $_GET['op'] ?? '';
if (!in_array($op, $allowed, true)) {
    http_response_code(400);
    echo json_encode(['status' => 'error', 'message' => 'Unknown request.']);
    exit;
}

$body = null;
switch ($op) {
    case 'today':
        // Deliberately avoids the words schedule/book/add/free/available/busy/
        // conflict — module_3's inner dispatch treats those as commands (create
        // an event, check a time slot) rather than "just tell me my day."
        // "calendar" still routes it to the schedule AI, but falls through to
        // generalScheduleQuery(), which is what we actually want here.
        $body = ['username' => 'laurie', 'message' => 'what does my calendar look like today', 'action' => 'query'];
        break;
    case 'check_notifications':
        $body = ['username' => 'laurie', 'message' => 'check my notifications', 'action' => 'check'];
        break;
    case 'acknowledge':
        $input = json_decode(file_get_contents('php://input'), true) ?: [];
        $notificationId = $input['notification_id'] ?? null;
        if (!$notificationId) {
            http_response_code(400);
            echo json_encode(['status' => 'error', 'message' => 'Missing notification_id.']);
            exit;
        }
        $body = [
            'username' => 'laurie', 'message' => 'acknowledge notification', 'action' => 'acknowledge',
            'notification_id' => $notificationId
        ];
        break;
}

$ch = curl_init('http://localhost/api.php?action=request');
curl_setopt_array($ch, [
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_POST => true,
    CURLOPT_POSTFIELDS => json_encode($body),
    CURLOPT_HTTPHEADER => ['Content-Type: application/json', 'Authorization: Bearer ' . $secret],
    CURLOPT_TIMEOUT => 15,
]);
$response = curl_exec($ch);
$status = curl_getinfo($ch, CURLINFO_HTTP_CODE);
$err = curl_error($ch);
curl_close($ch);

if ($err) {
    http_response_code(502);
    echo json_encode(['status' => 'error', 'message' => 'Could not reach Life First right now.']);
    exit;
}

http_response_code($status ?: 200);
echo $response;
