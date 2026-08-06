#!/usr/bin/env python3
"""
Config Scanner & Collector
Scans application modules for config files and collects them for dashboard analysis.
"""

import os
import sys
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

class ConfigScanner:
    def __init__(self, root_path: str, output_dir: str = "collected_configs"):
        self.root_path = Path(root_path).resolve()
        self.output_dir = Path(output_dir).resolve()
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Common config file patterns
        self.config_patterns = [
            "*.json", "*.yaml", "*.yml", "*.toml", "*.ini", "*.conf",
            "*.config", "*.cfg", "*.properties", "*.env", ".env*",
            "config.*", "settings.*", "*.settings"
        ]
        
        # Common config file names
        self.config_names = [
            "config", "configuration", "settings", "options", "preferences",
            ".env", "env", "environment"
        ]
        
        self.found_configs: List[Path] = []
        self.modules_scanned: List[str] = []
    
    def is_config_file(self, filepath: Path) -> bool:
        """Check if file matches config patterns."""
        name = filepath.name.lower()
        
        # Check exact names
        if any(cfg_name in name for cfg_name in self.config_names):
            return True
        
        # Check patterns
        for pattern in self.config_patterns:
            if filepath.match(pattern):
                return True
        
        return False
    
    def scan_directory(self, directory: Path = None) -> List[Path]:
        """Recursively scan directory for config files."""
        if directory is None:
            directory = self.root_path
            
        try:
            for item in directory.rglob("*"):
                if item.is_file() and self.is_config_file(item):
                    self.found_configs.append(item)
        except Exception as e:
            print(f"Error scanning {directory}: {e}")
        
        return self.found_configs
    
    def scan(self, scan_path: str = None) -> Dict[str, Dict]:
        """Scan and return config files with metadata."""
        if scan_path:
            self.root_path = Path(scan_path).resolve()
        
        self.found_configs = []
        self.scan_directory()
        
        results = {}
        for config_file in self.found_configs:
            try:
                # Determine app name from path
                relative_path = config_file.relative_to(self.root_path)
                parts = relative_path.parts
                app_name = parts[0] if len(parts) > 1 else config_file.stem
                
                results[str(config_file)] = {
                    'app_name': app_name,
                    'filename': config_file.name,
                    'relative_path': str(relative_path),
                    'size': config_file.stat().st_size,
                    'modified': datetime.fromtimestamp(config_file.stat().st_mtime).isoformat()
                }
            except Exception as e:
                print(f"Error processing {config_file}: {e}")
        
        return results
    
    def collect_configs(self) -> Path:
        """Copy all found config files to output directory."""
        if not self.found_configs:
            self.scan_directory()
            
        if not self.found_configs:
            print("No config files found!")
            return None
        
        # Create timestamped output directory
        output_path = self.output_dir / f"scan_{self.timestamp}"
        output_path.mkdir(parents=True, exist_ok=True)
        
        print(f"\nCollecting configs to: {output_path}\n")
        
        collected = []
        manifest = {
            "scan_time": self.timestamp,
            "root_path": str(self.root_path),
            "total_configs": len(self.found_configs),
            "modules": {},
            "files": []
        }
        
        for config_file in self.found_configs:
            try:
                # Determine module/component name from path
                relative_path = config_file.relative_to(self.root_path)
                parts = relative_path.parts
                module_name = parts[0] if len(parts) > 1 else "root"
                
                # Create module directory
                module_dir = output_path / module_name
                module_dir.mkdir(parents=True, exist_ok=True)
                
                # Copy config file
                dest = module_dir / config_file.name
                shutil.copy2(config_file, dest)
                
                # Track in manifest
                file_info = {
                    "original_path": str(config_file),
                    "relative_path": str(relative_path),
                    "collected_to": str(dest),
                    "size": config_file.stat().st_size
                }
                
                manifest["files"].append(file_info)
                
                if module_name not in manifest["modules"]:
                    manifest["modules"][module_name] = []
                manifest["modules"][module_name].append(file_info)
                
                collected.append(config_file)
                print(f"✓ Collected: {relative_path}")
                
            except Exception as e:
                print(f"✗ Failed to collect {config_file}: {e}")
        
        # Save manifest
        manifest_path = output_path / "manifest.json"
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)
        
        # Create summary
        summary_path = output_path / "SUMMARY.txt"
        with open(summary_path, 'w') as f:
            f.write(f"Config Collection Summary\n")
            f.write(f"{'='*60}\n")
            f.write(f"Scan Time: {self.timestamp}\n")
            f.write(f"Root Path: {self.root_path}\n")
            f.write(f"Total Configs Found: {len(self.found_configs)}\n")
            f.write(f"Successfully Collected: {len(collected)}\n\n")
            
            f.write(f"Modules Found:\n")
            for module, files in manifest["modules"].items():
                f.write(f"  - {module}: {len(files)} config file(s)\n")
        
        print(f"\n{'='*60}")
        print(f"Collection Complete!")
        print(f"  Output Directory: {output_path}")
        print(f"  Total Files: {len(collected)}")
        print(f"  Modules: {len(manifest['modules'])}")
        print(f"{'='*60}")
        
        return output_path
    
    def health_check(self) -> bool:
        """Check if scanner is healthy."""
        return self.root_path.exists()


def main():
    if len(sys.argv) < 2:
        print("Usage: python config_scanner.py <app_directory> [output_directory]")
        print("\nExample: python config_scanner.py /path/to/app collected_configs")
        sys.exit(1)
    
    app_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "collected_configs"
    
    if not os.path.exists(app_path):
        print(f"Error: Path does not exist: {app_path}")
        sys.exit(1)
    
    scanner = ConfigScanner(app_path, output_dir)
    
    print(f"Scanning for config files in: {scanner.root_path}")
    scanner.scan_directory()
    
    print(f"\nFound {len(scanner.found_configs)} config file(s)")
    
    if scanner.found_configs:
        scanner.collect_configs()


if __name__ == "__main__":
    main()
