#!/usr/bin/env python3
"""
AI Temperature Gauge & Adjuster
Monitors and controls AI model temperature settings for optimal performance
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime
import argparse

class AITempController:
    def __init__(self, config_path='/etc/systemd/system/ai_temp_config.json'):
        self.config_path = config_path
        self.config = self.load_config()
        self.models = self.config.get('models', {})
        
    def load_config(self):
        """Load temperature configuration"""
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return self.create_default_config()
    
    def create_default_config(self):
        """Create default temperature config"""
        default = {
            "version": "1.0.0",
            "last_update": datetime.now().isoformat(),
            "models": {
                "anglyene": {
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "top_k": 40,
                    "repeat_penalty": 1.1,
                    "min_temp": 0.0,
                    "max_temp": 2.0,
                    "preset": "balanced",
                    "status": "active"
                },
                "helix": {
                    "model": "qwen3-19b",
                    "ram": "8GB",
                    "quantization": "Q4_K_M",
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "top_k": 40,
                    "repeat_penalty": 1.1,
                    "context_length": 4096,
                    "batch_size": 512,
                    "threads": 4,
                    "min_temp": 0.0,
                    "max_temp": 2.0,
                    "preset": "balanced",
                    "status": "active",
                    "performance_mode": "memory_optimized"
                },
                "qwen2": {
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "top_k": 40,
                    "repeat_penalty": 1.1,
                    "min_temp": 0.0,
                    "max_temp": 2.0,
                    "preset": "balanced",
                    "status": "fallback"
                }
            },
            "presets": {
                "precise": {
                    "temperature": 0.3,
                    "top_p": 0.85,
                    "description": "Low creativity, high consistency - for factual/technical tasks"
                },
                "balanced": {
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "description": "Balanced creativity and consistency - general purpose"
                },
                "creative": {
                    "temperature": 1.2,
                    "top_p": 0.95,
                    "description": "High creativity, varied outputs - for creative tasks"
                },
                "wild": {
                    "temperature": 1.8,
                    "top_p": 0.98,
                    "description": "Maximum creativity, unpredictable - experimental"
                }
            },
            "monitoring": {
                "log_adjustments": true,
                "alert_on_extreme": true,
                "auto_adjust": false
            }
        }
        
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, 'w') as f:
            json.dump(default, f, indent=2)
        
        return default
    
    def save_config(self):
        """Save configuration to file"""
        self.config['last_update'] = datetime.now().isoformat()
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def display_gauge(self, model_name=None):
        """Display temperature gauge for model(s)"""
        print("\n" + "="*70)
        print("🌡️  AI TEMPERATURE GAUGE")
        print("="*70)
        
        if model_name:
            if model_name not in self.models:
                print(f"❌ Model '{model_name}' not found")
                return
            models_to_show = {model_name: self.models[model_name]}
        else:
            models_to_show = self.models
        
        for name, settings in models_to_show.items():
            temp = settings.get('temperature', 0.7)
            preset = settings.get('preset', 'unknown')
            status = settings.get('status', 'unknown')
            
            # Create visual gauge
            gauge = self.create_temp_gauge(temp, settings.get('max_temp', 2.0))
            
            print(f"\n📊 {name.upper()}")
            print(f"   Status: {status}")
            print(f"   Preset: {preset}")
            print(f"   {gauge}")
            print(f"   Temperature: {temp:.2f}")
            print(f"   Top-P: {settings.get('top_p', 'N/A')}")
            print(f"   Top-K: {settings.get('top_k', 'N/A')}")
            print(f"   Repeat Penalty: {settings.get('repeat_penalty', 'N/A')}")
    
    def create_temp_gauge(self, temp, max_temp=2.0):
        """Create visual temperature gauge"""
        gauge_length = 40
        position = int((temp / max_temp) * gauge_length)
        position = min(position, gauge_length)
        
        # Color zones
        if temp < 0.5:
            zone = "🔵 PRECISE"
            bar_char = "▓"
        elif temp < 1.0:
            zone = "🟢 BALANCED"
            bar_char = "▓"
        elif temp < 1.5:
            zone = "🟡 CREATIVE"
            bar_char = "▓"
        else:
            zone = "🔴 WILD"
            bar_char = "▓"
        
        gauge_bar = "[" + bar_char * position + "·" * (gauge_length - position) + "]"
        return f"{gauge_bar} {zone}"
    
    def set_temperature(self, model_name, temp):
        """Set temperature for a specific model"""
        if model_name not in self.models:
            print(f"❌ Model '{model_name}' not found")
            return False
        
        temp = float(temp)
        min_temp = self.models[model_name].get('min_temp', 0.0)
        max_temp = self.models[model_name].get('max_temp', 2.0)
        
        if temp < min_temp or temp > max_temp:
            print(f"⚠️  Temperature {temp} outside allowed range [{min_temp}, {max_temp}]")
            return False
        
        old_temp = self.models[model_name]['temperature']
        self.models[model_name]['temperature'] = temp
        self.models[model_name]['preset'] = 'custom'
        self.save_config()
        
        print(f"✓ {model_name} temperature: {old_temp:.2f} → {temp:.2f}")
        
        if self.config.get('monitoring', {}).get('log_adjustments', True):
            self.log_adjustment(model_name, 'temperature', old_temp, temp)
        
        return True
    
    def apply_preset(self, model_name, preset_name):
        """Apply a temperature preset to a model"""
        if model_name not in self.models:
            print(f"❌ Model '{model_name}' not found")
            return False
        
        presets = self.config.get('presets', {})
        if preset_name not in presets:
            print(f"❌ Preset '{preset_name}' not found")
            print(f"Available presets: {', '.join(presets.keys())}")
            return False
        
        preset = presets[preset_name]
        old_temp = self.models[model_name]['temperature']
        
        self.models[model_name]['temperature'] = preset['temperature']
        self.models[model_name]['top_p'] = preset['top_p']
        self.models[model_name]['preset'] = preset_name
        
        self.save_config()
        
        print(f"✓ Applied '{preset_name}' preset to {model_name}")
        print(f"  {preset['description']}")
        print(f"  Temperature: {old_temp:.2f} → {preset['temperature']:.2f}")
        
        return True
    
    def list_presets(self):
        """List all available presets"""
        print("\n" + "="*70)
        print("📋 AVAILABLE TEMPERATURE PRESETS")
        print("="*70)
        
        presets = self.config.get('presets', {})
        for name, preset in presets.items():
            print(f"\n🎚️  {name.upper()}")
            print(f"   Temperature: {preset['temperature']}")
            print(f"   Top-P: {preset['top_p']}")
            print(f"   {preset['description']}")
    
    def set_all_models(self, temp=None, preset=None):
        """Set temperature or preset for all models"""
        if temp:
            print(f"Setting all models to temperature {temp}...")
            for model_name in self.models.keys():
                self.set_temperature(model_name, temp)
        elif preset:
            print(f"Applying '{preset}' preset to all models...")
            for model_name in self.models.keys():
                self.apply_preset(model_name, preset)
    
    def log_adjustment(self, model, param, old_val, new_val):
        """Log temperature adjustments"""
        log_file = '/var/log/guardian/ai_temp_adjustments.log'
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'model': model,
            'parameter': param,
            'old_value': old_val,
            'new_value': new_val
        }
        
        with open(log_file, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
    
    def monitor_mode(self):
        """Real-time monitoring display"""
        print("🔍 Monitoring AI temperatures (Ctrl+C to exit)...")
        try:
            import time
            while True:
                os.system('clear' if os.name != 'nt' else 'cls')
                self.display_gauge()
                print("\n🔄 Refreshing in 5 seconds...")
                time.sleep(5)
        except KeyboardInterrupt:
            print("\n\n✓ Monitoring stopped")


def main():
    parser = argparse.ArgumentParser(description='AI Temperature Control')
    parser.add_argument('command', nargs='?', choices=['show', 'set', 'preset', 'list', 'monitor', 'all'],
                       help='Command to execute')
    parser.add_argument('--model', '-m', help='Model name (anglyene, helix, qwen2)')
    parser.add_argument('--temp', '-t', type=float, help='Temperature value')
    parser.add_argument('--preset', '-p', help='Preset name')
    
    args = parser.parse_args()
    
    controller = AITempController()
    
    if not args.command or args.command == 'show':
        controller.display_gauge(args.model)
    
    elif args.command == 'set':
        if not args.model or args.temp is None:
            print("❌ Usage: ai-temp set --model <name> --temp <value>")
            sys.exit(1)
        controller.set_temperature(args.model, args.temp)
        controller.display_gauge(args.model)
    
    elif args.command == 'preset':
        if not args.model or not args.preset:
            print("❌ Usage: ai-temp preset --model <name> --preset <preset>")
            sys.exit(1)
        controller.apply_preset(args.model, args.preset)
        controller.display_gauge(args.model)
    
    elif args.command == 'list':
        controller.list_presets()
    
    elif args.command == 'monitor':
        controller.monitor_mode()
    
    elif args.command == 'all':
        if args.temp:
            controller.set_all_models(temp=args.temp)
        elif args.preset:
            controller.set_all_models(preset=args.preset)
        else:
            print("❌ Usage: ai-temp all --temp <value> OR --preset <name>")
            sys.exit(1)
        controller.display_gauge()
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()