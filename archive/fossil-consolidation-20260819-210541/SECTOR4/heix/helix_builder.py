#!/usr/bin/env python3
"""
🧬 HELIX KERNEL BUILDER
One-click builder with single configuration variable

USAGE:
    1. Edit TEST_MODE below (1-5)
    2. Run: python3 build_helix.py
    3. That's it!

Built for testing and benchmarking
"""

import os
import sys
import json
import time
import shutil
import subprocess
from pathlib import Path

# ============================================================================
# ⚙️ CONFIGURATION - CHANGE THIS ONE VARIABLE
# ============================================================================

TEST_MODE = 3  # <-- CHANGE THIS NUMBER (1-5)

"""
TEST_MODE OPTIONS:

1 = MINIMAL    (256MB total, fast startup, low memory)
    - L1: 64MB  L2: 128MB  L3: 64MB
    - Good for: Quick tests, debugging
    - Boot time: <1 second
    
2 = LIGHT      (1GB total, balanced)
    - L1: 256MB  L2: 512MB  L3: 256MB
    - Good for: Normal testing, development
    - Boot time: 1-2 seconds
    
3 = STANDARD   (4GB total, production-like)
    - L1: 512MB  L2: 2GB  L3: 1.5GB
    - Good for: Real workload testing
    - Boot time: 2-5 seconds
    
4 = HEAVY      (8GB total, stress test)
    - L1: 1GB  L2: 4GB  L3: 3GB
    - Good for: Heavy benchmarking
    - Boot time: 5-10 seconds
    
5 = EXTREME    (16GB total, maximum)
    - L1: 2GB  L2: 8GB  L3: 6GB
    - Good for: Full system test
    - Boot time: 10-20 seconds
"""

# ============================================================================
# AUTOMATIC CONFIGURATION (Don't touch this)
# ============================================================================

CONFIGS = {
    1: {
        'name': 'MINIMAL',
        'l1_mb': 64,
        'l2_mb': 128,
        'l3_mb': 64,
        'vram_mb': 512,
        'compress_level': 1,
        'description': 'Fast startup, minimal memory'
    },
    2: {
        'name': 'LIGHT',
        'l1_mb': 256,
        'l2_mb': 512,
        'l3_mb': 256,
        'vram_mb': 2048,
        'compress_level': 3,
        'description': 'Balanced for development'
    },
    3: {
        'name': 'STANDARD',
        'l1_mb': 512,
        'l2_mb': 2048,
        'l3_mb': 1536,
        'vram_mb': 4096,
        'compress_level': 6,
        'description': 'Production-like workload'
    },
    4: {
        'name': 'HEAVY',
        'l1_mb': 1024,
        'l2_mb': 4096,
        'l3_mb': 3072,
        'vram_mb': 8192,
        'compress_level': 6,
        'description': 'Stress testing'
    },
    5: {
        'name': 'EXTREME',
        'l1_mb': 2048,
        'l2_mb': 8192,
        'l3_mb': 6144,
        'vram_mb': 16384,
        'compress_level': 9,
        'description': 'Maximum capacity'
    }
}

# ============================================================================
# BUILDER
# ============================================================================

