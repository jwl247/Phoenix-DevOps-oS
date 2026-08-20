// Phoenix LLM — tooltip
const LLM_URL = "http://localhost:8765/llm";

let llm;
try {
  llm = env.fetchJson(LLM_URL, { timeout: 500 });
} catch (_) {
  llm = null;
}

if (!llm) {
  return "Phoenix LLM engine: offline\nStart Phoenix kernel to enable.";
}

const warmed   = (llm.models_warmed ?? []).join(", ") || "none warmed yet";
const avail    = (llm.available_models ?? []).join(", ") || "none installed";
const sessions = llm.active_sessions ?? 0;

return [
  "Phoenix LLM Engine",
  "─────────────────────────────",
  "Active model  : " + (llm.active_model ?? "–"),
  "Sessions      : " + sessions,
  "Warmed models : " + warmed,
  "Available     : " + avail,
  "",
  "Large model (70b) paged via Helix vRAM.",
  "Set OLLAMA_MODEL_LARGE env var to override.",
].join("\n");
