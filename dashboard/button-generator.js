// button-generator.js
// Scripted button factory. Define buttons as plain data — the generator
// builds the DOM, wires clicks, and mounts panels. No per-button HTML.
//
//   ButtonGenerator.define({ id, label, sub, panel, onClick, onMount })
//   ButtonGenerator.mount(container, ctx)
//
// ctx = { invoke, slots, el, panel, mode }  (mode = 'app' | 'hud')
//
// The renderer (hud-layout.js) calls ButtonGenerator.mount() on boot.
// Adding a button = one .define() call. That's it.

const ButtonGenerator = {
    _registry: [],

    define(entry) {
        if (!entry || !entry.id) throw new Error('ButtonGenerator.define: id required');
        this._registry.push(entry);
        return this;
    },

    all() { return this._registry.slice(); },

    clear() { this._registry = []; return this; },

    // Build every registered button into `container`.
    mount(container, ctx) {
        if (!container) return;
        container.innerHTML = '';
        this._registry.forEach(entry => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'hud-action-btn';
            btn.id = 'action-' + entry.id;
            btn.dataset.actionId = entry.id;
            btn.innerHTML = `${entry.label}<span class="action-sub">${entry.sub || ''}</span>`;
            container.appendChild(btn);

            let panel = null;
            if (entry.panel) {
                panel = document.createElement('div');
                panel.className = 'hud-action-panel';
                panel.id = 'panel-' + entry.id;
                container.appendChild(panel);
            }

            const bound = {
                invoke: ctx.invoke,
                slots: ctx.slots,
                el: btn,
                panel,
                mode: ctx.mode || 'app'
            };

            btn.addEventListener('click', () => {
                if (panel) panel.classList.toggle('open');
                if (typeof entry.onClick === 'function') entry.onClick(bound);
            });

            if (typeof entry.onMount === 'function') entry.onMount(bound);
        });
    },

    // Re-render a single button by id (e.g. after mode change).
    refresh(id, ctx) {
        const entry = this._registry.find(e => e.id === id);
        if (!entry) return;
        const btn = document.getElementById('action-' + id);
        if (!btn) return;
        btn.innerHTML = `${entry.label}<span class="action-sub">${entry.sub || ''}</span>`;
        if (typeof entry.onMount === 'function') {
            const panel = document.getElementById('panel-' + id);
            entry.onMount({ invoke: ctx.invoke, slots: ctx.slots, el: btn, panel, mode: ctx.mode || 'app' });
        }
    }
};

// ── Built-in buttons ─────────────────────────────────────────────────────
// Order here = visual order in the right column. Add anywhere.

