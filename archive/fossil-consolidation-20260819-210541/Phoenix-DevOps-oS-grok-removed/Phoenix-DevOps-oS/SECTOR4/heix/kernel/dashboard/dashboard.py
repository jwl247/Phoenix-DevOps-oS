#!/usr/bin/env python3
"""
Agnostic Universal Kernel - Web Dashboard
Provides a web interface to monitor and control the kernel
"""

import json
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import logging


class KernelDashboard:
    """Web dashboard for kernel monitoring"""
    
    def __init__(self, kernel, port: int = 8080):
        self.kernel = kernel
        self.port = port
        self.server = None
        self.running = False
        self.logger = logging.getLogger("KernelDashboard")
    
    def start(self):
        """Start the dashboard server"""
        handler = self._create_handler()
        self.server = HTTPServer(('0.0.0.0', self.port), handler)
        self.running = True
        
        def serve():
            self.logger.info(f"Dashboard running on http://0.0.0.0:{self.port}")
            while self.running:
                self.server.handle_request()
        
        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
    
    def stop(self):
        """Stop the dashboard server"""
        self.running = False
        if self.server:
            self.server.shutdown()
    
    def _create_handler(self):
        kernel = self.kernel
        
        class DashboardHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass  # Suppress default logging
            
            def do_GET(self):
                parsed = urlparse(self.path)
                path = parsed.path
                
                if path == '/' or path == '/dashboard':
                    self._serve_dashboard()
                elif path == '/api/status':
                    self._serve_json(kernel.get_kernel_status())
                elif path == '/api/stats':
                    self._serve_json(kernel.get_component_stats())
                elif path == '/api/health':
                    self._serve_json({
                        comp: {'status': h.status, 'issues': h.issues}
                        for comp, h in kernel.health_status.items()
                    })
                elif path == '/api/micro-kernels':
                    self._serve_json({
                        mk_id: {
                            'purpose': mk.purpose,
                            'enabled': mk.enabled,
                            'priority': mk.priority
                        }
                        for mk_id, mk in kernel.micro_kernels.items()
                    })
                else:
                    self._serve_404()
            
            def do_POST(self):
                parsed = urlparse(self.path)
                path = parsed.path
                
                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else '{}'
                
                try:
                    data = json.loads(body) if body else {}
                except:
                    data = {}
                
                if path == '/api/heal':
                    component = data.get('component', 'all')
                    error = data.get('error', 'manual trigger')
                    if component == 'all':
                        results = {}
                        for comp in kernel.health_status.keys():
                            results[comp] = kernel._attempt_heal(comp, error)
                        self._serve_json({"results": results})
                    else:
                        result = kernel._attempt_heal(component, error)
                        self._serve_json({"success": result})
                
                elif path == '/api/clone':
                    target = data.get('target_path')
                    partial = data.get('partial', False)
                    components = data.get('components', [])
                    if target:
                        result = kernel.clone_kernel(target, partial, components)
                        self._serve_json({"success": result})
                    else:
                        self._serve_json({"error": "target_path required"}, 400)
                
                elif path == '/api/config/scan':
                    scan_path = data.get('path', '/')
                    results = kernel.scan_and_clone_configs(scan_path)
                    self._serve_json(results)
                
                elif path == '/api/micro-kernel/spawn':
                    purpose = data.get('purpose')
                    priority = data.get('priority', 5)
                    if purpose:
                        result = kernel.spawn_micro_kernel(purpose, priority)
                        self._serve_json({"success": result})
                    else:
                        self._serve_json({"error": "purpose required"}, 400)
                
                else:
                    self._serve_404()
            
            def _serve_json(self, data, status=200):
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(data, default=str).encode())
            
            def _serve_404(self):
                self.send_response(404)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Not found"}).encode())
            
            def _serve_dashboard(self):
                html = self._get_dashboard_html()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                self.wfile.write(html.encode())
            
            def _get_dashboard_html(self):
                return '''<!DOCTYPE html>
<html>
<head>
    <title>Agnostic Universal Kernel Dashboard</title>
    <meta charset="UTF-8">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #eee;
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        h1 {
            text-align: center;
            font-size: 2.5em;
            margin-bottom: 30px;
            background: linear-gradient(90deg, #00d4ff, #7c3aed);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        .card {
            background: rgba(255,255,255,0.05);
            border-radius: 16px;
            padding: 24px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.1);
        }
        .card h2 {
            color: #00d4ff;
            margin-bottom: 16px;
            font-size: 1.3em;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            padding-bottom: 10px;
        }
        .metric {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        .metric-label { color: #888; }
        .metric-value { color: #fff; font-weight: 600; }
        .status-indicator {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 8px;
        }
        .status-healthy { background: #10b981; box-shadow: 0 0 10px #10b981; }
        .status-warning { background: #f59e0b; box-shadow: 0 0 10px #f59e0b; }
        .status-error { background: #ef4444; box-shadow: 0 0 10px #ef4444; }
        button {
            background: linear-gradient(90deg, #7c3aed, #00d4ff);
            border: none;
            color: white;
            padding: 12px 24px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 1em;
            margin: 5px;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(124, 58, 237, 0.4);
        }
        .log {
            background: rgba(0,0,0,0.3);
            border-radius: 8px;
            padding: 16px;
            max-height: 300px;
            overflow-y: auto;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
        }
        .subsystem {
            display: flex;
            align-items: center;
            padding: 8px 0;
        }
        .subsystem-name { flex: 1; }
        .subsystem-status {
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.85em;
        }
        .subsystem-status.active { background: rgba(16, 185, 129, 0.2); color: #10b981; }
        .subsystem-status.inactive { background: rgba(239, 68, 68, 0.2); color: #ef4444; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 Agnostic Universal Kernel Dashboard</h1>
        
        <div class="grid">
            <div class="card">
                <h2>📊 System Status</h2>
                <div id="system-status">Loading...</div>
            </div>
            
            <div class="card">
                <h2>🧩 Subsystems</h2>
                <div id="subsystems">Loading...</div>
            </div>
            
            <div class="card">
                <h2>❤️ Health Monitor</h2>
                <div id="health-status">Loading...</div>
            </div>
            
            <div class="card">
                <h2>🔧 Micro Kernels</h2>
                <div id="micro-kernels">Loading...</div>
            </div>
        </div>
        
        <div class="card">
            <h2>📈 Performance Metrics</h2>
            <div id="performance">Loading...</div>
        </div>
        
        <div class="card">
            <h2>⚡ Quick Actions</h2>
            <button onclick="healSystem()">🔧 Heal System</button>
            <button onclick="cloneKernel()">📋 Clone Kernel</button>
            <button onclick="scanConfigs()">🔍 Scan Configs</button>
            <button onclick="spawnMicroKernel()">✨ Spawn Micro Kernel</button>
            <button onclick="refreshDashboard()">🔄 Refresh</button>
        </div>
    </div>
    
    <script>
        async function fetchData(url) {
            try {
                const resp = await fetch(url);
                return await resp.json();
            } catch (e) {
                console.error(e);
                return null;
            }
        }
        
        async function updateDashboard() {
            // System Status
            const status = await fetchData('/api/status');
            if (status) {
                document.getElementById('system-status').innerHTML = `
                    <div class="metric"><span class="metric-label">Version:</span><span class="metric-value">${status.version || 'N/A'}</span></div>
                    <div class="metric"><span class="metric-label">Running:</span><span class="metric-value">${status.running ? '✅ Yes' : '❌ No'}</span></div>
                    <div class="metric"><span class="metric-label">Platform:</span><span class="metric-value">${status.platform}</span></div>
                    <div class="metric"><span class="metric-label">Uptime:</span><span class="metric-value">${Math.floor(status.uptime_seconds || 0)}s</span></div>
                    <div class="metric"><span class="metric-label">Micro Kernels:</span><span class="metric-value">${status.micro_kernels}</span></div>
                    <div class="metric"><span class="metric-label">Health Issues:</span><span class="metric-value">${status.health_issues}</span></div>
                `;
                
                // Subsystems
                let subsysHtml = '';
                for (const [name, active] of Object.entries(status.subsystems || {})) {
                    subsysHtml += `
                        <div class="subsystem">
                            <span class="subsystem-name">${name}</span>
                            <span class="subsystem-status ${active ? 'active' : 'inactive'}">${active ? 'Active' : 'Inactive'}</span>
                        </div>
                    `;
                }
                document.getElementById('subsystems').innerHTML = subsysHtml || 'No subsystems';
            }
            
            // Health
            const health = await fetchData('/api/health');
            if (health) {
                let healthHtml = '';
                for (const [comp, info] of Object.entries(health)) {
                    const statusClass = info.status === 'healthy' ? 'healthy' : 'error';
                    healthHtml += `
                        <div class="metric">
                            <span><span class="status-indicator status-${statusClass}"></span>${comp}</span>
                            <span class="metric-value">${info.status}</span>
                        </div>
                    `;
                }
                document.getElementById('health-status').innerHTML = healthHtml || 'All systems healthy ✅';
            }
            
            // Micro Kernels
            const mks = await fetchData('/api/micro-kernels');
            if (mks) {
                let mkHtml = '';
                for (const [id, info] of Object.entries(mks)) {
                    mkHtml += `
                        <div class="metric">
                            <span><span class="status-indicator status-${info.enabled ? 'healthy' : 'warning'}"></span>${info.purpose}</span>
                            <span class="metric-value">Priority: ${info.priority}</span>
                        </div>
                    `;
                }
                document.getElementById('micro-kernels').innerHTML = mkHtml || 'No micro kernels';
            }
            
            // Performance
            const stats = await fetchData('/api/stats');
            if (stats && stats.helix_stack) {
                const hs = stats.helix_stack;
                document.getElementById('performance').innerHTML = `
                    <div class="grid">
                        <div>
                            <h3 style="color:#7c3aed;margin-bottom:10px;">Cache</h3>
                            <div class="metric"><span class="metric-label">L1 Size:</span><span class="metric-value">${(hs.cache?.l1_size_mb || 0).toFixed(2)} MB</span></div>
                            <div class="metric"><span class="metric-label">L2 Size:</span><span class="metric-value">${(hs.cache?.l2_size_mb || 0).toFixed(2)} MB</span></div>
                            <div class="metric"><span class="metric-label">L3 Size:</span><span class="metric-value">${(hs.cache?.l3_size_mb || 0).toFixed(2)} MB</span></div>
                            <div class="metric"><span class="metric-label">L1 Hits:</span><span class="metric-value">${hs.cache?.l1_hits || 0}</span></div>
                            <div class="metric"><span class="metric-label">Compressions:</span><span class="metric-value">${hs.cache?.compressions || 0}</span></div>
                        </div>
                        <div>
                            <h3 style="color:#00d4ff;margin-bottom:10px;">Memory</h3>
                            <div class="metric"><span class="metric-label">Allocated:</span><span class="metric-value">${(hs.memory?.allocated_mb || 0).toFixed(2)} MB</span></div>
                            <div class="metric"><span class="metric-label">Allocations:</span><span class="metric-value">${hs.memory?.total_allocations || 0}</span></div>
                            <div class="metric"><span class="metric-label">Peak Usage:</span><span class="metric-value">${(hs.memory?.peak_usage / 1024 / 1024 || 0).toFixed(2)} MB</span></div>
                        </div>
                    </div>
                `;
            }
        }
        
        async function healSystem() {
            if (confirm('Trigger system heal?')) {
                await fetch('/api/heal', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({component: 'all'})
                });
                alert('Heal triggered');
                updateDashboard();
            }
        }
        
        async function cloneKernel() {
            const path = prompt('Enter target path:', '/tmp/kernel_clone');
            if (path) {
                const resp = await fetch('/api/clone', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({target_path: path})
                });
                const result = await resp.json();
                alert(result.success ? 'Kernel cloned!' : 'Clone failed');
            }
        }
        
        async function scanConfigs() {
            const path = prompt('Enter path to scan:', '/etc');
            if (path) {
                const resp = await fetch('/api/config/scan', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({path: path})
                });
                const result = await resp.json();
                alert(`Found ${result.configs_found || 0} configs, cloned ${result.configs_cloned || 0}`);
            }
        }
        
        async function spawnMicroKernel() {
            const purpose = prompt('Enter micro kernel purpose:', 'custom_task');
            if (purpose) {
                const resp = await fetch('/api/micro-kernel/spawn', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({purpose: purpose, priority: 5})
                });
                const result = await resp.json();
                alert(result.success ? 'Micro kernel spawned!' : 'Spawn failed');
                updateDashboard();
            }
        }
        
        function refreshDashboard() {
            updateDashboard();
        }
        
        // Initial load and auto-refresh
        updateDashboard();
        setInterval(updateDashboard, 5000);
    </script>
</body>
</html>'''
        
        return DashboardHandler


if __name__ == "__main__":
    print("Dashboard module - import and use with kernel")
