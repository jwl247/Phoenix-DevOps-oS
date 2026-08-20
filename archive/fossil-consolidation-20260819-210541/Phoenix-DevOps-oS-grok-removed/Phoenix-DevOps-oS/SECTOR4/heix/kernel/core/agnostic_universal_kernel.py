#!/usr/bin/env python3
"""
Agnostic Universal Kernel
The main kernel that integrates all components
"""

import os
import sys
import json
import logging
import shutil
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

# Add kernel paths
KERNEL_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(KERNEL_ROOT / 'core'))
sys.path.insert(0, str(KERNEL_ROOT / 'modules'))

# Import kernel components
try:
    from agnostic_layer import AgnosticLayer
    from config_scanner import ConfigScanner
    from helix_translator import HelixTranslator
    from helix_vram import HelixMemoryManager, VRRAM
    from helix_complete_stack import HelixCompleteStack, HelixCache, HelixFS
except ImportError as e:
    logging.warning(f"Module import warning: {e}")


class DataTemperature(Enum):
    """Data temperature classifications"""
    HOT = "hot"
    WARM = "warm"
    COOL = "cool"
    COLD = "cold"
    FROZEN = "frozen"


@dataclass
class KernelHealth:
    """Kernel health status"""
    timestamp: datetime = field(default_factory=datetime.now)
    component: str = ""
    status: str = "healthy"
    issues: List[str] = field(default_factory=list)
    auto_healed: bool = False
    healing_actions: List[str] = field(default_factory=list)


@dataclass
class MicroKernelConfig:
    """Configuration for micro kernels"""
    id: str
    purpose: str
    enabled: bool = True
    priority: int = 5
    resources_allocated: Dict[str, Any] = field(default_factory=dict)
    health_check_interval: int = 60


@dataclass
class DataTemperatureConfig:
    """Configuration for data temperature management"""
    hot_threshold_days: int = 7
    warm_threshold_days: int = 30
    cool_threshold_days: int = 90
    cold_threshold_days: int = 180
    auto_migrate: bool = True
    scan_interval: int = 3600


