#!/usr/bin/env python3
"""
AI-Powered Dynamic Swap Manager v1.0 - LINUX VERSION
Manages Linux swap files dynamically for AI workloads.
Designed to be structurally close to the Windows version for easy unification later.

Run as root on phoenix-ext (or any Linux node).
Dashboard: http://localhost:8888

Phoenix DevOps OS | jwl247 | GPL v3
"""

import os
import sys
import time
import threading
import subprocess
import json
import shutil
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Optional, List
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler


################################################################################
# CONFIGURATION
################################################################################

@dataclass
class SystemConfig:
    total_ram_gb: float = 16.0
    max_swap_gb: float = 64.0
    min_swap_gb: float = 4.0
    initial_swap_gb: float = 8.0

    max_cpu_temp: float = 80.0
    thermal_throttle_temp: float = 75.0

    ai_mode: bool = True
    expand_threshold_percent: float = 75.0
    shrink_threshold_percent: float = 30.0

    monitoring_interval_seconds: int = 15
    web_dashboard_port: int = 8888

    control_file: str = "/var/lib/ai-paging/ai-paging-control.json"
    swap_dir: str = "/var/swap/ai-paging"
    base_swap_name: str = "ai_paging_base.swap"

    swappiness_high_pressure: int = 80
    swappiness_normal: int = 10


################################################################################
# LINUX SYSTEM MONITOR
################################################################################

class LinuxSystemMonitor:

    def _read_meminfo(self) -> Dict[str, int]:
        data = {}
        try:
            with open('/proc/meminfo') as f:
                for line in f:
                    if ':' in line:
                        key, val = line.split(':', 1)
                        parts = val.strip().split()
                        if parts:
                            data[key.strip()] = int(parts[0]) * 1024
        except Exception as e:
            logging.error(f"Failed to read /proc/meminfo: {e}")
        return data

    def virtual_memory(self):
        d = self._read_meminfo()
        total     = d.get('MemTotal', 0)
        available = d.get('MemAvailable', d.get('MemFree', 0))
        used      = total - available
        percent   = (used / total * 100) if total > 0 else 0
        class M:
            pass
        m = M(); m.total = total; m.available = available; m.used = used
        m.percent = round(percent, 1)
        return m

    def swap_memory(self):
        d = self._read_meminfo()
        total = d.get('SwapTotal', 0)
        free  = d.get('SwapFree', 0)
        used  = total - free
        percent = (used / total * 100) if total > 0 else 0
        class S:
            pass
        s = S(); s.total = total; s.used = used; s.free = free
        s.percent = round(percent, 1)
        return s

    def cpu_percent(self, interval: float = 1.0) -> float:
        def read_stats():
            with open('/proc/stat') as f:
                line = f.readline().strip()
            parts = [int(x) for x in line.split()[1:]]
            total = sum(parts)
            idle  = parts[3] + (parts[4] if len(parts) > 4 else 0)
            return total, idle
        try:
            t1, i1 = read_stats()
            time.sleep(max(0.1, interval))
            t2, i2 = read_stats()
            dt = t2 - t1
            if dt <= 0:
                return 0.0
            return round(min(100.0, 100.0 * (dt - (i2 - i1)) / dt), 1)
        except Exception:
            return 0.0

    def get_cpu_temperature(self) -> Optional[float]:
        try:
            for zone in Path('/sys/class/thermal').glob('thermal_zone*/temp'):
                val = zone.read_text().strip()
                if val:
                    t = int(val) / 1000.0
                    if 20 < t < 120:
                        return round(t, 1)
        except Exception:
            pass
        return None


################################################################################
# SWAP MANAGER
################################################################################

