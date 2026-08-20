// Phoenix LLM — toolbar plugin template
// Shows: active model name (shortened) + session count + paged-vRAM indicator.
// Polls http://localhost:8765/llm — served by phoenix_status_server.py

const LLM_URL = "http://localhost:8765/llm";

let llm;
try {
  llm = env.fetchJson(LLM_URL, { timeout: 500 });
} catch (_) {
  llm = null;
}

if (!llm) {
  return [icon("BiBrain"), " ", "–"];
}

// Shorten model name: "llama3.1:70b" → "70b", "phi3:mini" → "mini"
const rawModel   = llm.active_model ?? "–";
const shortModel = rawModel.includes(":") ? rawModel.split(":")[1] : rawModel;

const sessions   = llm.active_sessions ?? 0;
const warmed     = llm.models_warmed   ?? [];

// Colour hint: green dot when a large model is warmed
const hasLarge   = warmed.some(m => m.includes("70b") || m.includes("13b"));

const parts = [
  icon("BiBrain"),
  " ",
  shortModel,
];

if (sessions > 0) {
  parts.push("  ");
  parts.push(icon("HiUsers"));
  parts.push(" " + sessions);
}

if (hasLarge) {
  parts.push("  ");
  parts.push(icon("BsLightningChargeFill"));  // large model loaded
}

return parts;
