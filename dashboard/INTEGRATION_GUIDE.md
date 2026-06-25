# Phoenix Dashboard - Integration & Enhancement Guide

## Filesystem Access - How It Works

### Current State (Browser-Based)
The dashboard as built is a **static HTML/CSS/JavaScript** file that runs in your browser. By default:

❌ **Cannot access your PC's filesystem directly** (browser security sandbox)  
❌ **Cannot execute PowerShell/bash commands** (browser limitation)  
✅ **Can display data if provided via API or files**  
✅ **Fully functional UI with simulated data**

### Three Ways to Enable Filesystem Access

---

## Option 1: Electron App (RECOMMENDED - Easy)

**Difficulty: ⭐⭐☆☆☆ (Easy)**

Wrap the dashboard in Electron to get native filesystem and command execution.

### Setup (15 minutes):

1. **Install Node.js and Electron:**
   ```bash
   # Install Node.js from nodejs.org
   # Then install Electron
   npm install -g electron
   ```

2. **Create `package.json`:**
   ```json
   {
     "name": "phoenix-dashboard",
     "version": "1.0.0",
     "main": "main.js",
     "scripts": {
       "start": "electron ."
     },
     "dependencies": {
       "electron": "^28.0.0"
     }
   }
   ```

3. **Create `main.js`:**
   ```javascript
   const { app, BrowserWindow, ipcMain } = require('electron');
   const { exec } = require('child_process');
   const path = require('path');

   function createWindow() {
     const win = new BrowserWindow({
       width: 1920,
       height: 1080,
       webPreferences: {
         nodeIntegration: true,
         contextIsolation: false
       }
     });

     win.loadFile('index.html');
   }

   // Handle Phoenix commands
   ipcMain.handle('execute-command', async (event, command) => {
     return new Promise((resolve, reject) => {
       exec(`pwsh -Command "${command}"`, (error, stdout, stderr) => {
         if (error) {
           resolve({ success: false, error: stderr });
         } else {
           resolve({ success: true, output: stdout });
         }
       });
     });
   });

   app.whenReady().then(createWindow);
   ```

4. **Update `dashboard.js` to use Electron:**
   ```javascript
   // Add at top of dashboard.js
   const { ipcRenderer } = require('electron');

   // Replace executeUsysCommand function:
   executeUsysCommand: async function(command) {
     try {
       const result = await ipcRenderer.invoke('execute-command', `usys ${command}`);
       return result;
     } catch (error) {
       return { success: false, error: error.message };
     }
   }
   ```

5. **Run:**
   ```bash
   npm install
   npm start
   ```

**Result:** Full filesystem access, can execute all Phoenix commands, native app experience.

---

## Option 2: PowerShell Web Server (MODERATE)

**Difficulty: ⭐⭐⭐☆☆ (Moderate)**

Create a local web server that executes Phoenix commands and serves the dashboard.

### Setup (30 minutes):

