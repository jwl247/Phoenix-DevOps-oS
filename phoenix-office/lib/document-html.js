// document-html.js — Phoenix Office (standalone)
// Renders a document's fields into a plain, printable HTML page — the input
// LibreOffice converts to PDF. Kept separate from the conversion call
// itself so the rendering logic is testable without spawning soffice.

const fs = require('fs');
const { getBrand } = require('./brand');

function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

// LibreOffice's HTML import (Writer/Web) is NOT a browser — found by exporting
// a real PDF on 2026-09-26: it ignores flexbox and percentage/CSS widths (the
// field-name column collapsed to one letter per line), prints inline <svg> as
// its text, and puts a div's border under every child line. So this page uses
// only what it renders reliably: tables with HTML width attributes, images as
// data: URIs with explicit pixel sizes, and <br> for line breaks.
// Page body at 2.5cm margins on A4/Letter is ~600px wide.
const PAGE_PX = 560;

function svgImg(svg, widthPx, alt) {
    const m = /viewBox="0 0 ([\d.]+) ([\d.]+)"/.exec(svg);
    const h = m ? Math.round(widthPx * Number(m[2]) / Number(m[1])) : Math.round(widthPx / 2);
    return `<img src="data:image/svg+xml;base64,${Buffer.from(svg, 'utf8').toString('base64')}" width="${widthPx}" height="${h}" alt="${esc(alt)}">`;
}

function letterheadHtml() {
    const brand = getBrand();
    if (!brand) return '';
    let logo = '';
    if (brand.logoPath) {
        try { logo = svgImg(fs.readFileSync(brand.logoPath, 'utf8'), 110, brand.businessName || 'logo'); } catch (_) { /* missing/unreadable — skip, not fatal */ }
    }
    const lines = [
        brand.businessName ? `<b style="font-size:13pt">${esc(brand.businessName)}</b>` : '',
        ...brand.addressLines.map(l => `<span style="font-size:9pt; color:#555">${esc(l)}</span>`),
    ].filter(Boolean).join('<br>');
    return `<table width="${PAGE_PX}" cellpadding="0" cellspacing="0" border="0"><tr>
    ${logo ? `<td width="124" valign="middle">${logo}</td>` : ''}
    <td valign="middle">${lines}</td></tr></table>
  <hr size="2" noshade>`;
}

function renderDocumentHtml(doc) {
    const fields = doc.fields || {};
    const cp = doc.counterparty || {};
    const label = k => esc(k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()));
    const value = v => esc(v == null ? '' : v).replace(/\r?\n/g, '<br>');
    const cell = 'style="border-bottom:1px solid #dddddd; padding:6pt 8pt"';
    const rows = Object.entries(fields).map(([k, v]) =>
        `<tr><td width="170" valign="top" ${cell}><b style="color:#555555">${label(k)}</b></td><td valign="top" ${cell}>${value(v)}</td></tr>`
    ).join('\n');

    // Inline data: images only. A file:/// or http(s) src would have
    // LibreOffice fetch/embed an arbitrary local file or remote URL during
    // conversion — a pulled/shared document must not be able to do that.
    const sigImageOk = doc.signature && typeof doc.signature.image === 'string'
        && /^data:image\/(png|jpeg|gif|webp);base64,[A-Za-z0-9+/=\s]+$/.test(doc.signature.image);
    const sig = sigImageOk
        ? `<p style="margin-top:22pt"><img src="${esc(doc.signature.image)}" height="56" alt="signature"><br>
             <span style="font-size:9pt; color:#555555">Signed by ${esc(doc.signature.email || doc.signature.by || '')} — ${esc(doc.signed_at || '')}</span></p>`
        : '';

    const footer = doc.hash
        ? `<p style="margin-top:24pt; font-size:9pt; color:#777777">Signed ${esc(doc.signed_at || '')} — SHA3-512 ${esc(String(doc.hash.sha3 || '').slice(0, 24))}…</p>`
        : `<p style="margin-top:24pt; font-size:9pt; color:#777777">${esc(doc.state)} — not yet signed</p>`;

    const cpText = [cp.phone, cp.carrier, cp.email].filter(Boolean).map(esc).join(' · ');
    const letterhead = letterheadHtml();

    // Master schedule: phase_breakdown drawn as the schedule chart (dates
    // across, trades down, green/yellow/red bars) — lib/schedule-gantt.js.
    let chart = '';
    if ('phase_breakdown' in fields) {
        const svg = require('./schedule-gantt').scheduleSvg(fields, { width: 1000 });
        if (svg) chart = `<p>${svgImg(svg, PAGE_PX, 'Schedule by trade')}</p>`;
    }

    return `<!doctype html>
<html><head><meta charset="utf-8"><title>Phoenix Office Document</title>
<style>
  body { font-family: 'Segoe UI', Arial, sans-serif; color: #1a1a1a; }
  h1 { font-size: 18pt; margin: 12pt 0 6pt; }
</style></head>
<body>
  ${letterhead}
  <h1>${esc(doc.title || fields.project_name || 'Phoenix Office')} — ${esc(doc.state)}</h1>
  ${letterhead ? '' : '<hr size="2" noshade>'}
  ${chart}
  <table width="${PAGE_PX}" cellpadding="0" cellspacing="0" border="0"><col width="170"><col width="${PAGE_PX - 170}">${rows}</table>
  ${cpText ? `<p style="margin-top:16pt; font-size:10pt; color:#444444">Counterparty: ${cpText}</p>` : ''}
  ${sig}
  ${footer}
</body></html>`;
}

module.exports = { renderDocumentHtml, letterheadHtml };