class LinuxSwapManager:
    def __init__(self, config: SystemConfig):
        self.config = config
        self.swap_dir = Path(config.swap_dir)
        self.swap_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.swap_dir, 0o755)
        except:
            pass
        self.current_extra_swaps: List[Path] = []

    def _get_active_swaps(self) -> List[Dict]:
        swaps = []
        try:
            with open('/proc/swaps') as f:
                next(f)
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 5:
                        swaps.append({
                            'filename': parts[0],
                            'type': parts[1],
                            'size_kb': int(parts[2]),
                            'used_kb': int(parts[3]),
                            'priority': int(parts[4]),
                        })
        except Exception as e:
            logging.error(f"Error reading /proc/swaps: {e}")
        return swaps

    def get_current_swap_size_gb(self) -> float:
        return sum(s['size_kb'] for s in self._get_active_swaps()) / (1024 * 1024)

    def get_available_disk_space_gb(self, path: Optional[Path] = None) -> float:
        try:
            return shutil.disk_usage(path or self.swap_dir).free / (1024**3)
        except Exception:
            return 0.0

    def _create_swapfile(self, path: Path, size_gb: float) -> bool:
        size_mb = int(size_gb * 1024)
        try:
            if path.exists():
                logging.warning(f"Swapfile {path} already exists, skipping.")
                return False
            logging.info(f"Creating swapfile {path} ({size_gb:.1f}GB)...")

            r = subprocess.run(['fallocate', '-l', f'{size_mb}M', str(path)],
                               capture_output=True, text=True, timeout=120)
            if r.returncode != 0:
                logging.info("fallocate failed, falling back to dd...")
                r = subprocess.run(
                    ['dd', 'if=/dev/zero', f'of={path}', 'bs=1M',
                     f'count={size_mb}', 'status=none'],
                    capture_output=True, text=True, timeout=300)
                if r.returncode != 0:
                    logging.error(f"dd failed: {r.stderr}")
                    return False

            os.chmod(path, 0o600)
            os.chown(path, 0, 0)

            r = subprocess.run(['mkswap', str(path)],
                               capture_output=True, text=True, timeout=60)
            if r.returncode != 0:
                logging.error(f"mkswap failed: {r.stderr}")
                path.unlink(missing_ok=True)
                return False

            r = subprocess.run(['swapon', str(path)],
                               capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                logging.error(f"swapon failed: {r.stderr}")
                path.unlink(missing_ok=True)
                return False

            logging.info(f"Added swapfile {path.name} ({size_gb:.1f}GB)")
            self.current_extra_swaps.append(path)
            return True
        except Exception as e:
            logging.error(f"Failed to create swapfile {path}: {e}")
            path.unlink(missing_ok=True)
            return False

    def expand_swap(self, additional_gb: float) -> bool:
        current = self.get_current_swap_size_gb()
        if current >= self.config.max_swap_gb:
            logging.info("At max_swap_gb limit.")
            return False
        add_size = min(additional_gb, self.config.max_swap_gb - current)
        if add_size < 0.5:
            return False
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self._create_swapfile(self.swap_dir / f"ai_extra_{ts}.swap", add_size)

    def shrink_swap(self, reduce_gb: float) -> bool:
        extras = [s for s in self._get_active_swaps()
                  if s['filename'].startswith(str(self.swap_dir))
                  and 'ai_extra_' in s['filename']]
        if not extras:
            logging.info("No extra swapfiles to remove.")
            return False
        extras.sort(key=lambda x: x['size_kb'], reverse=True)
        target = Path(extras[0]['filename'])
        try:
            r = subprocess.run(['swapoff', str(target)],
                               capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                logging.error(f"swapoff failed: {r.stderr}")
                return False
            target.unlink(missing_ok=True)
            if target in self.current_extra_swaps:
                self.current_extra_swaps.remove(target)
            logging.info(f"Removed {target.name}")
            return True
        except Exception as e:
            logging.error(f"Error shrinking swap: {e}")
            return False

    def ensure_base_swap(self) -> bool:
        current = self.get_current_swap_size_gb()
        if current >= self.config.initial_swap_gb:
            logging.info(f"Base swap met ({current:.1f}GB >= {self.config.initial_swap_gb}GB)")
            return True
        needed = self.config.initial_swap_gb - current
        base   = self.swap_dir / self.config.base_swap_name
        return self._create_swapfile(base, needed)

    def set_swappiness(self, value: int) -> bool:
        try:
            r = subprocess.run(['sysctl', '-w', f'vm.swappiness={value}'],
                               capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                logging.info(f"vm.swappiness={value}")
                return True
            logging.error(f"sysctl failed: {r.stderr}")
            return False
        except Exception as e:
            logging.error(f"Failed to set swappiness: {e}")
            return False


################################################################################
# CONTROL SYSTEM
################################################################################

class ControlSystem:
    def __init__(self, control_file: str):
        self.control_file = Path(control_file)
        self.control_file.parent.mkdir(parents=True, exist_ok=True)
        self.state = {
            'enabled': True, 'emergency_stop': False,
            'thermal_throttle': False,
            'last_command': None, 'last_command_time': None,
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
                               'last_command': 'enable',
                               'last_command_time': datetime.now().isoformat()})
            self._save_state(); logging.info("ENABLED")

    def disable(self):
        with self.lock:
            self.state.update({'enabled': False, 'last_command': 'disable',
                               'last_command_time': datetime.now().isoformat()})
            self._save_state(); logging.info("DISABLED")

    def emergency_stop(self):
        with self.lock:
            self.state.update({'enabled': False, 'emergency_stop': True,
                               'last_command': 'emergency_stop',
                               'last_command_time': datetime.now().isoformat()})
            self._save_state(); logging.critical("EMERGENCY STOP")

    def set_thermal_throttle(self, throttle: bool):
        with self.lock:
            self.state['thermal_throttle'] = throttle
            self._save_state()

    def is_enabled(self) -> bool:
        with self.lock:
            return self.state['enabled'] and not self.state['emergency_stop']

    def get_state(self) -> dict:
        with self.lock:
            return self.state.copy()


################################################################################
# DASHBOARD
################################################################################

DASHBOARD_HTML = """<!DOCTYPE html>
<html><head><title>AI Swap Manager - Linux</title>
<meta http-equiv="refresh" content="5">
<style>
body{font-family:monospace;background:#000;color:#0f0;padding:20px}
.header{border:3px solid #0f0;padding:20px;background:#001100}
button{background:#0f0;color:#000;border:none;padding:12px 24px;margin:5px;cursor:pointer;font-weight:bold}
button:hover{background:#0a0}
.em{background:#f00!important;color:#fff!important}
pre{color:#fff;white-space:pre-wrap}
</style></head><body>
<div class="header">
<h1>AI SWAP MANAGER — LINUX</h1>
<button onclick="fetch('/api/control/enable')">ENABLE</button>
<button onclick="fetch('/api/control/disable')">DISABLE</button>
<button onclick="fetch('/api/control/expand')">ADD +4GB SWAP</button>
<button onclick="fetch('/api/control/shrink')">REMOVE EXTRA SWAP</button>
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
            body = json.dumps(self.manager.get_status_dict() if self.manager else {})
            self.wfile.write(body.encode())
        elif self.path.startswith('/api/control/'):
            action = self.path.split('/')[-1]
            if self.manager:
                if action == 'enable':   self.manager.control.enable()
                elif action == 'disable': self.manager.control.disable()
                elif action == 'emergency': self.manager.control.emergency_stop()
                elif action == 'expand': self.manager.swap_manager.expand_swap(4.0)
                elif action == 'shrink': self.manager.swap_manager.shrink_swap(4.0)
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        pass


################################################################################
# MAIN MANAGER
################################################################################

class AIPagingManagerLinux:
    def __init__(self, config: SystemConfig):
        self.config       = config
        self.monitor      = LinuxSystemMonitor()
        self.swap_manager = LinuxSwapManager(config)
        self.control      = ControlSystem(config.control_file)
        self.running      = False
        self.start_time   = datetime.now()
        self.stats = {'swap_expansions': 0, 'swap_shrinks': 0,
                      'thermal_events': 0, 'swappiness_changes': 0}

        log_file = Path("/var/log/ai-paging-manager.log")
        log_file.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [AI-SWAP-LINUX] %(message)s',
            handlers=[logging.FileHandler(log_file), logging.StreamHandler(sys.stdout)])
        logging.info("Linux AI Swap Manager initialized")
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

    def check_thermal_status(self):
        t = self.monitor.get_cpu_temperature()
        return {
            'cpu_temp': t,
            'throttle': t and t > self.config.thermal_throttle_temp,
            'emergency': t and t > self.config.max_cpu_temp,
        }

    def get_system_load(self):
        mem  = self.monitor.virtual_memory()
        swap = self.monitor.swap_memory()
        cpu  = self.monitor.cpu_percent(interval=1)
        return {
            'ram_percent':      mem.percent,
            'ram_available_gb': round(mem.available / (1024**3), 2),
            'swap_percent':     swap.percent,
            'swap_used_gb':     round(swap.used / (1024**3), 2),
            'cpu_percent':      cpu,
        }

    def get_status_dict(self):
        load    = self.get_system_load()
        thermal = self.check_thermal_status()
        uptime  = datetime.now() - self.start_time
        up_str  = f"{uptime.days}d {uptime.seconds//3600}h {(uptime.seconds%3600)//60}m"
        return {
            'control':  self.control.get_state(),
            'load':     load,
            'thermal':  thermal,
            'swap': {
                'current_total_gb': round(self.swap_manager.get_current_swap_size_gb(), 2),
                'max_target_gb':    self.config.max_swap_gb,
                'disk_free_gb':     round(self.swap_manager.get_available_disk_space_gb(), 2),
                'swap_dir':         str(self.config.swap_dir),
                'active_files':     len(self.swap_manager._get_active_swaps()),
            },
            'stats':    self.stats,
            'uptime':   up_str,
            'platform': 'linux',
        }

    def monitor_and_adapt(self):
        logging.info("Monitoring started")
        while self.running:
            try:
                if not self.control.is_enabled():
                    time.sleep(30)
                    continue

                load    = self.get_system_load()
                thermal = self.check_thermal_status()

                if thermal.get('emergency'):
                    logging.critical(f"Thermal emergency ({thermal['cpu_temp']}C) — pausing expansion")
                    self.stats['thermal_events'] += 1
                    time.sleep(60)
                    continue

                if load['swap_percent'] > self.config.expand_threshold_percent:
                    if self.swap_manager.get_current_swap_size_gb() < self.config.max_swap_gb:
                        logging.info(f"High swap ({load['swap_percent']:.1f}%) — expanding")
                        if self.swap_manager.expand_swap(4.0):
                            self.stats['swap_expansions'] += 1
                            self.swap_manager.set_swappiness(self.config.swappiness_high_pressure)
                            self.stats['swappiness_changes'] += 1

                elif load['swap_percent'] < self.config.shrink_threshold_percent:
                    if (self.swap_manager.get_current_swap_size_gb() > self.config.min_swap_gb
                            and self.swap_manager.current_extra_swaps):
                        logging.info(f"Low swap ({load['swap_percent']:.1f}%) — shrinking")
                        if self.swap_manager.shrink_swap(4.0):
                            self.stats['swap_shrinks'] += 1
                            self.swap_manager.set_swappiness(self.config.swappiness_normal)
                            self.stats['swappiness_changes'] += 1

                self._log_status(load, thermal)
                time.sleep(self.config.monitoring_interval_seconds)

            except KeyboardInterrupt:
                self.running = False
                break
            except Exception as e:
                logging.error(f"Monitor error: {e}")
                time.sleep(self.config.monitoring_interval_seconds)

    def _log_status(self, load, thermal):
        pf = self.swap_manager.get_current_swap_size_gb()
        logging.info(
            f"RAM {load['ram_percent']:.0f}% | "
            f"Swap {load['swap_percent']:.0f}% ({load['swap_used_gb']:.1f}GB) | "
            f"CPU {load['cpu_percent']:.0f}% | "
            f"Temp {thermal.get('cpu_temp','?')}C | "
            f"SwapTotal {pf:.1f}GB | "
            f"exp={self.stats['swap_expansions']} shr={self.stats['swap_shrinks']}"
        )

    def start(self):
        self.running = True
        if self.config.ai_mode:
            logging.info(f"Ensuring base swap >= {self.config.initial_swap_gb}GB...")
            self.swap_manager.ensure_base_swap()
            self.swap_manager.set_swappiness(self.config.swappiness_normal)
        self.monitor_and_adapt()

    def stop(self):
        self.running = False
        try:
            self.swap_manager.set_swappiness(60)
        except:
            pass
        logging.info("Stopped")


################################################################################
# CLI
################################################################################

def main():
    if os.geteuid() != 0:
        print("ERROR: requires root (sudo)")
        sys.exit(1)

    config = SystemConfig()

    if len(sys.argv) < 2:
        print("Usage: sudo python3 ai_paging_linux.py <command>")
        print("Commands: start | ensure-base | expand [gb] | shrink | enable | disable | emergency | status")
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == 'start':
        print(f"Starting — Dashboard: http://localhost:{config.web_dashboard_port}")
        manager = AIPagingManagerLinux(config)
        try:
            manager.start()
        except KeyboardInterrupt:
            manager.stop()
    else:
        control  = ControlSystem(config.control_file)
        swap_mgr = LinuxSwapManager(config)

        if cmd == 'enable':
            control.enable()
        elif cmd == 'disable':
            control.disable()
        elif cmd == 'emergency':
            control.emergency_stop()
        elif cmd == 'expand':
            gb = float(sys.argv[2]) if len(sys.argv) > 2 else 4.0
            print("Added swap" if swap_mgr.expand_swap(gb) else "Failed (limit or disk full)")
        elif cmd == 'shrink':
            print("Removed swap" if swap_mgr.shrink_swap(4.0) else "Nothing to remove")
        elif cmd == 'ensure-base':
            print("Base swap ready" if swap_mgr.ensure_base_swap() else "Failed")
        elif cmd == 'status':
            print(json.dumps(control.get_state(), indent=2, default=str))
            print(f"Current swap: {swap_mgr.get_current_swap_size_gb():.2f} GB")


if __name__ == "__main__":
    main()