1. **Create `server.ps1`:**
   ```powershell
   #Requires -Version 7.0
   # Phoenix Dashboard Web Server
   
   $port = 8787
   $listener = New-Object System.Net.HttpListener
   $listener.Prefixes.Add("http://localhost:$port/")
   $listener.Start()
   
   Write-Host "Phoenix Dashboard Server running on http://localhost:$port"
   Write-Host "Press Ctrl+C to stop"
   
   while ($listener.IsListening) {
       $context = $listener.GetContext()
       $request = $context.Request
       $response = $context.Response
       
       # CORS headers
       $response.Headers.Add("Access-Control-Allow-Origin", "*")
       $response.Headers.Add("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
       
       # Handle API requests
       if ($request.Url.AbsolutePath -match '^/api/(.+)$') {
           $command = $matches[1]
           
           try {
               # Execute usys command
               $output = & usys $command 2>&1 | Out-String
               $json = @{
                   success = $true
                   output = $output
               } | ConvertTo-Json
               
               $buffer = [System.Text.Encoding]::UTF8.GetBytes($json)
               $response.ContentType = "application/json"
               $response.ContentLength64 = $buffer.Length
               $response.OutputStream.Write($buffer, 0, $buffer.Length)
           }
           catch {
               $json = @{
                   success = $false
                   error = $_.Exception.Message
               } | ConvertTo-Json
               
               $buffer = [System.Text.Encoding]::UTF8.GetBytes($json)
               $response.ContentType = "application/json"
               $response.ContentLength64 = $buffer.Length
               $response.OutputStream.Write($buffer, 0, $buffer.Length)
           }
       }
       # Serve dashboard files
       else {
           $filePath = Join-Path $PSScriptRoot "dashboard$($request.Url.AbsolutePath)"
           if ($request.Url.AbsolutePath -eq '/') {
               $filePath = Join-Path $PSScriptRoot "dashboard/index.html"
           }
           
           if (Test-Path $filePath) {
               $content = [System.IO.File]::ReadAllBytes($filePath)
               $response.ContentLength64 = $content.Length
               
               # Set content type
               $ext = [System.IO.Path]::GetExtension($filePath)
               $response.ContentType = switch ($ext) {
                   '.html' { 'text/html' }
                   '.css'  { 'text/css' }
                   '.js'   { 'application/javascript' }
                   default { 'application/octet-stream' }
               }
               
               $response.OutputStream.Write($content, 0, $content.Length)
           }
           else {
               $response.StatusCode = 404
           }
       }
       
       $response.Close()
   }
   
   $listener.Stop()
   ```

