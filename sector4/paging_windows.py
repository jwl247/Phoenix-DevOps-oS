#!/usr/bin/env python3
"""
AI-Powered Dynamic Paging Manager v2.0 - WINDOWS VERSION
Manages Windows pagefile.sys dynamically for AI workloads

Windows sibling of sector4/paging.py (the Linux/NVMe v3.0 edition). This
one is simpler by design -- threshold-only, no PredictiveEngine or
VirtualProcessor circuit breaker -- and its actions are more consequential:
`start` disables Windows' auto-managed pagefile and sets a fixed size via
WMI, which needs a reboot to fully take effect. Requires Administrator.
Review that tradeoff before running `start`/`expand`/`shrink` for real.
"""

import os
import sys
import time
import threading
import subprocess
import json
import hashlib
import ctypes
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, fields
from typing import Dict, Optional
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler

# Check if running as admin
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

################################################################################
# CONFIGURATION
################################################################################

@dataclass
class SystemConfig:
    total_ram_gb: float = 16.0
    max_pagefile_gb: float = 64.0
    min_pagefile_gb: float = 4.0
    initial_pagefile_gb: float = 8.0
    
    max_cpu_temp: float = 80.0
    thermal_throttle_temp: float = 75.0
    
    ai_mode: bool = True
    expand_threshold_percent: float = 75.0
    shrink_threshold_percent: float = 30.0
    
    monitoring_interval_seconds: int = 15
    web_dashboard_port: int = 8888
    
    control_file: str = "C:\\ProgramData\\ai-paging-control.json"
    pagefile_drive: str = "C:"

    def __post_init__(self):
        """
        Override any field via PHOENIX_PAGING_<FIELD_NAME> (uppercase),
        same convention as sector4/paging.py's Linux sibling and the rest
        of Phoenix's PHOENIX_* env vars (usys, intake.py, etc.).
        """
        for f in fields(self):
            env_name = f"PHOENIX_PAGING_{f.name.upper()}"
            raw = os.environ.get(env_name)
            if raw is None:
                continue
            if f.type is bool or isinstance(getattr(self, f.name), bool):
                value = raw.strip().lower() in ("1", "true", "yes", "on")
            elif f.type is float or isinstance(getattr(self, f.name), float):
                value = float(raw)
            elif f.type is int or isinstance(getattr(self, f.name), int):
                value = int(raw)
            else:
                value = raw
            setattr(self, f.name, value)

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
    
    def cpu_percent(self, interval=1):
        try:
            result = subprocess.run(
                ['powershell', '-Command', 
                 '(Get-Counter "\\Processor(_Total)\\% Processor Time").CounterSamples.CookedValue'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return float(result.stdout.strip())
        except:
            return 0.0
    
    def get_cpu_temperature(self):
        # Requires OpenHardwareMonitor or similar
        return None
    
    def get_disk_temperature(self):
        return None

################################################################################
# PAGEFILE MANAGER
################################################################################

class WindowsPagefileManager:
    def __init__(self, config: SystemConfig):
        self.config = config
        self.current_size_mb = 0
        self.lock = threading.Lock()
        
    def get_current_pagefile_size(self) -> float:
        try:
            pagefile_path = Path(f"{self.config.pagefile_drive}\\pagefile.sys")
            if pagefile_path.exists():
                size_bytes = pagefile_path.stat().st_size
                return size_bytes / (1024**3)
            return 0
        except Exception as e:
            logging.error(f"Error reading pagefile size: {e}")
            return 0
    
    def set_pagefile_size(self, size_gb: float) -> bool:
        try:
            size_mb = int(size_gb * 1024)
            
            ps_script = f"""
$computersys = Get-WmiObject Win32_ComputerSystem -EnableAllPrivileges
$computersys.AutomaticManagedPagefile = $false
$computersys.Put()

$pagefileset = Get-WmiObject Win32_PageFileSetting -Filter "SettingID='pagefile.sys @ {self.config.pagefile_drive}'"

if ($pagefileset) {{
    $pagefileset.InitialSize = {size_mb}
    $pagefileset.MaximumSize = {size_mb}
    $pagefileset.Put()
}} else {{
    $pagefileset = ([WMIClass]"Win32_PageFileSetting").CreateInstance()
    $pagefileset.Name = "{self.config.pagefile_drive}\\pagefile.sys"
    $pagefileset.InitialSize = {size_mb}
    $pagefileset.MaximumSize = {size_mb}
    $pagefileset.Put()
}}
"""
            
            result = subprocess.run(
                ['powershell', '-Command', ps_script],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                self.current_size_mb = size_mb
                logging.info(f"✅ Pagefile set to {size_gb:.2f}GB")
                logging.warning("⚠️  Restart required for changes to take full effect")
                return True
            else:
                logging.error(f"Failed to set pagefile: {result.stderr}")
                return False
                
        except Exception as e:
            logging.error(f"Error setting pagefile: {e}")
            return False
    
    def expand_pagefile(self, additional_gb: float) -> bool:
        current = self.get_current_pagefile_size()
        new_size = min(current + additional_gb, self.config.max_pagefile_gb)
        
        if new_size > current:
            logging.info(f"📈 Expanding: {current:.2f}GB → {new_size:.2f}GB")
            return self.set_pagefile_size(new_size)
        return False
    
    def shrink_pagefile(self, reduce_gb: float) -> bool:
        current = self.get_current_pagefile_size()
        new_size = max(current - reduce_gb, self.config.min_pagefile_gb)
        
        if new_size < current:
            logging.info(f"📉 Shrinking: {current:.2f}GB → {new_size:.2f}GB")
            return self.set_pagefile_size(new_size)
        return False
    
    def get_available_disk_space_gb(self) -> float:
        try:
            free_bytes = ctypes.c_ulonglong(0)
            ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                ctypes.c_wchar_p(self.config.pagefile_drive + "\\"), 
                None, 
                None, 
                ctypes.pointer(free_bytes)
            )
            return free_bytes.value / (1024**3)
        except:
            return 0

################################################################################
# CONTROL SYSTEM
################################################################################

class ControlSystem:
    def __init__(self, control_file: str):
        self.control_file = Path(control_file)
        self.control_file.parent.mkdir(parents=True, exist_ok=True)
        
        self.state = {
            'enabled': True,
            'emergency_stop': False,
            'thermal_throttle': False,
            'last_command': None,
            'last_command_time': None
        }
        self.lock = threading.Lock()
        self._load_state()
    
    def _load_state(self):
        try:
            if self.control_file.exists():
                with open(self.control_file, 'r') as f:
                    saved_state = json.load(f)
                    self.state.update(saved_state)
        except:
            pass
    
    def _save_state(self):
        try:
            with open(self.control_file, 'w') as f:
                json.dump(self.state, f, indent=2, default=str)
        except Exception as e:
            logging.error(f"Could not save state: {e}")
    
    def enable(self):
        with self.lock:
            self.state['enabled'] = True
            self.state['emergency_stop'] = False
            self.state['last_command'] = 'enable'
            self.state['last_command_time'] = datetime.now()
            self._save_state()
            logging.info("✅ ENABLED")
    
    def disable(self):
        with self.lock:
            self.state['enabled'] = False
            self.state['last_command'] = 'disable'
            self.state['last_command_time'] = datetime.now()
            self._save_state()
            logging.info("⏸️  DISABLED")
    
    def emergency_stop(self):
        with self.lock:
            self.state['enabled'] = False
            self.state['emergency_stop'] = True
            self.state['last_command'] = 'emergency_stop'
            self.state['last_command_time'] = datetime.now()
            self._save_state()
            logging.critical("🚨 EMERGENCY STOP!")
    
    def set_thermal_throttle(self, throttle: bool):
        with self.lock:
            self.state['thermal_throttle'] = throttle
            self._save_state()
    
    def is_enabled(self):
        with self.lock:
            return self.state['enabled'] and not self.state['emergency_stop']
    
    def get_state(self):
        with self.lock:
            return self.state.copy()

################################################################################
# DASHBOARD
################################################################################

class DashboardHandler(BaseHTTPRequestHandler):
    manager = None
    
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            html = """
<!DOCTYPE html>
<html><head><title>AI Paging - Windows</title>
<meta http-equiv="refresh" content="5">
<style>
body{font-family:monospace;background:#000;color:#0f0;padding:20px}
.header{border:3px solid #0f0;padding:20px;background:#001100}
button{background:#0f0;color:#000;border:none;padding:12px 24px;margin:5px;cursor:pointer;font-weight:bold}
button:hover{background:#0a0}
.emergency{background:#f00!important;color:#fff!important}
pre{color:#fff}
</style></head><body>
<div class="header">
<h1>🪟 AI PAGING MANAGER</h1>
<button onclick="fetch('/api/control/enable')">🟢 ENABLE</button>
<button onclick="fetch('/api/control/disable')">⏸️ DISABLE</button>
<button onclick="fetch('/api/control/expand')">📈 EXPAND +4GB</button>
<button onclick="fetch('/api/control/shrink')">📉 SHRINK -4GB</button>
<button class="emergency" onclick="if(confirm('Emergency?'))fetch('/api/control/emergency')">🚨 EMERGENCY</button>
</div>
<pre id="status">Loading...</pre>
<script>
async function update(){
try{
const r=await fetch('/api/status');
const d=await r.json();
document.getElementById('status').textContent=JSON.stringify(d,null,2);
}catch(e){console.error(e)}
}
setInterval(update,5000);update();
</script></body></html>
"""
            self.wfile.write(html.encode())
        elif self.path == '/api/status':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(self.manager.get_status_dict()).encode())
        elif self.path.startswith('/api/control/'):
            action = self.path.split('/')[-1]
            if action == 'enable':
                self.manager.control.enable()
            elif action == 'disable':
                self.manager.control.disable()
            elif action == 'emergency':
                self.manager.control.emergency_stop()
            elif action == 'expand':
                self.manager.pagefile_manager.expand_pagefile(4.0)
            elif action == 'shrink':
                self.manager.pagefile_manager.shrink_pagefile(4.0)
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True}).encode())
        else:
            self.send_error(404)
    
    def log_message(self, format, *args):
        pass

