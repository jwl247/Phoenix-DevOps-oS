<?php
/**
 * MRS. WIGGINS - HEix7.3GIII API ROUTER 
 * Primary: Gemini | Secondary/Private: Llama3 (Ollama)
 */

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');

// --- IDENTITY BLOCK ---
$identity = [
    "name" => "Mrs. Wiggins",
    "host_designation" => "ENCOMPASS-E",
    "platform" => "Fedora",
    "kernel_version" => "HEix7.3GIII"
];

// --- CONFIG & INPUT ---
$config = parse_ini_file('.env');
$aiMode = $config['AI_MODE'] ?? 'local'; // 'gemini' or 'local'
$input = json_decode(file_get_contents('php://input'), true);
$message = $input['message'] ?? $input['prompt'] ?? '';

if (!$message) {
    echo json_encode(["status" => "ready", "identity" => $identity]);
    exit();
}

// --- BRAIN ROUTING ---
if ($aiMode === 'gemini') {
    // PRIMARY BRAIN: Gemini 1.5 Flash
    $url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=" . $config['GEMINI_API_KEY'];
    $data = ["contents" => [["parts" => [["text" => $message]]]]];
} else {
    // LOCAL BRAIN: Llama3 (Ollama)
    $url = "http://localhost:11434/api/generate";
    $data = [
        "model" => $config['OLLAMA_MODEL'] ?? "llama3:latest",
        "prompt" => $message,
        "stream" => false
    ];
}

// --- UNIFIED EXECUTION ---
$ch = curl_init($url);
curl_setopt($ch, CURLOPT_HTTPHEADER, ['Content-Type: application/json']);
curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($data));
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
$response = curl_exec($ch);
curl_close($ch);

// --- HUB NOTIFICATION ---
// Here we "pulse" the ENCOMPASS-E Hub to log that a brain-call was made
// file_get_contents("http://localhost:8080/log?module=GII-E&event=AI_CALL");

echo $response;
?>
