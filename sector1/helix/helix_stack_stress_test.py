#!/usr/bin/env python3
"""
Stress test for HelixCache's L1->L2->L3 tiering (helix_complete_stack.py).

The original demo() in that file never actually exercises promotion/
demotion/compression -- its 3,001 test blocks total 2.5MB against a 64MB
L1 cap, so nothing ever gets evicted. This test deliberately configures
tiny tier caps and pushes real pressure through them, then asserts the
tiering counters actually moved, to prove (or disprove) the logic for
real instead of trusting a demo that never triggered it.
"""

import sys
from helix_complete_stack import HelixSystem

def main():
    print("=" * 70)
    print("HELIX TIERING STRESS TEST -- forcing real L1->L2->L3 pressure")
    print("=" * 70)

    # Tiny caps on purpose: 1MB L1, 2MB L2, 4MB L3 -- a handful of
    # 100KB blocks will blow past each of these immediately.
    helix = HelixSystem(l1_cache_mb=1, l2_cache_mb=2, l3_cache_mb=4, virtual_ram_mb=64)

    block_size_kb = 100
    payload = 'x' * (block_size_kb * 1024)
    n_blocks = 200  # 200 * 100KB = ~20MB pushed through a 1MB L1 cap

    print(f"Allocating {n_blocks} blocks of {block_size_kb}KB each "
          f"({n_blocks * block_size_kb / 1024:.1f}MB total, L1 cap is 1MB)...")
    for i in range(n_blocks):
        helix.memory.malloc(f'stress_{i}', payload)

    stats = helix.get_stats()
    cache = stats['cache']
    print()
    print("Tiering counters after the push:")
    print(f"  L1 items:      {cache['l1_items']}")
    print(f"  L2 items:      {cache['l2_items']}")
    print(f"  L3 items:      {cache['l3_items']}")
    print(f"  Demotions:     {cache['demotions']}")
    print(f"  Compressions:  {cache['compressions']}")
    print(f"  Evictions:     {cache['evictions']}")
    print()

    # Now re-read the earliest blocks (should have been demoted furthest)
    # enough times each to cross the promotion thresholds coded in
    # HelixCache.get() -- access_count > 3 promotes L2->L1, > 2 promotes L3->L2.
    print("Re-reading the first 20 blocks 5x each to trigger promotion...")
    for i in range(20):
        for _ in range(5):
            helix.memory.read(f'stress_{i}')

    stats2 = helix.get_stats()
    cache2 = stats2['cache']
    print()
    print("Tiering counters after re-reads:")
    print(f"  L1 items:      {cache2['l1_items']}")
    print(f"  L2 items:      {cache2['l2_items']}")
    print(f"  L3 items:      {cache2['l3_items']}")
    print(f"  Promotions:    {cache2['promotions']}")
    print(f"  Demotions:     {cache2['demotions']}")
    print(f"  Compressions:  {cache2['compressions']}")
    print(f"  Evictions:     {cache2['evictions']}")
    print(f"  Hit rate:      {cache2['hit_rate']:.1f}%")
    print()

    failures = []
    if cache2['demotions'] == 0:
        failures.append("demotions stayed 0 -- L1->L2 demotion never fired despite 20x L1 cap pressure")
    if cache2['compressions'] == 0:
        failures.append("compressions stayed 0 -- L2->L3 demotion (which compresses) never fired")
    if cache2['promotions'] == 0:
        failures.append("promotions stayed 0 -- re-reading demoted blocks never promoted them back up")

    print("=" * 70)
    if failures:
        print(f"RESULT: BROKEN -- {len(failures)} tiering path(s) never fired:")
        for f in failures:
            print(f"  - {f}")
        print("=" * 70)
        sys.exit(1)
    else:
        print("RESULT: Tiering logic is real -- demotion, compression, and")
        print("promotion all fired under actual pressure, not just in theory.")
        print("=" * 70)
        sys.exit(0)

if __name__ == "__main__":
    main()
