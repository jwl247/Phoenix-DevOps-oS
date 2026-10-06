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

    // ── Folder bar (across the top) ─────────────────────────────────────
    // Fixed places HOME / ROOT / PHOENIX, then the 6 assignable slots. Each is
    // a dropdown listing EVERY entry of its folder (hidden files too). Click a
    // folder to go in, ↑ to go up. Drag files or folders from one
    // dropdown onto another (or onto a folder row) to COPY them; hold Shift to
    // MOVE. ✎ renames. Files dragged in from Explorer are copied. The main process
    // (slot-transfer.js) checks every request — this page only asks.
    const slotsState = { slots: [null, null, null, null, null, null], activeIndex: null };
    let placesList = [];
    const cols = {};                       // key -> { open, cwd, selected:Set, note }
    const DRAG_TYPE = 'application/x-phoenix-paths';
    const leaf = (p) => (p || '').replace(/[\\/]+$/, '').split(/[\\/]/).pop() || p;
    const parentOf = (p) => {
        const t = p.replace(/[\\/]+$/, '');
        const i = Math.max(t.lastIndexOf('/'), t.lastIndexOf('\\'));
        if (i < 0) return null;
        const up = t.slice(0, i + 1);
        return /^[A-Za-z]:\\$/.test(up) || up === '/' ? up : up.replace(/[\\/]$/, '');
    };
    const fmtSize = (n) => n == null ? '' : n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB`
        : n < 1073741824 ? `${(n / 1048576).toFixed(1)} MB` : `${(n / 1073741824).toFixed(2)} GB`;

    async function loadSlots() {
        const state = await invoke('get-dropdown-slots').catch(() => null);
        if (state) Object.assign(slotsState, state);      // mutate: the button ctx holds this object
        placesList = await invoke('slot-places').catch(() => []);
        renderSlots();
        renderStatusStrip();
    }

    function columns() {
        const list = placesList.map((p) => ({ key: 'place:' + p.key, label: p.label, root: p.path, drives: p.drives || null, place: true }));
        slotsState.slots.forEach((s, i) => list.push({ key: 'slot:' + i, label: s ? leaf(s).toUpperCase() : '+', root: s, index: i, place: false }));
        return list;
    }

    function colState(c) {
        if (!cols[c.key]) cols[c.key] = { open: false, cwd: c.root, selected: new Set(), note: '' };
        const st = cols[c.key];
        if (!st.cwd && c.root) st.cwd = c.root;        // a slot that just got a folder
        return st;
    }

    function renderSlots() {
        const bar = document.getElementById('hud-dropdown-slots');
        if (!bar) return;
        bar.innerHTML = '';
        for (const c of columns()) bar.appendChild(renderColumn(c));
    }

    function renderColumn(c) {
        const st = colState(c);
        const el = document.createElement('div');
        el.className = 'dropdown-slot' + (c.place ? ' place' : '') + (c.root || c.drives ? ' filled' : ' empty')
            + (!c.place && slotsState.activeIndex === c.index ? ' active-slot' : '') + (st.open ? ' open' : '');
        el.dataset.key = c.key;

        const head = document.createElement('div');
        head.className = 'slot-head';
        head.title = c.root || (c.drives ? 'every drive' : 'Drop a folder here from Explorer to make it a slot');
        head.innerHTML = `<span class="slot-caret">${c.root || c.drives ? (st.open ? '▴' : '▾') : ''}</span><span class="slot-path"></span>`;
        head.querySelector('.slot-path').textContent = c.root || c.drives ? c.label : `+ ${c.index + 1}`;
        if (!c.place && c.root) {
            const act = document.createElement('button');
            act.type = 'button'; act.className = 'slot-mini'; act.title = 'Make this the working directory (shell + Claude follow it)';
            act.textContent = '◉';
            act.addEventListener('click', (e) => { e.stopPropagation(); activateSlot(c.index); });
            const clr = document.createElement('button');
            clr.type = 'button'; clr.className = 'slot-mini'; clr.title = 'Clear this slot (the folder itself is not touched)';
            clr.textContent = '×';
            clr.addEventListener('click', (e) => { e.stopPropagation(); clearSlot(c.index); });
            head.append(act, clr);
        }
        head.addEventListener('click', () => {
            if (!(c.root || c.drives)) return;
            st.open = !st.open;
            renderSlots();
        });
        attachDrop(head, c, () => st.cwd || c.root);
        el.appendChild(head);

        if (st.open && (c.root || c.drives)) el.appendChild(renderPanel(c, st));
        return el;
    }

    function renderPanel(c, st) {
        const panel = document.createElement('div');
        panel.className = 'slot-panel';
        const crumb = document.createElement('div');
        crumb.className = 'slot-crumb';
        const up = document.createElement('button');
        up.type = 'button'; up.className = 'slot-mini'; up.textContent = '↑'; up.title = 'Up one folder';
        const atTop = c.drives && !c.root ? st.cwd === null : st.cwd === c.root;
        up.disabled = atTop;
        up.addEventListener('click', () => {
            const p = st.cwd ? parentOf(st.cwd) : null;
            // ROOT on Windows goes up from a drive root to the list of drives.
            st.cwd = (c.drives && !c.root && (st.cwd === p || p === null || /^[A-Za-z]:\\$/.test(st.cwd))) ? null : p;
            st.selected.clear(); renderSlots();
        });
        const where = document.createElement('span');
        where.className = 'slot-where';
        where.textContent = st.cwd || 'This PC — every drive';
        where.title = where.textContent;
        crumb.append(up, where);
        panel.appendChild(crumb);

        const list = document.createElement('div');
        list.className = 'slot-list';
        panel.appendChild(list);
        const note = document.createElement('div');
        note.className = 'slot-note';
        note.textContent = st.note || '';
        panel.appendChild(note);

        if (!st.cwd && c.drives) {
            for (const d of c.drives) list.appendChild(row(c, st, { name: d, path: d, isDir: true, size: null }));
        } else {
            list.textContent = 'reading…';
            invoke('slot-list', { dir: st.cwd }).then((r) => {
                list.textContent = '';
                if (!r.success) { list.textContent = r.error; return; }
                if (!r.items.length) list.textContent = '(empty folder)';
                for (const it of r.items) list.appendChild(row(c, st, it));
                where.textContent = `${st.cwd}  ·  ${r.items.length} item${r.items.length === 1 ? '' : 's'}`;
            }).catch((e) => { list.textContent = e.message; });
        }
        if (st.cwd) attachDrop(list, c, () => st.cwd);
        return panel;
    }

    function row(c, st, it) {
        const r = document.createElement('div');
        r.className = 'slot-row' + (it.isDir ? ' dir' : ' file') + (it.hidden ? ' hidden-entry' : '') + (st.selected.has(it.path) ? ' selected' : '');
        r.draggable = !(c.drives && !st.cwd);           // a drive itself is not draggable
        r.title = it.path + (it.link ? '  (link)' : '');
        r.dataset.path = it.path;
        r.innerHTML = '<span class="slot-ico"></span><span class="slot-name"></span><span class="slot-size"></span>';
        r.querySelector('.slot-ico').textContent = it.isDir ? '▸' : '·';
        r.querySelector('.slot-name').textContent = it.name;
        r.querySelector('.slot-size').textContent = fmtSize(it.size);
        // One click does it: a folder opens, a file gets selected. Ctrl-click picks
        // several (folders too) to drag together. ↗ on a file opens it.
        r.addEventListener('click', (e) => {
            if (e.ctrlKey || e.metaKey) {
                st.selected.has(it.path) ? st.selected.delete(it.path) : st.selected.add(it.path);
            } else if (it.isDir) {
                st.cwd = it.path; st.selected.clear(); renderSlots(); return;
            } else {
                st.selected.clear(); st.selected.add(it.path);
            }
            r.parentElement.querySelectorAll('.slot-row').forEach((x) => x.classList.toggle('selected', st.selected.has(x.dataset.path)));
        });
        if (!(c.drives && !st.cwd)) {
            const ren = document.createElement('button');
            ren.type = 'button'; ren.className = 'slot-mini slot-open'; ren.textContent = '✎'; ren.title = 'Rename';
            ren.addEventListener('click', (e) => { e.stopPropagation(); startRename(c, st, r, it); });
            r.appendChild(ren);
        }
        if (!it.isDir) {
            const open = document.createElement('button');
            open.type = 'button'; open.className = 'slot-mini slot-open'; open.textContent = '↗'; open.title = 'Open with its app';
            open.addEventListener('click', (e) => {
                e.stopPropagation();
                invoke('open-path', it.path).then((res) => { if (res && !res.success) alert(res.error); }).catch((err) => alert(err.message));
            });
            r.appendChild(open);
        }
        r.addEventListener('dragstart', (e) => {
            const paths = st.selected.has(it.path) ? [...st.selected] : [it.path];
            e.dataTransfer.setData(DRAG_TYPE, JSON.stringify(paths));
            e.dataTransfer.setData('text/plain', paths.join('\n'));
            e.dataTransfer.effectAllowed = 'copyMove';
        });
        if (it.isDir) attachDrop(r, c, () => it.path);
        return r;
    }

    function startRename(c, st, r, it) {
        const nameEl = r.querySelector('.slot-name');
        const input = document.createElement('input');
        input.className = 'slot-rename';
        input.value = it.name;
        r.draggable = false;
        nameEl.replaceWith(input);
        input.focus();
        const dot = it.isDir ? -1 : it.name.lastIndexOf('.');
        input.setSelectionRange(0, dot > 0 ? dot : it.name.length);     // like Explorer: the name, not the extension
        let done = false;
        const finish = async (save) => {
            if (done) return; done = true;
            const name = input.value.trim();
            if (save && name && name !== it.name) {
                const res = await invoke('slot-rename', { path: it.path, newName: name }).catch((e) => ({ success: false, error: e.message }));
                st.note = res.success ? `renamed to ${name}` : res.error;
                if (res.success && st.selected.delete(it.path)) st.selected.add(res.path);
            }
            renderSlots();
        };
        input.addEventListener('click', (e) => e.stopPropagation());
        input.addEventListener('keydown', (e) => { if (e.key === 'Enter') finish(true); if (e.key === 'Escape') finish(false); });
        input.addEventListener('blur', () => finish(true));
    }

    function attachDrop(el, c, destOf) {
        el.addEventListener('dragover', (e) => {
            const internal = e.dataTransfer.types.includes(DRAG_TYPE);
            if (!internal && !e.dataTransfer.types.includes('Files')) return;
            e.preventDefault(); e.stopPropagation();
            e.dataTransfer.dropEffect = internal && e.shiftKey ? 'move' : 'copy';
            el.classList.add('drag-over');
        });
        el.addEventListener('dragleave', () => el.classList.remove('drag-over'));
        el.addEventListener('drop', async (e) => {
            e.preventDefault(); e.stopPropagation();
            el.classList.remove('drag-over');
            const internal = e.dataTransfer.types.includes(DRAG_TYPE);
            const files = [...e.dataTransfer.files].map((f) => f.path).filter(Boolean);
            // An empty slot: a folder dropped from Explorer becomes the slot.
            if (!c.place && !c.root) {
                if (!files.length) return;
                const res = await invoke('set-dropdown-slot', { index: c.index, dirPath: files[0] });
                if (res.success) { slotsState.slots = res.slots; renderSlots(); } else alert(res.error);
                return;
            }
            const dest = destOf();
            if (!dest) return;
            const req = internal
                ? { sources: JSON.parse(e.dataTransfer.getData(DRAG_TYPE) || '[]'), toDir: dest, mode: e.shiftKey ? 'move' : 'copy' }
                : { sources: files, toDir: dest, mode: 'copy', external: true };
            if (!req.sources.length) return;
            const res = await invoke('slot-transfer', req).catch((err) => ({ success: false, error: err.message }));
            const st = colState(c);
            if (res.error) st.note = res.error;
            else {
                const verb = res.mode === 'copy' ? 'copied' : 'moved';
                st.note = `${res.done.length} ${verb} to ${leaf(dest)}`
                    + (res.skipped.length ? ` · ${res.skipped.length} skipped: ` + res.skipped.map((s) => `${s.name} (${s.reason})`).join('; ') : '');
            }
            Object.values(cols).forEach((s) => s.selected.clear());
            renderSlots();          // every open dropdown re-reads its folder
        });
    }

    async function activateSlot(i) {
        const result = await invoke('set-active-slot', { index: i });
        if (!result.success) return alert(result.error);
        previousActiveIndex = result.previousIndex ?? null;
        slotsState.activeIndex = i;
        renderSlots();
        renderStatusStrip();
    }

    async function clearSlot(i) {
        const result = await invoke('set-dropdown-slot', { index: i, dirPath: null });
        if (!result.success) return alert(result.error);
        slotsState.slots = result.slots;
        if (slotsState.activeIndex === i) slotsState.activeIndex = null;
        delete cols['slot:' + i];
        renderSlots();
        renderStatusStrip();
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
    // KITT HUD — WPF C# app. Exe path auto-resolved from repo hud/ directory;
    // falls back to dotnet run in dev. Click once to configure if needed.
    document.getElementById('switcher-hud')?.addEventListener('click', (e) => launchExternal('hud', e.currentTarget));

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
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');   // safe inside attributes too
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

    async function loadAtlas(pick) {
        const out = document.getElementById('atlas-result');
        const box = document.getElementById('atlas-search');
        if (typeof pick === 'string' && box) box.value = pick;
        const q = box?.value.trim();
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
        const near = related.filter(x => x.via === 'near' || x.via === 'area').slice(0, 3);
        // Every name is a link: click it to look that one up (walk the graph).
        const go = x => `<a href="#" class="atlas-go" data-path="${escapeHtml(x.path)}"><b>${escapeHtml(atlasName(x))}</b></a>`;
        const line = x => `<div class="glossary-entry-desc">&bull; ${go(x)} — ${escapeHtml(firstSentence(x.description))}</div>`;
        const cands = r.candidates || [];
        out.innerHTML = `
            ${cands.length ? `<div class="glossary-entry-meta">Did you mean: ${cands.map(go).join(' · ')}</div>` : ''}
            <div class="glossary-entry">
                <div class="glossary-entry-head"><span class="glossary-entry-name">${escapeHtml(atlasName(c))}</span></div>
                <div class="glossary-entry-desc">${escapeHtml(String(c.description || '').replace(/`/g, ''))}</div>
                ${c.key_fact ? `<div class="glossary-entry-meta">${escapeHtml(String(c.key_fact).replace(/`/g, ''))}</div>` : ''}
                <div class="glossary-entry-location">&#x1f4c1; ${escapeHtml(c.path)}</div>
                <div class="glossary-entry-connections"><b>Works with:</b></div>
                ${works.length ? works.map(line).join('') : '<div class="glossary-entry-desc">Nothing else is directly connected.</div>'}
                ${near.length ? `<div class="glossary-entry-connections"><b>Also nearby:</b></div>${near.map(line).join('')}` : ''}
            </div>`;
        out.querySelectorAll('.atlas-go').forEach(a => a.addEventListener('click', e => {
            e.preventDefault();
            loadAtlas(a.dataset.path);
        }));
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