class HelixBuilder:
    """Builds and configures Helix kernel"""
    
    def __init__(self, test_mode: int):
        if test_mode not in CONFIGS:
            print(f"❌ ERROR: TEST_MODE must be 1-5, got {test_mode}")
            sys.exit(1)
        
        self.config = CONFIGS[test_mode]
        self.test_mode = test_mode
        self.build_dir = Path.cwd() / 'helix_build'
        self.output_dir = Path.cwd() / 'helix_kernel'
        
    def print_banner(self):
        """Print build configuration"""
        print("=" * 70)
        print("🧬 HELIX KERNEL BUILDER")
        print("=" * 70)
        print()
        print(f"📋 Configuration: {self.config['name']}")
        print(f"   {self.config['description']}")
        print()
        print("Memory Tiers:")
        print(f"   L3 (HOT):        {self.config['l1_mb']:>6} MB")
        print(f"   L2 (WARM):       {self.config['l2_mb']:>6} MB")
        print(f"   L1 (COLD):       {self.config['l3_mb']:>6} MB")
        print(f"   Virtual RAM:     {self.config['vram_mb']:>6} MB")
        print()
        print(f"Compression Level: {self.config['compress_level']}/9")
        print()
        print("=" * 70)
        print()
    
    def create_directories(self):
        """Create build directories"""
        print("📁 Creating directories...")
        self.build_dir.mkdir(exist_ok=True)
        self.output_dir.mkdir(exist_ok=True)
        print("   ✓ Directories ready")
        print()
    
    def generate_config_file(self):
        """Generate helix_config.json"""
        print("⚙️  Generating configuration...")
        
        config_data = {
            'version': '1.0.0',
            'test_mode': self.test_mode,
            'mode_name': self.config['name'],
            'memory': {
                'l3_hot_mb': self.config['l1_mb'],
                'l2_warm_mb': self.config['l2_mb'],
                'l1_cold_mb': self.config['l3_mb'],
                'virtual_ram_mb': self.config['vram_mb']
            },
            'compression': {
                'level': self.config['compress_level'],
                'algorithm': 'zlib'
            },
            'storage': {
                'quadralingual': True,
                'languages': ['vector', 'nosql', 'relational', 'timeseries']
            },
            'translator': {
                'enabled': True,
                'ingress_egress': True
            },
            'preload': {
                'enabled': True,
                'strategy': 'temperature_based',
                'hot_threshold': 3,
                'warm_threshold': 2
            }
        }
        
        config_path = self.output_dir / 'helix_config.json'
        with open(config_path, 'w') as f:
            json.dump(config_data, f, indent=2)
        
        print(f"   ✓ Config saved to: {config_path}")
        print()
        
        return config_path
    
    def generate_kernel_wrapper(self):
        """Generate Python kernel wrapper with embedded config"""
        print("🔧 Generating kernel wrapper...")
        
        wrapper_code = f'''#!/usr/bin/env python3
"""
🧬 Helix Kernel - Auto-generated
Mode: {self.config['name']}
Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}
"""

import sys
import json
from pathlib import Path

# Embedded configuration
CONFIG = {json.dumps(self.config, indent=4)}

class HelixKernel:
    """Helix kernel with embedded configuration"""
    
    def __init__(self):
        self.config = CONFIG
        print(f"🧬 Helix Kernel - {{self.config['name']}} Mode")
        print(f"   L3: {{self.config['l1_mb']}}MB | L2: {{self.config['l2_mb']}}MB | L1: {{self.config['l3_mb']}}MB")
        print()
    
    def start(self):
        """Start the kernel"""
        # Import your actual helix modules here
        try:
            # This will import your complete stack
            from helix_complete_package import init_helix, helix_stats
            
            # Initialize with embedded config
            init_helix(
                l1_mb=self.config['l3_mb'],  # Note: inverted for your naming
                l2_mb=self.config['l2_mb'],
                l3_mb=self.config['l1_mb'],
                vram_mb=self.config['vram_mb']
            )
            
            return True
        except ImportError as e:
            print(f"⚠️  Warning: Could not import helix modules: {{e}}")
            print("   Running in config-only mode")
            return False
    
    def get_stats(self):
        """Get kernel statistics"""
        try:
            from helix_complete_package import helix_stats
            helix_stats()
        except:
            print("Stats not available (modules not loaded)")

def main():
    kernel = HelixKernel()
    success = kernel.start()
    
    if success:
        print("✓ Kernel started successfully!")
        print()
        print("Available commands:")
        print("  kernel.get_stats()  - Show statistics")
        print()
    else:
        print("Running in configuration mode only")
        print(f"Configuration: {{json.dumps(kernel.config, indent=2)}}")

if __name__ == "__main__":
    main()
'''
        
        wrapper_path = self.output_dir / 'helix_kernel.py'
        with open(wrapper_path, 'w') as f:
            f.write(wrapper_code)
        
        # Make executable
        os.chmod(wrapper_path, 0o755)
        
        print(f"   ✓ Kernel wrapper: {wrapper_path}")
        print()
        
        return wrapper_path
    
    def generate_launcher(self):
        """Generate simple launcher script"""
        print("🚀 Generating launcher...")
        
        launcher_code = f'''#!/usr/bin/env python3
"""
Quick launcher for Helix kernel
Just run: python3 launch_helix.py
"""

import sys
from pathlib import Path

# Add helix to path
sys.path.insert(0, str(Path(__file__).parent))

from helix_kernel import HelixKernel

if __name__ == "__main__":
    kernel = HelixKernel()
    kernel.start()
    
    print()
    print("=" * 70)
    print("Helix is ready! Press Ctrl+C to stop")
    print("=" * 70)
    
    try:
        # Keep running
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print()
        print("Shutting down...")
        kernel.get_stats()
'''
        
        launcher_path = self.output_dir / 'launch_helix.py'
        with open(launcher_path, 'w') as f:
            f.write(launcher_code)
        
        os.chmod(launcher_path, 0o755)
        
        print(f"   ✓ Launcher: {launcher_path}")
        print()
        
        return launcher_path
    
    def generate_benchmark_script(self):
        """Generate benchmarking script"""
        print("📊 Generating benchmark script...")
        
        benchmark_code = '''#!/usr/bin/env python3
"""
Helix Benchmark Script
Tests performance with current configuration
"""

import time
import random
from helix_kernel import HelixKernel

def benchmark_malloc_free(iterations=1000):
    """Test malloc/free speed"""
    from helix_complete_package import helix_malloc, helix_free
    
    print(f"Benchmarking malloc/free ({iterations} iterations)...")
    
    start = time.time()
    ptrs = []
    
    for i in range(iterations):
        ptr = helix_malloc(1024)
        ptrs.append(ptr)
    
    for ptr in ptrs:
        helix_free(ptr)
    
    elapsed = time.time() - start
    ops_per_sec = (iterations * 2) / elapsed  # malloc + free
    
    print(f"  Time: {elapsed:.2f}s")
    print(f"  Ops/sec: {ops_per_sec:,.0f}")
    print()

def benchmark_cache_hits(iterations=10000):
    """Test cache hit rates"""
    from helix_complete_package import helix_malloc, helix_read, helix_write, helix_free
    
    print(f"Benchmarking cache hits ({iterations} iterations)...")
    
    # Allocate some data
    ptrs = []
    for i in range(100):
        ptr = helix_malloc(512)
        helix_write(ptr, f"Data {i}".encode())
        ptrs.append(ptr)
    
    start = time.time()
    
    # Random access pattern
    for _ in range(iterations):
        ptr = random.choice(ptrs)
        helix_read(ptr, 10)
    
    elapsed = time.time() - start
    ops_per_sec = iterations / elapsed
    
    print(f"  Time: {elapsed:.2f}s")
    print(f"  Ops/sec: {ops_per_sec:,.0f}")
    print()
    
    # Cleanup
    for ptr in ptrs:
        helix_free(ptr)

def main():
    print("=" * 70)
    print("🧬 HELIX BENCHMARK")
    print("=" * 70)
    print()
    
    kernel = HelixKernel()
    kernel.start()
    
    print()
    benchmark_malloc_free(1000)
    benchmark_cache_hits(10000)
    
    kernel.get_stats()

if __name__ == "__main__":
    main()
'''
        
        benchmark_path = self.output_dir / 'benchmark_helix.py'
        with open(benchmark_path, 'w') as f:
            f.write(benchmark_code)
        
        os.chmod(benchmark_path, 0o755)
        
        print(f"   ✓ Benchmark: {benchmark_path}")
        print()
        
        return benchmark_path
    
    def copy_source_files(self):
        """Copy your existing helix files"""
        print("📦 Looking for source files...")
        
        source_files = [
        "franken",
        "encompass_syncthing.py"
        ]
        
        copied = 0
        for filename in source_files:
            src = Path.cwd() / filename
            if src.exists():
                dst = self.output_dir / filename
                shutil.copy2(src, dst)
                print(f"   ✓ Copied: {filename}")
                copied += 1
        
        if copied == 0:
            print("   ⚠️  No source files found in current directory")
            print("   Place your helix .py files here and rebuild")
        else:
            print(f"   ✓ Copied {copied} source files")
        
        print()
    
    def generate_readme(self):
        """Generate README with instructions"""
        print("📝 Generating README...")
        
        readme = f'''# 🧬 Helix Kernel - {self.config['name']} Mode

Auto-generated on {time.strftime('%Y-%m-%d %H:%M:%S')}

## Configuration

```
Mode:            {self.config['name']}
L3 (HOT):        {self.config['l1_mb']} MB
L2 (WARM):       {self.config['l2_mb']} MB
L1 (COLD):       {self.config['l3_mb']} MB
Virtual RAM:     {self.config['vram_mb']} MB
Compression:     Level {self.config['compress_level']}/9
```

## Quick Start

### 1. Launch Helix
```bash
python3 launch_helix.py
```

### 2. Run Benchmark
```bash
python3 benchmark_helix.py
```

### 3. Test Manually
```python
from helix_kernel import HelixKernel

kernel = HelixKernel()
kernel.start()
kernel.get_stats()
```

## Configuration File

See `helix_config.json` for full configuration.

## Changing Test Mode

To rebuild with different settings:
1. Edit `TEST_MODE` in `build_helix.py` (line 18)
2. Run: `python3 build_helix.py`
3. New kernel built in `helix_kernel/`

## Test Modes

1. MINIMAL   - 256MB total, fast startup
2. LIGHT     - 1GB total, balanced
3. STANDARD  - 4GB total, production-like
4. HEAVY     - 8GB total, stress test
5. EXTREME   - 16GB total, maximum

Current mode: **{self.config['name']}** (Mode {self.test_mode})

## Files Generated

- `helix_kernel.py` - Main kernel with embedded config
- `launch_helix.py` - Quick launcher
- `benchmark_helix.py` - Performance testing
- `helix_config.json` - Configuration file
- Source files (*.py) - Your helix modules

## Notes

This is TEST MODE {self.test_mode}. Built for testing and benchmarking.
For production deployment, consider compiling to C and creating a proper kernel module.
'''
        
        readme_path = self.output_dir / 'README.md'
        with open(readme_path, 'w') as f:
            f.write(readme)
        
        print(f"   ✓ README: {readme_path}")
        print()
    
    def build(self):
        """Run the full build process"""
        self.print_banner()
        
        self.create_directories()
        config_path = self.generate_config_file()
        kernel_path = self.generate_kernel_wrapper()
        launcher_path = self.generate_launcher()
        benchmark_path = self.generate_benchmark_script()
        self.copy_source_files()
        self.generate_readme()
        
        print("=" * 70)
        print("✅ BUILD COMPLETE!")
        print("=" * 70)
        print()
        print(f"📁 Output directory: {self.output_dir}")
        print()
        print("Quick commands:")
        print(f"   cd {self.output_dir}")
        print("   python3 launch_helix.py       # Start kernel")
        print("   python3 benchmark_helix.py    # Run benchmark")
        print()
        print("To change configuration:")
        print("   1. Edit TEST_MODE in build_helix.py")
        print("   2. Run: python3 build_helix.py")
        print()

# ============================================================================
# MAIN
# ============================================================================

def main():
    try:
        builder = HelixBuilder(TEST_MODE)
        builder.build()
    except KeyboardInterrupt:
        print("\n\n⚠️  Build cancelled")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Build failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
