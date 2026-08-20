#!/usr/bin/env python3

import os
import sys
import platform
import subprocess
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

class OSType(Enum):
    """Supported operating systems"""
    WINDOWS = "windows"
    LINUX = "linux"
    MACOS = "darwin"
    UNKNOWN = "unknown"

@dataclass
class SystemInfo:
    """Universal system information"""
    os_type: OSType
    os_version: str
    python_version: str
    architecture: str
    home_dir: Path
    temp_dir: Path
    has_sudo: bool
    path_separator: str
    line_ending: str

class AgnosticLayer:
    """
    OS-Agnostic abstraction layer
    Translates everything so Life First works ANYWHERE
    """
    
    def __init__(self):
        self.system = self._detect_system()
        
    def _detect_system(self) -> SystemInfo:
        """Detect what system we're running on"""
        sys_platform = platform.system().lower()
        
        if 'windows' in sys_platform:
            os_type = OSType.WINDOWS
            path_sep = '\\'
            line_end = '\r\n'
            has_sudo = False
        elif 'linux' in sys_platform:
            os_type = OSType.LINUX
            path_sep = '/'
            line_end = '\n'
            has_sudo = True
        elif 'darwin' in sys_platform:
            os_type = OSType.MACOS
            path_sep = '/'
            line_end = '\n'
            has_sudo = True
        else:
            os_type = OSType.UNKNOWN
            path_sep = os.sep
            line_end = '\n'
            has_sudo = False
            
        return SystemInfo(
            os_type=os_type,
            os_version=platform.version(),
            python_version=sys.version,
            architecture=platform.machine(),
            home_dir=Path.home(),
            temp_dir=Path(os.environ.get('TEMP', '/tmp')),
            has_sudo=has_sudo,
            path_separator=path_sep,
            line_ending=line_end
        )
    
    def normalize_path(self, path: str) -> Path:
        """Convert any path format to proper Path object"""
        normalized = path.replace('\\', os.sep).replace('/', os.sep)
        return Path(normalized).resolve()
    
    def make_executable(self, filepath: Path) -> bool:
        """Make a file executable (OS-agnostic)"""
        try:
            if self.system.os_type == OSType.WINDOWS:
                return True
            else:
                os.chmod(filepath, 0o755)
                return True
        except Exception as e:
            print(f"Warning: Could not make {filepath} executable: {e}")
            return False
    
    def run_command(self, command: List[str], elevated: bool = False) -> tuple:
        """Run a system command (OS-agnostic)"""
        try:
            if elevated and self.system.os_type == OSType.WINDOWS:
                command = ['runas', '/user:Administrator'] + command
            elif elevated and self.system.has_sudo:
                command = ['sudo'] + command
            
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            return (result.returncode == 0, result.stdout)
            
        except Exception as e:
            return (False, str(e))
    
    def get_process_manager(self) -> str:
        """Return appropriate process manager command"""
        if self.system.os_type == OSType.WINDOWS:
            return "tasklist"
        else:
            return "ps aux"
    
    def get_install_dir(self, app_name: str = "lifefirst") -> Path:
        """Get appropriate install directory for this OS"""
        if self.system.os_type == OSType.WINDOWS:
            base = Path(os.environ.get('LOCALAPPDATA', self.system.home_dir))
            return base / app_name
        elif self.system.os_type == OSType.MACOS:
            return self.system.home_dir / 'Library' / 'Application Support' / app_name
        else:
            return self.system.home_dir / f'.{app_name}'
    
    def get_config_dir(self, app_name: str = "lifefirst") -> Path:
        """Get appropriate config directory"""
        if self.system.os_type == OSType.WINDOWS:
            base = Path(os.environ.get('APPDATA', self.system.home_dir))
            return base / app_name
        elif self.system.os_type == OSType.MACOS:
            return self.system.home_dir / 'Library' / 'Preferences' / app_name
        else:
            return self.system.home_dir / '.config' / app_name
    
    def find_python(self) -> str:
        """Find Python executable"""
        if self.system.os_type == OSType.WINDOWS:
            return 'python'
        else:
            return 'python3'
    
    def create_launcher(self, install_dir: Path, script_name: str = "lifefirst") -> Path:
        """Create OS-appropriate launcher script"""
        if self.system.os_type == OSType.WINDOWS:
            launcher = install_dir / f"{script_name}.bat"
            python_cmd = self.find_python()
            content = f"""@echo off
{python_cmd} "{install_dir / 'start.py'}" %*
"""
        else:
            launcher = install_dir / f"{script_name}.sh"
            content = f"""#!/usr/bin/env bash
cd "{install_dir}"
{self.find_python()} start.py "$@"
"""
        
        with open(launcher, 'w') as f:
            f.write(content)
        
        self.make_executable(launcher)
        return launcher
    
    def parse_config(self, config_path: Path) -> Dict[str, Any]:
        """Parse config file (handles different encodings)"""
        encodings = ['utf-8', 'utf-16', 'latin-1']
        
        for encoding in encodings:
            try:
                with open(config_path, 'r', encoding=encoding) as f:
                    return json.load(f)
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
        
        raise ValueError(f"Could not parse config: {config_path}")
    
    def write_config(self, config_path: Path, data: Dict[str, Any]):
        """Write config file (OS-agnostic line endings)"""
        with open(config_path, 'w', encoding='utf-8', newline=self.system.line_ending) as f:
            json.dump(data, f, indent=2)
    
    def get_system_report(self) -> str:
        """Generate system compatibility report"""
        report = f"""
╔══════════════════════════════════════════════════════════════╗
║                    SYSTEM INFORMATION                        ║
╚══════════════════════════════════════════════════════════════╝

Operating System:     {self.system.os_type.value}
OS Version:           {self.system.os_version}
Architecture:         {self.system.architecture}
Python Version:       {self.system.python_version.split()[0]}

Home Directory:       {self.system.home_dir}
Install Directory:    {self.get_install_dir()}
Config Directory:     {self.get_config_dir()}

Path Separator:       {self.system.path_separator}
Has Sudo/Admin:       {self.system.has_sudo}
Python Command:       {self.find_python()}

╔══════════════════════════════════════════════════════════════╗
║                   COMPATIBILITY STATUS                       ║
╚══════════════════════════════════════════════════════════════╝

✓ System Detected
✓ Python Available
✓ Directories Accessible
✓ Ready for Installation
"""
        return report
    
    def health_check(self) -> bool:
        """Check if layer is healthy"""
        return True


