#!/usr/bin/env python3
"""
AI-Powered Dynamic Paging Manager v2.0 - WINDOWS VERSION
Manages Windows pagefile.sys dynamically for AI workloads.

Run as Administrator on the Windows host.
Dashboard: http://localhost:8888

Phoenix DevOps OS | jwl247 | GPL v3
"""

import os
import sys
import time
import threading
import subprocess
import json
import ctypes
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler


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


################################################################################
# WINDOWS SYSTEM MONITOR
################################################################################

class WindowsSystemMonitor:
    def __init__(self):
        self.kernel32 = ctypes.windll.kernel32

    def get_memory_status(self):
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength",                ctypes.c_ulong),
                ("dwMemoryLoad",            ctypes.c_ulong),
                ("ullTotalPhys",            ctypes.c_ulonglong),
                ("ullAvailPhys",            ctypes.c_ulonglong),
                ("ullTotalPageFile",        ctypes.c_ulonglong),
                ("ullAvailPageFile",        ctypes.c_ulonglong),
                ("ullTotalVirtual",         ctypes.c_ulonglong),
                ("ullAvailVirtual",         ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual",ctypes.c_ulonglong),
            ]
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        self.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return stat

    def virtual_memory(self):
        stat = self.get_memory_status()
        class MemInfo:
            pass
        m = MemInfo()
        m.total     = stat.ullTotalPhys
        m.available = stat.ullAvailPhys
        m.used      = stat.ullTotalPhys - stat.ullAvailPhys
        m.percent   = stat.dwMemoryLoad
        return m

    def swap_memory(self):
        stat  = self.get_memory_status()
        total = stat.ullTotalPageFile - stat.ullTotalPhys
        avail = stat.ullAvailPageFile
        used  = total - avail if total > 0 else 0
        class SwapInfo:
            pass
        s = SwapInfo()
        s.total   = total
        s.used    = used
        s.free    = avail
        s.percent = (used / total * 100) if total > 0 else 0
        return s

    def cpu_percent(self, interval=1):
        try:
            r = subprocess.run(
                ['powershell', '-Command',
                 '(Get-Counter "\\Processor(_Total)\\% Processor Time").CounterSamples.CookedValue'],
                capture_output=True, text=True, timeout=5)
            return float(r.stdout.strip())
        except:
            return 0.0

    def get_cpu_temperature(self):
        return None  # requires OpenHardwareMonitor

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
            p = Path(f"{self.config.pagefile_drive}\\pagefile.sys")
            if p.exists():
                return p.stat().st_size / (1024**3)
            return 0
        except Exception as e:
            logging.error(f"Error reading pagefile size: {e}")
            return 0

    def set_pagefile_size(self, size_gb: float) -> bool:
        try:
            size_mb = int(size_gb * 1024)
            ps = f"""
$cs = Get-WmiObject Win32_ComputerSystem -EnableAllPrivileges
$cs.AutomaticManagedPagefile = $false
$cs.Put()
$pf = Get-WmiObject Win32_PageFileSetting -Filter "SettingID='pagefile.sys @ {self.config.pagefile_drive}'"
if ($pf) {{
    $pf.InitialSize = {size_mb}
    $pf.MaximumSize = {size_mb}
    $pf.Put()
}} else {{
    $pf = ([WMIClass]"Win32_PageFileSetting").CreateInstance()
    $pf.Name = "{self.config.pagefile_drive}\\pagefile.sys"
    $pf.InitialSize = {size_mb}
    $pf.MaximumSize = {size_mb}
    $pf.Put()
}}
"""
            r = subprocess.run(['powershell', '-Command', ps],
                               capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                self.current_size_mb = size_mb
                logging.info(f"Pagefile set to {size_gb:.2f}GB")
                logging.warning("Restart required for changes to take full effect")
                return True
            else:
                logging.error(f"Failed to set pagefile: {r.stderr}")
                return False
        except Exception as e:
            logging.error(f"Error setting pagefile: {e}")
            return False

    def expand_pagefile(self, additional_gb: float) -> bool:
        current  = self.get_current_pagefile_size()
        new_size = min(current + additional_gb, self.config.max_pagefile_gb)
        if new_size > current:
            logging.info(f"Expanding: {current:.2f}GB -> {new_size:.2f}GB")
            return self.set_pagefile_size(new_size)
        return False

    def shrink_pagefile(self, reduce_gb: float) -> bool:
        current  = self.get_current_pagefile_size()
        new_size = max(current - reduce_gb, self.config.min_pagefile_gb)
        if new_size < current:
            logging.info(f"Shrinking: {current:.2f}GB -> {new_size:.2f}GB")
            return self.set_pagefile_size(new_size)
        return False

    def get_available_disk_space_gb(self) -> float:
        try:
            free = ctypes.c_ulonglong(0)
            ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                ctypes.c_wchar_p(self.config.pagefile_drive + "\\"),
                None, None, ctypes.pointer(free))
            return free.value / (1024**3)
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
            'last_command_time': None,
        }
        self.lock = threading.Lock()
        self._load_state()

    def _load_state(self):
        try:
            if self.control_file.exists():
                self.state.update(json.loads(self.control_file.read_text()))
        except:
            pass

    def _save_state(self):
        try:
            self.control_file.write_text(json.dumps(self.state, indent=2, default=str))
        except Exception as e:
            logging.error(f"Could not save state: {e}")

    def enable(self):
        with self.lock:
            self.state.update({'enabled': True, 'emergency_stop': False,
                               'last_command': 'enable', 'last_command_time': datetime.now()})
            self._save_state()
            logging.info("ENABLED")

    def disable(self):
        with self.lock:
            self.state.update({'enabled': False,
                               'last_command': 'disable', 'last_command_time': datetime.now()})
            self._save_state()
            logging.info("DISABLED")

    def emergency_stop(self):
        with self.lock:
            self.state.update({'enabled': False, 'emergency_stop': True,
                               'last_command': 'emergency_stop', 'last_command_time': datetime.now()})
            self._save_state()
            logging.critical("EMERGENCY STOP")

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
            self.wfile.write(DASHBOARD_HTML.encode())

        elif self.path == '/api/status':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(self.manager.get_status_dict(), default=str).encode())

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
            self.wfile.write(b'{"ok":true}')
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        pass


