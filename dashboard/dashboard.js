// Phoenix DevOps OS - Command Center Dashboard JavaScript
// Handles interactivity, data updates, and Phoenix integration
// Electron-enabled version with real Phoenix command execution

// Check if running in Electron
const isElectron = typeof window !== 'undefined' && !!window.phoenix;
let ipcRenderer = null;

if (isElectron) {
    ipcRenderer = window.phoenix;
    console.log('Running in Electron - Real Phoenix integration enabled');
} else {
    console.log('Running in browser - Using simulated data');
}

const SECTOR_META = {
    '1': {
        label: 'Sector 1',
        statusCmd: 'usys status',
        folderKey: '1',
        presets: ['usys status'],
        gatedPrefixes: [],
        hint: 'Boot/kernel — sector1/, frank3, GRUB. ON enables boot-path checks.'
    },
    '2': {
        label: 'Sector 2',
        statusCmd: 'intake status',
        folderKey: '2',
        presets: ['intake status', 'usys clone'],
        gatedPrefixes: ['intake', 'usys clone'],
        hint: 'Packages/clone — intake, clonepool. ON enables intake + clone commands.'
    },
    '3': {
        label: 'Sector 3',
        statusCmd: 'usys status',
        folderKey: '3',
        presets: ['usys status'],
        gatedPrefixes: [],
        hint: 'Comms/network — sector3/services/, dashboard units. ON lists service files.'
    },
    '4': {
        label: 'Sector 4',
        statusCmd: 'usys status',
        folderKey: '4',
        presets: ['usys status', 'usys search'],
        gatedPrefixes: ['usys search'],
        hint: 'Helix/Frank — SECTOR4/, vault. ON enables vault search commands.'
    },
    helix: {
        label: 'Helix Engine',
        statusCmd: 'usys status',
        folderKey: 'helix',
        presets: ['usys status'],
        gatedPrefixes: [],
        hint: 'C-core — phoenix-core/ ingress/egress. ON monitors engine path.'
    }
};

const RUNIT_EXTS = new Set(['.ps1', '.sh', '.py', '.js', '.mjs', '.cjs', '.exe', '.cmd', '.bat', '.com']);

class PhoenixDashboard {
    constructor() {
        this._sectorState = this._loadSectorState();
        this._activeSector = this._sectorState.active || 'helix';
        this._sectorPaths = {};
        this._drawerPane = 'cli';
        this.init();
        this.setupEventListeners();
        this.startDataUpdates();
        this.initCanvas();
    }

    init() {
        this.updateTime();
        setInterval(() => this.updateTime(), 1000);
        this.initSwitches();
        this.initControlPanel();
        this.initOperatorDrawer();
        this.initNavBar();
        this.initHelpDeskHUD();
    }

