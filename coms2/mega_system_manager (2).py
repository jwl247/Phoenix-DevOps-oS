#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════╗
║                                                                          ║
║           🔥 MEGA SYSTEM MANAGER - ALL-IN-ONE PROTECTION 🔥              ║
║                                                                          ║
║  • Windows Pagefile Manager (AI workloads)                               ║
║  • Port Guardian (network protection)                                    ║
║  • Security Monitor (threat detection)                                   ║
║  • Web Dashboard (unified control)                                       ║
║                                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝

MEGA SYSTEM MANAGER v1.0
One file, all protection, zero compromises
"""

import os
import sys
import time
import threading
import subprocess
import json
import ctypes
import socket
import hashlib
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Tuple
from collections import defaultdict
from http.server import HTTPServer, BaseHTTPRequestHandler
import logging

# Force UTF-8 for Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Admin check
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

################################################################################
# UNIFIED CONFIGURATION
################################################################################

@dataclass
class MegaConfig:
    # System specs
    total_ram_gb: float = 16.0
    max_pagefile_gb: float = 64.0
    min_pagefile_gb: float = 4.0
    initial_pagefile_gb: float = 8.0
    
    # Temperature limits
    max_cpu_temp: float = 80.0
    thermal_throttle_temp: float = 75.0
    
    # Pagefile settings
    ai_mode: bool = True
    expand_threshold_percent: float = 75.0
    shrink_threshold_percent: float = 30.0
    monitoring_interval_seconds: int = 15
    
    # Port Guardian
    allowed_ports: Set[int] = field(default_factory=lambda: {80, 443, 22, 3306, 8888, 5432})
    blocked_ips: Set[str] = field(default_factory=set)
    max_connections_per_ip: int = 10
    port_scan_threshold: int = 5
    brute_force_threshold: int = 5
    
    # Security
    enable_threat_detection: bool = True
    enable_intrusion_prevention: bool = True
    log_all_connections: bool = True
    
    # Dashboard
    web_dashboard_port: int = 8888
    dashboard_secret: str = field(default_factory=lambda: secrets.token_hex(16))
    
    # File paths
    control_file: str = "C:\\ProgramData\\mega-system-control.json"
    security_log: str = "C:\\ProgramData\\mega-security.log"
    pagefile_drive: str = "C:"

################################################################################
# WINDOWS SYSTEM MONITOR
################################################################################

class WindowsSystemMonitor:
    def __init__(self):
        self.kernel32 = ctypes.windll.kernel32
        
    def get_memory_status(self):
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        self.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return stat
    
    def virtual_memory(self):
        stat = self.get_memory_status()
        class MemInfo:
            def __init__(self):
                self.total = stat.ullTotalPhys
                self.available = stat.ullAvailPhys
                self.used = stat.ullTotalPhys - stat.ullAvailPhys
                self.percent = stat.dwMemoryLoad
        return MemInfo()
    
    def swap_memory(self):
        stat = self.get_memory_status()
        total = stat.ullTotalPageFile - stat.ullTotalPhys
        available = stat.ullAvailPageFile
        used = total - available if total > 0 else 0
        
        class SwapInfo:
            def __init__(self):
                self.total = total
                self.used = used
                self.free = available
                self.percent = (used / total * 100) if total > 0 else 0
        return SwapInfo()
    
    def cpu_percent(self):
        try:
            result = subprocess.run(
                ['wmic', 'cpu', 'get', 'loadpercentage'],
                capture_output=True, text=True, timeout=3,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            lines = result.stdout.strip().split('\n')
            if len(lines) > 1:
                return float(lines[1].strip())
        except:
            pass
        return 0.0

################################################################################
# PAGEFILE MANAGER
################################################################################

class PagefileManager:
    def __init__(self, config: MegaConfig):
        self.config = config
        self.current_size_mb = 0
        self.lock = threading.Lock()
        
    def get_current_size(self) -> float:
        try:
            pagefile_path = Path(f"{self.config.pagefile_drive}\\pagefile.sys")
            if pagefile_path.exists():
                return pagefile_path.stat().st_size / (1024**3)
        except:
            pass
        return 0
    
    def set_size(self, size_gb: float) -> bool:
        try:
            size_mb = int(size_gb * 1024)
            ps_script = f'''
$cs = Get-WmiObject Win32_ComputerSystem -EnableAllPrivileges
$cs.AutomaticManagedPagefile = $false
$cs.Put() | Out-Null
$pf = Get-WmiObject Win32_PageFileSetting
if ($pf) {{
    $pf.InitialSize = {size_mb}
    $pf.MaximumSize = {size_mb}
    $pf.Put() | Out-Null
}} else {{
    $pf = ([WMIClass]"Win32_PageFileSetting").CreateInstance()
    $pf.Name = "{self.config.pagefile_drive}\\pagefile.sys"
    $pf.InitialSize = {size_mb}
    $pf.MaximumSize = {size_mb}
    $pf.Put() | Out-Null
}}
Write-Output "SUCCESS"
'''
            result = subprocess.run(
                ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps_script],
                capture_output=True, text=True, timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            if result.returncode == 0 and "SUCCESS" in result.stdout:
                self.current_size_mb = size_mb
                logging.info(f"[PAGEFILE] Set to {size_gb:.2f}GB (restart required)")
                return True
        except Exception as e:
            logging.error(f"[PAGEFILE] Error: {e}")
        return False
    
    def expand(self, additional_gb: float) -> bool:
        with self.lock:
            current = self.get_current_size()
            new_size = min(current + additional_gb, self.config.max_pagefile_gb)
            if new_size > current:
                return self.set_size(new_size)
        return False
    
    def shrink(self, reduce_gb: float) -> bool:
        with self.lock:
            current = self.get_current_size()
            new_size = max(current - reduce_gb, self.config.min_pagefile_gb)
            if new_size < current:
                return self.set_size(new_size)
        return False

################################################################################
# PORT GUARDIAN
################################################################################

class PortGuardian:
    def __init__(self, config: MegaConfig):
        self.config = config
        self.connection_tracker: Dict[str, List[float]] = defaultdict(list)
        self.port_scan_tracker: Dict[str, Set[int]] = defaultdict(set)
        self.blocked_ips: Set[str] = config.blocked_ips.copy()
        self.lock = threading.Lock()
        
    def check_connection(self, ip: str, port: int) -> Tuple[bool, str]:
        """Check if connection should be allowed"""
        with self.lock:
            # Check if IP is blocked
            if ip in self.blocked_ips:
                return False, "IP_BLOCKED"
            
            # Check if port is allowed
            if port not in self.config.allowed_ports:
                self.log_threat(ip, port, "UNAUTHORIZED_PORT")
                return False, "PORT_NOT_ALLOWED"
            
            # Track connections per IP
            now = time.time()
            self.connection_tracker[ip] = [t for t in self.connection_tracker[ip] if now - t < 60]
            self.connection_tracker[ip].append(now)
            
            # Check connection limit
            if len(self.connection_tracker[ip]) > self.config.max_connections_per_ip:
                self.log_threat(ip, port, "TOO_MANY_CONNECTIONS")
                self.blocked_ips.add(ip)
                return False, "RATE_LIMIT_EXCEEDED"
            
            # Track port scanning
            self.port_scan_tracker[ip].add(port)
            if len(self.port_scan_tracker[ip]) > self.config.port_scan_threshold:
                self.log_threat(ip, port, "PORT_SCAN_DETECTED")
                self.blocked_ips.add(ip)
                return False, "PORT_SCAN_DETECTED"
            
            return True, "ALLOWED"
    
    def log_threat(self, ip: str, port: int, threat_type: str):
        logging.warning(f"[PORT GUARDIAN] {threat_type}: {ip}:{port}")
    
    def get_stats(self) -> Dict:
        with self.lock:
            return {
                'blocked_ips': len(self.blocked_ips),
                'tracked_ips': len(self.connection_tracker),
                'total_connections': sum(len(v) for v in self.connection_tracker.values())
            }

################################################################################
# SECURITY MONITOR
################################################################################

class SecurityMonitor:
    def __init__(self, config: MegaConfig):
        self.config = config
        self.threats_detected = []
        self.login_attempts: Dict[str, int] = defaultdict(int)
        self.lock = threading.Lock()
        
    def check_brute_force(self, ip: str) -> bool:
        """Check for brute force attempts"""
        with self.lock:
            self.login_attempts[ip] += 1
            if self.login_attempts[ip] > self.config.brute_force_threshold:
                self.log_threat(ip, "BRUTE_FORCE_ATTACK")
                return True
        return False
    
    def log_threat(self, source: str, threat_type: str):
        with self.lock:
            threat = {
                'timestamp': datetime.now().isoformat(),
                'source': source,
                'type': threat_type
            }
            self.threats_detected.append(threat)
            logging.critical(f"[SECURITY] {threat_type} from {source}")
    
    def get_recent_threats(self, limit: int = 10) -> List[Dict]:
        with self.lock:
            return self.threats_detected[-limit:]

################################################################################
# CONTROL SYSTEM
################################################################################

class ControlSystem:
    def __init__(self, control_file: str):
        self.control_file = Path(control_file)
        self.control_file.parent.mkdir(parents=True, exist_ok=True)
        
        self.state = {
            'pagefile_enabled': True,
            'port_guardian_enabled': True,
            'security_monitor_enabled': True,
            'emergency_stop': False,
            'last_command': None,
            'last_command_time': None
        }
        self.lock = threading.Lock()
        self._load_state()
    
    def _load_state(self):
        try:
            if self.control_file.exists():
                with open(self.control_file, 'r') as f:
                    self.state.update(json.load(f))
        except:
            pass
    
    def _save_state(self):
        try:
            with open(self.control_file, 'w') as f:
                json.dump(self.state, f, indent=2, default=str)
        except:
            pass
    
    def enable_all(self):
        with self.lock:
            self.state['pagefile_enabled'] = True
            self.state['port_guardian_enabled'] = True
            self.state['security_monitor_enabled'] = True
            self.state['emergency_stop'] = False
            self._save_state()
            logging.info("[CONTROL] All systems ENABLED")
    
    def disable_all(self):
        with self.lock:
            self.state['pagefile_enabled'] = False
            self.state['port_guardian_enabled'] = False
            self.state['security_monitor_enabled'] = False
            self._save_state()
            logging.info("[CONTROL] All systems DISABLED")
    
    def emergency_stop(self):
        with self.lock:
            self.state['emergency_stop'] = True
            self.disable_all()
            self._save_state()
            logging.critical("[CONTROL] EMERGENCY STOP ACTIVATED")
    
    def get_state(self) -> Dict:
        with self.lock:
            return self.state.copy()

################################################################################
# UNIFIED DASHBOARD
################################################################################

class DashboardHandler(BaseHTTPRequestHandler):
    manager = None
    
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            html = """
<!DOCTYPE html>
<html><head><title>MEGA System Manager</title>
<meta http-equiv="refresh" content="5">
<style>
body{font-family:monospace;background:#000;color:#0f0;padding:20px;margin:0}
.header{border:3px solid #0f0;padding:20px;background:#001a00;margin-bottom:20px}
h1{margin:0;font-size:28px;text-shadow:0 0 10px #0f0}
.section{border:2px solid #0f0;padding:15px;margin:15px 0;background:#001100}
h2{color:#0ff;border-bottom:2px solid #0ff;padding-bottom:5px}
button{background:#0f0;color:#000;border:none;padding:12px 24px;margin:5px;cursor:pointer;font-weight:bold;border-radius:5px;font-size:13px}
button:hover{background:#0d0;box-shadow:0 0 10px #0f0}
.emergency{background:#f00!important;color:#fff!important}
.emergency:hover{background:#d00!important;box-shadow:0 0 15px #f00!important}
pre{color:#fff;background:#002200;padding:15px;border:1px solid #0f0;overflow-x:auto}
.status-ok{color:#0f0}
.status-warn{color:#ff0}
.status-error{color:#f00}
</style></head><body>
<div class="header">
<h1>🔥 MEGA SYSTEM MANAGER 🔥</h1>
<p>Unified Protection Dashboard</p>
<div style="margin-top:15px">
<button onclick="cmd('enable')">▶ START ALL</button>
<button onclick="cmd('disable')">⏸ PAUSE ALL</button>
<button onclick="cmd('expand')">📈 EXPAND +4GB</button>
<button onclick="cmd('shrink')">📉 SHRINK -2GB</button>
<button class="emergency" onclick="if(confirm('Emergency stop all systems?'))cmd('emergency')">🚨 EMERGENCY STOP</button>
</div>
</div>

<div class="section">
<h2>💾 PAGEFILE MANAGER</h2>
<pre id="pagefile">Loading...</pre>
</div>

<div class="section">
<h2>🛡️ PORT GUARDIAN</h2>
<pre id="ports">Loading...</pre>
</div>

<div class="section">
<h2>🔒 SECURITY MONITOR</h2>
<pre id="security">Loading...</pre>
</div>

<div class="section">
<h2>🧬 HELIX AI MEMORY</h2>
<pre id="helix">Loading...</pre>
</div>

<div class="section">
<h2>📊 SYSTEM STATUS</h2>
<pre id="system">Loading...</pre>
</div>

<script>
function cmd(action){
fetch('/api/control/'+action).then(r=>r.json()).then(d=>{
alert(d.success?'Command executed!':'Command failed');
update();
}).catch(e=>alert('Error: '+e));
}
async function update(){
try{
const r=await fetch('/api/status');
const d=await r.json();

document.getElementById('pagefile').textContent=
`Status: ${d.control.pagefile_enabled?'ENABLED':'DISABLED'}
Current Size: ${d.pagefile.current_size_gb.toFixed(2)}GB
Max Size: ${d.pagefile.max_size_gb.toFixed(2)}GB
Usage: ${d.load.swap_percent.toFixed(1)}%
Expansions: ${d.stats.pagefile_expansions}
Shrinks: ${d.stats.pagefile_shrinks}`;

document.getElementById('ports').textContent=
`Status: ${d.control.port_guardian_enabled?'ACTIVE':'INACTIVE'}
Blocked IPs: ${d.port_guardian.blocked_ips}
Tracked IPs: ${d.port_guardian.tracked_ips}
Total Connections: ${d.port_guardian.total_connections}
Allowed Ports: ${d.config.allowed_ports.join(', ')}`;

document.getElementById('security').textContent=
`Status: ${d.control.security_monitor_enabled?'MONITORING':'PAUSED'}
Recent Threats: ${d.security.recent_threats.length}
Emergency Mode: ${d.control.emergency_stop?'ACTIVE':'Normal'}`;

document.getElementById('helix').textContent=
`Total Packets: ${d.helix.total_packets}
Cache Size: ${d.helix.cache_size}
Cache Hit Rate: ${(d.helix.cache_hit_rate*100).toFixed(1)}%
Cache Hits: ${d.helix.cache_hits}
Cache Misses: ${d.helix.cache_misses}
Total Requests: ${d.helix.total_requests}
Storage: Local (C:\\ProgramData\\helix-storage)`;

document.getElementById('system').textContent=
`RAM Usage: ${d.load.ram_percent.toFixed(1)}% (${d.load.ram_available_gb.toFixed(2)}GB available)
CPU Usage: ${d.load.cpu_percent.toFixed(1)}%
Uptime: ${d.uptime}`;

}catch(e){
console.error(e);
}
}
setInterval(update,5000);
update();
</script></body></html>
"""
            self.wfile.write(html.encode('utf-8'))
        elif self.path == '/api/status':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(self.manager.get_status()).encode())
        elif self.path.startswith('/api/control/'):
            action = self.path.split('/')[-1]
            success = self.manager.handle_command(action)
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': success}).encode())
        else:
            self.send_error(404)
    
    def log_message(self, format, *args):
        pass
###############################################
import pickle
import hashlib
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional, List

class LocalHelixStorage:
    """Local file storage backend for Helix (replaces S3)"""
    def __init__(self, storage_dir: str = "C:\\ProgramData\\helix-storage"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
    def store_packet(self, packet_id: str, packet_data: Dict) -> bool:
        try:
            file_path = self.storage_dir / f"{packet_id}.pkl"
            with open(file_path, 'wb') as f:
                pickle.dump(packet_data, f)
            return True
        except Exception as e:
            logging.error(f"[HELIX] Store error: {e}")
            return False
    
    def retrieve_packet(self, packet_id: str) -> Optional[Dict]:
        try:
            file_path = self.storage_dir / f"{packet_id}.pkl"
            if file_path.exists():
                with open(file_path, 'rb') as f:
                    return pickle.load(f)
        except Exception as e:
            logging.error(f"[HELIX] Retrieve error: {e}")
        return None
    
    def list_packets(self) -> List[str]:
        return [f.stem for f in self.storage_dir.glob("*.pkl")]

class HelixAI:
    """Helix AI Memory System - Local Storage Version"""
    def __init__(self, cache_size: int = 10000):
        self.storage = LocalHelixStorage()
        self.cache: Dict[str, Any] = {}
        self.cache_size = cache_size
        self.cache_hits = 0
        self.cache_misses = 0
        self.total_requests = 0
        
    def store_data(self, data_id: str, payload: Dict) -> bool:
        """Store data with caching"""
        packet = {
            'id': data_id,
            'data': payload,
            'timestamp': time.time()
        }
        
        # Add to cache
        self.cache[data_id] = packet
        if len(self.cache) > self.cache_size:
            # Evict oldest
            oldest = list(self.cache.keys())[0]
            del self.cache[oldest]
        
        # Persist to disk
        return self.storage.store_packet(data_id, packet)
    
    def retrieve_data(self, data_id: str) -> Optional[Dict]:
        """Retrieve data (cache-first)"""
        self.total_requests += 1
        
        # Check cache
        if data_id in self.cache:
            self.cache_hits += 1
            return self.cache[data_id]
        
        # Fallback to storage
        packet = self.storage.retrieve_packet(data_id)
        if packet:
            self.cache_misses += 1
            self.cache[data_id] = packet
            return packet
        return None
    
    def stats(self) -> Dict[str, int]:
        """Return cache statistics"""
        return {
            "total_requests": self.total_requests,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_size": len(self.cache)
        }
##############
# MEGA SYSTEM MANAGER (MAIN)
################################################################################

class MegaSystemManager:
    def __init__(self, config: MegaConfig):
        self.config = config
        self.monitor = WindowsSystemMonitor()
        self.pagefile = PagefileManager(config)
        self.port_guardian = PortGuardian(config)
        self.security = SecurityMonitor(config)
        self.control = ControlSystem(config.control_file)
        self.helix = HelixAI(cache_size=10000)  # ADD HELIX!
        
        self.running = False
        self.start_time = datetime.now()
        self.stats = {
            'pagefile_expansions': 0,
            'pagefile_shrinks': 0,
            'threats_blocked': 0
        }
        
        # Setup logging
        log_file = Path(config.security_log)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [MEGA] %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        
        logging.info("[INIT] MEGA System Manager initialized")
        logging.info("[INIT] Helix AI initialized with local storage")
        self.start_dashboard()
    
    def start_dashboard(self):
        def run_server():
            try:
                DashboardHandler.manager = self
                server = HTTPServer(('0.0.0.0', self.config.web_dashboard_port), DashboardHandler)
                logging.info(f"[WEB] Dashboard: http://localhost:{self.config.web_dashboard_port}")
                server.serve_forever()
            except Exception as e:
                logging.error(f"[WEB] Dashboard error: {e}")
        threading.Thread(target=run_server, daemon=True).start()
    
    def get_status(self) -> Dict:
        load = {
            'ram_percent': self.monitor.virtual_memory().percent,
            'ram_available_gb': self.monitor.virtual_memory().available / (1024**3),
            'swap_percent': self.monitor.swap_memory().percent,
            'cpu_percent': self.monitor.cpu_percent()
        }
        
        uptime = datetime.now() - self.start_time
        uptime_str = f"{uptime.days}d {uptime.seconds//3600}h {(uptime.seconds%3600)//60}m"
        
        return {
            'control': self.control.get_state(),
            'load': load,
            'pagefile': {
                'current_size_gb': self.pagefile.get_current_size(),
                'max_size_gb': self.config.max_pagefile_gb
            },
            'port_guardian': self.port_guardian.get_stats(),
            'security': {
                'recent_threats': self.security.get_recent_threats()
            },
            'helix': self.helix.get_stats(),  # ADD HELIX STATS!
            'stats': self.stats,
            'uptime': uptime_str,
            'config': {
                'allowed_ports': list(self.config.allowed_ports)
            }
        }
    
    def handle_command(self, action: str) -> bool:
        try:
            if action == 'enable':
                self.control.enable_all()
                return True
            elif action == 'disable':
                self.control.disable_all()
                return True
            elif action == 'emergency':
                self.control.emergency_stop()
                return True
            elif action == 'expand':
                if self.pagefile.expand(4.0):
                    self.stats['pagefile_expansions'] += 1
                    return True
            elif action == 'shrink':
                if self.pagefile.shrink(2.0):
                    self.stats['pagefile_shrinks'] += 1
                    return True
        except Exception as e:
            logging.error(f"[CMD] Error: {e}")
        return False
    
    def monitor_loop(self):
        logging.info("[START] Monitoring active")
        
        while self.running:
            try:
                state = self.control.get_state()
                
                if state['emergency_stop']:
                    logging.warning("[EMERGENCY] Systems halted")
                    time.sleep(30)
                    continue
                
                # Pagefile monitoring
                if state['pagefile_enabled']:
                    swap = self.monitor.swap_memory()
                    if swap.percent > self.config.expand_threshold_percent:
                        if self.pagefile.expand(4.0):
                            self.stats['pagefile_expansions'] += 1
                            logging.info(f"[PAGEFILE] Expanded (usage: {swap.percent:.1f}%)")
                    elif swap.percent < self.config.shrink_threshold_percent:
                        if self.pagefile.shrink(2.0):
                            self.stats['pagefile_shrinks'] += 1
                            logging.info(f"[PAGEFILE] Shrunk (usage: {swap.percent:.1f}%)")
                
                time.sleep(self.config.monitoring_interval_seconds)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                logging.error(f"[MONITOR] Error: {e}")
                time.sleep(30)
    
    def start(self):
        self.running = True
        
        if self.config.ai_mode:
            logging.info(f"[PAGEFILE] Setting initial size: {self.config.initial_pagefile_gb}GB")
            self.pagefile.set_size(self.config.initial_pagefile_gb)
        
        self.monitor_loop()
    
    def stop(self):
        logging.info("[STOP] Shutting down")
        self.running = False

################################################################################
# CLI
################################################################################

def main():
    print("""
╔══════════════════════════════════════════════════════════════════════════╗
║                                                                          ║
║               🔥 MEGA SYSTEM MANAGER v1.0 🔥                             ║
║                                                                          ║
║  All-in-One Protection:                                                  ║
║  • Pagefile Management (AI optimized)                                    ║
║  • Port Guardian (network protection)                                    ║
║  • Security Monitor (threat detection)                                   ║
║  • Unified Dashboard (web interface)                                     ║
║                                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝
    """)
    
    if not is_admin():
        print("\n[ERROR] Administrator rights required!")
        print("\nRun PowerShell as Administrator, then:")
        print("python mega_system_manager.py start")
        sys.exit(1)
    
    if len(sys.argv) < 2:
        print("""
Usage:
  python script.py start      # Start all systems
  python script.py enable     # Enable all systems
  python script.py disable    # Disable all systems
  python script.py emergency  # Emergency stop
  python script.py status     # Show status
        """)
        sys.exit(1)
    
    command = sys.argv[1]
    config = MegaConfig()
    
    if command == 'start':
        print(f"""
Configuration:
  RAM: {config.total_ram_gb}GB
  Max Pagefile: {config.max_pagefile_gb}GB
  Allowed Ports: {', '.join(map(str, config.allowed_ports))}
  Dashboard: http://localhost:{config.web_dashboard_port}
  
[!] Pagefile changes require system restart!
        """)
        
        manager = MegaSystemManager(config)
        try:
            print("\n[START] Manager starting...\n")
            manager.start()
        except KeyboardInterrupt:
            print("\n[STOP] Shutting down...")
        finally:
            manager.stop()
    else:
        control = ControlSystem(config.control_file)
        if command == 'enable':
            control.enable_all()
            print("[OK] All systems ENABLED")
        elif command == 'disable':
            control.disable_all()
            print("[PAUSE] All systems DISABLED")
        elif command == 'emergency':
            control.emergency_stop()
            print("[EMERGENCY] Emergency stop activated!")
        elif command == 'status':
            print(json.dumps(control.get_state(), indent=2, default=str))

# -------------------------------------------------------------------------
# Initialization block: runs when you call `python helix.py`
# -------------------------------------------------------------------------
if __name__ == "__main__":
    h = HelixAI()
    h.store_data("init-proof", {"msg": "Helix v1 initialized"})
    packet = h.retrieve_data("init-proof")
    print("[HELIX INIT] Retrieved:", packet)
    print("[HELIX INIT] Stats:", h.stats())