ButtonGenerator
    .define({
        id: 'hud-toggle',
        label: 'HUD MODE',
        sub: 'toggle translucent glass overlay',
        onClick({ invoke, el }) {
            const original = el.textContent;
            el.textContent = 'switching...';
            invoke('hud-toggle').then(r => {
                el.textContent = original;
                if (!r.success) alert(r.error);
            }).catch(e => { el.textContent = original; alert(e.message); });
        }
    })
    .define({
        id: 'telemetry',
        label: 'TELEMETRY',
        sub: 'CPU / MEM / DISK / worker stats',
        onClick({ el }) {
            document.querySelector('.right-panel')?.classList.toggle('hud-telemetry-hidden');
        }
    })
    .define({
        id: 'google',
        label: 'GOOGLE',
        sub: 'open google.com in Chrome',
        onClick({ invoke }) {
            invoke('launch-google', { url: 'https://www.google.com' })
                .then(r => { if (!r.success) alert(r.error); })
                .catch(e => alert(e.message));
        }
    })
    .define({
        id: 'steam',
        label: 'STEAM',
        sub: 'open the Steam client',
        onClick({ invoke }) {
            invoke('launch-steam', {})
                .then(r => { if (!r.success) alert(r.error); })
                .catch(e => alert(e.message));
        }
    })
    .define({
        id: 'scriptforge',
        label: 'SCRIPTFORGE',
        sub: 'code lint · security scan · convert',
        onClick({ invoke, el }) {
            const original = el.textContent;
            el.textContent = 'opening...';
            invoke('launch-scriptforge', {})
                .then(r => { el.textContent = original; if (!r.success) alert(r.error); })
                .catch(e => { el.textContent = original; alert(e.message); });
        }
    })
    // ── PoC: Windows steers, Debian runs ─────────────────────────────────
    .define({
        id: 'poc-debian',
        label: 'DEBIAN ENGINE',
        sub: 'usys run debian -Persist — Helix warm',
        onClick({ invoke, el }) {
            const original = el.textContent;
            el.textContent = 'engaging...';
            invoke('execute-command', 'usys run debian -Persist')
                .then(r => {
                    el.textContent = original;
                    if (!r.success) alert(r.error || r.stderr || 'failed');
                })
                .catch(e => { el.textContent = original; alert(e.message); });
        }
    })
    .define({
        id: 'poc-helix',
        label: 'HELIX STATUS',
        sub: 'read shared snapshot + service state',
        panel: true,
        onClick({ invoke, panel }) {
            if (!panel) return;
            panel.innerHTML = 'reading...';
            Promise.all([
                invoke('execute-command', 'usys status').catch(e => ({ success: false, error: e.message })),
                invoke('read-file', 'F:/Phoenix/helix-pages/windows_snapshot.json').catch(e => ({ success: false, error: e.message }))
            ]).then(([status, snap]) => {
                const lines = [];
                if (status.success && status.output) lines.push(status.output.trim());
                else lines.push('usys status: ' + (status.error || 'unavailable'));
                if (snap.success && snap.content) {
                    try {
                        const j = JSON.parse(snap.content);
                        lines.push('snapshot: hot=' + j.hot_mb + ' warm=' + j.warm_mb +
                                   ' hit=' + j.hit_rate + ' @ ' + new Date(j.timestamp * 1000).toLocaleTimeString());
                    } catch (_) { lines.push('snapshot: ' + snap.content.slice(0, 120)); }
                } else {
                    lines.push('snapshot: ' + (snap.error || 'not readable'));
                }
                panel.innerHTML = '<pre style="white-space:pre-wrap;font-size:10px;margin:0;">' +
                    lines.join('\n\n') + '</pre>';
            });
        }
    })
    .define({
        id: 'poc-phoronix',
        label: 'PHORONIX',
        sub: 'run pts/smallpt on Debian via Phoenix',
        onClick({ invoke, el }) {
            const original = el.textContent;
            el.textContent = 'running...';
            // Runs the suite on the Debian side; results land in /phoenix/Projects/phoronix-results
            invoke('execute-command', 'usys run phoronix pts/smallpt')
                .then(r => {
                    el.textContent = original;
                    if (!r.success) alert(r.error || r.stderr || 'failed');
                })
                .catch(e => { el.textContent = original; alert(e.message); });
        }
    })
    .define({
        id: 'poc-watch',
        label: 'WATCH DOWNLOADS',
        sub: 'auto-intake everything in F:\\Phoenix\\Downloads',
        onClick({ invoke, el }) {
            const original = el.textContent;
            el.textContent = 'starting...';
            const script = (window.phoenixDashboard && window.phoenixDashboard._phoenixRoot
                ? window.phoenixDashboard._phoenixRoot
                : 'D:/Users/jwlef/Phoenix/Phoenix-DevOps-oS') +
                '/tools/poc/watch-downloads.ps1';
            invoke('run-file', { filePath: script, args: '' })
                .then(r => {
                    el.textContent = original;
                    if (!r.success) alert(r.error || r.stderr || 'failed');
                })
                .catch(e => { el.textContent = original; alert(e.message); });
        }
    })
    .define({
        id: 'poc-intake-now',
        label: 'INTAKE DOWNLOADS NOW',
        sub: 'one-shot phx-sync Downloads',
        onClick({ invoke, el }) {
            const original = el.textContent;
            el.textContent = 'intaking...';
            invoke('execute-command', 'phx-sync Downloads')
                .then(r => {
                    el.textContent = original;
                    if (!r.success) alert(r.error || r.stderr || 'failed');
                })
                .catch(e => { el.textContent = original; alert(e.message); });
        }
    })
    .define({
        id: 'guide',
        label: 'PHOENIX GUIDE',
        sub: "ollama chat · manual · Laurie's guide",
        onClick() {
            window.phoenixDashboard?._hudNavSwitch('guide');
        }
    })
    .define({
        id: 'venv',
        label: 'VENV',
        sub: 'auto-detect in active slot',
        panel: true,
        onClick({ invoke, slots, panel }) {
            if (!panel) return;
            if (slots.activeIndex === null) {
                panel.innerHTML = 'No active working-dir slot. Click a filled dropdown slot first.';
                return;
            }
            const dirPath = slots.slots[slots.activeIndex];
            panel.innerHTML = 'checking for venv...';
            invoke('detect-venv', { dirPath }).then(detected => {
                if (!detected.found) { panel.innerHTML = detected.error; return; }
                panel.innerHTML = `Found: ${detected.activateScript} <button id="venv-activate-btn">Activate in PS7</button>`;
                document.getElementById('venv-activate-btn')?.addEventListener('click', async () => {
                    const result = await invoke('activate-venv', { activateScript: detected.activateScript });
                    if (!result.success) alert(result.error);
                });
            });
        }
    })
    .define({
        id: 'run',
        label: 'RUN',
        sub: 'opens RUNIT drawer',
        onClick() {
            window.phoenixDashboard?._hudNavSwitch('codes');
            document.querySelector('.drawer-tab[data-drawer="runit"]')?.click();
        }
    })
    .define({
        id: 'ps7',
        label: 'OPEN PS7',
        onClick({ invoke, el }) {
            const original = el.textContent;
            el.textContent = 'launching...';
            invoke('launch-external-app', { key: 'ps7' }).then(r => {
                el.textContent = original;
                if (!r.success) {
                    if (r.needsConfig) {
                        invoke('open-exe-dialog', { title: 'Locate ps7' }).then(picked => {
                            if (picked.success) {
                                invoke('set-external-app-path', { key: 'ps7', exePath: picked.exePath })
                                    .then(sr => { if (sr.success) el.click(); else alert(sr.error); });
                            }
                        });
                    } else alert(r.error);
                }
            });
        }
    })
    .define({
        id: 'explorer',
        label: 'OPEN FILE EXPLORER',
        onClick({ invoke, slots }) {
            const dirPath = slots.activeIndex !== null ? slots.slots[slots.activeIndex] : null;
            if (!dirPath) {
                invoke('get-user-dirs').then(dirs => invoke('open-path', dirs.phoenix || dirs.home));
                return;
            }
            invoke('open-path', dirPath);
        }
    })
    .define({
        id: 'clonepool',
        label: 'CLONEPOOL',
        sub: 'clone / sync any intaked file',
        panel: true
    })
    .define({
        id: 'screenshot',
        label: 'SCREENSHOT',
        sub: 'single-shot, sent to Claude on request',
        panel: true,
        onClick({ invoke, panel }) {
            if (!panel) return;
            panel.innerHTML = 'capturing...';
            invoke('capture-screenshot').then(capture => {
                if (!capture.success) { panel.innerHTML = `<span style="color:var(--red-light)">${capture.error}</span>`; return; }
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
        }
    })
    .define({
        id: 'live-monitor',
        label: 'LIVE MONITOR',
        sub: 'periodic capture — Claude watches via file, no per-frame API cost',
        panel: true,
        onClick({ invoke, panel }) {
            if (!panel) return;
            const render = (status) => {
                panel.innerHTML = status.running
                    ? `<div style="font-size:10px;color:var(--green,#4ade80);margin-bottom:6px;">● live — capturing every ${status.intervalMs / 1000}s</div>
                       <button id="live-monitor-stop" class="hud-action-btn">Stop</button>`
                    : `<div style="font-size:10px;opacity:0.7;margin-bottom:6px;">not running</div>
                       <label style="font-size:10px;display:block;margin-bottom:4px;">interval: <span id="live-monitor-interval-val">10s</span></label>
                       <input type="range" id="live-monitor-interval" min="5" max="60" step="5" value="10" style="width:100%;margin-bottom:6px;">
                       <button id="live-monitor-start" class="hud-action-btn">Start</button>`;
                document.getElementById('live-monitor-stop')?.addEventListener('click', async () => {
                    await invoke('live-capture-stop');
                    render({ running: false });
                });
                const slider = document.getElementById('live-monitor-interval');
                slider?.addEventListener('input', () => {
                    document.getElementById('live-monitor-interval-val').textContent = `${slider.value}s`;
                });
                document.getElementById('live-monitor-start')?.addEventListener('click', async () => {
                    const intervalMs = (parseInt(slider?.value || '10', 10)) * 1000;
                    const result = await invoke('live-capture-start', { intervalMs });
                    render({ running: true, intervalMs: result.intervalMs || intervalMs });
                });
            };
            invoke('live-capture-status').then(render).catch(() => render({ running: false }));
        }
    });

// Expose for the renderer + let other scripts register more at runtime.
if (typeof window !== 'undefined') {
    window.ButtonGenerator = ButtonGenerator;
    // Back-compat alias so anything still calling ActionButtons keeps working.
    window.ActionButtons = ButtonGenerator;
}

// Guarded — this file is loaded as a plain <script> in the renderer (no
// CommonJS there). Only export when actually running under Node.
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ButtonGenerator;
}
