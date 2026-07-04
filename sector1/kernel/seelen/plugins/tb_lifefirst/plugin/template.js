// Life First — toolbar plugin template
// Shows: heart icon + pending notification count from Module 6.
// Polls http://localhost:8765/lifefirst — served by phoenix_status_server.py
// Red heart when unread alerts, hollow heart when clear.

const LF_URL = "http://localhost:8765/lifefirst";

let lf;
try {
  lf = env.fetchJson(LF_URL, { timeout: 500 });
} catch (_) {
  lf = null;
}

if (!lf) {
  return [icon("IoHeartOutline"), " ", "–"];
}

const pending  = lf.pending_notifications ?? 0;
const online   = lf.api_online ?? false;

if (!online) {
  return [icon("IoHeartDislikeOutline"), " ", "offline"];
}

const heartIcon = pending > 0 ? "IoHeart" : "IoHeartOutline";

const parts = [icon(heartIcon), " "];

if (pending > 0) {
  parts.push(pending > 99 ? "99+" : String(pending));
}

return parts;
