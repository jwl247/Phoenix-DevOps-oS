# AI Paging Manager v2.0 - Setup & Usage Guide

## 🎯 What's New in v2.0

### ✅ IMPROVEMENTS
- **🔴 ON/OFF Button**: Enable/disable without stopping the service
- **🚨 Emergency Stop**: Instantly halt all operations
- **🌡️ Temperature Monitoring**: CPU & disk thermal protection
- **🔥 Thermal Throttling**: Auto-pause when temps hit 75°C
- **🛑 Emergency Shutdown**: Auto-stop at 80°C+
- **📊 Web Dashboard**: Real-time monitoring at http://localhost:8888
- **🤖 AI-Optimized**: Larger pages (64MB), LRU eviction, preloading
- **🪟 Windows Support**: Manages pagefile.sys dynamically

---

## 📦 Linux Version Setup

### Requirements
- Ubuntu/Debian/RHEL Linux
- Python 3.8+
- Root access (sudo)
- 100GB+ free disk space

### Installation

```bash
# 1. Copy script to your server
scp ai_paging_manager_linux_v2.py user@your-server:/opt/

# 2. SSH into server
ssh user@your-server

# 3. Make executable
sudo chmod +x /opt/ai_paging_manager_linux_v2.py

# 4. Start the manager
sudo python3 /opt/ai_paging_manager_linux_v2.py start
```

### Control Commands

```bash
# Turn ON (resume operations)
sudo python3 /opt/ai_paging_manager_linux_v2.py enable

# Turn OFF (pause operations, keep monitoring)
sudo python3 /opt/ai_paging_manager_linux_v2.py disable

# Emergency stop (immediate halt)
sudo python3 /opt/ai_paging_manager_linux_v2.py emergency

# Check status
sudo python3 /opt/ai_paging_manager_linux_v2.py status
```

### Web Dashboard
Open browser: `http://your-server-ip:8888`

---

## 🪟 Windows Version Setup

### Requirements
- Windows 10/11 or Windows Server
- Python 3.8+
- Administrator privileges
- 100GB+ free disk space

### Installation

```powershell
# 1. Right-click PowerShell -> "Run as Administrator"

# 2. Navigate to the script
cd C:\Users\jwlef\Downloads

# 3. Start the manager
python ai_paging_manager_windows_v2.py start
```

### Control Commands

```powershell
# Turn ON
python ai_paging_manager_windows_v2.py enable

# Turn OFF
python ai_paging_manager_windows_v2.py disable

# Emergency stop
python ai_paging_manager_windows_v2.py emergency

# Manually expand pagefile by 8GB
python ai_paging_manager_windows_v2.py expand 8

# Manually shrink pagefile by 4GB
python ai_paging_manager_windows_v2.py shrink 4

# Check status
python ai_paging_manager_windows_v2.py status
```

### Web Dashboard
Open browser: `http://localhost:8888`

⚠️ **IMPORTANT**: Pagefile changes require a system restart to take full effect!

---

## 🚨 Thermal Protection

### Temperature Thresholds

| Condition | CPU Temp | Action |
|-----------|----------|--------|
| Normal | < 75°C | Full operation |
| Throttle | 75-80°C | Pause operations, wait for cooling |
| Emergency | > 80°C | Immediate shutdown, disable manager |

### Disk Temperature
- **Warning**: > 50°C
- **Critical**: > 60°C (emergency stop)

### What Happens During Thermal Events

1. **Throttle (75°C)**: 
   - Pauses creating new swap
   - Waits 30-60 seconds
   - Resumes when cooled

2. **Emergency (80°C)**:
   - Immediate stop
   - Sets emergency flag
   - Requires manual re-enable
   - Logs critical event

---

## 🤖 AI Mode Optimizations

When `ai_mode = True` (default):

- **Larger Pages**: 64MB instead of 4MB (better for model weights)
- **LRU Eviction**: Keeps frequently accessed pages (model layers)
- **Higher Priority**: AI model pages get priority 5+
- **Preload Swap**: 8GB swap created immediately
- **Fewer Doppelgangers**: 6 max (but larger, 4GB each)
- **Higher Clone Threshold**: 75% instead of 70%

Perfect for:
- LLaMA, Mistral, GPT-style models
- Stable Diffusion
- ComfyUI workflows
- Ollama
- vLLM

---

## 📊 Dashboard Features

### Real-Time Monitoring
- System load (RAM, swap, CPU)
- Temperature status
- Pagefile/swap size
- Active doppelgangers (Linux)
- Statistics & events

