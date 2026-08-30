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
    // Legacy id-based handlers below remain as a fallback for any button
    // that isn't in the generator registry.

    function mountGeneratedButtons() {
        const container = document.getElementById('hud-right-column');
        if (!container || !window.ButtonGenerator) return;
        window.ButtonGenerator.mount(container, {
            invoke,
            slots: slotsState,
            mode: 'app'
        });
    }

    // 1. Telemetry — toggles visibility of the existing, already-real metrics panel
    document.getElementById('action-telemetry')?.addEventListener('click', () => {
        document.querySelector('.right-panel')?.classList.toggle('hud-telemetry-hidden');
    });

    // 2. Phoenix Guide — reuses existing GUIDE/HELP CHAT panes
    document.getElementById('action-guide')?.addEventListener('click', () => {
        window.phoenixDashboard?._hudNavSwitch('guide');
    });

    // 3. Venv — auto-detect against the active slot
    document.getElementById('action-venv')?.addEventListener('click', async () => {
        const panel = document.getElementById('panel-venv');
        if (!panel) return;
        panel.classList.add('open');
        if (slotsState.activeIndex === null) {
            panel.innerHTML = 'No active working-dir slot. Click a filled dropdown slot first.';
            return;
        }
        const dirPath = slotsState.slots[slots.activeIndex];
        panel.innerHTML = 'checking for venv...';
        const detected = await invoke('detect-venv', { dirPath });
        if (!detected.found) {
            panel.innerHTML = detected.error;
            return;
        }
        panel.innerHTML = `Found: ${detected.activateScript} <button id="venv-activate-btn">Activate in PS7</button>`;
        document.getElementById('venv-activate-btn')?.addEventListener('click', async () => {
            const result = await invoke('activate-venv', { activateScript: detected.activateScript });
            if (!result.success) alert(result.error);
        });
    });

    // 4. Run — reuses the existing RUNIT drawer by switching to CODES/runit tab
    document.getElementById('action-run')?.addEventListener('click', () => {
        window.phoenixDashboard?._hudNavSwitch('codes');
        document.querySelector('.drawer-tab[data-drawer="runit"]')?.click();
        if (slotsState.activeIndex !== null) {
            const dirPath = slotsState.slots[slotsState.activeIndex];
            const runitPath = document.getElementById('runit-path');
            if (runitPath && !runitPath.value) runitPath.placeholder = `${dirPath}\\...`;
        }
    });

    // 5. Open PS7 — same launcher as the switcher
    document.getElementById('action-ps7')?.addEventListener('click', (e) => launchExternal('ps7', e.currentTarget));

    // 6. Open File Explorer — existing open-path, targets active slot or PHOENIX_ROOT
    document.getElementById('action-explorer')?.addEventListener('click', async () => {
        const dirPath = slotsState.activeIndex !== null ? slotsState.slots[slotsState.activeIndex] : null;
        if (!dirPath) {
            const dirs = await invoke('get-user-dirs').catch(() => ({}));
            await invoke('open-path', dirs.phoenix || dirs.home);
            return;
        }
        await invoke('open-path', dirPath);
    });

    // 7. Clonepool browser
    let clonepoolSearchTimer = null;

    function renderClonepoolRows(panel, result) {
        const list = document.createElement('div');
        result.files.forEach(file => {
            const row = document.createElement('div');
            row.style.cssText = 'display:flex;justify-content:space-between;gap:6px;padding:4px 0;font-size:10px;border-bottom:1px solid rgba(255,255,255,0.06);';
            const name = document.createElement('span');
            name.textContent = file.relPath;
            name.title = file.relPath;
            name.style.cssText = 'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;';
            const cloneBtn = document.createElement('button');
            cloneBtn.textContent = 'CLONE';
            cloneBtn.className = 'hud-action-btn';
            cloneBtn.style.cssText = 'padding:2px 8px;font-size:9px;';
            cloneBtn.addEventListener('click', async () => {
                const dirResult = await invoke('open-directory-dialog', { title: 'Clone to...' });
                if (!dirResult.success) return;
                const cloneResult = await invoke('clone-file-to-workdir', {
                    sourcePath: file.absPath, targetDir: dirResult.dir, mode: 'clone'
                });
                alert(cloneResult.success ? `Cloned to ${cloneResult.destPath}` : cloneResult.error);
            });
            const syncBtn = document.createElement('button');
            syncBtn.textContent = 'SYNC';
            syncBtn.className = 'hud-action-btn';
            syncBtn.style.cssText = 'padding:2px 8px;font-size:9px;';
            syncBtn.addEventListener('click', async () => {
                const dirResult = await invoke('open-directory-dialog', { title: 'Sync to...' });
                if (!dirResult.success) return;
                const syncResult = await invoke('clone-file-to-workdir', {
                    sourcePath: file.absPath, targetDir: dirResult.dir, mode: 'sync'
                });
                if (!syncResult.success) { alert(syncResult.error); return; }
                alert(syncResult.copied ? `Synced to ${syncResult.destPath}` : 'Already up to date.');
            });
            row.appendChild(name);
            row.appendChild(cloneBtn);
            row.appendChild(syncBtn);
            list.appendChild(row);
        });
        return list;
    }

    async function loadClonepool(panel, query) {
        const status = panel.querySelector('.clonepool-status');
        const listSlot = panel.querySelector('.clonepool-list');
        if (status) status.textContent = 'loading...';
        const result = await invoke('list-clonepool-files', { query });
        if (!result.success) {
            if (status) status.textContent = '';
            listSlot.innerHTML = `<span style="color:var(--red-light)">${result.error}</span>`;
            return;
        }
        if (!result.files.length) {
            if (status) status.textContent = query ? `no matches for "${query}"` : 'clonepool is empty';
            listSlot.innerHTML = '';
            return;
        }
        if (status) {
            status.textContent = result.truncated
                ? `showing ${result.files.length} of ${result.matched}${query ? ` matching "${query}"` : ''} (${result.total} total — narrow with search)`
                : `${result.files.length}${query ? ` matching "${query}"` : ''} of ${result.total} total`;
        }
        listSlot.innerHTML = '';
        listSlot.appendChild(renderClonepoolRows(panel, result));
    }

    document.getElementById('action-clonepool')?.addEventListener('click', async () => {
        const panel = document.getElementById('panel-clonepool');
        if (!panel) return;
        panel.classList.toggle('open');
        if (!panel.classList.contains('open')) return;

        panel.innerHTML = `
            <input type="text" class="clonepool-search" placeholder="filter by path..."
                   style="width:100%;box-sizing:border-box;margin-bottom:6px;padding:4px 6px;font-size:10px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.12);color:inherit;">
            <div class="clonepool-status" style="font-size:9px;opacity:0.6;margin-bottom:4px;"></div>
            <div class="clonepool-list"></div>
        `;
        const searchInput = panel.querySelector('.clonepool-search');
        searchInput.addEventListener('input', () => {
            clearTimeout(clonepoolSearchTimer);
            clonepoolSearchTimer = setTimeout(() => loadClonepool(panel, searchInput.value), 250);
        });

        await loadClonepool(panel, '');
    });

    // 8. Screenshot — single-shot capture + optional Claude analysis
    document.getElementById('action-screenshot')?.addEventListener('click', async () => {
        const panel = document.getElementById('panel-screenshot');
        if (!panel) return;
        panel.classList.add('open');
        panel.innerHTML = 'capturing...';
        const capture = await invoke('capture-screenshot');
        if (!capture.success) {
            panel.innerHTML = `<span style="color:var(--red-light)">${capture.error}</span>`;
            return;
        }
        panel.innerHTML = `
            <img src="${capture.dataUrl}" style="max-width:100%;border-radius:4px;margin-bottom:8px;">
            <button id="screenshot-analyze-btn" class="hud-action-btn">Analyze with Claude</button>
            <div id="screenshot-analysis-result" style="margin-top:8px;font-size:10px;white-space:pre-wrap;"></div>
        `;
        document.getElementById('screenshot-analyze-btn')?.addEventListener('click', async () => {
            const resultEl = document.getElementById('screenshot-analysis-result');
            resultEl.textContent = 'analyzing...';
            const analysis = await invoke('analyze-screenshot', { filePath: capture.filePath });
            resultEl.textContent = analysis.success ? analysis.reply : analysis.error;
        });
    });

    // 8b. Live Monitor — periodic capture only, no per-tick API call. Writes
    // to a separate overwritten file (live/latest.png), not the watched
    // hud-screenshots/ folder the manual SCREENSHOT button uses — see
    // screenshot-analysis.js's LIVE_DIR comment for why mixing those would
    // spam a Claude-side file watcher with one event per tick.
    document.getElementById('action-live-monitor')?.addEventListener('click', async () => {
        const panel = document.getElementById('panel-live-monitor');
        if (!panel) return;
        panel.classList.toggle('open');
        if (!panel.classList.contains('open')) return;

        const renderPanel = (status) => {
            panel.innerHTML = status.running
                ? `<div style="font-size:10px;color:var(--green,#4ade80);margin-bottom:6px;">● live — capturing every ${status.intervalMs / 1000}s</div>
                   <button id="live-monitor-stop" class="hud-action-btn">Stop</button>`
                : `<div style="font-size:10px;opacity:0.7;margin-bottom:6px;">not running</div>
                   <label style="font-size:10px;display:block;margin-bottom:4px;">interval: <span id="live-monitor-interval-val">10s</span></label>
                   <input type="range" id="live-monitor-interval" min="5" max="60" step="5" value="10" style="width:100%;margin-bottom:6px;">
                   <button id="live-monitor-start" class="hud-action-btn">Start</button>`;

            document.getElementById('live-monitor-stop')?.addEventListener('click', async () => {
                await invoke('live-capture-stop');
                renderPanel({ running: false });
            });
            const slider = document.getElementById('live-monitor-interval');
            slider?.addEventListener('input', () => {
                document.getElementById('live-monitor-interval-val').textContent = `${slider.value}s`;
            });
            document.getElementById('live-monitor-start')?.addEventListener('click', async () => {
                const intervalMs = (parseInt(slider?.value || '10', 10)) * 1000;
                const result = await invoke('live-capture-start', { intervalMs });
                renderPanel({ running: true, intervalMs: result.intervalMs || intervalMs });
            });
        };

        const current = await invoke('live-capture-status').catch(() => ({ running: false }));
        renderPanel(current);
    });

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

    // ── Boot ──────────────────────────────────────────────────────────────
    document.addEventListener('DOMContentLoaded', () => {
        loadSlots().then(mountGeneratedButtons);
    });
})();
