# 🧬 Helix Kernel - STANDARD Mode

Auto-generated on 2026-01-23 16:32:03

## Configuration

```
Mode:            STANDARD
L3 (HOT):        512 MB
L2 (WARM):       2048 MB
L1 (COLD):       1536 MB
Virtual RAM:     4096 MB
Compression:     Level 6/9
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

Current mode: **STANDARD** (Mode 3)

## Files Generated

- `helix_kernel.py` - Main kernel with embedded config
- `launch_helix.py` - Quick launcher
- `benchmark_helix.py` - Performance testing
- `helix_config.json` - Configuration file
- Source files (*.py) - Your helix modules

## Notes

This is TEST MODE 3. Built for testing and benchmarking.
For production deployment, consider compiling to C and creating a proper kernel module.