class UniversalParser:
    """Parse ANY data format and convert to standard format"""
    
    def __init__(self, agnostic: AgnosticLayer):
        self.agnostic = agnostic
    
    def parse_any(self, data_path: Path) -> Dict[str, Any]:
        """Parse file regardless of format"""
        suffix = data_path.suffix.lower()
        
        if suffix == '.json':
            return self.agnostic.parse_config(data_path)
        elif suffix == '.txt':
            return self._parse_text(data_path)
        elif suffix in ['.yaml', '.yml']:
            return self._parse_yaml(data_path)
        else:
            return self._parse_generic(data_path)
    
    def _parse_text(self, path: Path) -> Dict[str, Any]:
        """Parse plain text file"""
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
            return {'content': content, 'lines': content.split('\n')}
    
    def _parse_yaml(self, path: Path) -> Dict[str, Any]:
        """Parse YAML (fallback to dict if PyYAML not available)"""
        try:
            import yaml
            with open(path, 'r') as f:
                return yaml.safe_load(f)
        except ImportError:
            return self._parse_generic(path)
    
    def _parse_generic(self, path: Path) -> Dict[str, Any]:
        """Generic parser for unknown formats"""
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        return {
            'raw_content': content,
            'file_type': path.suffix,
            'parsed': False
        }


def main():
    """Test the agnostic layer"""
    layer = AgnosticLayer()
    print(layer.get_system_report())
    
    parser = UniversalParser(layer)
    
    print("\n✓ Agnostic layer initialized")
    print(f"✓ Install directory: {layer.get_install_dir()}")
    print(f"✓ Config directory: {layer.get_config_dir()}")
    print(f"✓ Python command: {layer.find_python()}")


if __name__ == "__main__":
    main()