################################################################################
# MAIN MANAGER
################################################################################

class AIPagingManagerWindows:
    def __init__(self, config: SystemConfig):
        self.config = config
        self.monitor = WindowsSystemMonitor()
        self.pagefile_manager = WindowsPagefileManager(config)
        self.control = ControlSystem(config.control_file)
        
        self.running = False
        self.start_time = datetime.now()
        self.stats = {
            'pagefile_expansions': 0,
            'pagefile_shrinks': 0,
            'thermal_throttle_events': 0,
            'emergency_stops': 0
        }
        
        log_file = Path("C:\\ProgramData\\ai-paging-manager.log")
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [AI-PAGING] %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        
        logging.info("✅ Windows AI Paging Manager initialized")
        self.start_dashboard()
    
    def start_dashboard(self):
        def run_server():
            try:
                DashboardHandler.manager = self
                server = HTTPServer(('0.0.0.0', self.config.web_dashboard_port), DashboardHandler)
                logging.info(f"📊 Dashboard: http://localhost:{self.config.web_dashboard_port}")
                server.serve_forever()
            except Exception as e:
                logging.error(f"Dashboard error: {e}")
        
        threading.Thread(target=run_server, daemon=True).start()
    
    def check_thermal_status(self):
        cpu_temp = self.monitor.get_cpu_temperature()
        return {
            'cpu_temp': cpu_temp,
            'disk_temp': None,
            'throttle': False,
            'emergency': False
        }
    
    def get_system_load(self):
        memory = self.monitor.virtual_memory()
        swap = self.monitor.swap_memory()
        cpu = self.monitor.cpu_percent(interval=1)
        
        return {
            'ram_percent': memory.percent,
            'ram_available_gb': memory.available / (1024**3),
            'swap_percent': swap.percent,
            'swap_used_gb': swap.used / (1024**3),
            'cpu_percent': cpu,
            'combined_load': (memory.percent + swap.percent) / 2
        }
    
    def get_status_dict(self):
        load = self.get_system_load()
        thermal = self.check_thermal_status()
        control = self.control.get_state()
        pagefile_size = self.pagefile_manager.get_current_pagefile_size()
        disk_free = self.pagefile_manager.get_available_disk_space_gb()
        
        uptime = datetime.now() - self.start_time
        uptime_str = f"{uptime.days}d {uptime.seconds//3600}h {(uptime.seconds%3600)//60}m"
        
        return {
            'control': control,
            'load': load,
            'thermal': thermal,
            'pagefile': {
                'current_size_gb': pagefile_size,
                'max_size_gb': self.config.max_pagefile_gb,
                'disk_free_gb': disk_free,
                'location': f"{self.config.pagefile_drive}\\pagefile.sys"
            },
            'stats': self.stats,
            'uptime': uptime_str
        }
    
    def monitor_and_adapt(self):
        logging.info("🚀 Starting monitoring")
        
        while self.running:
            try:
                if not self.control.is_enabled():
                    logging.info("⏸️  Disabled")
                    time.sleep(30)
                    continue
                
                load = self.get_system_load()
                
                # Expand if needed
                if load['swap_percent'] > self.config.expand_threshold_percent:
                    current = self.pagefile_manager.get_current_pagefile_size()
                    if current < self.config.max_pagefile_gb:
                        logging.info(f"📈 High usage ({load['swap_percent']:.1f}%) - expanding")
                        if self.pagefile_manager.expand_pagefile(4.0):
                            self.stats['pagefile_expansions'] += 1
                
                # Shrink if possible
                elif load['swap_percent'] < self.config.shrink_threshold_percent:
                    current = self.pagefile_manager.get_current_pagefile_size()
                    if current > self.config.min_pagefile_gb:
                        logging.info(f"📉 Low usage ({load['swap_percent']:.1f}%) - shrinking")
                        if self.pagefile_manager.shrink_pagefile(2.0):
                            self.stats['pagefile_shrinks'] += 1
                
                self.log_status(load)
                time.sleep(self.config.monitoring_interval_seconds)
                
            except KeyboardInterrupt:
                self.running = False
                break
            except Exception as e:
                logging.error(f"Error: {e}")
                time.sleep(self.config.monitoring_interval_seconds)
    
    def log_status(self, load):
        pagefile_size = self.pagefile_manager.get_current_pagefile_size()
        
        status = f"""
        ═══════════════════════════════════════
        AI PAGING - {datetime.now().strftime('%H:%M:%S')}
        ═══════════════════════════════════════
        RAM: {load['ram_percent']:.1f}% ({load['ram_available_gb']:.2f}GB free)
        Pagefile: {load['swap_percent']:.1f}% ({load['swap_used_gb']:.2f}GB used)
        CPU: {load['cpu_percent']:.1f}%
        
        Pagefile Size: {pagefile_size:.2f}GB
        Expansions: {self.stats['pagefile_expansions']}
        Shrinks: {self.stats['pagefile_shrinks']}
        ═══════════════════════════════════════
        """
        logging.info(status)
    
    def start(self):
        self.running = True
        
        if self.config.ai_mode:
            logging.info(f"🤖 Setting initial pagefile: {self.config.initial_pagefile_gb}GB")
            self.pagefile_manager.set_pagefile_size(self.config.initial_pagefile_gb)
        
        self.monitor_and_adapt()
    
    def stop(self):
        logging.info("🛑 Stopping")
        self.running = False
        logging.info("✅ Stopped")