class AgnosticUniversalKernel:
    """
    The Agnostic Universal Kernel - runs alongside Linux kernel
    Provides:
    - Self-healing capabilities
    - Config scanning and cloning
    - Data temperature management
    - Micro kernel spawning
    - API integration
    - Web dashboard
    """
    
    def __init__(self, config_path: str = None):
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger("AgnosticKernel")
        
        # Load configuration
        self.config = self._load_config(config_path)
        
        # Setup directories
        self.kernel_dir = Path(self.config.get('kernel_dir', '/tmp/agnostic_kernel'))
        self.data_dir = self.kernel_dir / 'data'
        self.config_dir = self.kernel_dir / 'configs'
        self.backup_dir = self.kernel_dir / 'backups'
        self.log_dir = self.kernel_dir / 'logs'
        
        for d in [self.kernel_dir, self.data_dir, self.config_dir, self.backup_dir, self.log_dir]:
            d.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        self._init_components()
        
        # State
        self.running = False
        self.micro_kernels: Dict[str, MicroKernelConfig] = {}
        self.health_status: Dict[str, KernelHealth] = {}
        self.start_time = None
        
        self.logger.info("Agnostic Universal Kernel initialized")
    
    def _load_config(self, config_path: str = None) -> Dict:
        """Load kernel configuration"""
        default_config = {
            'kernel_version': '7.3',
            'kernel_dir': '/tmp/agnostic_kernel',
            'dashboard': {'enabled': True, 'port': 8080},
            'api_integration': {'enabled': True, 'port': 8000},
            'data_temperature': {
                'enabled': True,
                'hot_threshold_days': 7,
                'warm_threshold_days': 30,
                'cool_threshold_days': 90,
                'cold_threshold_days': 180,
                'auto_migrate': True
            },
            'self_healing': {'enabled': True, 'check_interval': 60},
            'micro_kernels': {
                'versioning': {'enabled': True, 'priority': 1},
                'data_clone': {'enabled': True, 'priority': 2},
                'security': {'enabled': True, 'priority': 3},
                'backup': {'enabled': True, 'priority': 4},
                'monitoring': {'enabled': True, 'priority': 5},
                'api': {'enabled': True, 'priority': 6}
            }
        }
        
        if config_path and Path(config_path).exists():
            try:
                with open(config_path, 'r') as f:
                    loaded_config = json.load(f)
                    default_config.update(loaded_config)
            except Exception as e:
                self.logger.warning(f"Could not load config from {config_path}: {e}")
        
        return default_config
    
    def _init_components(self):
        """Initialize kernel components"""
        try:
            self.agnostic = AgnosticLayer()
            self.logger.info("✓ Agnostic Layer initialized")
        except Exception as e:
            self.agnostic = None
            self.logger.warning(f"Could not init AgnosticLayer: {e}")
        
        try:
            self.config_scanner = ConfigScanner(str(self.kernel_dir))
            self.logger.info("✓ Config Scanner initialized")
        except Exception as e:
            self.config_scanner = None
            self.logger.warning(f"Could not init ConfigScanner: {e}")
        
        try:
            self.stack = HelixCompleteStack(
                l1_cache_mb=64,
                l2_cache_mb=256,
                l3_cache_mb=512,
                virtual_ram_mb=2048
            )
            self.storage = self.stack.memory
            self.vrram = self.stack.memory
            self.logger.info("✓ Helix Complete Stack initialized")
        except Exception as e:
            self.stack = None
            self.storage = None
            self.vrram = None
            self.logger.warning(f"Could not init HelixCompleteStack: {e}")
        
        try:
            self.translator = HelixTranslator(self.stack)
            self.logger.info("✓ Helix Translator initialized")
        except Exception as e:
            self.translator = None
            self.logger.warning(f"Could not init HelixTranslator: {e}")
        
        # Placeholders for optional components
        self.helix_sync = None
        self.sys_manager = None
    
    # ==================== SELF-HEALING ====================
    
    def _attempt_heal(self, component: str, error: str) -> bool:
        """Attempt to heal a component"""
        self.logger.warning(f"Attempting to heal {component}: {error}")
        
        healing_actions = []
        healed = False
        
        try:
            if component == 'storage' and self.stack:
                # Re-initialize storage
                self.storage = self.stack.memory
                healed = True
                healing_actions.append("Re-initialized storage")
            
            elif component == 'config_scanner':
                self.config_scanner = ConfigScanner(str(self.kernel_dir))
                healed = True
                healing_actions.append("Re-initialized config scanner")
            
            elif component == 'translator':
                self.translator = HelixTranslator(self.stack)
                healed = True
                healing_actions.append("Re-initialized translator")
            
            else:
                healing_actions.append(f"No healing procedure for {component}")
            
        except Exception as e:
            healing_actions.append(f"Healing failed: {e}")
            self.logger.error(f"Failed to heal {component}: {e}")
        
        # Record health status
        self.health_status[component] = KernelHealth(
            component=component,
            status="healthy" if healed else "unhealthy",
            issues=[error] if not healed else [],
            auto_healed=healed,
            healing_actions=healing_actions
        )
        
        return healed
    
    # ==================== CONFIG SCANNING ====================
    
    def scan_and_clone_configs(self, scan_path: str = "/") -> Dict[str, Any]:
        """Scan system for config files and clone them"""
        try:
            self.logger.info(f"Starting config scan from: {scan_path}")
            
            if self.config_scanner:
                scan_results = self.config_scanner.scan(scan_path)
            else:
                scan_results = {}
            
            cloned_configs = {}
            
            for config_file, metadata in scan_results.items():
                app_name = metadata.get('app_name', Path(config_file).stem)
                clone_dir = self.config_dir / app_name
                clone_dir.mkdir(parents=True, exist_ok=True)
                
                if os.path.exists(config_file):
                    clone_path = clone_dir / Path(config_file).name
                    shutil.copy2(config_file, clone_path)
                    
                    metadata_path = clone_dir / f"{Path(config_file).stem}_metadata.json"
                    with open(metadata_path, 'w') as f:
                        json.dump(metadata, f, indent=4)
                    
                    cloned_configs[config_file] = str(clone_path)
                    self.logger.info(f"Cloned config: {config_file} -> {clone_path}")
            
            return {
                "scan_timestamp": datetime.now().isoformat(),
                "configs_found": len(scan_results),
                "configs_cloned": len(cloned_configs),
                "cloned_configs": cloned_configs
            }
            
        except Exception as e:
            self.logger.error(f"Error scanning/cloning configs: {e}")
            return {}
    
    # ==================== KERNEL CLONING ====================
    
    def clone_kernel(self, target_path: str, partial: bool = False, components: List[str] = None) -> bool:
        """Clone the kernel to a new location"""
        try:
            target = Path(target_path)
            target.mkdir(parents=True, exist_ok=True)
            
            self.logger.info(f"Cloning kernel to: {target}")
            
            if partial and components:
                for comp in components:
                    src = self.kernel_dir / comp
                    if src.exists():
                        dst = target / comp
                        if src.is_dir():
                            shutil.copytree(src, dst, dirs_exist_ok=True)
                        else:
                            shutil.copy2(src, dst)
            else:
                shutil.copytree(self.kernel_dir, target, dirs_exist_ok=True)
            
            # Save clone metadata
            metadata = {
                "clone_timestamp": datetime.now().isoformat(),
                "source_kernel": str(self.kernel_dir),
                "partial": partial,
                "components": components,
                "kernel_version": self.config.get('kernel_version')
            }
            
            with open(target / "CLONE_METADATA.json", 'w') as f:
                json.dump(metadata, f, indent=4)
            
            self.logger.info(f"Kernel cloned successfully to: {target}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error cloning kernel: {e}")
            return False
    
    # ==================== DATA TEMPERATURE ====================
    
    def classify_data_temperature(self, file_path: str) -> DataTemperature:
        """Classify data based on access patterns and age"""
        try:
            stat = os.stat(file_path)
            last_access = datetime.fromtimestamp(stat.st_atime)
            days_since_access = (datetime.now() - last_access).days
            
            config = self.config.get("data_temperature", {})
            
            if days_since_access < config.get("hot_threshold_days", 7):
                return DataTemperature.HOT
            elif days_since_access < config.get("warm_threshold_days", 30):
                return DataTemperature.WARM
            elif days_since_access < config.get("cool_threshold_days", 90):
                return DataTemperature.COOL
            elif days_since_access < config.get("cold_threshold_days", 180):
                return DataTemperature.COLD
            else:
                return DataTemperature.FROZEN
                
        except Exception as e:
            self.logger.error(f"Error classifying data temperature: {e}")
            return DataTemperature.WARM
    
    def migrate_data_by_temperature(self):
        """Automatically migrate data based on temperature"""
        if not self.config.get("data_temperature", {}).get("auto_migrate", False):
            return
        
        try:
            self.logger.info("Starting data temperature migration")
            
            for root, dirs, files in os.walk(self.data_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    temp = self.classify_data_temperature(file_path)
                    
                    target_dir = self.data_dir / temp.value
                    target_dir.mkdir(exist_ok=True)
                    
                    rel_path = os.path.relpath(file_path, self.data_dir)
                    target_path = target_dir / rel_path
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    if not target_path.exists():
                        shutil.move(file_path, target_path)
                        self.logger.debug(f"Migrated {file} to {temp.value} storage")
            
            self.logger.info("Data temperature migration completed")
            
        except Exception as e:
            self.logger.error(f"Error during data migration: {e}")
    
    # ==================== MICRO KERNELS ====================
    
    def spawn_micro_kernel(self, purpose: str, priority: int = 5) -> bool:
        """Spawn a new micro kernel"""
        try:
            micro_kernel = MicroKernelConfig(
                id=f"mk_{purpose}_{datetime.now().timestamp()}",
                purpose=purpose,
                priority=priority
            )
            
            self.micro_kernels[micro_kernel.id] = micro_kernel
            self.logger.info(f"Spawned micro kernel: {micro_kernel.id} for {purpose}")
            
            return True
        except Exception as e:
            self.logger.error(f"Error spawning micro kernel: {e}")
            return False
    
    # ==================== KERNEL STATUS ====================
    
    def get_kernel_status(self) -> Dict[str, Any]:
        """Get comprehensive kernel status"""
        uptime = 0
        if self.start_time:
            uptime = time.time() - self.start_time
        
        return {
            "version": self.config.get("kernel_version"),
            "running": self.running,
            "platform": sys.platform,
            "uptime_seconds": uptime,
            "micro_kernels": len(self.micro_kernels),
            "health_issues": len([h for h in self.health_status.values() if h.status != "healthy"]),
            "subsystems": {
                "agnostic": self.agnostic is not None,
                "stack": self.stack is not None,
                "storage": self.storage is not None,
                "vrram": self.vrram is not None,
                "translator": self.translator is not None,
                "config_scanner": self.config_scanner is not None,
                "helix_sync": self.helix_sync is not None,
                "sys_manager": self.sys_manager is not None,
            },
            "directories": {
                "kernel_dir": str(self.kernel_dir),
                "data_dir": str(self.data_dir),
                "config_dir": str(self.config_dir),
                "backup_dir": str(self.backup_dir)
            }
        }
    
    def get_component_stats(self) -> Dict[str, Any]:
        """Get stats from all components"""
        stats = {}
        
        if self.stack:
            stats['helix_stack'] = self.stack.get_stats()
        
        if self.translator:
            stats['translator'] = self.translator.get_stats()
        
        if self.agnostic:
            stats['agnostic'] = {
                'os_type': self.agnostic.system.os_type.value,
                'architecture': self.agnostic.system.architecture
            }
        
        stats['micro_kernels'] = {
            mk_id: {
                'purpose': mk.purpose,
                'enabled': mk.enabled,
                'priority': mk.priority
            }
            for mk_id, mk in self.micro_kernels.items()
        }
        
        stats['health'] = {
            comp: {
                'status': h.status,
                'issues': h.issues,
                'auto_healed': h.auto_healed
            }
            for comp, h in self.health_status.items()
        }
        
        return stats
    
    # ==================== MAIN CONTROL ====================
    
    def _check_all_components_health(self):
        """Check health of all components"""
        components = {
            "agnostic": self.agnostic,
            "stack": self.stack,
            "storage": self.storage,
            "vrram": self.vrram,
            "translator": self.translator,
            "config_scanner": self.config_scanner
        }
        
        for name, component in components.items():
            if component is not None:
                try:
                    if hasattr(component, 'health_check'):
                        is_healthy = component.health_check()
                    else:
                        is_healthy = True
                    
                    if is_healthy:
                        self.health_status[name] = KernelHealth(
                            component=name,
                            status="healthy"
                        )
                    else:
                        self._attempt_heal(name, "Health check failed")
                        
                except Exception as e:
                    self._attempt_heal(name, str(e))
    
    def _start_health_monitoring(self):
        """Start continuous health monitoring"""
        def monitor():
            while self.running:
                self._check_all_components_health()
                time.sleep(60)
        
        monitor_thread = threading.Thread(target=monitor, daemon=True)
        monitor_thread.start()
    
    def _start_temperature_management(self):
        """Start data temperature management"""
        def manage():
            while self.running:
                self.migrate_data_by_temperature()
                time.sleep(3600)
        
        temp_thread = threading.Thread(target=manage, daemon=True)
        temp_thread.start()
    
    def start(self):
        """Start the kernel"""
        try:
            self.running = True
            self.start_time = time.time()
            self.logger.info("Starting Agnostic Universal Kernel")
            
            # Initialize default micro kernels
            for mk_name, mk_config in self.config.get('micro_kernels', {}).items():
                if mk_config.get('enabled', True):
                    self.spawn_micro_kernel(mk_name, mk_config.get('priority', 5))
            
            # Start health monitoring
            if self.config.get('self_healing', {}).get('enabled', True):
                self._start_health_monitoring()
            
            # Start data temperature management
            if self.config.get('data_temperature', {}).get('enabled', True):
                self._start_temperature_management()
            
            self.logger.info("Kernel started successfully")
            
            # Return status
            return self.get_kernel_status()
                
        except Exception as e:
            self.logger.error(f"Error starting kernel: {e}")
            self._attempt_heal("kernel_start", str(e))
            return None
    
    def shutdown(self):
        """Gracefully shutdown the kernel"""
        self.logger.info("Shutting down kernel")
        self.running = False
        
        # Backup before shutdown
        backup_path = self.backup_dir / f"shutdown_backup_{datetime.now().timestamp()}"
        self.clone_kernel(str(backup_path))
        
        self.logger.info("Kernel shutdown complete")


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Agnostic Universal Kernel")
    parser.add_argument("--config", help="Path to configuration file")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon")
    parser.add_argument("--clone", help="Clone kernel to specified path")
    parser.add_argument("--scan-configs", help="Scan directory for configs")
    parser.add_argument("--status", action="store_true", help="Show kernel status")
    
    args = parser.parse_args()
    
    # Initialize kernel
    kernel = AgnosticUniversalKernel(config_path=args.config)
    
    if args.clone:
        kernel.clone_kernel(args.clone)
        print(f"Kernel cloned to: {args.clone}")
        return
    
    if args.scan_configs:
        results = kernel.scan_and_clone_configs(args.scan_configs)
        print(f"Config scan results: {json.dumps(results, indent=2)}")
        return
    
    if args.status:
        status = kernel.get_kernel_status()
        print(json.dumps(status, indent=2))
        return
    
    # Start kernel
    try:
        status = kernel.start()
        print(f"Kernel started: {json.dumps(status, indent=2)}")
        
        if args.daemon:
            # Keep running
            while kernel.running:
                time.sleep(1)
    except KeyboardInterrupt:
        kernel.shutdown()


if __name__ == "__main__":
    main()
