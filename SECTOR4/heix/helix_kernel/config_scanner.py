#!/usr/bin/env python3
"""
Config Scanner & Collector (Upgraded)
Scans application modules for config files and in-code settings.
"""

import os
import sys
import json
import re
import shutil
from pathlib import Path
from datetime import datetime

class ConfigScanner:
    def __init__(self, root_path, output_dir="collected_configs"):
        self.root_path = Path(root_path).resolve()
        self.output_dir = Path(output_dir).resolve()
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Patterns for identifying config files by name/extension
        self.config_file_patterns = [
            "*.json", "*.yaml", "*.yml", "*.toml", "*.ini", "*.conf",
            "*.config", "*.cfg", "*.properties", "*.env", ".env*",
            "config.*", "settings.*", "*.settings"
        ]
        self.config_file_names = [
            "config", "configuration", "settings", "options", "preferences",
            ".env", "env", "environment"
        ]
        
        # Regex patterns for finding in-code configuration variables
        self.in_code_patterns = [
            re.compile(r"^\s*[A-Z_][A-Z0-9_]+\s*=\s*.*"),
            re.compile(r"define\s*\("),
            re.compile(r'^\s*["\'][a-zA-Z_][a-zA-Z0-9_]+["\']\s*:\s*.*'),
        ]
        
        self.found_configs = []
        self.found_in_code_settings = {}
    
    def is_config_file(self, filepath):
        """Check if file matches dedicated config file patterns."""
        name = filepath.name.lower()
        if any(cfg_name in name for cfg_name in self.config_file_names):
            return True
        for pattern in self.config_file_patterns:
            if filepath.match(pattern):
                return True
        return False

    def scan_file_for_in_code_settings(self, filepath):
        """Scans a single file's content for configuration lines."""
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            discovered_lines = []
            for i, line in enumerate(lines, 1):
                # Skip commented out or empty lines
                if line.strip().startswith(('#', '//', '*', ';')) or not line.strip():
                    continue

                for pattern in self.in_code_patterns:
                    if pattern.match(line.strip()):
                        discovered_lines.append({"line_num": i, "line_text": line.strip()})
                        break # Move to next line once a pattern is matched
            
            if discovered_lines:
                self.found_in_code_settings[filepath] = discovered_lines
        except Exception as e:
            # Silently ignore files we can't read
            pass

    def scan_directory(self, directory):
        """Recursively scan directory for all file types."""
        print("Scanning for all files to analyze content...")
        try:
            for item in directory.rglob("*"):
                # Exclude this script's own output directory
                if self.output_dir.as_posix() in item.as_posix():
                    continue
                if item.is_file():
                    if self.is_config_file(item):
                        if item not in self.found_configs:
                            self.found_configs.append(item)
                    
                    self.scan_file_for_in_code_settings(item)
        except Exception as e:
            print(f"Error scanning {directory}: {e}")
    
    def generate_report(self):
        """Generates a report of all findings."""
        if not self.found_configs and not self.found_in_code_settings:
            print("No config files or in-code settings found!")
            return
        
        output_path = self.output_dir / f"scan_{self.timestamp}"
        output_path.mkdir(parents=True, exist_ok=True)
        
        print(f"\nGenerating report in: {output_path}\n")
        
        manifest = {
            "scan_time": self.timestamp,
            "root_path": str(self.root_path),
            "dedicated_configs_found": len(self.found_configs),
            "files_with_in_code_settings": len(self.found_in_code_settings),
            "collected_files": [],
            "in_code_settings": []
        }

        for config_file in self.found_configs:
            try:
                relative_path = config_file.relative_to(self.root_path)
                dest_path = output_path / "collected_files" / relative_path
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(config_file, dest_path)
                
                file_info = {
                    "type": "dedicated_config",
                    "original_path": str(config_file),
                    "collected_path": str(dest_path.relative_to(output_path)),
                }
                manifest["collected_files"].append(file_info)
                print(f"✓ Collected dedicated config: {relative_path}")
            except Exception as e:
                print(f"✗ Failed to collect {config_file}: {e}")
        
        for filepath, lines in self.found_in_code_settings.items():
            setting_info = {
                "type": "in_code_setting",
                "file_path": str(filepath.relative_to(self.root_path)),
                "settings": lines
            }
            manifest["in_code_settings"].append(setting_info)

        manifest_path = output_path / "manifest.json"
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)

        summary_path = output_path / "SUMMARY.txt"
        with open(summary_path, 'w') as f:
            f.write(f"Config Collection Summary (Upgraded Scan)\n")
            f.write(f"{ '='*60}\n")
            f.write(f"Scan Time: {self.timestamp}\n")
            f.write(f"Root Path: {self.root_path}\n")
            f.write(f"Dedicated Config Files Found: {len(self.found_configs)}\n")
            f.write(f"Files with In-Code Settings: {len(self.found_in_code_settings)}\n\n")
            
            f.write(f"Collected Dedicated Config Files:\n")
            f.write(f"---------------------------------\n")
            for file_info in manifest["collected_files"]:
                f.write(f"  - {Path(file_info['collected_path']).name}\n")
            
            f.write(f"\n\nFiles with Discovered In-Code Settings:\n")
            f.write(f"-----------------------------------------\n")
            for setting_info in sorted(manifest["in_code_settings"], key=lambda x: x['file_path']):
                f.write(f"  - {setting_info['file_path']} ({len(setting_info['settings'])} settings found)\n")
        
        print(f"\n{'='*60}")
        print(f"Collection Complete!")
        print(f"  Output Directory: {output_path}")
        print(f"  Manifest: {manifest_path}")
        print(f"  Summary: {summary_path}")
        print(f"{'='*60}")

def main():
    if len(sys.argv) < 2:
        print("Usage: python config_scanner.py <app_directory> [output_directory]")
        sys.exit(1)
    
    app_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "collected_configs"
    
    if not os.path.exists(app_path):
        print(f"Error: Path does not exist: {app_path}")
        sys.exit(1)
    
    scanner = ConfigScanner(app_path, output_dir)
    scanner.scan_directory(scanner.root_path)
    scanner.generate_report()

if __name__ == "__main__":
    main()
