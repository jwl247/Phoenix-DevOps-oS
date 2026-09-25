// document-html.js — Phoenix Office (standalone)
// Renders a document's fields into a plain, printable HTML page — the input
// LibreOffice converts to PDF. Kept separate from the conversion call
// itself so the rendering logic is testable without spawning soffice.

const fs = require('fs');
const { getBrand } = require('./brand');

function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

// Inlined raw SVG, not an <img src="file://...">  — LibreOffice's headless
// HTML->PDF conversion isn't guaranteed to resolve external file paths the
// same way a browser would, and this avoids that class of problem entirely.
function letterheadHtml() {
    const brand = getBrand();
    if (!brand) return '';
    let logoSvg = '';
    if (brand.logoPath) {
        try { logoSvg = fs.readFileSync(brand.logoPath, 'utf8'); } catch (_) { /* missing/unreadable — skip, not fatal */ }
    }
    return `<div class="letterhead">
    <div class="letterhead-logo">${logoSvg}</div>
    <div class="letterhead-text">
      ${brand.businessName ? `<div class="lh-name">${esc(brand.businessName)}</div>` : ''}
      ${brand.addressLines.map(l => `<div class="lh-addr">${esc(l)}</div>`).join('')}
    </div>
  </div>`;
}

function renderDocumentHtml(doc) {
    const fields = doc.fields || {};
    const cp = doc.counterparty || {};
    const rows = Object.entries(fields).map(([k, v]) =>
        `<tr><th>${esc(k.replace(/_/g, ' '))}</th><td>${esc(v == null ? '' : v)}</td></tr>`
    ).join('\n');

    // Inline data: images only. A file:/// or http(s) src would have
    // LibreOffice fetch/embed an arbitrary local file or remote URL during
    // conversion — a pulled/shared document must not be able to do that.
    const sigImageOk = doc.signature && typeof doc.signature.image === 'string'
        && /^data:image\/(png|jpeg|gif|webp);base64,[A-Za-z0-9+/=\s]+$/.test(doc.signature.image);
    const sig = sigImageOk
        ? `<div class="signature">
             <img src="${esc(doc.signature.image)}" alt="signature">
             <div class="sig-caption">Signed by ${esc(doc.signature.email || doc.signature.by || '')} — ${esc(doc.signed_at || '')}</div>
           </div>`
        : '';

    const footer = doc.hash
        ? `<p class="footer">Signed ${esc(doc.signed_at || '')} — SHA3-512 ${esc(String(doc.hash.sha3 || '').slice(0, 24))}…</p>`
        : `<p class="footer">${esc(doc.state)} — not yet signed</p>`;

    const letterhead = letterheadHtml();
    const h1Class = letterhead ? '' : ' class="no-letterhead"';

    return `<!doctype html>
<html><head><meta charset="utf-8"><title>Phoenix Office Document</title>
<style>
  body { font-family: 'Segoe UI', Arial, sans-serif; color: #1a1a1a; margin: 2.5cm; }
  .letterhead { display: flex; align-items: center; gap: 14pt; margin-bottom: 16pt;
    padding-bottom: 12pt; border-bottom: 2px solid #333; }
  .letterhead-logo svg { display: block; height: 40pt; width: auto; }
  .lh-name { font-size: 13pt; font-weight: 700; }
  .lh-addr { font-size: 9pt; color: #555; }
  h1 { font-size: 18pt; padding-bottom: 6pt; }
  h1.no-letterhead { border-bottom: 2px solid #333; }
  table { width: 100%; border-collapse: collapse; margin-top: 14pt; }
  th, td { text-align: left; padding: 8pt 10pt; border-bottom: 1px solid #ddd; vertical-align: top; }
  th { width: 32%; color: #555; font-weight: 600; text-transform: capitalize; }
  .cp { margin-top: 16pt; font-size: 10pt; color: #444; }
  .signature { margin-top: 22pt; }
  .signature img { max-height: 56pt; display: block; }
  .sig-caption { font-size: 9pt; color: #555; border-top: 1px solid #333; padding-top: 4pt; margin-top: 2pt; width: fit-content; min-width: 220pt; }
  .footer { margin-top: 24pt; font-size: 9pt; color: #777; }
</style></head>
<body>
  ${letterhead}
  <h1${h1Class}>Phoenix Office — ${esc(doc.state)}</h1>
  <table>${rows}</table>
  <p class="cp">Counterparty: ${esc(cp.phone || '')} ${esc(cp.carrier || '')} ${esc(cp.email || '')}</p>
  ${sig}
  ${footer}
</body></html>`;
}

module.exports = { renderDocumentHtml, letterheadHtml };
