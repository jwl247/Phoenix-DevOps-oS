// brand.js — Phoenix Office (standalone)
// Optional letterhead branding (logo + business name + address) for
// exported documents. Reads brand.json at the app root; missing/invalid
// file degrades to "no branding" rather than breaking anything — this
// product ships generic by default, PBM's own build just drops a
// brand.json + logo file in.

const fs = require('fs');
const path = require('path');

const BRAND_FILE = path.join(__dirname, '..', 'brand.json');

function getBrand() {
    try {
        const raw = JSON.parse(fs.readFileSync(BRAND_FILE, 'utf8'));
        const businessName = typeof raw.businessName === 'string' ? raw.businessName.trim() : '';
        const addressLines = Array.isArray(raw.addressLines) ? raw.addressLines.filter(l => typeof l === 'string' && l.trim()) : [];
        if (!businessName && !addressLines.length) return null;
        let logoPath = null;
        if (typeof raw.logoPath === 'string' && raw.logoPath.trim()) {
            const resolved = path.join(path.dirname(BRAND_FILE), raw.logoPath.trim());
            if (fs.existsSync(resolved)) logoPath = resolved;
        }
        return { businessName, addressLines, logoPath };
    } catch (_) {
        return null; // no brand.json, or it's malformed — generic, unbranded output
    }
}

module.exports = { getBrand };