2. **Update `dashboard.js`:**
   ```javascript
   executeUsysCommand: async function(command) {
     try {
       const response = await fetch(`http://localhost:8787/api/${command}`);
       const data = await response.json();
       return data;
     } catch (error) {
       return { success: false, error: error.message };
     }
   }
   ```

3. **Run:**
   ```powershell
   pwsh -File server.ps1
   # Then open http://localhost:8787 in browser
   ```

**Result:** Full Phoenix command execution via web API, accessible from any browser.

---

## Option 3: File-Based Updates (EASIEST)

**Difficulty: ⭐☆☆☆☆ (Very Easy)**

Have Phoenix write status to JSON files that the dashboard reads.

### Setup (10 minutes):

1. **Create status update script `update-dashboard-data.ps1`:**
   ```powershell
   # Run this periodically (e.g., every 5 seconds)
   $dataDir = "$HOME\Phoenix\dashboard-data"
   New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
   
   # Get system status
   $status = usys status | Out-String
   
   # Get sector file counts
   $sectors = @{
       sector1 = (Get-ChildItem "$env:PHOENIX_ROOT\sector1" -Recurse -File).Count
       sector2 = (Get-ChildItem "$env:PHOENIX_ROOT\sector2" -Recurse -File).Count
       sector3 = (Get-ChildItem "$env:PHOENIX_ROOT\sector3" -Recurse -File).Count
       sector4 = (Get-ChildItem "$env:PHOENIX_ROOT\sector4" -Recurse -File).Count
   }
   
   # Get clonepool info
   $clonepool = @{
       totalFiles = (Get-ChildItem "$env:CLONEPOOL_DIR" -Recurse -File).Count
       suites = (Get-ChildItem "$env:CLONEPOOL_DIR" -Directory | Where-Object { Test-Path "$($_.FullName)\.suite.json" }).Count
       lastSync = (Get-Date).ToString('HH:mm:ss')
   }
   
   # Write to JSON
   @{
       timestamp = (Get-Date).ToString('o')
       sectors = $sectors
       clonepool = $clonepool
       status = $status
   } | ConvertTo-Json | Set-Content "$dataDir\status.json"
   ```

2. **Update `dashboard.js` to read files:**
   ```javascript
   async loadSystemStatus() {
     try {
       const response = await fetch('file:///C:/Users/YourUser/Phoenix/dashboard-data/status.json');
       const data = await response.json();
       
       // Update UI with real data
       document.getElementById('s1-files').textContent = `${data.sectors.sector1} files`;
       document.getElementById('s2-files').textContent = `${data.sectors.sector2} files`;
       // ... etc
     } catch (error) {
       console.log('Using simulated data');
     }
   }
   ```

3. **Run update script periodically:**
   ```powershell
   # Run in background
   while ($true) {
       .\update-dashboard-data.ps1
       Start-Sleep -Seconds 5
   }
   ```

**Result:** Dashboard shows real Phoenix data, no server needed, but read-only.

---

## Future Enhancements - Difficulty Ratings

### Easy (1-2 hours each) ⭐⭐☆☆☆

1. **WebSocket Integration**
   - Use existing PowerShell web server
   - Add WebSocket support for real-time updates
   - No polling needed, instant updates

2. **Drag-and-Drop File Upload**
   - HTML5 File API (already in browsers)
   - Drop files on dashboard → auto-clone/intake
   - Just add event listeners

3. **Log Viewer Panel**
   - Read Phoenix log files
   - Display in scrollable panel
   - Filter by level/date

4. **Dark/Light Theme Toggle**
   - CSS variables already set up
   - Just add alternate color scheme
   - Toggle button switches themes

### Moderate (3-5 hours each) ⭐⭐⭐☆☆

5. **Suite Execution from Dashboard**
   - Add "Run" button to suite list
   - Execute via API/Electron
   - Show output in terminal

6. **Alert Notifications**
   - Monitor for errors/warnings
   - Browser notifications API
   - Sound alerts for critical events

7. **Network Topology Visualization**
   - Use D3.js or similar
   - Show sector connections
   - Interactive node graph

8. **Mobile-Optimized View**
   - Responsive CSS (already started)
   - Touch-friendly controls
   - Simplified layout for small screens

### Advanced (6-10 hours each) ⭐⭐⭐⭐☆

9. **User Authentication**
   - Login system
   - Session management
   - Role-based access control

10. **Voice Commands (Experimental)**
    - Web Speech API
    - Voice recognition for commands
    - Text-to-speech feedback

---

## Recommended Implementation Path

### Phase 1: Get Real Data (Choose One)
1. **Start with Electron** (if you want a native app)
2. **Or PowerShell Web Server** (if you prefer browser-based)
3. **Or File-Based** (if you want simplest solution)

### Phase 2: Add Easy Enhancements
- Drag-and-drop file upload
- Log viewer
- Theme toggle

### Phase 3: Add Moderate Features
- Suite execution
- Notifications
- Better mobile support

### Phase 4: Advanced Features (Optional)
- Authentication
- Voice commands
- Advanced visualizations

---

## Quick Start Recommendation

**For You:** I recommend **Option 1 (Electron)** because:

✅ Easiest to set up (15 minutes)  
✅ Full filesystem access  
✅ Can execute all Phoenix commands  
✅ Native app experience  
✅ No server management  
✅ Works offline  
✅ Can package as .exe for distribution  

**Next Steps:**
1. Install Node.js
2. Copy the Electron setup code above
3. Run `npm install && npm start`
4. You'll have a fully functional dashboard with real Phoenix data!

---

## Security Considerations

### Browser-Based (Options 2 & 3):
- ⚠️ Web server exposes API on localhost
- ✅ Only accessible from your machine
- ✅ Can add authentication if needed

### Electron (Option 1):
- ✅ No network exposure
- ✅ Full control over permissions
- ✅ Can restrict filesystem access if needed

### File-Based (Option 3):
- ✅ Read-only by default
- ✅ No network exposure
- ✅ Most secure option

---

## Need Help?

If you want me to:
1. Set up Electron integration → I can create all the files
2. Build the PowerShell web server → I can write the complete server
3. Create the file-based system → I can make the update scripts
4. Implement any enhancement → Just ask!

Let me know which approach you'd like to take, and I'll help you implement it!