// hud-layout.js
// Renderer wiring for the HUD restructure. Loaded AFTER dashboard.js, so
// window.phoenixDashboard already exists and its real _hudNavSwitch /
// AI chat / MAP / RUNIT logic is reused, not duplicated.
//
// Everything here calls real IPC channels. Where a channel can fail
// (unconfigured app path, missing venv, worker route not deployed),
// the UI shows the real error text — nothing here fakes success.

(function () {
    const invoke = (channel, ...args) => {
        if (!window.phoenix) return Promise.reject(new Error('Not running in Electron.'));
        return window.phoenix.invoke(channel, ...args);
    };

    // ── Dropdown slots ──────────────────────────────────────────────────
    let slotsState = { slots: [null, null, null, null, null, null], activeIndex: null };

    async function loadSlots() {
        const state = await invoke('get-dropdown-slots').catch(() => null);
        if (state) slotsState = state;
        renderSlots();
        renderStatusStrip();
    }

    function renderSlots() {
        const container = document.getElementById('hud-dropdown-slots');
        if (!container) return;
        container.innerHTML = '';
        slotsState.slots.forEach((slotPath, i) => {
            const el = document.createElement('div');
            el.className = 'dropdown-slot' + (slotPath ? ' filled' : '') + (slotsState.activeIndex === i ? ' active-slot' : '');
            el.dataset.slotIndex = String(i);

            const label = document.createElement('span');
            label.className = 'slot-path';
            label.textContent = slotPath ? slotPath.split(/[\\/]/).pop() : `slot ${i + 1} — drag a folder`;
            el.appendChild(label);

            el.addEventListener('click', async () => {
                if (!slotPath) return;
                const result = await invoke('set-active-slot', { index: i });
                if (result.success) {
                    slotsState.activeIndex = i;
                    renderSlots();
                    renderStatusStrip();
                } else {
                    alert(result.error);
                }
            });

            el.addEventListener('dragover', e => { e.preventDefault(); el.classList.add('drag-over'); });
            el.addEventListener('dragleave', () => el.classList.remove('drag-over'));
            el.addEventListener('drop', async e => {
                e.preventDefault();
                el.classList.remove('drag-over');
                const file = e.dataTransfer.files[0];
                if (!file || !file.path) return;
                const result = await invoke('set-dropdown-slot', { index: i, dirPath: file.path });
                if (result.success) {
                    slotsState.slots = result.slots;
                    renderSlots();
                } else {
                    alert(result.error);
                }
            });

            container.appendChild(el);
        });
    }

    let previousActiveIndex = null;

    function renderStatusStrip() {
        const hereEl = document.getElementById('status-you-are-here');
        const wereEl = document.getElementById('status-you-were-here');
        if (!hereEl || !wereEl) return;
        const activePath = slotsState.activeIndex !== null ? slotsState.slots[slotsState.activeIndex] : null;
        const prevPath = previousActiveIndex !== null ? slotsState.slots[previousActiveIndex] : null;
        hereEl.textContent = activePath ? activePath.split(/[\\/]/).pop() : '— no active slot —';
        wereEl.textContent = prevPath ? prevPath.split(/[\\/]/).pop() : '—';
    }

    // ── Status strip expand (Sector Map + CLI) ──────────────────────────
    document.getElementById('hud-status-strip')?.addEventListener('click', (e) => {
        // Don't toggle when clicking inside the expanded area itself.
        if (e.target.closest('.hud-status-expand')) return;
        document.getElementById('hud-status-expand')?.classList.toggle('open');
    });

    document.getElementById('expand-cli')?.addEventListener('click', () => {
        window.phoenixDashboard?._hudNavSwitch('codes');
        document.querySelector('.drawer-tab[data-drawer="cli"]')?.click();
    });

    // ── Sector switches → buttons (reuses existing SECTOR_META / toggle logic) ─
    // The original toggle-switch elements already carry data-sector and a
    // working click-to-toggle handler wired elsewhere in dashboard.js.
    // We only change their visual class, not their behavior.
    document.querySelectorAll('.toggle-switch[data-sector]').forEach(el => {
        el.classList.add('sector-btn');
    });

    // ── Left switchers: PS7 / Bash / GitHub Desktop / Glossary ──────────
    async function launchExternal(key, buttonEl) {
        const original = buttonEl.textContent;
        buttonEl.textContent = 'launching...';
        const result = await invoke('launch-external-app', { key });
        buttonEl.textContent = original;
        if (!result.success) {
            if (result.needsConfig) {
                const picked = await invoke('open-exe-dialog', { title: `Locate ${key}` });
                if (picked.success) {
                    const setResult = await invoke('set-external-app-path', { key, exePath: picked.exePath });
                    if (setResult.success) {
                        return launchExternal(key, buttonEl);
                    }
                    alert(setResult.error);
                }
            } else {
                alert(result.error);
            }
        }
    }

    document.getElementById('switcher-ps7')?.addEventListener('click', (e) => launchExternal('ps7', e.currentTarget));
    document.getElementById('switcher-bash')?.addEventListener('click', (e) => launchExternal('bash', e.currentTarget));
    document.getElementById('switcher-github')?.addEventListener('click', (e) => launchExternal('githubDesktop', e.currentTarget));

    // GLOSSARY now lives as a full HUD nav pane — this switcher is just a
    // shortcut into it, same pattern as PS7 SHELL.
    document.getElementById('switcher-glossary')?.addEventListener('click', () => {
        window.phoenixDashboard?._hudNavSwitch('glossary');
    });

    // ── Right column actions ─────────────────────────────────────────────
    // Buttons are now GENERATED by ButtonGenerator (button-generator.js).
    // We just mount them into #hud-right-column and hand over the shared ctx.
    // The old id-based fallbacks that used to sit here (telemetry, guide,
    // venv, run, ps7, explorer, clonepool, screenshot, live-monitor) were
    // removed 2026-09-28 (DASH-F01/F13): they ran at script-parse time,
    // before mount() created #action-* on DOMContentLoaded, so none ever
    // bound — and the venv one referenced an undefined `slots`. Every one
    // of those buttons lives in button-generator.js now, including the
    // clonepool browser.

    function mountGeneratedButtons() {
        const container = document.getElementById('hud-right-column');
        if (!container || !window.ButtonGenerator) return;
        window.ButtonGenerator.mount(container, {
            invoke,
            slots: slotsState,
            mode: 'app'
        });
    }

    // 9. SHELL + CLAUDE — real persistent PTYs behind xterm.js. Both open in
    //    the active working directory (the active folder slot) and follow it
    //    when it changes. CLAUDE is the same shell dropped straight into an
    //    interactive `claude` — the hotline.
    const hudTerminals = (function () {
        const made = {};   // session -> { term, fit, started }

        function build(session, hostId) {
            const host = document.getElementById(hostId);
            if (!host || typeof Terminal === 'undefined') return null;

            const term = new Terminal({
                fontFamily: '"Cascadia Mono", "Consolas", "Courier New", monospace',
                fontSize: 13,
                cursorBlink: true,
                theme: { background: 'rgba(5,7,12,0.0)', foreground: '#c8e6d0', cursor: '#00ff88' },
                allowTransparency: true
            });
            let fit = null;
            try { fit = new FitAddon.FitAddon(); term.loadAddon(fit); } catch (_) { fit = null; }
            term.open(host);
            term.onData(d => window.phoenix?.send('term-input', { session, data: d }));

            const doFit = () => {
                if (!fit) return;
                try {
                    fit.fit();
                    window.phoenix?.send('term-resize', { session, cols: term.cols, rows: term.rows });
                } catch (_) {}
            };
            window.addEventListener('resize', doFit);

            const rec = { term, fit, doFit, started: false };
            made[session] = rec;
            return rec;
        }

        // Route incoming PTY data to the right xterm.
        window.phoenix?.onStream('term-data', ({ session, data }) => {
            const rec = made[session];
            if (rec) rec.term.write(data);
        });

        return {
            async show(session, hostId) {
                const rec = made[session] || build(session, hostId);
                if (!rec) return;
                if (!rec.started) {
                    rec.started = true;
                    rec.doFit();
                    const res = await invoke('term-start', { session, cols: rec.term.cols, rows: rec.term.rows })
                        .catch(e => ({ started: false, error: e.message }));
                    if (!res.started) {
                        rec.term.write(`\r\n\x1b[31m${res.error || 'terminal failed to start'}\x1b[0m\r\n`);
                        return;
                    }
                }
                setTimeout(() => { rec.doFit(); rec.term.focus(); }, 60);
            }
        };
    })();

    window.phoenixHudShell  = { show: () => hudTerminals.show('shell',  'term-host-shell') };
    window.phoenixHudClaude = { show: () => hudTerminals.show('claude', 'term-host-claude') };

    // 10. GLOSSARY — searchable TOC/index over the clonepool + D1.
    // Backend (get-glossary/get-categories) confirmed working end-to-end
    // against the live worker (docs/GLOSSARY.md) — this just replaces the
    // old raw-JSON-dump popout with an actual searchable list.
    let glossaryCategoriesLoaded = false;
    let glossarySearchTimer = null;

    function escapeHtml(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    async function loadGlossaryCategories() {
        const select = document.getElementById('glossary-category');
        if (!select || glossaryCategoriesLoaded) return;
        const result = await invoke('get-categories').catch(e => ({ success: false, error: e.message }));
        if (!result.success || !result.categories) return; // filter still works without it
        glossaryCategoriesLoaded = true;
        result.categories.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c.name;
            opt.textContent = c.name;
            select.appendChild(opt);
        });
    }

    // ── Sector derivation from pool_path ─────────────────────────────────
    // pool_path looks like "/c/Users/jwlef/Phoenix/clonepool/<hex>" or
    // "/home/jwlef/Phoenix/clonepool/<hex>". Category + description give
    // the connection to the sector it lives in.
    const SECTOR_CONNECTIONS = {
        'subsystem': 'Sector 1 — boot/kernel',
        'scripts':   'Sector 2 — intake/clone',
        'comms':     'Sector 3 — comms/network',
        'database':  'Sector 4 — helix/vault',
        'directory': 'Sector 2 — clonepool snapshot',
        'media':     'Sector 2 — docs/media',
        'distro':    'Sector 2 — distro suite',
        'infrastructure': 'Sector 2 — infrastructure'
    };

    function deriveLocation(g) {
        // Show the clonepool path shortened to the last two segments.
        // pool_path: /c/Users/jwlef/Phoenix/clonepool/<hex>
        if (!g.pool_path) return null;
        const parts = g.pool_path.replace(/\\/g, '/').split('/').filter(Boolean);
        const last2 = parts.slice(-2).join('/');
        return `clonepool/${last2}`;
    }

    function renderGlossaryEntry(g) {
        const stateWord  = g.state || 'white';
        const location   = deriveLocation(g);
        const sector     = SECTOR_CONNECTIONS[g.category] || null;
        const address    = g.b58 || (g.hex ? g.hex.slice(0, 16) + '…' : null);
        const amended    = g.amended ? ' · amended' : '';
        const sizeStr    = g.size ? formatBytes(g.size) : null;
        const dateStr    = g.intaked_at ? g.intaked_at.slice(0, 10) : null;

        // Meta row: category · version · size · date · amended flag
        const meta = [g.category, g.version, sizeStr, dateStr].filter(Boolean).join('  ·  ') + amended;

        // Connections row: sector + b58 address
        const conn = [sector, address ? `TAV:${address}` : null].filter(Boolean).join('  ·  ');

        return `
            <div class="glossary-entry" data-hex="${escapeHtml(g.hex || '')}" data-name="${escapeHtml(g.name)}">
                <div class="glossary-entry-head">
                    <span class="glossary-entry-name">${escapeHtml(g.name)}</span>
                    <span class="glossary-state glossary-state-${escapeHtml(stateWord)}">${escapeHtml(stateWord)}</span>
                </div>
                ${g.description ? `<div class="glossary-entry-desc">${escapeHtml(g.description)}</div>` : ''}
                ${location   ? `<div class="glossary-entry-location">&#x1f4c1; ${escapeHtml(location)}</div>` : ''}
                ${conn       ? `<div class="glossary-entry-connections">&#x1f517; ${escapeHtml(conn)}</div>` : ''}
                ${meta       ? `<div class="glossary-entry-meta">${escapeHtml(meta)}</div>` : ''}
                <div class="glossary-entry-history" style="display:none;"></div>
                <button class="glossary-history-btn" data-hex="${escapeHtml(g.hex || '')}" title="show version history">&#x25BC; history</button>
            </div>`;
    }

    function formatBytes(b) {
        if (b >= 1048576) return (b / 1048576).toFixed(1) + ' MB';
        if (b >= 1024)    return (b / 1024).toFixed(1) + ' KB';
        return b + ' B';
    }

    // Expand/collapse version history on click
    document.getElementById('glossary-list')?.addEventListener('click', async e => {
        const btn = e.target.closest('.glossary-history-btn');
        if (!btn) return;
        const hex = btn.dataset.hex;
        if (!hex) return;
        const entry   = btn.closest('.glossary-entry');
        const histDiv = entry?.querySelector('.glossary-entry-history');
        if (!histDiv) return;

        if (histDiv.style.display !== 'none') {
            histDiv.style.display = 'none';
            btn.innerHTML = '&#x25BC; history';
            return;
        }

        btn.innerHTML = '&#x25BA; loading…';
        histDiv.style.display = 'block';
        histDiv.innerHTML = '<span style="color:var(--text-dim)">fetching…</span>';

        const result = await invoke('get-custody', { hex }).catch(e => ({ success: false, error: e.message }));
        if (!result.success) {
            histDiv.innerHTML = `<span style="color:var(--red-light)">${escapeHtml(result.error)}</span>`;
            btn.innerHTML = '&#x25BC; history';
            return;
        }

        const rows = result.custody || [];
        if (!rows.length) {
            histDiv.innerHTML = '<span style="color:var(--text-dim)">no custody records</span>';
        } else {
            histDiv.innerHTML = rows.map(r => {
                const qr   = r.qr_top  ? `<span class="glossary-qr">${escapeHtml(r.qr_top)}</span>` : '';
                const tick = r.validated ? ' ✓' : '';
                return `<div class="glossary-custody-row">
                    <span class="glossary-custody-action">${escapeHtml(r.action)}${tick}</span>
                    <span class="glossary-custody-actor"> · ${escapeHtml(r.actor || '—')}</span>
                    <span class="glossary-custody-date"> · ${escapeHtml((r.intaked_at || '').slice(0, 16))}</span>
                    ${qr}
                </div>`;
            }).join('');
        }
        btn.innerHTML = '&#x25BC; history';
    });

    async function loadGlossaryResults() {
        const listEl  = document.getElementById('glossary-list');
        const countEl = document.getElementById('glossary-count');
        if (!listEl) return;
        const q        = document.getElementById('glossary-search')?.value.trim() || '';
        const category = document.getElementById('glossary-category')?.value || '';
        const state    = document.getElementById('glossary-state')?.value || '';

        listEl.innerHTML = '<div class="place-loading">loading glossary…</div>';
        const result = await invoke('get-glossary', { q, category }).catch(e => ({ success: false, error: e.message }));
        if (!result.success) {
            listEl.innerHTML = `<span style="color:var(--red-light)">${escapeHtml(result.error)}</span>`;
            if (countEl) countEl.textContent = '';
            return;
        }

        let entries = result.glossary || [];
        // State filter is client-side — worker doesn't support it server-side.
        if (state) entries = entries.filter(g => (g.state || 'white') === state);
        // Alphabetical — worker returns insertion order by default.
        entries.sort((a, b) => (a.name || '').localeCompare(b.name || ''));

        if (countEl) {
            countEl.textContent = `${entries.length}${entries.length !== result.count ? ` of ${result.count}` : ''} entr${entries.length === 1 ? 'y' : 'ies'}`;
        }
        if (!entries.length) {
            listEl.innerHTML = '<div class="place-loading">no matching entries</div>';
            return;
        }
        listEl.innerHTML = entries.map(renderGlossaryEntry).join('');
    }

    document.querySelector('.hud-nav-btn[data-hud-nav="glossary"]')?.addEventListener('click', async () => {
        await loadGlossaryCategories();
        loadGlossaryResults();
    });

    document.getElementById('glossary-search')?.addEventListener('input', () => {
        clearTimeout(glossarySearchTimer);
        glossarySearchTimer = setTimeout(loadGlossaryResults, 300);
    });
    document.getElementById('glossary-category')?.addEventListener('change', loadGlossaryResults);
    document.getElementById('glossary-state')?.addEventListener('change', loadGlossaryResults);
    document.getElementById('glossary-refresh')?.addEventListener('click', loadGlossaryResults);

    // ── Atlas — plain answer: what it is + what it really works with ──────
    // Same rules as .claude/skills/atlas/SKILL.md: real connections (`edge`)
    // first, at most 3 same-folder neighbours (`area`), never the random
    // `backfill`, no ids or raw fields.
    const atlasName = c => (c.name || c.path || '').replace(/\/$/, '').split('/').pop();
    const firstSentence = s => {
        const t = String(s || '').replace(/`/g, '').trim();
        const m = t.match(/^(.{20,220}?[.!?])(\s|$)/);
        return m ? m[1] : t.slice(0, 220);
    };

    async function loadAtlas() {
        const out = document.getElementById('atlas-result');
        const q = document.getElementById('atlas-search')?.value.trim();
        if (!out || !q) return;
        out.innerHTML = '<div class="place-loading">looking it up...</div>';
        const r = await invoke('get-atlas', { q }).catch(e => ({ success: false, error: e.message }));
        if (!r.success || !r.center) {
            out.innerHTML = `<div class="place-loading">${escapeHtml(r.error || 'Nothing found.')}</div>`;
            return;
        }
        const c = r.center;
        const related = r.related || [];
        const works = related.filter(x => x.via === 'edge');
        const near = related.filter(x => x.via === 'area').slice(0, 3);
        const line = x => `<div class="glossary-entry-desc">&bull; <b>${escapeHtml(atlasName(x))}</b> — ${escapeHtml(firstSentence(x.description))}</div>`;
        out.innerHTML = `
            <div class="glossary-entry">
                <div class="glossary-entry-head"><span class="glossary-entry-name">${escapeHtml(atlasName(c))}</span></div>
                <div class="glossary-entry-desc">${escapeHtml(String(c.description || '').replace(/`/g, ''))}</div>
                ${c.key_fact ? `<div class="glossary-entry-meta">${escapeHtml(String(c.key_fact).replace(/`/g, ''))}</div>` : ''}
                <div class="glossary-entry-location">&#x1f4c1; ${escapeHtml(c.path)}</div>
                <div class="glossary-entry-connections"><b>Works with:</b></div>
                ${works.length ? works.map(line).join('') : '<div class="glossary-entry-desc">Nothing else is directly connected.</div>'}
                ${near.length ? `<div class="glossary-entry-connections"><b>Also in the same place:</b></div>${near.map(line).join('')}` : ''}
            </div>`;
    }

    document.getElementById('atlas-go')?.addEventListener('click', loadAtlas);
    document.getElementById('atlas-search')?.addEventListener('keydown', e => { if (e.key === 'Enter') loadAtlas(); });
    document.querySelector('.hud-nav-btn[data-hud-nav="atlas"]')?.addEventListener('click', () => {
        setTimeout(() => document.getElementById('atlas-search')?.focus(), 0);
    });

    // ── Boot ──────────────────────────────────────────────────────────────
    document.addEventListener('DOMContentLoaded', () => {
        loadSlots().then(mountGeneratedButtons);
    });
})();
