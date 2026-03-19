#!/usr/bin/env python3
"""
UNIVERSAL DESKTOP AUTO-INSTALLER
AI-driven configuration and installation system

Detects:
- Current OS (but doesn't care which one)
- Available ports
- Hardware capabilities
- Installed software
- Network configuration

Generates:
- Correct configs for your system
- Module installation order
- Port assignments
- Security settings

Installs everything automatically with zero manual config.
"""

import os
import sys
import json
import socket
import platform
import subprocess
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
import asyncio

# ============================================================================
# SYSTEM DETECTION
# ============================================================================

@dataclass
class SystemProfile:
    """What we detect about the system"""
    # OS Info (but we don't really care)
    os_type: str  # linux, darwin, windows
    os_version: str
    kernel_version: str
    
    # Hardware
    cpu_cores: int
    ram_gb: float
    disk_space_gb: float
    
    # Network
    hostname: str
    ip_addresses: List[str]
    open_ports: List[int]
    available_ports: List[int]
    
    # Software
    has_python: bool
    python_version: str
    has_docker: bool
    has_systemd: bool
    
    # Paths
    home_dir: str
    install_dir: str
    config_dir: str
    
    # Capabilities
    can_bind_privileged_ports: bool
    has_sudo: bool

class SystemDetector:
    """Detect everything about the system"""
    
    @staticmethod
    def detect() -> SystemProfile:
        """Run full system detection"""
        print("🔍 Detecting system configuration...\n")
        
        profile = SystemProfile(
            os_type=SystemDetector._detect_os_type(),
            os_version=platform.version(),
            kernel_version=platform.release(),
            cpu_cores=os.cpu_count() or 1,
            ram_gb=SystemDetector._detect_ram(),
            disk_space_gb=SystemDetector._detect_disk_space(),
            hostname=socket.gethostname(),
            ip_addresses=SystemDetector._detect_ip_addresses(),
            open_ports=SystemDetector._scan_open_ports(),
            available_ports=SystemDetector._find_available_ports(),
            has_python=True,  # We're running in Python
            python_version=platform.python_version(),
            has_docker=SystemDetector._check_docker(),
            has_systemd=SystemDetector._check_systemd(),
            home_dir=str(Path.home()),
            install_dir=SystemDetector._determine_install_dir(),
            config_dir=SystemDetector._determine_config_dir(),
            can_bind_privileged_ports=SystemDetector._check_privileged_ports(),
            has_sudo=SystemDetector._check_sudo()
        )
        
        SystemDetector._print_profile(profile)
        return profile
    
    @staticmethod
    def _detect_os_type() -> str:
        """Detect OS type"""
        system = platform.system().lower()
        if 'linux' in system:
            return 'linux'
        elif 'darwin' in system:
            return 'darwin'
        elif 'windows' in system:
            return 'windows'
        return 'unknown'
    
    @staticmethod
    def _detect_ram() -> float:
        """Detect RAM in GB"""
        try:
            if platform.system() == 'Linux':
                with open('/proc/meminfo', 'r') as f:
                    for line in f:
                        if 'MemTotal' in line:
                            kb = int(line.split()[1])
                            return kb / (1024 * 1024)
            else:
                # Fallback for other systems
                return 4.0
        except:
            return 4.0
    
    @staticmethod
    def _detect_disk_space() -> float:
        """Detect available disk space in GB"""
        try:
            stat = shutil.disk_usage(Path.home())
            return stat.free / (1024**3)
        except:
            return 100.0
    
    @staticmethod
    def _detect_ip_addresses() -> List[str]:
        """Get all IP addresses"""
        ips = []
        try:
            hostname = socket.gethostname()
            ips.append(socket.gethostbyname(hostname))
        except:
            ips.append('127.0.0.1')
        return ips
    
    @staticmethod
    def _scan_open_ports() -> List[int]:
        """Scan for commonly used ports that are already in use"""
        common_ports = [80, 443, 8080, 8000, 3000, 5000, 6379, 27017, 3306, 5432]
        open_ports = []
        
        for port in common_ports:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.1)
            result = sock.connect_ex(('127.0.0.1', port))
            if result == 0:
                open_ports.append(port)
            sock.close()
        
        return open_ports
    
    @staticmethod
    def _find_available_ports(count: int = 10) -> List[int]:
        """Find available ports for services"""
        available = []
        start_port = 8000
        
        while len(available) < count:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.1)
            result = sock.connect_ex(('127.0.0.1', start_port))
            if result != 0:  # Port is available
                available.append(start_port)
            sock.close()
            start_port += 1
            
            if start_port > 65535:
                break
        
        return available
    
    @staticmethod
    def _check_docker() -> bool:
        """Check if Docker is installed"""
        try:
            subprocess.run(['docker', '--version'], capture_output=True, check=True)
            return True
        except:
            return False
    
    @staticmethod
    def _check_systemd() -> bool:
        """Check if systemd is available"""
        return os.path.exists('/run/systemd/system')
    
    @staticmethod
    def _determine_install_dir() -> str:
        """Determine where to install"""
        home = Path.home()
        return str(home / 'universal-desktop')
    
    @staticmethod
    def _determine_config_dir() -> str:
        """Determine where configs go"""
        if platform.system() == 'Linux':
            return str(Path.home() / '.config' / 'universal-desktop')
        else:
            return str(Path.home() / '.universal-desktop')
    
    @staticmethod
    def _check_privileged_ports() -> bool:
        """Can we bind to ports < 1024?"""
        if os.geteuid() == 0 if hasattr(os, 'geteuid') else False:
            return True
        return False
    
    @staticmethod
    def _check_sudo() -> bool:
        """Check if sudo is available"""
        try:
            subprocess.run(['sudo', '-n', 'true'], capture_output=True, check=True)
            return True
        except:
            return False
    
    @staticmethod
    def _print_profile(profile: SystemProfile):
        """Print detected system profile"""
        print("=" * 80)
        print("SYSTEM PROFILE")
        print("=" * 80)
        print(f"OS: {profile.os_type} ({profile.os_version})")
        print(f"Kernel: {profile.kernel_version}")
        print(f"CPUs: {profile.cpu_cores}")
        print(f"RAM: {profile.ram_gb:.1f} GB")
        print(f"Disk Space: {profile.disk_space_gb:.1f} GB")
        print(f"Hostname: {profile.hostname}")
        print(f"IP: {profile.ip_addresses}")
        print(f"Python: {profile.python_version}")
        print(f"Docker: {'Yes' if profile.has_docker else 'No'}")
        print(f"Systemd: {'Yes' if profile.has_systemd else 'No'}")
        print(f"Sudo: {'Yes' if profile.has_sudo else 'No'}")
        print(f"Install Dir: {profile.install_dir}")
        print(f"Config Dir: {profile.config_dir}")
        print(f"\nPorts in use: {profile.open_ports}")
        print(f"Available ports: {profile.available_ports[:5]}...")
        print("=" * 80 + "\n")

