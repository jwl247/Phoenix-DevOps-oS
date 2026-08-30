// action-buttons.js
// Declarative registry for HUD right-column action buttons.
// Add a button = one object here. No HTML edits, no per-button wiring.
//
// Each entry:
//   id        unique button id (becomes element id="action-<id>")
//   label     main text
//   sub       small subtitle
//   panel     optional id of a panel div this button toggles (id="panel-<id>")
//   onClick   function(ctx) called on click; ctx = { invoke, slots, el, panel }
//   onMount   optional function(ctx) called once after the button is inserted
//
// The renderer (hud-layout.js) calls ActionButtons.mount() on boot.

const ActionButtons = {
    _registry: [],

    define(entry) {
        this._registry.push(entry);
        return this;
    },

    all() {
        return this._registry.slice();
    },

    // Build the button + optional panel markup and append to the right column.
    mount(container, ctx) {
        if (!container) return;
        this._registry.forEach(entry => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'hud-action-btn';
            btn.id = 'action-' + entry.id;
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
                panel
            };

            btn.addEventListener('click', () => {
                if (panel) panel.classList.toggle('open');
                if (typeof entry.onClick === 'function') entry.onClick(bound);
            });

            if (typeof entry.onMount === 'function') entry.onMount(bound);
        });
    }
};

// ── Built-in buttons ─────────────────────────────────────────────────────

ActionButtons
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
        id: 'guide',
        label: 'PHOENIX GUIDE',
        sub: 'ollama chat · manual · Laurie's guide',
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
        // panel content filled by hud-layout.js (keeps the search/list logic there)
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
    window.ActionButtons = ActionButtons;
}

module.exports = ActionButtons;
