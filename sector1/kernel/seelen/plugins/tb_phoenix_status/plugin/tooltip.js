// Phoenix Status — tooltip
const PHOENIX_STATUS_URL = "http://localhost:8765/status";

let status;
try {
  status = env.fetchJson(PHOENIX_STATUS_URL, { timeout: 500 });
} catch (_) {
  status = null;
}

if (!status) {
  return "Phoenix kernel: offline\nStart with: python main_kernel.py";
}

const lines = [
  "Phoenix DevOps OS",
  "─────────────────────────",
  "Helix ops/sec : " + (status.helix_ops_per_sec ?? "–"),
  "Helix hit rate: " + (status.helix_hit_rate ?? "–") + "%",
  "Frank routes  : " + (status.frank_routes ?? "–"),
  "Clone pool    : " + (status.clone_pool_items ?? "–") + " items",
  "LLM sessions  : " + (status.llm_sessions ?? "–"),
  "Uptime        : " + (status.uptime_sec ? Math.floor(status.uptime_sec / 60) + "m" : "–"),
];

return lines.join("\n");
