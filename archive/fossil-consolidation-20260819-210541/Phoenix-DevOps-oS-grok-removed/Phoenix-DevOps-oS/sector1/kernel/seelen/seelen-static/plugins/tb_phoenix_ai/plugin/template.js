// Phoenix AI — toolbar plugin template
// Shows: robot icon + current model tag + "thinking" spinner when a session is active.
// Polls http://localhost:8765/ai  (served by phoenix_status_server.py)

const AI_URL = "http://localhost:8765/ai";

let ai;
try {
  ai = env.fetchJson(AI_URL, { timeout: 500 });
} catch (_) {
  ai = null;
}

if (!ai) {
  return [icon("RiRobot2Line"), " ", "–"];
}

if (!ai.available) {
  return [icon("RiRobot2Line"), " ", "offline"];
}

// Shorten model tag: "llama3.1:8b" → "8b",  "phi3:mini" → "mini"
const raw   = ai.active_model ?? "–";
const tag   = raw.includes(":") ? raw.split(":").pop() : raw;

const parts = [icon("RiRobot2Line"), " ", tag];

if ((ai.active_sessions ?? 0) > 0) {
  parts.push("  ");
  parts.push(icon("AiOutlineLoading3Quarters"));   // a session in-flight
  parts.push(" " + ai.active_sessions);
}

return parts;