################################################################################
# CLI
################################################################################

def main():
    print("""
    ╔═══════════════════════════════════════╗
    ║   AI Paging Manager - Windows v2.0    ║
    ╚═══════════════════════════════════════╝
    """)
    
    if not is_admin():
        print("❌ ERROR: Run as Administrator!")
        print("Right-click PowerShell → 'Run as Administrator'")
        sys.exit(1)
    
    if len(sys.argv) < 2:
        print("""
Usage:
  python ai_paging_windows_v2_FULL.py start      # Start manager
  python ai_paging_windows_v2_FULL.py enable     # Turn ON
  python ai_paging_windows_v2_FULL.py disable    # Turn OFF
  python ai_paging_windows_v2_FULL.py emergency  # Emergency stop
  python ai_paging_windows_v2_FULL.py expand 8   # Add 8GB
  python ai_paging_windows_v2_FULL.py shrink 4   # Remove 4GB
  python ai_paging_windows_v2_FULL.py status     # Show status
        """)
        sys.exit(1)
    
    command = sys.argv[1]
    config = SystemConfig()
    
    if command != 'start':
        control = ControlSystem(config.control_file)
        pagefile = WindowsPagefileManager(config)
        
        if command == 'enable':
            control.enable()
            print("✅ ENABLED")
        elif command == 'disable':
            control.disable()
            print("⏸️  DISABLED")
        elif command == 'emergency':
            control.emergency_stop()
            print("🚨 EMERGENCY STOP")
        elif command == 'expand':
            gb = float(sys.argv[2]) if len(sys.argv) > 2 else 4.0
            if pagefile.expand_pagefile(gb):
                print(f"✅ Expanded by {gb}GB (restart required)")
        elif command == 'shrink':
            gb = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0
            if pagefile.shrink_pagefile(gb):
                print(f"✅ Shrunk by {gb}GB (restart required)")
        elif command == 'status':
            print(json.dumps(control.get_state(), indent=2, default=str))
        return
    
    # Start manager
    print(f"""
Configuration:
  RAM: {config.total_ram_gb}GB
  Max Pagefile: {config.max_pagefile_gb}GB
  Initial: {config.initial_pagefile_gb}GB
  Dashboard: http://localhost:{config.web_dashboard_port}
  
⚠️  Pagefile changes require restart!
    """)
    
    manager = AIPagingManagerWindows(config)
    
    try:
        print("\n🚀 Starting...\n")
        manager.start()
    except KeyboardInterrupt:
        print("\n⏹️  Shutting down...")
    finally:
        manager.stop()

if __name__ == "__main__":
    main()
