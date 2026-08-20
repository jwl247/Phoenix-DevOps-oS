// Clone Pool — tooltip
const CP_URL = "http://localhost:8765/clonepool";

let cp;
try {
  cp = env.fetchJson(CP_URL, { timeout: 500 });
} catch (_) {
  cp = null;
}

if (!cp) {
  return "Clone pool: offline\nStart Phoenix kernel to connect.";
}

return [
  "Phoenix Clone Pool",
  "─────────────────────────────",
  "Active     (white) : " + (cp.active     ?? 0),
  "Deprecated (grey)  : " + (cp.deprecated ?? 0),
  "Retired    (black) : " + (cp.retired    ?? 0),
  "Total              : " + (cp.total      ?? 0),
  "",
  "T1 (primary)   : " + (cp.t1 ?? 0),
  "T2 (secondary) : " + (cp.t2 ?? 0),
  "T3 (tertiary)  : " + (cp.t3 ?? 0),
  "T4 (tertiary)  : " + (cp.t4 ?? 0),
  "",
  "DB: " + (cp.db_path ?? "–"),
].join("\n");