DASHBOARD_HTML = """<!DOCTYPE html>
<html><head><title>AI Paging - Windows</title>
<meta http-equiv="refresh" content="5">
<style>
body{font-family:monospace;background:#000;color:#0f0;padding:20px}
.header{border:3px solid #0f0;padding:20px;background:#001100}
button{background:#0f0;color:#000;border:none;padding:12px 24px;margin:5px;cursor:pointer;font-weight:bold}
button:hover{background:#0a0}
.em{background:#f00!important;color:#fff!important}
pre{color:#fff}
</style></head><body>
<div class="header">
<h1>AI PAGING MANAGER — WINDOWS</h1>
<button onclick="fetch('/api/control/enable')">ENABLE</button>
<button onclick="fetch('/api/control/disable')">DISABLE</button>
<button onclick="fetch('/api/control/expand')">EXPAND +4GB</button>
<button onclick="fetch('/api/control/shrink')">SHRINK -4GB</button>
<button class="em" onclick="if(confirm('Emergency stop?'))fetch('/api/control/emergency')">EMERGENCY</button>
</div>
<pre id="s">Loading...</pre>
<script>
async function upd(){
  try{const r=await fetch('/api/status');document.getElementById('s').textContent=JSON.stringify(await r.json(),null,2);}
  catch(e){}
}
setInterval(upd,5000);upd();
</script></body></html>"""


################################################################################
# MAIN MANAGER
################################################################################