    updateTime() {
        const now = new Date();
        const timeStr = now.toLocaleTimeString('en-US', { 
            hour12: false, 
            hour: '2-digit', 
            minute: '2-digit', 
            second: '2-digit' 
        });
        const dateStr = now.toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: '2-digit'
        });
        document.getElementById('system-time').textContent = `${dateStr} ${timeStr}`;
    }

    _loadSectorState() {
        const defaults = { active: 'helix', sectors: { '1': false, '2': false, '3': false, '4': false, helix: true } };
        try {
            const raw = localStorage.getItem('phoenix_sector_state');
            if (!raw) return defaults;
            const parsed = JSON.parse(raw);
            return { ...defaults, ...parsed, sectors: { ...defaults.sectors, ...parsed.sectors } };
        } catch {
            return defaults;
        }
    }

    _saveSectorState() {
        localStorage.setItem('phoenix_sector_state', JSON.stringify(this._sectorState));
    }

    _applySwitchVisual(sector, isActive) {
        const sw = document.querySelector(`.toggle-switch[data-sector="${sector}"]`);
        if (!sw) return;
        sw.classList.toggle('active', isActive);
        const light = sw.querySelector('.switch-light');
        if (light) light.classList.toggle('active', isActive);
    }

    initSwitches() {
        Object.entries(this._sectorState.sectors).forEach(([sector, on]) => {
            this._applySwitchVisual(sector, !!on);
        });
        this._updateSectorHint();

        document.querySelectorAll('.toggle-switch').forEach(sw => {
            sw.addEventListener('click', () => {
                const sector = sw.dataset.sector;
                const isActive = !sw.classList.contains('active');
                this._applySwitchVisual(sector, isActive);
                this.handleSectorToggle(sector, isActive);
            });
        });
    }

    async handleSectorToggle(sector, isActive) {
        this._sectorState.sectors[sector] = isActive;
        if (isActive) {
            this._activeSector = sector;
            this._sectorState.active = sector;
        } else if (this._activeSector === sector) {
            const fallback = Object.entries(this._sectorState.sectors)
                .find(([id, on]) => on && id !== sector);
            this._activeSector = fallback ? fallback[0] : 'helix';
            this._sectorState.active = this._activeSector;
        }
        this._saveSectorState();
        this._updateSectorHint();
        this._refreshCliPresets();
        this._renderSectorMap();

        const meta = SECTOR_META[sector];
        const label = meta?.label || `Sector ${sector}`;
        this._cliLine(`[${label}] ${isActive ? 'ENABLED' : 'DISABLED'}`, isActive ? 'cli-ok' : 'cli-warn');

        if (isActive && meta?.statusCmd) {
            await this.runPhoenixCli(meta.statusCmd, { sector, silentGate: true });
        }
    }

    _updateSectorHint() {
        const el = document.getElementById('sector-hint');
        if (!el) return;
        const meta = SECTOR_META[this._activeSector];
        const on = this._sectorState.sectors[this._activeSector];
        const state = on ? 'ON' : 'OFF';
        el.textContent = meta
            ? `${meta.label} (${state}) — ${meta.hint}`
            : 'Switches gate sector subsystems. ON = monitor + enable CLI commands for that sector.';
    }

    _isSectorEnabled(sector) {
        return !!this._sectorState.sectors[sector];
    }

    _sectorForCommand(cmd) {
        const lower = (cmd || '').trim().toLowerCase();
        if (lower.startsWith('intake') || lower.startsWith('usys clone')) return '2';
        if (lower.startsWith('usys search')) return '4';
        return null;
    }

    _commandAllowed(cmd) {
        const gate = this._sectorForCommand(cmd);
        if (!gate) return true;
        return this._isSectorEnabled(gate);
    }

    async initControlPanel() {
        if (isElectron && ipcRenderer) {
            try {
                this._sectorPaths = await ipcRenderer.invoke('get-sector-paths') || {};
            } catch (_) {
                this._sectorPaths = {};
            }
        }

        const runBtn = document.getElementById('sector-action-run');
        if (runBtn) {
            runBtn.addEventListener('click', () => this._runSectorAction());
        }

        document.querySelectorAll('.control-btn.small[data-cmd]').forEach(btn => {
            btn.addEventListener('click', () => {
                const cmd = btn.dataset.cmd;
                if (cmd) this.runPhoenixCli(cmd);
            });
        });

        this._refreshCliPresets();
        this._renderSectorMap();
    }

    _refreshCliPresets() {
        const select = document.getElementById('cli-preset');
        if (!select) return;
        const meta = SECTOR_META[this._activeSector];
        const presets = new Set(['usys status', 'intake status', 'usys clone', 'usys search', 'help']);
        if (meta?.presets) meta.presets.forEach(p => presets.add(p));

        const current = select.value;
        select.innerHTML = '<option value="">— preset —</option>';
        for (const p of presets) {
            const opt = document.createElement('option');
            opt.value = p;
            opt.textContent = p;
            select.appendChild(opt);
        }
        if ([...select.options].some(o => o.value === current)) select.value = current;
    }

    async _runSectorAction() {
        const action = document.getElementById('sector-action-select')?.value || 'status';
        const sector = this._activeSector;
        const meta = SECTOR_META[sector];

        if (!this._isSectorEnabled(sector)) {
            this._cliLine(`[${meta?.label || sector}] switch is OFF — turn it ON first`, 'cli-warn');
            return;
        }

        if (action === 'status') {
            await this.runPhoenixCli(meta?.statusCmd || 'usys status', { sector });
            return;
        }

        if (action === 'open') {
            const folder = this._sectorPaths[meta?.folderKey || sector];
            if (!folder) {
                this._cliLine(`[${meta?.label}] folder not found on disk`, 'cli-err');
                return;
            }
            if (isElectron && ipcRenderer) {
                const result = await ipcRenderer.invoke('open-path', folder);
                if (result.success) {
                    this._cliLine(`opened ${folder}`, 'cli-ok');
                    await this.navigateTo(folder, null);
                } else {
                    this._cliLine(result.error || 'open failed', 'cli-err');
                }
            }
            return;
        }

        if (action === 'services') {
            const base = this._sectorPaths['3'];
            if (!base) {
                this._cliLine('sector3 path not found', 'cli-err');
                return;
            }
            const servicesDir = base.replace(/[/\\]$/, '') + (base.includes('\\') ? '\\services' : '/services');
            if (isElectron && ipcRenderer) {
                const listing = await ipcRenderer.invoke('list-directory', servicesDir);
                if (!listing.success) {
                    this._cliLine(listing.error || 'services folder missing', 'cli-err');
                    return;
                }
                this._cliLine(`[Sector 3 services] ${servicesDir}`, 'cli-system');
                for (const item of listing.items.sort((a, b) => a.name.localeCompare(b.name))) {
                    this._cliLine(`  ${item.isDirectory ? '📁' : '·'} ${item.name}`, 'cli-dim');
                }
            }
        }
    }

    initOperatorDrawer() {
        document.querySelectorAll('.drawer-tab[data-drawer]').forEach(tab => {
            tab.addEventListener('click', () => this._switchDrawerPane(tab.dataset.drawer));
        });

        const collapse = document.getElementById('drawer-collapse');
        const drawer = document.getElementById('operator-drawer');
        if (collapse && drawer) {
            const syncDrawer = () => {
                collapse.textContent = drawer.classList.contains('collapsed') ? '▼' : '▲';
            };
            syncDrawer();
            collapse.addEventListener('click', () => {
                drawer.classList.toggle('collapsed');
                syncDrawer();
            });
        }

        const preset = document.getElementById('cli-preset');
        const cliInput = document.getElementById('cli-input');
        if (preset && cliInput) {
            preset.addEventListener('change', () => {
                if (preset.value) cliInput.value = preset.value;
            });
        }

        document.getElementById('cli-run')?.addEventListener('click', () => {
            const cmd = cliInput?.value?.trim();
            if (cmd) this.runPhoenixCli(cmd);
        });
        document.getElementById('cli-clear')?.addEventListener('click', () => this._clearCliOutput());
        cliInput?.addEventListener('keydown', e => {
            if (e.key === 'Enter') {
                const cmd = cliInput.value.trim();
                if (cmd) this.runPhoenixCli(cmd);
            }
        });

        document.getElementById('runit-browse')?.addEventListener('click', () => this._runitBrowse());
        document.getElementById('runit-run')?.addEventListener('click', () => this._runitExecute());
        document.getElementById('runit-path')?.addEventListener('keydown', e => {
            if (e.key === 'Enter') this._runitExecute();
        });

        const drop = document.getElementById('runit-drop');
        if (drop) {
            ['dragenter', 'dragover'].forEach(evt => {
                drop.addEventListener(evt, e => {
                    e.preventDefault();
                    e.stopPropagation();
                    drop.classList.add('drag-over');
                });
            });
            ['dragleave', 'drop'].forEach(evt => {
                drop.addEventListener(evt, e => {
                    e.preventDefault();
                    e.stopPropagation();
                    drop.classList.remove('drag-over');
                });
            });
            drop.addEventListener('drop', e => {
                const file = e.dataTransfer?.files?.[0];
                if (file?.path) this._setRunitPath(file.path);
            });
            drop.addEventListener('click', () => this._runitBrowse());
        }
    }

    _switchDrawerPane(pane) {
        this._drawerPane = pane;
        document.querySelectorAll('.drawer-tab[data-drawer]').forEach(t => {
            t.classList.toggle('active', t.dataset.drawer === pane);
        });
        document.getElementById('drawer-cli')?.classList.toggle('active', pane === 'cli');
        document.getElementById('drawer-runit')?.classList.toggle('active', pane === 'runit');
        const drawer = document.getElementById('operator-drawer');
        if (drawer) drawer.classList.remove('collapsed');
        const collapse = document.getElementById('drawer-collapse');
        if (collapse) collapse.textContent = '▲';
    }

    _cliLine(text, className = '') {
        const out = document.getElementById('cli-output');
        if (!out) return;
        const line = document.createElement('div');
        line.className = `cli-line ${className}`.trim();
        line.textContent = text;
        out.appendChild(line);
        out.scrollTop = out.scrollHeight;
    }

    _runitLine(text, className = '') {
        const out = document.getElementById('runit-output');
        if (!out) return;
        const line = document.createElement('div');
        line.className = `runit-line ${className}`.trim();
        line.textContent = text;
        out.appendChild(line);
        out.scrollTop = out.scrollHeight;
    }

    _clearCliOutput() {
        const out = document.getElementById('cli-output');
        if (!out) return;
        out.innerHTML = `
            <div class="cli-line cli-system">Phoenix DevOps OS — type commands below or pick from dropdown</div>
            <div class="cli-line cli-dim">Sector switches on the left gate which subsystems are active.</div>
        `;
    }

    async runPhoenixCli(cmd, opts = {}) {
        const trimmed = (cmd || '').trim();
        if (!trimmed) return;

        if (!opts.silentGate && !this._commandAllowed(trimmed)) {
            const gate = this._sectorForCommand(trimmed);
            const meta = SECTOR_META[gate];
            this._cliLine(`blocked: ${meta?.label || `Sector ${gate}`} switch is OFF`, 'cli-warn');
            return;
        }

        this._hudNavSwitch('codes');
        this._switchDrawerPane('cli');
        this._cliLine(`> ${trimmed}`, 'cli-cmd');

        if (!isElectron || !ipcRenderer) {
            this._cliLine('(simulated) command would run in Electron desktop', 'cli-dim');
            return;
        }

        try {
            const result = await ipcRenderer.invoke('execute-command', trimmed);
            if (result.output) {
                result.output.split(/\r?\n/).forEach(line => {
                    if (line) this._cliLine(line);
                });
            }
            if (result.stderr) {
                result.stderr.split(/\r?\n/).forEach(line => {
                    if (line) this._cliLine(line, 'cli-warn');
                });
            }
            if (result.success) {
                this._cliLine('ok', 'cli-ok');
            } else {
                this._cliLine(result.error || 'command failed', 'cli-err');
            }
        } catch (e) {
            this._cliLine(e.message, 'cli-err');
        }
    }

    async _runitBrowse() {
        if (!isElectron || !ipcRenderer) return;
        const result = await ipcRenderer.invoke('open-file-dialog', {
            title: 'Select script to RUNIT',
            properties: ['openFile'],
            filters: [
                { name: 'Runnable', extensions: ['ps1', 'sh', 'py', 'js', 'exe', 'cmd', 'bat'] },
                { name: 'All', extensions: ['*'] }
            ]
        });
        if (!result.canceled && result.filePaths?.[0]) {
            this._setRunitPath(result.filePaths[0]);
        }
    }

    _setRunitPath(filePath) {
        const ext = (filePath.match(/\.[^.\\/]+$/) || [''])[0].toLowerCase();
        if (ext && !RUNIT_EXTS.has(ext)) {
            this._runitLine(`unsupported type: ${ext}`, 'cli-warn');
            return;
        }
        const input = document.getElementById('runit-path');
        if (input) input.value = filePath;
        this._hudNavSwitch('codes');
        this._switchDrawerPane('runit');
        const drop = document.getElementById('runit-drop');
        drop?.classList.add('has-file');
        const label = drop?.querySelector('.runit-drop-label');
        if (label) label.textContent = filePath.split(/[/\\]/).pop();
    }

    async _runitExecute() {
        const filePath = document.getElementById('runit-path')?.value?.trim();
        const args = document.getElementById('runit-args')?.value?.trim() || '';
        if (!filePath) {
            this._runitLine('no file — drop, browse, or click a file in the tree', 'cli-warn');
            return;
        }

        this._hudNavSwitch('codes');
        this._switchDrawerPane('runit');
        this._runitLine(`▶ ${filePath}${args ? ' ' + args : ''}`, 'cli-cmd');

        if (!isElectron || !ipcRenderer) {
            this._runitLine('(simulated) RUNIT requires Electron', 'cli-dim');
            return;
        }

        try {
            const result = await ipcRenderer.invoke('run-file', { filePath, args });
            if (result.command) this._runitLine(result.command, 'cli-dim');
            if (result.output) {
                result.output.split(/\r?\n/).forEach(line => {
                    if (line) this._runitLine(line);
                });
            }
            if (result.stderr) {
                result.stderr.split(/\r?\n/).forEach(line => {
                    if (line) this._runitLine(line, 'cli-warn');
                });
            }
            if (result.success) {
                this._runitLine('exit 0', 'cli-ok');
            } else {
                this._runitLine(result.error || 'run failed', 'cli-err');
            }
        } catch (e) {
            this._runitLine(e.message, 'cli-err');
        }
    }

    _bindFileItem(el, item) {
        if (!item?.path || item.isDirectory) return;
        const ext = (item.name.match(/\.[^.]+$/) || [''])[0].toLowerCase();
        if (!RUNIT_EXTS.has(ext)) return;

        el.classList.add('place-runnable');
        el.title = 'Click → RUNIT drawer · double-click → run';

        const runBtn = document.createElement('button');
        runBtn.type = 'button';
        runBtn.className = 'place-run-btn';
        runBtn.textContent = '▶';
        runBtn.title = 'RUNIT';
        runBtn.addEventListener('click', e => {
            e.stopPropagation();
            this._setRunitPath(item.path);
            this._runitExecute();
        });
        el.appendChild(runBtn);

        el.addEventListener('click', e => {
            if (e.target === runBtn) return;
            this._setRunitPath(item.path);
        });
        el.addEventListener('dblclick', e => {
            e.preventDefault();
            this._setRunitPath(item.path);
            this._runitExecute();
        });
    }

    setupEventListeners() {
        // Nav bar — location buttons
        document.querySelectorAll('.nav-btn[data-navkey]').forEach(btn => {
            btn.addEventListener('click', () => {
                const key = btn.dataset.navkey;
                const p = this._userDirs?.[key];
                if (p) this.navigateTo(p, btn);
            });
        });

        // Terminal overlay
        const terminalClose = document.getElementById('terminal-close');
        if (terminalClose) {
            terminalClose.addEventListener('click', () => {
                document.getElementById('terminal-overlay').style.display = 'none';
            });
        }
    }

    // ── Navigation ─────────────────────────────────────────────────────────────
    async navigateTo(dirPath, activeBtn) {
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.root-tree-btn').forEach(b => b.classList.remove('active'));
        if (activeBtn) {
            activeBtn.classList.add('active');
        }
        document.getElementById('nav-path').textContent = dirPath;

        const container = document.getElementById('fs-places');
        container.innerHTML = '<div class="place-loading">reading...</div>';

        if (!isElectron || !ipcRenderer) {
            container.innerHTML = '<div class="place-loading">filesystem not available outside Electron</div>';
            return;
        }

        try {
            const result = await ipcRenderer.invoke('list-directory', dirPath);
            if (!result.success) throw new Error(result.error);

            const SKIP = new Set(['.git', 'node_modules', '.metadata']);
            const items = result.items.filter(i => !SKIP.has(i.name));
            const dirs  = items.filter(i => i.isDirectory).sort((a, b) => a.name.localeCompare(b.name));
            const files = items.filter(i => !i.isDirectory).sort((a, b) => a.name.localeCompare(b.name));

            if (!dirs.length && !files.length) {
                container.innerHTML = '<div class="place-loading">empty</div>';
                return;
            }

            container.innerHTML = '';
            for (const dir of dirs) container.appendChild(this._makePlaceBox(dir.name, dir.path));
            // Files that aren't inside a dir go in a single "files" box
            if (files.length) {
                const box = this._makePlaceBox(`— ${files.length} file${files.length > 1 ? 's' : ''}`, null, files);
                container.appendChild(box);
            }
        } catch (e) {
            container.innerHTML = `<div class="place-loading">error: ${e.message}</div>`;
        }
    }

    async initNavBar() {
        if (!isElectron || !ipcRenderer) return;

        const [userDirs, drives] = await Promise.all([
            ipcRenderer.invoke('get-user-dirs').catch(() => ({})),
            ipcRenderer.invoke('get-drives').catch(() => [])
        ]);
        this._userDirs = userDirs;

        // Wire the static nav buttons — hide any whose path doesn't exist
        document.querySelectorAll('.nav-btn[data-navkey]').forEach(btn => {
            const key = btn.dataset.navkey;
            if (!userDirs[key]) btn.style.display = 'none';
        });

        // Add root/drive buttons dynamically
        const rootGroup = document.getElementById('nav-root');
        if (rootGroup) {
            const rootKeys = [
                'root', 'mnt', 'opt', 'etc', 'usr', 'var', 'home_root', 'tmp', 'srv', 'media',
                'users', 'program_files', 'program_files_x86', 'windows', 'bin', 'sbin', 'boot'
            ];
            rootKeys.forEach(k => {
                if (!userDirs[k]) return;
                const btn = document.createElement('button');
                btn.className = 'nav-btn';
                const navLabels = {
                    home_root: '/home', users: 'Users',
                    program_files: 'Program Files', program_files_x86: 'Program Files (x86)',
                    windows: 'Windows', root: userDirs[k] || '/'
                };
                btn.textContent = navLabels[k] || `/${k}`;
                btn.addEventListener('click', () => this.navigateTo(userDirs[k], btn));
                rootGroup.appendChild(btn);
            });
            // Windows drives
            drives.forEach(d => {
                const btn = document.createElement('button');
                btn.className = 'nav-btn';
                btn.textContent = d.name;
                btn.addEventListener('click', () => this.navigateTo(d.path, btn));
                rootGroup.appendChild(btn);
            });
            if (!rootGroup.children.length) rootGroup.style.display = 'none';
        }

        this._initFrequentDirs();
        await this._initRootTree();

        const phoenixRoot = userDirs['phoenix'];
        if (phoenixRoot) {
            const phoenixBtn = document.querySelector('.nav-btn[data-navkey="phoenix"]');
            this.navigateTo(phoenixRoot, phoenixBtn);
        }
    }

    async _initRootTree() {
        const container = document.getElementById('root-tree');
        if (!container) return;

        if (!isElectron || !ipcRenderer) {
            container.innerHTML = '<span class="place-loading">root tree requires Electron</span>';
            return;
        }

        try {
            const entries = await ipcRenderer.invoke('get-root-tree');
            if (!entries?.length) {
                container.innerHTML = '<span class="place-loading">no root entries</span>';
                return;
            }

            container.innerHTML = '';
            for (const entry of entries) {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'root-tree-btn';
                btn.textContent = entry.label;
                btn.title = entry.path;
                if (entry.group) btn.dataset.group = entry.group;
                btn.addEventListener('click', () => this.navigateTo(entry.path, btn));
                container.appendChild(btn);
            }
        } catch (e) {
            container.innerHTML = `<span class="place-loading">root error: ${e.message}</span>`;
        }
    }

    _initFrequentDirs() {
        const STORAGE_KEY = 'phoenix_frequent_dirs';
        const load = () => { try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'); } catch { return []; } };
        const save = (list) => localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
        const render = () => {
            const list = load();
            const container = document.getElementById('frequent-list');
            if (!container) return;
            container.innerHTML = '';
            list.forEach((p, i) => {
                const entry = document.createElement('div');
                entry.className = 'frequent-entry';
                const pathBtn = document.createElement('button');
                pathBtn.className = 'frequent-path-btn';
                pathBtn.textContent = p;
                pathBtn.title = p;
                pathBtn.addEventListener('click', () => this.navigateTo(p, null));
                const rm = document.createElement('button');
                rm.className = 'frequent-remove';
                rm.textContent = '×';
                rm.addEventListener('click', () => { const l = load(); l.splice(i, 1); save(l); render(); });
                entry.appendChild(pathBtn);
                entry.appendChild(rm);
                container.appendChild(entry);
            });
        };
        render();

        const addBtn   = document.getElementById('frequent-add');
        const inputRow = document.getElementById('frequent-input-row');
        const input    = document.getElementById('frequent-input');
        const saveBtn  = document.getElementById('frequent-save');

        if (addBtn) {
            addBtn.addEventListener('click', () => {
                inputRow.style.display = inputRow.style.display === 'none' ? 'flex' : 'none';
                if (inputRow.style.display === 'flex') input.focus();
            });
        }
        const commit = () => {
            const val = input.value.trim();
            if (!val) return;
            const list = load();
            if (!list.includes(val)) { list.push(val); save(list); }
            input.value = '';
            inputRow.style.display = 'none';
            render();
        };
        if (saveBtn) saveBtn.addEventListener('click', commit);
        if (input)   input.addEventListener('keydown', e => { if (e.key === 'Enter') commit(); if (e.key === 'Escape') inputRow.style.display = 'none'; });
    }

    showHelixEngine() {
        this.showTerminal();
        this.addTerminalLine('=== HELIX ENGINE STATUS ===');
        this.addTerminalLine('Languages: NOSQL / VECTOR / RELATIONAL / TIMESERIES');
        this.addTerminalLine('Compression: zlib level 5');
        this.addTerminalLine('Status: not yet benchmarked on this build');
    }

    showCatalog() {
        this.showTerminal();
        this.executeCommand('usys search ""');
    }

    showSecurity() {
        this.showTerminal();
        this.addTerminalLine('=== SECURITY STATUS ===');
        this.addTerminalLine('REALsure Security: ACTIVE');
        this.addTerminalLine('Installer Guardian: MONITORING');
        this.addTerminalLine('User Scope: ENFORCED');
        this.addTerminalLine('Elevation: NOT REQUIRED');
        this.addTerminalLine('File Permissions: SECURED');
    }

    async showSettings() {
        this.showTerminal();
        this.addTerminalLine('=== PHOENIX SETTINGS ===');
        if (isElectron && ipcRenderer) {
            const env = await ipcRenderer.invoke('get-env-vars');
            this.addTerminalLine('PHOENIX_ROOT: '       + (env.PHOENIX_ROOT       || 'Not set'));
            this.addTerminalLine('CLONEPOOL_DIR: '      + (env.CLONEPOOL_DIR      || 'Not set'));
            this.addTerminalLine('PHOENIX_AUTH: '       + (env.PHOENIX_AUTH       || 'Not set'));
            this.addTerminalLine('PHOENIX_WORKER_URL: ' + (env.PHOENIX_WORKER_URL || 'Not set'));
        } else {
            this.addTerminalLine('(env not available outside Electron)');
        }
    }

    showTerminal() {
        const overlay = document.getElementById('terminal-overlay');
        overlay.style.display = 'flex';
        const content = document.getElementById('terminal-content');
        content.innerHTML = '<div class="terminal-line">Phoenix DevOps OS v0.1.0</div>';
    }

    addTerminalLine(text) {
        const content = document.getElementById('terminal-content');
        const line = document.createElement('div');
        line.className = 'terminal-line';
        line.textContent = text;
        content.appendChild(line);
        content.scrollTop = content.scrollHeight;
    }

    executeCommand(cmd) {
        this.runPhoenixCli(cmd);
    }

    getEnvVar(name) {
        return null;
    }

    startDataUpdates() {
        setInterval(() => this.updateMetrics(), 3000);
        this.updateMetrics();
    }

    async updateMetrics() {
        if (isElectron && ipcRenderer) {
            try {
                const m = await ipcRenderer.invoke('get-os-metrics');
                document.getElementById('cpu-usage').textContent = `${m.cpu}%`;
                document.getElementById('cpu-bar').style.width = `${m.cpu}%`;
                document.getElementById('mem-usage').textContent = `${m.memory}%`;
                document.getElementById('mem-bar').style.width = `${m.memory}%`;
                document.getElementById('disk-usage').textContent = `${m.disk}%`;
                document.getElementById('disk-bar').style.width = `${m.disk}%`;
                return;
            } catch (e) {
                console.warn('get-os-metrics failed, falling back:', e.message);
            }
        }
        // Browser / fallback — static display, no fake random numbers
        document.getElementById('cpu-usage').textContent = '--';
        document.getElementById('mem-usage').textContent = '--';
        document.getElementById('disk-usage').textContent = '--';
    }


    _makePlaceBox(name, fullPath, preloadedItems) {
        const box = document.createElement('div');
        box.className = 'place-box';
        const safeId = 'pc-' + name.replace(/[^a-zA-Z0-9]/g, '_');
        box.innerHTML = `
            <div class="place-header" data-open="false">
                <span class="place-arrow">▶</span>
                <span class="place-name">${name}</span>
                <span class="place-count" id="${safeId}"></span>
            </div>
            <div class="place-dropdown" style="display:none;"></div>
        `;

        const header   = box.querySelector('.place-header');
        const dropdown = box.querySelector('.place-dropdown');

        if (!fullPath && preloadedItems) {
            // Files-only box — show count and pre-render items on first open
            const el = document.getElementById(safeId);
            if (el) el.textContent = `${preloadedItems.length}`;
            header.addEventListener('click', () => {
                const isOpen = header.dataset.open === 'true';
                if (isOpen) {
                    dropdown.style.display = 'none';
                    header.dataset.open = 'false';
                    header.querySelector('.place-arrow').textContent = '▶';
                } else {
                    dropdown.style.display = 'block';
                    header.dataset.open = 'true';
                    header.querySelector('.place-arrow').textContent = '▼';
                    if (!dropdown.dataset.loaded) {
                        dropdown.dataset.loaded = 'true';
                        preloadedItems.forEach(item => {
                            const el = document.createElement('div');
                            el.className = 'place-item place-file';
                            el.innerHTML = `<span class="item-icon">·</span><span class="place-file-name">${item.name}</span>`;
                            this._bindFileItem(el, item);
                            dropdown.appendChild(el);
                        });
                    }
                }
            });
            return box;
        }

        header.addEventListener('click', async () => {
            const isOpen = header.dataset.open === 'true';
            if (isOpen) {
                dropdown.style.display = 'none';
                header.dataset.open = 'false';
                header.querySelector('.place-arrow').textContent = '▶';
            } else {
                dropdown.style.display = 'block';
                header.dataset.open = 'true';
                header.querySelector('.place-arrow').textContent = '▼';
                if (!dropdown.dataset.loaded) {
                    dropdown.dataset.loaded = 'true';
                    await this._loadPlaceItems(dropdown, fullPath);
                }
            }
        });

        // Load item count (non-blocking)
        if (isElectron && ipcRenderer) {
            ipcRenderer.invoke('list-directory', fullPath).then(r => {
                const el = document.getElementById(safeId);
                if (el && r.success) el.textContent = `${r.items.length}`;
            }).catch(() => {});
        }

        return box;
    }

    async _loadPlaceItems(container, dirPath) {
        container.innerHTML = '<div class="place-loading-inner">loading...</div>';
        try {
            const result = await ipcRenderer.invoke('list-directory', dirPath);
            if (!result.success) throw new Error(result.error);

            if (!result.items.length) {
                container.innerHTML = '<div class="place-item place-empty">empty</div>';
                return;
            }

            container.innerHTML = '';
            const sorted = [...result.items].sort((a, b) => {
                if (a.isDirectory && !b.isDirectory) return -1;
                if (!a.isDirectory && b.isDirectory) return 1;
                return a.name.localeCompare(b.name);
            });

            for (const item of sorted) {
                const el = document.createElement('div');
                if (item.isDirectory) {
                    el.className = 'place-item place-dir';
                    const subdrop = document.createElement('div');
                    subdrop.className = 'place-subdropdown';
                    subdrop.style.display = 'none';
                    el.innerHTML = `<span class="item-arrow">▶</span><span>${item.name}/</span>`;
                    el.appendChild(subdrop);
                    el.addEventListener('click', async (e) => {
                        e.stopPropagation();
                        const isOpen = el.dataset.open === 'true';
                        if (isOpen) {
                            subdrop.style.display = 'none';
                            el.dataset.open = 'false';
                            el.querySelector('.item-arrow').textContent = '▶';
                        } else {
                            subdrop.style.display = 'block';
                            el.dataset.open = 'true';
                            el.querySelector('.item-arrow').textContent = '▼';
                            if (!subdrop.dataset.loaded) {
                                subdrop.dataset.loaded = 'true';
                                await this._loadPlaceItems(subdrop, item.path);
                            }
                        }
                    });
                } else {
                    el.className = 'place-item place-file';
                    el.innerHTML = `<span class="item-icon">·</span><span class="place-file-name">${item.name}</span>`;
                    this._bindFileItem(el, item);
                }
                container.appendChild(el);
            }
        } catch (e) {
            container.innerHTML = `<div class="place-item">error: ${e.message}</div>`;
        }
    }

    initHelpDeskHUD() {
        this._hudHistory = [];
        this._hudStats   = null;
        this._hudBusy    = false;
        this._manualRaw  = '';

        const input   = document.getElementById('hud-input');
        const sendBtn = document.getElementById('hud-send');

        const submit = () => {
            const msg = input.value.trim();
            if (!msg || this._hudBusy) return;
            input.value = '';
            this._hudSend(msg);
        };

        sendBtn.addEventListener('click', submit);
        input.addEventListener('keydown', e => { if (e.key === 'Enter') submit(); });

        document.querySelectorAll('.hud-nav-btn[data-hud-nav]').forEach(btn => {
            btn.addEventListener('click', () => this._hudNavSwitch(btn.dataset.hudNav));
        });

        document.getElementById('manual-reload').addEventListener('click', () => this._loadManual());
        document.getElementById('manual-search').addEventListener('input', e => this._filterManual(e.target.value));

        if (isElectron && ipcRenderer) {
            ipcRenderer.invoke('get-phoenix-stats').then(s => { if (s?.success) this._hudStats = s; });
            this._refreshHelpDeskStatus();
            setInterval(() => this._refreshHelpDeskStatus(), 30000);
        }

        this._loadManual();
    }

    _hudNavSwitch(nav) {
        document.querySelectorAll('.hud-nav-btn[data-hud-nav]').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.hudNav === nav);
        });
        document.querySelectorAll('.hud-nav-pane[data-hud-nav]').forEach(pane => {
            pane.classList.toggle('active', pane.dataset.hudNav === nav);
        });
        if (nav === 'help-chat' && !this._manualRaw) this._loadManual();
        if (nav === 'sector-map') this._renderSectorMap();
        if (nav === 'ai-chat') document.getElementById('hud-input')?.focus();
        if (nav === 'shell'  && window.phoenixHudShell)  window.phoenixHudShell.show();
        if (nav === 'claude' && window.phoenixHudClaude) window.phoenixHudClaude.show();
        if (nav === 'guide') {
            if (!this._guideLoaded) { this._guideLoaded = true; this._loadGuide(); }
            else if (this._laurieMode) document.getElementById('laurie-input')?.focus();
        }
    }

    async _loadGuide() {
        const body     = document.getElementById('guide-body');
        const laurieEl  = document.getElementById('laurie-guide');
        if (!body) return;

        // Decide which experience: Laurie gets the gentle conversation,
        // everyone else gets the dev manual — until this is vetted.
        let laurieMode = false;
        if (isElectron && ipcRenderer) {
            const prof = await ipcRenderer.invoke('get-profile').catch(() => ({}));
            laurieMode = !!prof.laurieGuide;
        }
        this._laurieMode = laurieMode;

        if (laurieMode && laurieEl) {
            body.style.display = 'none';
            laurieEl.style.display = 'flex';
            this._initLaurieGuide();
            return;
        }

        // Dev: the manual.
        if (laurieEl) laurieEl.style.display = 'none';
        body.style.display = 'block';
        body.textContent = 'loading guide...';
        if (!isElectron || !ipcRenderer) {
            body.textContent = 'Guide requires Electron runtime.';
            return;
        }
        const result = await ipcRenderer.invoke('get-user-manual');
        if (!result.success) {
            body.textContent = result.error || 'Could not load guide.';
            return;
        }
        this._guideRaw = result.content;
        body.innerHTML = this._markdownToHtml(this._guideRaw);
    }

    // ── Laurie's Guide — a gentle guided conversation ─────────────────────
    _initLaurieGuide() {
        if (this._laurieInit) { document.getElementById('laurie-input')?.focus(); return; }
        this._laurieInit = true;
        this._laurieBusy = false;
        this._laurieHistory = [];

        const input = document.getElementById('laurie-input');
        const send  = document.getElementById('laurie-send');
        const go = () => {
            const msg = input.value.trim();
            if (!msg || this._laurieBusy) return;
            input.value = '';
            this._laurieSend(msg);
        };
        send?.addEventListener('click', go);
        input?.addEventListener('keydown', e => { if (e.key === 'Enter') go(); });

        document.getElementById('laurie-plain-link')?.addEventListener('click', async () => {
            const box = document.getElementById('laurie-messages');
            const r = await ipcRenderer.invoke('get-laurie-guide').catch(() => ({}));
            if (r.success) {
                const div = document.createElement('div');
                div.className = 'laurie-msg laurie-msg-plain';
                div.innerHTML = this._markdownToHtml(r.content);
                box.appendChild(div);
                box.scrollTop = box.scrollHeight;
            }
        });

        // First open ever gets the welcome — the surprise.
        let firstOpen = true;
        try { firstOpen = !localStorage.getItem('phoenix.laurie.welcomed'); } catch (_) {}
        if (firstOpen) {
            this._laurieAppend(
                "Hi Laurie. This is your guide — but it's not a manual, it's a conversation. " +
                "Ask me anything about Phoenix in your own words and I'll walk you through it, " +
                "one small step at a time. Nothing you do here can break anything. " +
                "It really is easier than it sounds. What would you like to do first?",
                'laurie-msg-assist'
            );
            try { localStorage.setItem('phoenix.laurie.welcomed', '1'); } catch (_) {}
        } else {
            this._laurieAppend("Welcome back, Laurie. What would you like to do?", 'laurie-msg-assist');
        }
        input?.focus();
    }

    _laurieAppend(text, cls) {
        const box = document.getElementById('laurie-messages');
        if (!box) return null;
        const div = document.createElement('div');
        div.className = `laurie-msg ${cls}`;
        // Light touch: render **bold** and `code`, escape everything else.
        // Keeps her replies clean without a full markdown engine.
        const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        div.innerHTML = esc(text)
            .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
            .replace(/`([^`]+)`/g, '<code>$1</code>');
        box.appendChild(div);
        box.scrollTop = box.scrollHeight;
        return div;
    }

    async _laurieSend(message) {
        this._laurieBusy = true;
        document.getElementById('laurie-send').disabled = true;
        this._laurieAppend(message, 'laurie-msg-user');
        this._laurieHistory.push({ role: 'user', content: message });

        const thinking = this._laurieAppend('…', 'laurie-msg-thinking');
        const box = document.getElementById('laurie-messages');

        let streamDiv = null, streamText = '';
        let unsub = null;
        if (isElectron && ipcRenderer && window.phoenix?.onStream) {
            unsub = window.phoenix.onStream('ai-chat-stream-chunk', ({ delta }) => {
                if (!streamDiv) { thinking.remove(); streamDiv = this._laurieAppend('', 'laurie-msg-assist'); }
                streamText += delta;
                streamDiv.textContent = streamText;
                box.scrollTop = box.scrollHeight;
            });
        }

        let result = { success: false, error: 'The guide needs the Phoenix desktop to run.' };
        if (isElectron && ipcRenderer) {
            result = await ipcRenderer.invoke('ai-chat', {
                message, history: this._laurieHistory, mode: 'laurie'
            }).catch(e => ({ success: false, error: e.message }));
        }
        if (unsub) unsub();
        if (!streamDiv) thinking.remove();

        if (result.success) {
            if (streamDiv) streamDiv.textContent = result.reply;
            else this._laurieAppend(result.reply, 'laurie-msg-assist');
            this._laurieHistory.push({ role: 'assistant', content: result.reply });
        } else {
            this._laurieAppend(result.error || 'Something went wrong — wait a moment and try again. Nothing is broken.', 'laurie-msg-assist');
        }

        this._laurieBusy = false;
        document.getElementById('laurie-send').disabled = false;
        document.getElementById('laurie-input')?.focus();
    }

    _renderSectorMap() {
        const el = document.getElementById('sector-map-body');
        if (!el) return;
        const rows = Object.entries(SECTOR_META).map(([id, meta]) => {
            const on = this._isSectorEnabled(id) ? 'ON' : 'OFF';
            const active = this._activeSector === id ? ' ← active' : '';
            const path = this._sectorPaths[meta.folderKey];
            return `<div class="sector-map-row"><span class="sector-map-id">${meta.label}</span><span class="sector-map-state ${on === 'ON' ? 'on' : 'off'}">${on}</span><span class="sector-map-path">${path || '—'}${active}</span></div>`;
        });
        el.innerHTML = `<div class="sector-map-hint">Sector switches (left panel) gate CLI commands and EXECUTE actions.</div>${rows.join('')}`;
    }

    async _refreshHelpDeskStatus() {
        if (!isElectron || !ipcRenderer) return;

        // This status line only means something for the helpdesk/ollama
        // provider — pinging Ollama and showing its state when a different
        // provider (claude / subscription) is actually configured just
        // shows a stale "OLLAMA" label that has nothing to do with what's
        // really answering. Check the configured provider first.
        const authStatus = await ipcRenderer.invoke('get-ai-status').catch(() => null);
        const provider = (authStatus?.provider || 'helpdesk').toLowerCase();

        if (provider === 'claude') {
            this._updateProviderIndicator('status-ok', `CLAUDE API (${authStatus.model || 'claude-sonnet-5'})`, 'claude (api key)',
                'AI Chat ready — Claude API. Use HELP CHAT tab for the operator manual.');
            return;
        }
        if (provider === 'subscription') {
            this._updateProviderIndicator('status-ok', 'CLAUDE (subscription)', 'claude (subscription) — full tool access',
                'AI Chat ready — Claude (subscription, full tool access, no Ollama). Use HELP CHAT tab for the operator manual.');
            return;
        }

        await ipcRenderer.invoke('ensure-ollama').catch(() => {});
        const status = await ipcRenderer.invoke('check-ollama').catch(() => ({ online: false }));
        this._updateHelpDeskStatus(status);
    }

    _updateProviderIndicator(statusClass, statusText, providerText, welcomeText) {
        const el = document.getElementById('helpdesk-status');
        const provider = document.getElementById('hud-provider');
        const welcome = document.getElementById('hud-welcome-msg');
        if (el) { el.textContent = statusText; el.className = statusClass; }
        if (provider && !this._hudBusy) provider.textContent = providerText;
        if (welcome && welcomeText) welcome.textContent = welcomeText;
    }

    _updateHelpDeskStatus(status) {
        if (status?.online) {
            const model = status.model || (status.models && status.models[0]) || 'llama3.2';
            this._updateProviderIndicator('status-ok', `OLLAMA (${model})`, `ollama → claude · ${model}`,
                'AI Chat ready. Ollama primary, Claude fallback. Use HELP CHAT tab for the operator manual.');
        } else {
            this._updateProviderIndicator('status-warn', 'OLLAMA OFFLINE', `ollama offline — ${status?.reason || 'start Ollama app'}`,
                'AI Chat ready. Ollama primary, Claude fallback. Use HELP CHAT tab for the operator manual.');
        }
    }

    async _loadManual() {
        const body = document.getElementById('manual-body');
        if (!body) return;
        body.textContent = 'loading manual...';
        if (!isElectron || !ipcRenderer) {
            body.textContent = 'Manual requires Electron runtime.';
            return;
        }
        const result = await ipcRenderer.invoke('get-user-manual');
        if (!result.success) {
            body.textContent = result.error || 'Could not load manual.';
            return;
        }
        this._manualRaw = result.content;
        this._renderManual(this._manualRaw);
    }

    _renderManual(text) {
        const body = document.getElementById('manual-body');
        if (!body) return;
        body.innerHTML = this._markdownToHtml(text);
    }

    _filterManual(query) {
        if (!this._manualRaw) return;
        const q = query.trim().toLowerCase();
        if (!q) {
            this._renderManual(this._manualRaw);
            return;
        }
        const sections = this._manualRaw.split(/\n(?=## )/);
        const matched = sections.filter(s => s.toLowerCase().includes(q));
        this._renderManual(matched.length ? matched.join('\n') : 'No matching sections.');
    }

    _markdownToHtml(md) {
        return md
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/^### (.+)$/gm, '<h3>$1</h3>')
            .replace(/^## (.+)$/gm, '<h2>$1</h2>')
            .replace(/^# (.+)$/gm, '<h1>$1</h1>')
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            .replace(/^\|(.+)\|$/gm, (line) => {
                const cells = line.split('|').filter(c => c.trim()).map(c => `<td>${c.trim()}</td>`).join('');
                return `<tr>${cells}</tr>`;
            })
            .replace(/(<tr>.*<\/tr>\n?)+/g, m => `<table>${m}</table>`)
            .replace(/^- (.+)$/gm, '<li>$1</li>')
            .replace(/(<li>.*<\/li>\n?)+/g, m => `<ul>${m}</ul>`)
            .replace(/\n\n/g, '<br><br>')
            .replace(/\n/g, '<br>');
    }

    _hudAppend(text, cls) {
        const box = document.getElementById('hud-messages');
        const div = document.createElement('div');
        div.className = `hud-msg ${cls}`;
        div.textContent = text;
        box.appendChild(div);
        box.scrollTop = box.scrollHeight;
        return div;
    }

    async _hudSend(message) {
        this._hudBusy = true;
        document.getElementById('hud-send').disabled = true;

        this._hudAppend(message, 'hud-msg-user');
        this._hudHistory.push({ role: 'user', content: message });

        const thinking = this._hudAppend('connecting to Ollama (first reply may take ~15s)...', 'hud-msg-thinking');
        const box = document.getElementById('hud-messages');

        // Streamed reply support: a chunk means Claude API streaming is
        // actually in flight for this turn, so swap the "thinking" line
        // for a live-growing message div on the FIRST delta. Ollama/
        // subscription paths never send chunks, so `streamDiv` stays
        // null and the old wait-for-full-response flow below still runs.
        let streamDiv = null;
        let streamText = '';
        let unsubscribe = null;
        if (isElectron && ipcRenderer && window.phoenix?.onStream) {
            unsubscribe = window.phoenix.onStream('ai-chat-stream-chunk', ({ delta }) => {
                if (!streamDiv) {
                    thinking.remove();
                    streamDiv = this._hudAppend('', 'hud-msg-assist');
                }
                streamText += delta;
                streamDiv.textContent = streamText;
                box.scrollTop = box.scrollHeight;
            });
        }

        let result;
        if (isElectron && ipcRenderer) {
            result = await ipcRenderer.invoke('ai-chat', {
                message,
                history: this._hudHistory,
                phoenixStats: this._hudStats
            });
        } else {
            result = { success: false, error: 'AI chat requires Electron runtime.' };
        }
        if (unsubscribe) unsubscribe();

        if (!streamDiv) thinking.remove();

        if (result.success) {
            if (streamDiv) {
                // Streamed text already rendered incrementally — just make
                // sure the final text matches exactly (in case a delta was
                // still in flight when the invoke resolved).
                streamDiv.textContent = result.reply;
            } else {
                this._hudAppend(result.reply, 'hud-msg-assist');
            }
            this._hudHistory.push({ role: 'assistant', content: result.reply });
            const fb = result.fallback ? ` (fallback from ${result.fallbackFrom || 'ollama'})` : '';
            document.getElementById('hud-provider').textContent = `${result.provider}${fb}`;
            if (this._hudHistory.length > 40) this._hudHistory = this._hudHistory.slice(-40);
        } else {
            if (streamDiv) streamDiv.remove();
            const err = (result.error || 'Help Desk unavailable.').replace(/\n/g, ' · ');
            this._hudAppend(err, 'hud-msg-error');
            document.getElementById('hud-provider').textContent = 'help desk offline — Ollama app must be running';
            this._refreshHelpDeskStatus();
        }

        this._hudBusy = false;
        document.getElementById('hud-send').disabled = false;
        document.getElementById('hud-input').focus();
    }

    initCanvas() {
        const canvas = document.getElementById('main-canvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');

        const resize = () => {
            const w = canvas.offsetWidth;
            const h = canvas.offsetHeight;
            if (w > 0 && h > 0) {
                canvas.width = w;
                canvas.height = h;
            }
        };
        resize();

        const hudZone = document.getElementById('hud-zone');
        if (typeof ResizeObserver !== 'undefined' && hudZone) {
            new ResizeObserver(resize).observe(hudZone);
        } else {
            window.addEventListener('resize', resize);
        }

        this.animateCanvas(ctx, canvas);
    }

    animateCanvas(ctx, canvas) {
        const embers = Array.from({ length: 48 }, () => ({
            x: Math.random(),
            y: 0.6 + Math.random() * 0.4,
            speed: 0.001 + Math.random() * 0.003,
            size: 1 + Math.random() * 2.5,
            hue: 20 + Math.random() * 35
        }));

        const animate = () => {
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            for (const e of embers) {
                e.y -= e.speed;
                if (e.y < 0.15) {
                    e.y = 0.85 + Math.random() * 0.12;
                    e.x = Math.random();
                }
                const px = e.x * canvas.width;
                const py = e.y * canvas.height;
                const grad = ctx.createRadialGradient(px, py, 0, px, py, e.size * 3);
                grad.addColorStop(0, `hsla(${e.hue}, 100%, 65%, 0.55)`);
                grad.addColorStop(1, 'hsla(20, 100%, 50%, 0)');
                ctx.fillStyle = grad;
                ctx.beginPath();
                ctx.arc(px, py, e.size * 3, 0, Math.PI * 2);
                ctx.fill();
            }

            requestAnimationFrame(animate);
        };

        animate();
    }
}

// ── Phoenix AI Auth Modal ─────────────────────────────────────────────────────
class PhoenixAuthModal {
    constructor(onDone) {
        this.onDone = onDone;
        this.overlay = document.getElementById('auth-overlay');
        this._init();
    }

    async _init() {
        // Pre-fill from saved/env
        let status = { provider: 'helpdesk', hasKey: false, model: '', ollamaUrl: 'http://localhost:11434' };
        if (isElectron && ipcRenderer) {
            status = await ipcRenderer.invoke('get-ai-status');
        }

        const savedTab = status.provider === 'claude' ? 'claude'
                       : status.provider === 'subscription' ? 'subscription'
                       : status.provider === 'ollama' ? 'ollama'
                       : 'helpdesk';
        this._switchTab(savedTab);

        if (status.hasKey) {
            document.getElementById('auth-api-key').value = '••••••••••••••••';
            document.getElementById('auth-api-key').dataset.prefilled = 'true';
        }
        if (status.model) {
            document.getElementById('auth-model').value = status.model;
            document.getElementById('auth-helpdesk-ollama-model').value = status.model;
        }
        if (status.ollamaUrl) {
            document.getElementById('auth-ollama-url').value = status.ollamaUrl;
            document.getElementById('auth-helpdesk-ollama-url').value = status.ollamaUrl;
        }
        document.querySelectorAll('.auth-tab').forEach(tab => {
            tab.addEventListener('click', () => this._switchTab(tab.dataset.tab));
        });

        this._checkCliStatus();
        this._checkOllamaStatus();

        const revealBtn = document.getElementById('auth-reveal');
        const keyInput  = document.getElementById('auth-api-key');
        revealBtn.addEventListener('click', () => {
            keyInput.type = keyInput.type === 'password' ? 'text' : 'password';
        });
        keyInput.addEventListener('focus', () => {
            if (keyInput.dataset.prefilled === 'true') {
                keyInput.value = '';
                delete keyInput.dataset.prefilled;
            }
        });

        // Skip — use whatever is already in env
        document.getElementById('auth-skip').addEventListener('click', () => this._dismiss());

        // Launch
        document.getElementById('auth-go').addEventListener('click', () => this._submit());
        document.getElementById('auth-api-key').addEventListener('keydown', e => {
            if (e.key === 'Enter') this._submit();
        });
    }

    _switchTab(tab) {
        document.querySelectorAll('.auth-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
        document.getElementById('section-helpdesk').style.display     = tab === 'helpdesk'     ? '' : 'none';
        document.getElementById('section-subscription').style.display = tab === 'subscription' ? '' : 'none';
        document.getElementById('section-claude').style.display       = tab === 'claude'       ? '' : 'none';
        document.getElementById('section-ollama').style.display       = tab === 'ollama'       ? '' : 'none';
    }

    async _checkOllamaStatus() {
        const el = document.getElementById('auth-ollama-status');
        if (!el || !isElectron || !ipcRenderer) return;
        const result = await ipcRenderer.invoke('check-ollama');
        if (result.online) {
            const models = (result.models || []).slice(0, 3).join(', ') || 'no models listed';
            el.innerHTML = `<span class="cli-ok">&#10003; ollama online — ${models}</span>`;
        } else {
            el.innerHTML = `<span class="cli-warn">&#9888; ollama offline — will use Claude fallback (${result.reason})</span>`;
        }
    }

    async _checkCliStatus() {
        const el = document.getElementById('auth-cli-status');
        if (!el) return;
        if (!isElectron || !ipcRenderer) {
            el.innerHTML = '<span class="cli-warn">CLI check requires Electron</span>';
            return;
        }
        const result = await ipcRenderer.invoke('check-claude-cli');
        if (!result.available) {
            el.innerHTML = `<span class="cli-err">&#10007; not installed</span><br><span class="cli-hint">${result.reason}</span>`;
        } else if (!result.loggedIn) {
            el.innerHTML = `<span class="cli-warn">&#9888; ${result.version} — not logged in</span><br><span class="cli-hint">${result.reason}</span>`;
        } else {
            el.innerHTML = `<span class="cli-ok">&#10003; ${result.version} — logged in</span>`;
        }
    }

    _activeTab() {
        const active = document.querySelector('.auth-tab.active');
        return active ? active.dataset.tab : 'helpdesk';
    }

    async _submit() {
        const tab      = this._activeTab();
        const provider = tab;
        const keyInput = document.getElementById('auth-api-key');
        const key      = (tab === 'claude' && keyInput.dataset.prefilled !== 'true') ? keyInput.value.trim() : '';

        let model = '';
        let ollamaUrl = '';

        if (tab === 'helpdesk') {
            model     = document.getElementById('auth-helpdesk-ollama-model').value.trim();
            ollamaUrl = document.getElementById('auth-helpdesk-ollama-url').value.trim();
        } else if (tab === 'ollama') {
            model     = document.getElementById('auth-ollama-model')?.value.trim() || document.getElementById('auth-helpdesk-ollama-model').value.trim();
            ollamaUrl = document.getElementById('auth-ollama-url').value.trim();
        } else {
            model = document.getElementById('auth-model').value.trim();
        }

        const save = document.getElementById('auth-save').checked;
        const status = document.getElementById('auth-status');
        status.textContent = 'authenticating...';
        status.className = 'auth-status auth-status-pending';

        let result = { success: true };
        if (isElectron && ipcRenderer) {
            result = await ipcRenderer.invoke('set-ai-auth', { provider, key, model, ollamaUrl, save });
        }

        if (result.success) {
            status.textContent = `provider set: ${result.provider}`;
            status.className = 'auth-status auth-status-ok';
            setTimeout(() => this._dismiss(), 600);
        } else {
            status.textContent = result.error || 'failed';
            status.className = 'auth-status auth-status-err';
        }
    }

    _dismiss() {
        this.overlay.style.opacity = '0';
        setTimeout(() => { this.overlay.style.display = 'none'; }, 300);
        this.onDone?.();
    }

    show() {
        this.overlay.style.display = 'flex';
        this.overlay.style.opacity = '1';
    }
}