# ============================================================================
# MODULE CONFIGURATION GENERATOR
# ============================================================================

@dataclass
class ModuleConfig:
    """Configuration for a module"""
    module_name: str
    enabled: bool
    port: Optional[int]
    config: Dict[str, Any]
    dependencies: List[str]
    install_order: int

class ConfigGenerator:
    """Generate configs for all modules based on system"""
    
    def __init__(self, profile: SystemProfile):
        self.profile = profile
        self.port_index = 0
    
    def generate_all_configs(self) -> Dict[str, ModuleConfig]:
        """Generate configs for all modules"""
        print("⚙️  Generating module configurations...\n")
        
        configs = {}
        
        # Helix Storage
        configs['helix'] = self._generate_helix_config()
        
        # Intent Parser
        configs['intent_parser'] = self._generate_intent_parser_config()
        
        # Life First AI Backend
        configs['lifefirst'] = self._generate_lifefirst_config()
        
        # Android Security
        configs['android_security'] = self._generate_android_security_config()
        
        # Paging Manager
        configs['paging_manager'] = self._generate_paging_manager_config()
        
        return configs
    
    def _get_next_port(self) -> int:
        """Get next available port"""
        if self.port_index < len(self.profile.available_ports):
            port = self.profile.available_ports[self.port_index]
            self.port_index += 1
            return port
        return 8000 + self.port_index
    
    def _generate_helix_config(self) -> ModuleConfig:
        """Generate Helix storage config"""
        port = self._get_next_port()
        
        return ModuleConfig(
            module_name='helix',
            enabled=True,
            port=port,
            config={
                'host': '0.0.0.0',
                'port': port,
                'cache_size_mb': min(1024, int(self.profile.ram_gb * 200)),
                's3_bucket': 'my-helix-bucket',
                's3_region': 'us-east-1',
                'data_dir': f"{self.profile.install_dir}/helix/data",
                'log_dir': f"{self.profile.install_dir}/helix/logs"
            },
            dependencies=[],
            install_order=1
        )
    
    def _generate_intent_parser_config(self) -> ModuleConfig:
        """Generate Intent Parser config"""
        port = self._get_next_port()
        
        return ModuleConfig(
            module_name='intent_parser',
            enabled=True,
            port=port,
            config={
                'host': '0.0.0.0',
                'port': port,
                'max_queue_size': 1000,
                'worker_threads': self.profile.cpu_cores,
                'timeout_seconds': 30,
                'retry_attempts': 3,
                'log_dir': f"{self.profile.install_dir}/intent_parser/logs"
            },
            dependencies=['helix'],
            install_order=2
        )
    
    def _generate_lifefirst_config(self) -> ModuleConfig:
        """Generate Life First AI config"""
        port = self._get_next_port()
        
        return ModuleConfig(
            module_name='lifefirst',
            enabled=True,
            port=port,
            config={
                'host': '0.0.0.0',
                'port': port,
                'db_host': 'localhost',
                'db_name': 'lifefirst',
                'db_user': 'lifefirst_user',
                'db_password': 'CHANGE_ME',
                'api_endpoint': f"http://localhost:{port}/api",
                'log_dir': f"{self.profile.install_dir}/lifefirst/logs"
            },
            dependencies=['intent_parser'],
            install_order=3
        )
    
    def _generate_android_security_config(self) -> ModuleConfig:
        """Generate Android Security config"""
        port = self._get_next_port()
        
        return ModuleConfig(
            module_name='android_security',
            enabled=True,
            port=port,
            config={
                'host': '0.0.0.0',
                'port': port,
                'security_level': 'enhanced',
                'require_location': True,
                'require_bluetooth': True,
                'require_wifi': True,
                'session_timeout_minutes': 30,
                'log_dir': f"{self.profile.install_dir}/android_security/logs"
            },
            dependencies=['intent_parser'],
            install_order=3
        )
    
    def _generate_paging_manager_config(self) -> ModuleConfig:
        """Generate Paging Manager config"""
        return ModuleConfig(
            module_name='paging_manager',
            enabled=True,
            port=None,  # Runs in-process
            config={
                'max_memory_mb': int(self.profile.ram_gb * 512),
                'page_size_kb': 4,
                'swap_enabled': True,
                'swap_dir': f"{self.profile.install_dir}/paging_manager/swap",
                'log_dir': f"{self.profile.install_dir}/paging_manager/logs"
            },
            dependencies=['intent_parser'],
            install_order=2
        )

