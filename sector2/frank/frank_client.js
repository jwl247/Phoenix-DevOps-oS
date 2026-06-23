/**
 * frank_client.js — Phoenix Office side
 * Drop this into the worker. Frank lives at localhost:7347.
 * The UI never calls the filesystem directly — it calls Frank.
 */

const FRANK_URL = "http://127.0.0.1:7347";
const POLL_MS   = 800;   // how often the status bar refreshes

// ── STATUS POLLING ────────────────────────────────────────────────────────────
let _frankTimer = null;

export function frankStart(onUpdate) {
  if (_frankTimer) return;
  const poll = async () => {
    try {
      const r = await fetch(`${FRANK_URL}/status`);
      if (r.ok) onUpdate(await r.json());
    } catch { onUpdate(null); }   // bridge offline → bars go dark, no crash
  };
  poll();
  _frankTimer = setInterval(poll, POLL_MS);
}

export function frankStop() {
  clearInterval(_frankTimer);
  _frankTimer = null;
}

// ── SAVE ──────────────────────────────────────────────────────────────────────
/**
 * Call this instead of any direct file write.
 * Frank decides drive, pressure, buffer, version — all of it.
 *
 * @param {string} docId    - stable document id (uuid or slug)
 * @param {string} title    - human name shown in catalog
 * @param {string} docType  - "doc" | "sheet" | "slide" | "draw"
 * @param {string} content  - serialised document content
 * @returns {Promise<object>} Frank's save result
 */
export async function frankSave(docId, title, docType, content) {
  try {
    const r = await fetch(`${FRANK_URL}/save`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ doc_id: docId, title, doc_type: docType, content }),
    });
    return await r.json();
  } catch (err) {
    // bridge offline — queue locally, retry on next save
    _localQueue.push({ docId, title, docType, content, ts: Date.now() });
    return { status: "local_queue", buffered: true, message: "Frank bridge offline — queued locally" };
  }
}

// ── LOCAL FALLBACK QUEUE ──────────────────────────────────────────────────────
// If the HTTP bridge is down (e.g. mid-restart), saves accumulate here
// and flush automatically when the bridge comes back online.
const _localQueue = [];

setInterval(async () => {
  if (!_localQueue.length) return;
  try {
    await fetch(`${FRANK_URL}/status`);   // ping
    while (_localQueue.length) {
      const item = _localQueue.shift();
      await frankSave(item.docId, item.title, item.docType, item.content);
    }
  } catch { /* still offline */ }
}, 5000);

// ── UI HELPERS ────────────────────────────────────────────────────────────────
/**
 * Render Frank status into the three bar elements.
 * Matches the frank-bar HTML in the Phoenix Office worker.
 *
 * @param {object|null} status  - from /status, or null if offline
 */
export function frankRenderBars(status) {
  const set = (id, pct, color) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.querySelector("div").style.width  = Math.round(pct) + "%";
    el.querySelector("div").style.background = color;
  };

  if (!status) {
    ["l1bar","l2bar","l3bar"].forEach(id => set(id, 0, "rgba(62,207,142,.2)"));
    const p = document.getElementById("frankPct");
    if (p) p.textContent = "offline";
    return;
  }

  const { drives, avg, tier, buffered, thresholds } = status;
  const vals = Object.values(drives);
  const [v1, v2, v3] = [vals[0]||0, vals[1]||0, vals[2]||0];

  const barColor = p =>
    p >= thresholds.high ? "rgba(239,68,68,.8)"  :
    p >= thresholds.med  ? "rgba(251,191,36,.8)" :
                           "#3ecf8e";

  set("l1bar", v1, barColor(v1));
  set("l2bar", v2, barColor(v2));
  set("l3bar", v3, barColor(v3));

  const pctEl = document.getElementById("frankPct");
  if (pctEl) {
    pctEl.textContent = Math.round(avg) + "% " + tier;
    pctEl.style.color = barColor(avg);
  }

  const msgEl = document.getElementById("frankMsg");
  if (msgEl && buffered > 0)
    msgEl.textContent = `L2 buffer: ${buffered} pending`;

  // tell the save button if Frank is healthy
  const saveBtn = document.getElementById("saveBtn");
  if (saveBtn) saveBtn.title = `Frank3 — ${tier} tier, avg ${Math.round(avg)}%`;
}

// ── AUTO-SAVE DEBOUNCE ────────────────────────────────────────────────────────
let _saveDebounce = null;

/**
 * Call on every keystroke. Frank saves 2s after the user stops typing.
 * No spinners, no "saving…" toast unless Frank returns buffered:true.
 */
export function frankAutoSave(docId, title, docType, getContent) {
  clearTimeout(_saveDebounce);
  _saveDebounce = setTimeout(async () => {
    const content = getContent();
    const result  = await frankSave(docId, title, docType, content);
    if (result.buffered) {
      const msg = document.getElementById("frankMsg");
      if (msg) msg.textContent = "Drives hot — Frank buffered";
    }
  }, 2000);
}
