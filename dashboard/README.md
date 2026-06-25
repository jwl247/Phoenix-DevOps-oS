# Phoenix DevOps OS - Command Center Dashboard

A futuristic, sci-fi themed web dashboard for Phoenix DevOps OS, inspired by command center interfaces with holographic displays and real-time system monitoring.

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

1. **Copy dashboard files to your Phoenix installation:**
   ```bash
   cp -r dashboard ~/Phoenix/Phoenix-DevOps-oS/
   ```

2. **Open in browser:**
   ```bash
   # Windows
   start dashboard/index.html
   
   # Linux/macOS
   open dashboard/index.html
   # or
   xdg-open dashboard/index.html
   ```

## File Structure

```
dashboard/
├── index.html       # Main HTML structure
├── styles.css       # Sci-fi themed CSS styling
├── dashboard.js     # Interactive JavaScript
└── README.md        # This file
```

## Integration with Phoenix

The dashboard includes integration hooks for Phoenix usys commands:

### JavaScript Integration API

```javascript
// Execute usys commands
window.phoenixIntegration.executeUsysCommand('status');

// Get system status
window.phoenixIntegration.getSystemStatus();

// List available suites
window.phoenixIntegration.listSuites();

// Clone a file
window.phoenixIntegration.cloneFile('/path/to/file', 'category', 'tag');

// Intake a file
window.phoenixIntegration.intakeFile('/path/to/file');

// Run a suite
window.phoenixIntegration.runSuite('suite-name', 'version');
```

### Real Phoenix Integration

To connect the dashboard to actual Phoenix commands, you can:

1. **Use PowerShell Web Server** - Host the dashboard and execute PowerShell commands via API
2. **Electron App** - Wrap the dashboard in Electron for native command execution
3. **WebSocket Bridge** - Create a WebSocket server that executes usys commands
4. **File-based Updates** - Have Phoenix write status to JSON files that the dashboard reads

Example PowerShell integration:
```powershell
# Create a simple web server that executes usys commands
$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add('http://localhost:8787/')
$listener.Start()

while ($listener.IsListening) {
    $context = $listener.GetContext()
    $request = $context.Request
    $response = $context.Response
    
    if ($request.Url.AbsolutePath -eq '/api/status') {
        $output = usys status | Out-String
        $buffer = [System.Text.Encoding]::UTF8.GetBytes($output)
        $response.ContentLength64 = $buffer.Length
        $response.OutputStream.Write($buffer, 0, $buffer.Length)
    }
    
    $response.Close()
}
```

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

- [ ] WebSocket integration for real-time Phoenix data
- [ ] Drag-and-drop file upload for clone/intake
- [ ] Suite execution directly from dashboard
- [ ] Log viewer panel
- [ ] Network topology visualization
- [ ] Alert notifications
- [ ] User authentication
- [ ] Dark/Light theme toggle
- [ ] Mobile-optimized view
- [ ] Voice commands (experimental)

## License

GPL v3 - Same as Phoenix DevOps OS

## Credits

Built for Phoenix DevOps OS by jwl247  
Design inspired by sci-fi command center interfaces  
Part of the Phoenix DevOps ecosystem

---

**Phoenix DevOps OS** - Agnostic. Deterministic. Prefetched. Self-healing. Fast as you please.