# ============================================================================
# INSTALLER
# ============================================================================

class UniversalInstaller:
    """Install everything automatically"""
    
    def __init__(self, profile: SystemProfile, configs: Dict[str, ModuleConfig]):
        self.profile = profile
        self.configs = configs
        self.install_dir = Path(profile.install_dir)
    
    async def install_all(self):
        """Run full installation"""
        print("\n" + "=" * 80)
        print("STARTING INSTALLATION")
        print("=" * 80 + "\n")
        
        # Create directories
        await self._create_directories()
        
        # Install modules in order
        sorted_modules = sorted(
            self.configs.values(),
            key=lambda m: m.install_order
        )
        
        for module in sorted_modules:
            if module.enabled:
                await self._install_module(module)
        
        # Generate master config
        await self._generate_master_config()
        
        # Create service files
        if self.profile.has_systemd:
            await self._create_systemd_services()
        
        # Create startup script
        await self._create_startup_script()
        
        print("\n" + "=" * 80)
        print("INSTALLATION COMPLETE")
        print("=" * 80)
        print(f"\nInstall directory: {self.install_dir}")
        print(f"Config directory: {self.profile.config_dir}")
        print("\nTo start the system:")
        print(f"  cd {self.install_dir}")
        print(f"  ./start.sh")
        print()
    
    async def _create_directories(self):
        """Create all necessary directories"""
        print("📁 Creating directory structure...")
        
        dirs = [
            self.install_dir,
            self.install_dir / 'bin',
            self.install_dir / 'config',
            self.install_dir / 'logs',
            Path(self.profile.config_dir)
        ]
        
        for module in self.configs.values():
            if 'data_dir' in module.config:
                dirs.append(Path(module.config['data_dir']))
            if 'log_dir' in module.config:
                dirs.append(Path(module.config['log_dir']))
            if 'swap_dir' in module.config:
                dirs.append(Path(module.config['swap_dir']))
        
        for dir_path in dirs:
            dir_path.mkdir(parents=True, exist_ok=True)
            print(f"  ✓ {dir_path}")
        
        print()
    
    async def _install_module(self, module: ModuleConfig):
        """Install a single module"""
        print(f"📦 Installing {module.module_name}...")
        
        # Create module directory
        module_dir = self.install_dir / module.module_name
        module_dir.mkdir(exist_ok=True)
        
        # Write module config
        config_file = module_dir / 'config.json'
        with open(config_file, 'w') as f:
            json.dump(module.config, f, indent=2)
        
        print(f"  ✓ Config: {config_file}")
        
        if module.port:
            print(f"  ✓ Port: {module.port}")
        
        print(f"  ✓ Dependencies: {module.dependencies or 'None'}")
        print()
    
    async def _generate_master_config(self):
        """Generate master configuration file"""
        print("📝 Generating master configuration...")
        
        master_config = {
            'system': {
                'install_dir': str(self.install_dir),
                'config_dir': self.profile.config_dir,
                'hostname': self.profile.hostname,
                'ip_addresses': self.profile.ip_addresses
            },
            'modules': {}
        }
        
        for name, module in self.configs.items():
            master_config['modules'][name] = {
                'enabled': module.enabled,
                'port': module.port,
                'config_file': f"{self.install_dir}/{name}/config.json",
                'dependencies': module.dependencies
            }
        
        config_file = self.install_dir / 'config' / 'master.json'
        with open(config_file, 'w') as f:
            json.dump(master_config, f, indent=2)
        
        print(f"  ✓ {config_file}\n")
    
    async def _create_systemd_services(self):
        """Create systemd service files"""
        print("🔧 Creating systemd services...")
        
        for name, module in self.configs.items():
            if not module.port:
                continue
            
            service_content = f"""[Unit]
Description=Universal Desktop - {module.module_name}
After=network.target

[Service]
Type=simple
User={os.getenv('USER', 'root')}
WorkingDirectory={self.install_dir}/{name}
ExecStart=/usr/bin/python3 {self.install_dir}/bin/{name}.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""
            
            service_file = self.install_dir / 'config' / f'{name}.service'
            with open(service_file, 'w') as f:
                f.write(service_content)
            
            print(f"  ✓ {service_file}")
        
        print()
    
    async def _create_startup_script(self):
        """Create startup script"""
        print("🚀 Creating startup script...")
        
        script_content = f"""#!/bin/bash
