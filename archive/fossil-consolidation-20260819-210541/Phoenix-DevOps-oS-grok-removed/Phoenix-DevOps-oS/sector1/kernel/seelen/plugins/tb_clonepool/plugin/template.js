// Clone Pool — toolbar plugin template
// Shows active item count and a T1 indicator.
// Polls http://localhost:8765/clonepool

const CP_URL = "http://localhost:8765/clonepool";

let cp;
try {
  cp = env.fetchJson(CP_URL, { timeout: 500 });
} catch (_) {
  cp = null;
}

if (!cp) {
  return [icon("VscDatabase"), " ", "–"];
}

const total  = cp.total  ?? 0;
const active = cp.active ?? 0;

// Show warning indicator when any items are deprecated or retired
const hasGrey  = (cp.deprecated ?? 0) > 0;
const hasBlack = (cp.retired    ?? 0) > 0;

const parts = [icon("VscDatabase"), " ", String(active)];

if (hasBlack) {
  parts.push("  ");
  parts.push(icon("FaSkullCrossbones"));  // retired items present
} else if (hasGrey) {
  parts.push("  ");
  parts.push(icon("TbAlertTriangle"));    // deprecated items present
}

return parts;
