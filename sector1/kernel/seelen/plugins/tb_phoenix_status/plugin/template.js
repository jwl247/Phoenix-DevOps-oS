// Phoenix Status — toolbar plugin template
// Polls the Phoenix kernel status endpoint (Frank Ring 3, port 8765).
// Falls back to a static "offline" indicator when the kernel is not running.
//
// Variables injected by Seelen: none (we fetch ourselves via env.fetch)
// Compatible scope: [] (no built-in Seelen scope needed)

const PHOENIX_STATUS_URL = "http://localhost:8765/status";

let status;
try {
  status = env.fetchJson(PHOENIX_STATUS_URL, { timeout: 500 });
} catch (_) {
  status = null;
}

if (!status) {
  return [icon("SiPhoenixframework"), " ", "offline"];
}

const helix  = status.helix_ops_per_sec  ?? 0;
const frank  = status.frank_routes       ?? 0;
const pool   = status.clone_pool_items   ?? 0;

const helixLabel = helix >= 1000
  ? (helix / 1000).toFixed(0) + "k"
  : helix + "";

return [
  icon("SiPhoenixframework"),
  " ",
  helixLabel + " ops",
  "  ",
  icon("GiRingedPlanet"),
  " " + frank + "r",
  "  ",
  icon("VscDatabase"),
  " " + pool,
];
