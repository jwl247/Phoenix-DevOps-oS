// config-centralizer-ui.js — Phoenix Dashboard, Settings tab
// Wires the real backend in config-centralizer.js (Node port of a recovered
// config_centralizer.py) into the Settings pane. Talks to it exclusively
// through window.phoenix.invoke — no mock data, unlike the original
// PyQt6 widget this was ported from, which was wired to hardcoded fake
// results instead of its own real scanner.

(function () {
    let lastResults = [];

    function escapeHtml(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function fmtSize(bytes) {
        if (bytes < 1024) return `${bytes}B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
    }

    function renderSummary(summary) {
        const el = document.getElementById('cc-summary');
        if (!el) return;
        if (!summary || summary.total === 0) {
            el.textContent = 'No configs found.';
            return;
        }
        const cats = Object.entries(summary.categories || {})
            .map(([k, v]) => `${k}: ${v}`).join('  ·  ');
        el.textContent = `Found ${summary.total}  ·  recommended ${summary.recommended}  ·  sensitive ${summary.sensitive}  ·  ${cats}`;
    }

    function renderList(results) {
        const el = document.getElementById('cc-list');
        if (!el) return;
        if (!results.length) {
            el.innerHTML = '<div class="place-loading">no configs found</div>';
            return;
        }
        el.innerHTML = results.map((item, i) => `
            <div class="cc-item${item.sensitive ? ' sensitive' : ''}">
                <input type="checkbox" class="cc-item-check" data-idx="${i}" ${item.recommend_import ? 'checked' : ''}>
                <span class="cc-item-path" title="${escapeHtml(item.path)}">${item.sensitive ? '🔒 ' : ''}${escapeHtml(item.path)}</span>
                <span class="cc-item-cat">${escapeHtml(item.category)}</span>
                <span class="cc-item-meta">${fmtSize(item.size)}</span>
            </div>
        `).join('');
    }

    async function runScan() {
        const scanBtn = document.getElementById('cc-scan-btn');
        const importSelectedBtn = document.getElementById('cc-import-selected-btn');
        const importRecBtn = document.getElementById('cc-import-recommended-btn');
        const listEl = document.getElementById('cc-list');

        scanBtn.disabled = true;
        scanBtn.textContent = 'SCANNING...';
        listEl.innerHTML = '<div class="place-loading">scanning system...</div>';

        const result = await window.phoenix.invoke('config-centralizer-scan').catch(e => ({ success: false, error: e.message }));

        scanBtn.disabled = false;
        scanBtn.textContent = 'SCAN SYSTEM';

        if (!result.success) {
            listEl.innerHTML = `<span style="color:var(--red-light)">${escapeHtml(result.error)}</span>`;
            return;
        }

        lastResults = result.results;
        renderSummary(result.summary);
        renderList(lastResults);
        importSelectedBtn.disabled = lastResults.length === 0;
        importRecBtn.disabled = lastResults.length === 0;
    }

    function getSelectedItems() {
        const checks = document.querySelectorAll('.cc-item-check:checked');
        return Array.from(checks).map(c => lastResults[parseInt(c.dataset.idx, 10)]).filter(Boolean);
    }

    async function doImport(items) {
        if (!items.length) {
            alert('No configs selected.');
            return;
        }
        if (!confirm(`Import ${items.length} config(s) into the centralized master directory?`)) return;

        const summaryEl = document.getElementById('cc-summary');
        summaryEl.textContent = `Importing ${items.length} config(s)...`;

        const result = await window.phoenix.invoke('config-centralizer-import', { items })
            .catch(e => ({ success: false, error: e.message }));

        if (!result.success) {
            summaryEl.textContent = `Import failed: ${result.error}`;
            return;
        }
        const okCount = result.results.filter(r => r.success).length;
        summaryEl.textContent = `Imported ${okCount}/${items.length} config(s) into ~/.phoenix/config-centralizer/master`;
    }

    async function doSyncAll() {
        const summaryEl = document.getElementById('cc-summary');
        summaryEl.textContent = 'Syncing all centralized configs back to their original locations...';
        const result = await window.phoenix.invoke('config-centralizer-sync-all').catch(e => ({ success: false, error: e.message }));
        if (!result.success) {
            summaryEl.textContent = `Sync failed: ${result.error}`;
            return;
        }
        const entries = Object.values(result.results || {});
        const okCount = entries.filter(r => r.success).length;
        summaryEl.textContent = `Synced ${okCount}/${entries.length} centralized config(s).`;
    }

    function init() {
        const scanBtn = document.getElementById('cc-scan-btn');
        const importSelectedBtn = document.getElementById('cc-import-selected-btn');
        const importRecBtn = document.getElementById('cc-import-recommended-btn');
        const syncBtn = document.getElementById('cc-sync-btn');
        if (!scanBtn) return; // Settings pane not in DOM yet — script loaded before markup, harmless no-op

        scanBtn.addEventListener('click', runScan);
        importSelectedBtn.addEventListener('click', () => doImport(getSelectedItems()));
        importRecBtn.addEventListener('click', () => doImport(lastResults.filter(r => r.recommend_import)));
        syncBtn.addEventListener('click', doSyncAll);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
