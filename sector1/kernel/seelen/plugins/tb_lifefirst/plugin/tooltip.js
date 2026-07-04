// Life First — tooltip
const LF_URL = "http://localhost:8765/lifefirst";

let lf;
try {
  lf = env.fetchJson(LF_URL, { timeout: 500 });
} catch (_) {
  lf = null;
}

if (!lf) {
  return "Life First API: offline\nDeploy lifefirst_modules on your Ubuntu server.";
}

const modules = lf.modules ?? {};
const modLines = Object.entries(modules).map(([name, active]) =>
  (active ? "✓" : "✗") + " " + name
);

const lines = [
  "Life First AI System",
  "─────────────────────────────",
  "API          : " + (lf.api_online ? "online" : "offline"),
  "Pending      : " + (lf.pending_notifications ?? 0) + " notifications",
  "Active users : " + (lf.active_users ?? "–"),
  "",
  "Modules:",
  ...modLines,
];

return lines.join("\n");
