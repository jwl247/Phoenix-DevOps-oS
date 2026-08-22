// hud-layout.js
// Renderer wiring for the HUD restructure. Loaded AFTER dashboard.js, so
// window.phoenixDashboard already exists and its real _hudNavSwitch /
// AI chat / MAP / RUNIT logic is reused, not duplicated.
//
// Everything here calls real IPC channels. Where a channel can fail
// (unconfigured app path, missing venv, worker route not deployed), the
// UI shows the real error text — nothing here fakes success.

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

    document.getElementById('switcher-glossary')?.addEventListener('click', async () => {
        const panel = document.getElementById('panel-glossary');
        if (!panel) return;
        panel.classList.toggle('open');
        if (!panel.classList.contains('open')) return;
        panel.innerHTML = 'loading glossary from D1...';
        const result = await invoke('get-glossary');
        if (!result.success) {
            panel.innerHTML = `<span style="color:var(--red-light)">${result.error}</span>`;
            return;
        }
        panel.innerHTML = `<pre style="white-space:pre-wrap;font-size:10px;">${JSON.stringify(result, null, 2)}</pre>`;
    });

    // ── Right column actions ─────────────────────────────────────────────

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
        const dirPath = slotsState.slots[slotsState.activeIndex];
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

    // 9. PS7 SHELL — embedded, unrestricted (unlike the gated PHOENIX CLI)
    let ps7ShellHistory = [];
    let ps7ShellHistoryPos = 0;

    function ps7ShellAppend(html) {
        const out = document.getElementById('ps7-shell-output');
        if (!out) return;
        const line = document.createElement('div');
        line.innerHTML = html;
        out.appendChild(line);
        out.scrollTop = out.scrollHeight;
    }

    function ps7ShellSetCwd(cwd) {
        const cwdEl = document.getElementById('ps7-shell-cwd');
        if (cwdEl) cwdEl.textContent = `${cwd}>`;
    }

    // Lives as a full HUD nav pane (same size/placement as AI CHAT) rather
    // than a small right-column popout — dashboard.js's generic
    // .hud-nav-btn[data-hud-nav] listener already handles showing the pane;
    // this just loads the tracked cwd and focuses the input on switch-in.
    document.querySelector('.hud-nav-btn[data-hud-nav="ps7-shell"]')?.addEventListener('click', async () => {
        const state = await invoke('ps7-shell-get-cwd').catch(() => null);
        if (state) ps7ShellSetCwd(state.cwd);
        document.getElementById('ps7-shell-input')?.focus();
    });

    document.getElementById('ps7-shell-input')?.addEventListener('keydown', async (e) => {
        const input = e.currentTarget;
        if (e.key === 'ArrowUp') {
            e.preventDefault();
            if (!ps7ShellHistory.length) return;
            ps7ShellHistoryPos = Math.max(0, ps7ShellHistoryPos - 1);
            input.value = ps7ShellHistory[ps7ShellHistoryPos] || '';
            return;
        }
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            ps7ShellHistoryPos = Math.min(ps7ShellHistory.length, ps7ShellHistoryPos + 1);
            input.value = ps7ShellHistory[ps7ShellHistoryPos] || '';
            return;
        }
        if (e.key !== 'Enter') return;

        const command = input.value;
        if (!command.trim()) return;
        ps7ShellHistory.push(command);
        ps7ShellHistoryPos = ps7ShellHistory.length;

        const cwdEl = document.getElementById('ps7-shell-cwd');
        const promptText = cwdEl ? cwdEl.textContent : '>';
        const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        ps7ShellAppend(`<span class="ps7-shell-prompt">${esc(promptText)}</span> <span class="ps7-shell-cmd">${esc(command)}</span>`);

        input.value = '';
        input.disabled = true;
        const result = await invoke('ps7-shell-run', { command }).catch(e => ({ success: false, error: e.message }));
        input.disabled = false;
        input.focus();

        if (result.cwd) ps7ShellSetCwd(result.cwd);
        if (result.output) ps7ShellAppend(`<span class="ps7-shell-stdout">${esc(result.output).replace(/\n/g, '<br>')}</span>`);
        if (!result.success && result.error) {
            ps7ShellAppend(`<span class="ps7-shell-stderr">${esc(result.error).replace(/\n/g, '<br>')}</span>`);
        }
    });

    // ── Boot ──────────────────────────────────────────────────────────────
    document.addEventListener('DOMContentLoaded', () => {
        loadSlots();
    });
})();
