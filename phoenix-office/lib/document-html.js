// document-html.js — Phoenix Office (standalone)
// Renders a document's fields into a plain, printable HTML page — the input
// LibreOffice converts to PDF. Kept separate from the conversion call
// itself so the rendering logic is testable without spawning soffice.

function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

function renderDocumentHtml(doc) {
    const fields = doc.fields || {};
    const cp = doc.counterparty || {};
    const rows = Object.entries(fields).map(([k, v]) =>
        `<tr><th>${esc(k.replace(/_/g, ' '))}</th><td>${esc(v == null ? '' : v)}</td></tr>`
    ).join('\n');

    const footer = doc.hash
        ? `<p class="footer">Signed ${esc(doc.signed_at || '')} — SHA3-512 ${esc(String(doc.hash.sha3 || '').slice(0, 24))}…</p>`
        : `<p class="footer">${esc(doc.state)} — not yet signed</p>`;

    return `<!doctype html>
<html><head><meta charset="utf-8"><title>Phoenix Office Document</title>
<style>
  body { font-family: 'Segoe UI', Arial, sans-serif; color: #1a1a1a; margin: 2.5cm; }
  h1 { font-size: 18pt; border-bottom: 2px solid #333; padding-bottom: 6pt; }
  table { width: 100%; border-collapse: collapse; margin-top: 14pt; }
  th, td { text-align: left; padding: 8pt 10pt; border-bottom: 1px solid #ddd; vertical-align: top; }
  th { width: 32%; color: #555; font-weight: 600; text-transform: capitalize; }
  .cp { margin-top: 16pt; font-size: 10pt; color: #444; }
  .footer { margin-top: 24pt; font-size: 9pt; color: #777; }
</style></head>
<body>
  <h1>Phoenix Office — ${esc(doc.state)}</h1>
  <table>${rows}</table>
  <p class="cp">Counterparty: ${esc(cp.phone || '')} ${esc(cp.carrier || '')} ${esc(cp.email || '')}</p>
  ${footer}
</body></html>`;
}

module.exports = { renderDocumentHtml };