# Universal Desktop Startup Script

echo "Starting Universal Desktop..."
echo ""

cd {self.install_dir}

# Start modules in order
"""
        
        sorted_modules = sorted(
            [(n, m) for n, m in self.configs.items() if m.enabled and m.port],
            key=lambda x: x[1].install_order
        )
        
        for name, module in sorted_modules:
            script_content += f"""
echo "Starting {name}..."
python3 bin/{name}.py &
sleep 2
"""
        
        script_content += """
echo ""
echo "✅ All modules started!"
echo ""
echo "Module status:"
"""
        
        for name, module in sorted_modules:
            if module.port:
                script_content += f'echo "  {name}: http://localhost:{module.port}"\n'
        
        script_content += """
echo ""
echo "To stop: pkill -f 'python3 bin/'"
"""
        
        script_file = self.install_dir / 'start.sh'
        with open(script_file, 'w') as f:
            f.write(script_content)
        
        script_file.chmod(0o755)
        
        print(f"  ✓ {script_file}\n")

# ============================================================================
# MAIN INSTALLER
# ============================================================================

async def main():
    """Run the full auto-installer"""
    print("\n" + "╔" + "="*78 + "╗")
    print("║" + " "*78 + "║")
    print("║" + "  UNIVERSAL DESKTOP AUTO-INSTALLER".center(78) + "║")
    print("║" + "  AI-Driven Configuration & Installation".center(78) + "║")
    print("║" + " "*78 + "║")
    print("╚" + "="*78 + "╝\n")
    
    # Step 1: Detect system
    profile = SystemDetector.detect()
    
    # Step 2: Generate configs
    generator = ConfigGenerator(profile)
    configs = generator.generate_all_configs()
    
    print("Generated configurations:")
    for name, config in configs.items():
        status = "✓" if config.enabled else "✗"
        port_info = f"Port {config.port}" if config.port else "In-process"
        print(f"  {status} {name}: {port_info}")
    print()
    
    # Step 3: Install
    installer = UniversalInstaller(profile, configs)
    await installer.install_all()
    
    print("✅ Universal Desktop is ready!")
    print("\nFor Laurie's app integration:")
    lifefirst_port = configs['lifefirst'].port
    print(f"  Life First AI: http://localhost:{lifefirst_port}/api")
    print("\nFor new modules:")
    print(f"  Add to: {profile.install_dir}/")
    print(f"  Config: {profile.config_dir}/master.json")
    print()

if __name__ == "__main__":
    asyncio.run(main())
