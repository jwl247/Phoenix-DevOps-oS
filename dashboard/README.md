# Phoenix DevOps OS - Command Center Dashboard

A futuristic, sci-fi themed **Electron** desktop app for Phoenix DevOps OS — not a static
web page. It's the real day-to-day control surface: a live PS7 terminal (`terminal-pty.js`,
real `pwsh.exe`/`node-pty`), an interactive Claude Code hotline pane, the clonepool browser,
Glossary panel, HUD-mode glass overlay, Office/ScriptForge launchers, and Config Centralizer
(Settings). Everything below that talks about opening `index.html` in a browser describes an
earlier static prototype and is out of date — see **Starting the dashboard** for the real,
current way to run it. (There's also a separate `hud/` project — a WPF/.NET app with voice +
a live desktop-monitor pane — that is a different thing from this dashboard; don't confuse
the two.)

## Starting the dashboard

```powershell
# From the repo root, or from dashboard/ itself:
pwsh -ExecutionPolicy Bypass -File dashboard\start.ps1
```

This is the real entry point — it self-elevates to Administrator once (the embedded SHELL/
CLAUDE panes and admin-gated panels need it; opt out with `-NoElevate` or
`$env:PHOENIX_NO_ELEVATE=1`), loads `~/.phoenix/phoenix.env`, runs `npm install` on first run
if `node_modules` is missing, then launches the real app (`npm start` → `electron .`).

If Phoenix's installer (`install.ps1`, repo root) already ran, a Scheduled Task installed by
`sector3/services/install-dashboard-windows.ps1` autostarts this at logon (already elevated,
so no UAC prompt then) — you may not need to launch it by hand at all.

Manual/low-level equivalent, if you already have `node_modules` installed and don't need the
env/elevation setup `start.ps1` does:
```bash
cd dashboard
npm install   # first time only
npm start     # electron .
```

## Features

### Visual Design
- **Sci-Fi Holographic Theme** - Green holographic effects with animated scanlines and grid overlays
- **Three-Panel Layout** - Left control panel, center main display, right metrics panel
- **Animated Elements** - Floating Phoenix logo, rotating canvas graphics, pulsing indicators
- **Responsive Design** - Adapts to different screen sizes

### Left Panel
- **Sector Control Switches** - Toggle switches with red LED indicators for each sector (1-4) and Helix Engine
- **Status Display** - Shows altitude, airspeed, and heading metrics
- **Warning Labels** - Security warnings for authorized personnel

### Center Display
- **Holographic Viewport** - Main display area with grid overlay and scanline effects
- **HUD Information** - Real-time system status, Helix engine status, throughput metrics
- **Phoenix Logo** - Animated floating logo with glow effects
- **Control Grid** - 8 interactive buttons for system functions:
  - System Status
  - Clone Pool
  - Intake
  - Suites
  - Helix Engine
  - Catalog
  - Security
  - Settings
- **Data Panels** - Three bottom panels showing:
  - Sector Status (file counts)
  - Engine Metrics (cache, RAM, compression, languages)
  - Clonepool Info (files, suites, storage, sync time)

### Right Panel
- **System Metrics** - CPU, Memory, and Disk usage with animated progress bars
- **Circular Gauges** - Uptime and Health status with SVG gauges
- **Temperature Displays** - Dual temperature monitors

### Interactive Features
- **Terminal Overlay** - Click any control button to open a terminal window
- **Real-time Updates** - Metrics update every 2 seconds, sector status every 5 seconds
- **Toggle Switches** - Click to activate/deactivate sectors
- **Animated Canvas** - Rotating circles and points in the main viewport

## Installation

The dashboard ships as part of the Phoenix DevOps OS repo — there's nothing to copy
separately. Clone/pull the repo, then see **Starting the dashboard** above. `npm install`
(inside `dashboard/`) is the only setup step, and `start.ps1` runs it for you automatically
on first launch if `node_modules` is missing.

## File Structure