class AIPagingManagerWindows:
    def __init__(self, config: SystemConfig):
        self.config   = config
        self.monitor  = WindowsSystemMonitor()
        self.pagefile_manager = WindowsPagefileManager(config)
        self.control  = ControlSystem(config.control_file)
        self.running  = False
        self.start_time = datetime.now()
        self.stats = {'expansions': 0, 'shrinks': 0, 'thermal_events': 0}

        log_file = Path("C:\\ProgramData\\ai-paging-manager.log")
        log_file.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [AI-PAGING] %(message)s',
            handlers=[logging.FileHandler(log_file), logging.StreamHandler()])

        logging.info("Windows AI Paging Manager initialized")
        self._start_dashboard()

    def _start_dashboard(self):
        def _run():
            try:
                DashboardHandler.manager = self
                srv = HTTPServer(('0.0.0.0', self.config.web_dashboard_port), DashboardHandler)
                logging.info(f"Dashboard: http://localhost:{self.config.web_dashboard_port}")
                srv.serve_forever()
            except Exception as e:
                logging.error(f"Dashboard error: {e}")
        threading.Thread(target=_run, daemon=True).start()

    def get_system_load(self):
        mem  = self.monitor.virtual_memory()
        swap = self.monitor.swap_memory()
        cpu  = self.monitor.cpu_percent(interval=1)
        return {
            'ram_percent':      mem.percent,
            'ram_available_gb': mem.available / (1024**3),
            'swap_percent':     swap.percent,
            'swap_used_gb':     swap.used / (1024**3),
            'cpu_percent':      cpu,
        }

    def get_status_dict(self):
        load    = self.get_system_load()
        uptime  = datetime.now() - self.start_time
        up_str  = f"{uptime.days}d {uptime.seconds//3600}h {(uptime.seconds%3600)//60}m"
        return {
            'control':  self.control.get_state(),
            'load':     load,
            'pagefile': {
                'current_gb': self.pagefile_manager.get_current_pagefile_size(),
                'max_gb':     self.config.max_pagefile_gb,
                'disk_free_gb': self.pagefile_manager.get_available_disk_space_gb(),
                'location':   f"{self.config.pagefile_drive}\\pagefile.sys",
            },
            'stats':  self.stats,
            'uptime': up_str,
        }

    def monitor_and_adapt(self):
        logging.info("Monitoring started")
        while self.running:
            try:
                if not self.control.is_enabled():
                    time.sleep(30)
                    continue

                load = self.get_system_load()

                if load['swap_percent'] > self.config.expand_threshold_percent:
                    current = self.pagefile_manager.get_current_pagefile_size()
                    if current < self.config.max_pagefile_gb:
                        logging.info(f"High swap ({load['swap_percent']:.1f}%) — expanding")
                        if self.pagefile_manager.expand_pagefile(4.0):
                            self.stats['expansions'] += 1

                elif load['swap_percent'] < self.config.shrink_threshold_percent:
                    current = self.pagefile_manager.get_current_pagefile_size()
                    if current > self.config.min_pagefile_gb:
                        logging.info(f"Low swap ({load['swap_percent']:.1f}%) — shrinking")
                        if self.pagefile_manager.shrink_pagefile(2.0):
                            self.stats['shrinks'] += 1

                self._log_status(load)
                time.sleep(self.config.monitoring_interval_seconds)

            except KeyboardInterrupt:
                self.running = False
                break
            except Exception as e:
                logging.error(f"Monitor error: {e}")
                time.sleep(self.config.monitoring_interval_seconds)

    def _log_status(self, load):
        pf = self.pagefile_manager.get_current_pagefile_size()
        logging.info(
            f"RAM {load['ram_percent']:.0f}% | "
            f"Swap {load['swap_percent']:.0f}% ({load['swap_used_gb']:.1f}GB) | "
            f"CPU {load['cpu_percent']:.0f}% | "
            f"Pagefile {pf:.1f}GB | "
            f"exp={self.stats['expansions']} shr={self.stats['shrinks']}"
        )

    def start(self):
        self.running = True
        if self.config.ai_mode:
            logging.info(f"Setting initial pagefile: {self.config.initial_pagefile_gb}GB")
            self.pagefile_manager.set_pagefile_size(self.config.initial_pagefile_gb)
        self.monitor_and_adapt()

    def stop(self):
        self.running = False
        logging.info("Stopped")


################################################################################
# CLI
################################################################################

def main():
    if not is_admin():
        print("ERROR: Run as Administrator (right-click PowerShell -> Run as Administrator)")
        sys.exit(1)

    config = SystemConfig()

    if len(sys.argv) < 2:
        print("Usage: python ai_paging_windows.py <command>")
        print("Commands: start | enable | disable | emergency | expand [gb] | shrink [gb] | status")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == 'start':
        print(f"Starting — Dashboard: http://localhost:{config.web_dashboard_port}")
        manager = AIPagingManagerWindows(config)
        try:
            manager.start()
        except KeyboardInterrupt:
            manager.stop()

    else:
        control  = ControlSystem(config.control_file)
        pagefile = WindowsPagefileManager(config)

        if cmd == 'enable':
            control.enable(); print("Enabled")
        elif cmd == 'disable':
            control.disable(); print("Disabled")
        elif cmd == 'emergency':
            control.emergency_stop(); print("Emergency stop")
        elif cmd == 'expand':
            gb = float(sys.argv[2]) if len(sys.argv) > 2 else 4.0
            pagefile.expand_pagefile(gb); print(f"Expanded +{gb}GB (restart required)")
        elif cmd == 'shrink':
            gb = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0
            pagefile.shrink_pagefile(gb); print(f"Shrunk -{gb}GB (restart required)")
        elif cmd == 'status':
            print(json.dumps(control.get_state(), indent=2, default=str))


if __name__ == "__main__":
    main()
