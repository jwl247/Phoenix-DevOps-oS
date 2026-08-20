#!/usr/bin/env python3
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
