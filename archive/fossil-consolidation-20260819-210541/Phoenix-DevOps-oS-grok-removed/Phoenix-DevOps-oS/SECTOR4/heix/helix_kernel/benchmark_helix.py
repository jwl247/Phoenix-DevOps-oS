#!/usr/bin/env python3
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
