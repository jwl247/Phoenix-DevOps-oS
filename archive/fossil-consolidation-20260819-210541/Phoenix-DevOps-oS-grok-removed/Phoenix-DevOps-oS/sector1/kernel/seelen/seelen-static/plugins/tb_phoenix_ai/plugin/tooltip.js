// Phoenix AI — toolbar tooltip
const AI_URL = "http://localhost:8765/ai";

let ai;
try {
  ai = env.fetchJson(AI_URL, { timeout: 500 });
} catch (_) {
  ai = null;
}

if (!ai || !ai.available) {
  return "Phoenix AI: offline\nStart kernel: python main_kernel.py";
}

const lines = [
  "Phoenix AI Assistant",
  "────────────────────────",
  "Active model  : " + (ai.active_model   ?? "–"),
  "Sessions live : " + (ai.active_sessions ?? 0),
  "Models warmed : " + (ai.models_warmed  ?? []).join(", "),
  "",
  "Click to open chat",
];

return lines.join("\n");