### One-Click Controls
- 🟢 **Enable**: Turn on manager
- ⏸️ **Disable**: Pause operations
- 📈 **Expand**: Add 4GB (Windows only)
- 📉 **Shrink**: Remove 4GB (Windows only)
- 🚨 **Emergency Stop**: Immediate halt

### Auto-Refresh
Dashboard updates every 5 seconds automatically

---

## 🔧 Configuration

Edit these values in the script:

```python
@dataclass
class SystemConfig:
    # System specs
    total_ram_gb: float = 16.0
    max_swap_gb: float = 64.0          # Linux: max swap
    max_pagefile_gb: float = 64.0      # Windows: max pagefile
    
    # Temperature limits
    max_cpu_temp: float = 80.0         # Emergency stop temp
    thermal_throttle_temp: float = 75.0  # Throttle temp
    
    # AI mode
    ai_mode: bool = True
    page_size_mb: int = 64             # 64MB for AI, 4MB for normal
    
    # Web dashboard
    web_dashboard_port: int = 8888
```

---

## 📈 Performance Tips

### For AI Self-Hosting

1. **Preload Swap**: Set `initial_pagefile_gb = 16.0` for large models
2. **Increase Max**: Set `max_pagefile_gb = 128.0` if you have disk space
3. **Larger Pages**: Keep `page_size_mb = 64` or higher
4. **Monitor Temps**: Install OpenHardwareMonitor (Windows) for thermal monitoring

### For General Use

1. **Disable AI Mode**: Set `ai_mode = False`
2. **Smaller Pages**: Set `page_size_mb = 4`
3. **More Doppelgangers**: Set `max_doppelgangers = 12`

---

## 🛠️ Troubleshooting

### Linux Issues

**"Permission denied"**
```bash
sudo python3 ai_paging_manager_linux_v2.py start
```

**"mkswap not found"**
```bash
sudo apt install util-linux  # Ubuntu/Debian
sudo yum install util-linux  # RHEL/CentOS
```

**Temperature monitoring unavailable**
```bash
# Install lm-sensors
sudo apt install lm-sensors
sudo sensors-detect
```

### Windows Issues

**"Not running as Administrator"**
- Right-click PowerShell → "Run as Administrator"
- Or right-click Python → "Run as Administrator"

**Temperature monitoring unavailable**
- Install OpenHardwareMonitor: https://openhardwaremonitor.org/
- Or use HWiNFO: https://www.hwinfo.com/

**Pagefile changes not taking effect**
- **You must restart Windows** for pagefile changes!
- Check: Control Panel → System → Advanced → Performance → Virtual Memory

---

## 📝 Logs

### Linux
- Main log: `/var/log/ai-paging-{manager_id}.log`
- Control state: `/tmp/ai-paging-control.json`

### Windows
- Main log: `C:\ProgramData\ai-paging-manager.log`
- Control state: `C:\ProgramData\ai-paging-control.json`

---

## 🚀 Running as a Service

### Linux (systemd)

Create `/etc/systemd/system/ai-paging.service`:

```ini
[Unit]
Description=AI Paging Manager
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/python3 /opt/ai_paging_manager_linux_v2.py start
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable ai-paging
sudo systemctl start ai-paging
sudo systemctl status ai-paging
```

### Windows (Task Scheduler)

1. Open Task Scheduler
2. Create Basic Task
3. Trigger: "When the computer starts"
4. Action: "Start a program"
5. Program: `python.exe`
6. Arguments: `C:\Users\jwlef\Downloads\ai_paging_manager_windows_v2.py start`
7. Run with highest privileges ✅

---

## ⚠️ Important Safety Notes

1. **Always monitor temperatures** when first running
2. **Thermal protection is critical** - don't disable it
3. **Test with low loads first** before deploying AI models
4. **Keep 100GB+ disk space free** at all times
5. **Windows requires restart** after pagefile changes
6. **Use emergency stop** if system becomes unstable

---

## 📞 Emergency Commands

If system is overheating or unstable:

### Linux
```bash
# Emergency stop
sudo python3 /opt/ai_paging_manager_linux_v2.py emergency

# Kill process
sudo pkill -f ai_paging_manager

# Remove all swap files
sudo swapoff -a
sudo rm -f /var/ai-swap/*
```

### Windows
```powershell
# Emergency stop
python ai_paging_manager_windows_v2.py emergency

# Kill process
taskkill /F /IM python.exe

# Reset pagefile to Windows defaults
# (Control Panel → System → Advanced → Performance → Virtual Memory → System managed size)
```

---

## 🎉 Enjoy Your Upgraded System!

Your 16GB RAM system can now handle AI workloads that normally need 64GB+ of physical RAM!

**Questions?** Check the logs or visit the dashboard at http://localhost:8888