function _bootDashboard(modal) {
    if (window.phoenixDashboard) return;
    // On the skip path _dismiss() never runs, so hide the overlay here — the
    // CSS default is display:flex, otherwise it just sits on top of the HUD.
    const overlay = document.getElementById('auth-overlay');
    if (overlay) overlay.style.display = 'none';
    window.phoenixDashboard = new PhoenixDashboard();
    console.log('Phoenix DevOps OS Desktop initialized');
    if (modal) modal.onDone = null;
}

// Initialize desktop when DOM is loaded
document.addEventListener('DOMContentLoaded', async () => {
    const modal = new PhoenixAuthModal(() => _bootDashboard(modal));

    let skipAuth = false;
    if (isElectron && ipcRenderer) {
        try {
            const status = await ipcRenderer.invoke('get-ai-status');
            skipAuth = !!status.skipAuthModal;
        } catch (_) {}
    }

    if (skipAuth) {
        _bootDashboard(modal);
    } else {
        modal.show();
    }

    document.getElementById('hud-provider').addEventListener('click', () => modal.show());
});

// Integration functions for Phoenix commands
window.phoenixIntegration = {
    // Execute a Phoenix usys command
    executeUsysCommand: async function(command) {
        if (isElectron && ipcRenderer) {
            try {
                console.log(`Executing: usys ${command}`);
                const result = await ipcRenderer.invoke('execute-command', `usys ${command}`);
                return result;
            } catch (error) {
                console.error('Command execution failed:', error);
                return { success: false, error: error.message };
            }
        } else {
            // Browser fallback - simulated data
            console.log(`[Simulated] Executing: usys ${command}`);
            return { success: true, output: 'Command executed (simulated)' };
        }
    },

    // Get system status
    getSystemStatus: async function() {
        return this.executeUsysCommand('status');
    },

    // List suites
    listSuites: async function() {
        return this.executeUsysCommand('list-suites');
    },

    // Clone a file
    cloneFile: async function(filePath, category = '', tag = '') {
        const cmd = `clone "${filePath}" ${category} "${tag}"`;
        return this.executeUsysCommand(cmd);
    },

    // Intake a file
    intakeFile: async function(filePath) {
        return this.executeUsysCommand(`intake "${filePath}"`);
    },

    // Run a suite
    runSuite: async function(suiteName, version = '') {
        const cmd = version ? `run ${suiteName}@${version}` : `run ${suiteName}`;
        return this.executeUsysCommand(cmd);
    }
};

// Made with Bob
