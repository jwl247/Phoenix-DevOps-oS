// Scriptr Forge — toolbar tooltip
const SCRIPTR_URL = "http://localhost:8765/scriptr";

let sf;
try {
  sf = env.fetchJson(SCRIPTR_URL, { timeout: 500 });
} catch (_) {
  sf = null;
}

if (!sf || !sf.available) {
  return "Scriptr Forge: offline\nStart kernel: python main_kernel.py";
}

const lines = [
  "Scriptr Forge",
  "────────────────────────",
  "Saved scripts : " + (sf.saved_scripts ?? 0),
  "Running now   : " + (sf.running       ?? 0),
  "Last run      : " + (sf.last_run_name ?? "–"),
  "Last exit     : " + (sf.last_run_exit ?? "–"),
  "",
  "Click to open Scriptr Forge",
];

return lines.join("\n");
