import platform
import shutil
import os
from pathlib import Path

def get_platform() -> str:
    s = platform.system()
    if s == 'Windows': return 'windows'
    if s == 'Darwin':  return 'darwin'
    return 'linux'

def get_distro() -> str:
    try:
        text = Path('/etc/os-release').read_text()
        for line in text.splitlines():
            if line.startswith('ID='):
                return line.split('=')[1].strip().strip('"').lower()
    except:
        pass
    return 'unknown'

def in_wsl() -> bool:
    try:
        return 'microsoft' in Path('/proc/version').read_text().lower()
    except:
        return False

def get_backend() -> str | None:
    p = get_platform()
    if p == 'windows':
        for b in ('winget', 'choco', 'scoop'):
            if shutil.which(b): return b
    elif p == 'linux':
        for b in ('apt', 'dnf', 'pacman', 'zypper'):
            if shutil.which(b): return b
    elif p == 'darwin':
        if shutil.which('brew'): return 'brew'
    return None

def get_all_backends() -> list:
    candidates = ('apt','dnf','pacman','zypper','brew','winget','choco','scoop','pip')
    return [b for b in candidates if shutil.which(b)]

def sysinfo() -> dict:
    return {
        'platform' : get_platform(),
        'distro'   : get_distro(),
        'wsl'      : in_wsl(),
        'backend'  : get_backend(),
        'available': get_all_backends(),
        'python'   : platform.python_version(),
        'arch'     : platform.machine(),
    }