```
dashboard/
├── main.js                 # Electron main process
├── preload.js               # contextBridge — the only renderer/main boundary
├── index.html                # Renderer UI
├── start.ps1                 # Real launch script — self-elevates, loads env, npm start
├── terminal-pty.js           # SHELL pane — real pwsh/bash via node-pty
├── hud-layout.js / hud-layout-backend.js / hud-glass.css   # HUD-mode overlay + Glossary IPC
├── button-generator.js       # Declarative right-column button grid
├── config-centralizer.js     # Settings tab — real credential/config scanner
├── office-launcher.js / scriptforge-launcher.js / google-launcher.js  # App launchers
├── manual/PHOENIX_MANUAL.md / manual/LAURIE_GUIDE.md   # In-app docs
└── package.json               # npm start = electron ., build = electron-builder
```

See `dashboard/CONNECTIONS.md` for the full dependency/connection map.

## Integration with Phoenix

This is already real, not a to-do — the sections below describing a `window.phoenixIntegration`
API and hypothetical "how you might wire this up" options (PowerShell web server, WebSocket
bridge, etc.) described an earlier static-prototype plan and were never actually built that
way. The dashboard is Electron; `main.js` is the process with real Node/filesystem/child-process
access, and `preload.js` exposes a safe, `contextBridge`-based API to the renderer as
`window.phoenix` (not `window.phoenixIntegration`) — `contextIsolation` is on and
`nodeIntegration` is off in the renderer, so this bridge is the only way the UI reaches the
system. See `preload.js` for the exact current channel list (it changes as features are added)
and `main.js` for what each one actually does — that pair is the source of truth, not this doc.

## Customization

### Colors
Edit `styles.css` to change the color scheme:
```css
:root {
    --primary-green: #00ff88;  /* Main accent color */
    --dark-green: #00cc66;     /* Secondary accent */
    --bg-dark: #0a0e1a;        /* Background */
    --red-light: #ff3333;      /* Switch indicators */
}
```

### Metrics Update Frequency
Edit `dashboard.js`:
```javascript
// Change update intervals (in milliseconds)
setInterval(() => this.updateMetrics(), 2000);      // Metrics: 2 seconds
setInterval(() => this.updateSectorStatus(), 5000); // Status: 5 seconds
```

### Add Custom Buttons
Add to the control grid in `index.html`:
```html
<button class="control-btn" data-action="custom">
    <span class="btn-icon">🔧</span>
    <span class="btn-label">CUSTOM ACTION</span>
</button>
```

Then handle in `dashboard.js`:
```javascript
case 'custom':
    this.handleCustomAction();
    break;
```

## Browser Compatibility

- ✅ Chrome/Edge (Recommended)
- ✅ Firefox
- ✅ Safari
- ⚠️ IE11 (Limited support)

## Performance

- Lightweight: ~50KB total (HTML + CSS + JS)
- Smooth animations at 60fps
- Low CPU usage (~2-5%)
- No external dependencies

## Screenshots

The dashboard features:
- Dark sci-fi theme with green holographic effects
- Animated grid overlays and scanlines
- Red LED toggle switches
- Real-time metrics with progress bars
- Circular SVG gauges
- Terminal overlay for command execution

## Future Enhancements

This list predates most of what's actually built now — several of these shipped (as real
Electron IPC, not the web-dashboard shape originally imagined here) and are already checked
off in the root `CLAUDE.md` BUILD STATUS instead of tracked here:

- [x] Suite execution / clone / intake directly from the app — real terminal + CLAUDE panes
- [x] User authentication — boot-time auth modal, three-tier AI backend
- [x] Voice — **not here**, built instead in the separate `hud/` (WPF) project, Milestone 3
- [ ] Log viewer panel
- [ ] Network topology visualization
- [ ] Alert notifications
- [ ] Dark/Light theme toggle
- [ ] Mobile-optimized view

See root `CLAUDE.md` § BUILD STATUS Phase 6 for the authoritative, currently-maintained list.

## License

GPL v3 - Same as Phoenix DevOps OS

## Credits

Built for Phoenix DevOps OS by jwl247  
Design inspired by sci-fi command center interfaces  
Part of the Phoenix DevOps ecosystem

---

**Phoenix DevOps OS** - Agnostic. Deterministic. Prefetched. Self-healing. Fast as you please.