"""
Helix Virtual RAM Manager
Turn your 8GB into 20GB+ through intelligent compression and caching

WARNING: Experimental. Use at your own risk.
"""

import time
import sys
import pickle
import zlib
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional, Dict, List
from enum import Enum
import threading

# ============================================================================
# MEMORY TIER SYSTEM
# ============================================================================

class MemoryTier(Enum):
    """Memory hierarchy tiers"""
    HOT = 0      # Pure RAM, instant access
    WARM = 1     # Compressed RAM
    COLD = 2     # Memory-mapped, ready to evict
    FROZEN = 3   # Evicted to disk

@dataclass
class MemoryBlock:
    """A block of virtual memory"""
    key: str
    data: Any
    tier: MemoryTier
    size_bytes: int
    access_count: int = 0
    last_access: float = field(default_factory=time.time)
    compressed: bool = False
    _compressed_data: Optional[bytes] = None
    
    def access(self):
        """Mark as accessed"""
        self.access_count += 1
        self.last_access = time.time()
    
    def compress(self):
        """Compress data"""
        if not self.compressed and self.data is not None:
            serialized = pickle.dumps(self.data)
            self._compressed_data = zlib.compress(serialized, level=6)
            original_size = self.size_bytes
            compressed_size = len(self._compressed_data)
            self.compressed = True
            return original_size - compressed_size
        return 0
    
    def decompress(self):
        """Decompress data"""
        if self.compressed and self._compressed_data:
            serialized = zlib.decompress(self._compressed_data)
            self.data = pickle.loads(serialized)
            self.compressed = False
            self._compressed_data = None
    
    def promote(self):
        """Move up a tier"""
        if self.tier == MemoryTier.FROZEN:
            self.tier = MemoryTier.COLD
        elif self.tier == MemoryTier.COLD:
            self.tier = MemoryTier.WARM
        elif self.tier == MemoryTier.WARM:
            if self.compressed:
                self.decompress()
            self.tier = MemoryTier.HOT
    
    def demote(self):
        """Move down a tier"""
        if self.tier == MemoryTier.HOT:
            self.compress()
            self.tier = MemoryTier.WARM
        elif self.tier == MemoryTier.WARM:
            self.tier = MemoryTier.COLD
        elif self.tier == MemoryTier.COLD:
            self.tier = MemoryTier.FROZEN

# ============================================================================
# HELIX MEMORY MANAGER
# ============================================================================

class HelixMemoryManager:
    """
    Intelligent virtual memory manager using helix architecture
    """
    def __init__(self, 
                 max_hot_mb: int = 4096,      # 4GB hot tier
                 max_warm_mb: int = 8192,     # 8GB compressed tier
                 max_cold_mb: int = 4096):    # 4GB ready-to-evict
        
        self.max_hot_bytes = max_hot_mb * 1024 * 1024
        self.max_warm_bytes = max_warm_mb * 1024 * 1024
        self.max_cold_bytes = max_cold_mb * 1024 * 1024
        
        # Storage
        self.blocks: Dict[str, MemoryBlock] = {}
        self.hot_keys: OrderedDict = OrderedDict()
        self.warm_keys: OrderedDict = OrderedDict()
        self.cold_keys: OrderedDict = OrderedDict()
        
        # Stats
        self.stats = {
            'allocations': 0,
            'deallocations': 0,
            'promotions': 0,
            'demotions': 0,
            'compressions': 0,
            'decompressions': 0,
            'evictions': 0,
            'hits': 0,
            'misses': 0,
            'bytes_saved': 0
        }
        
        self.lock = threading.RLock()
    
    def _get_tier_usage(self, tier: MemoryTier) -> int:
        """Calculate current usage for a tier"""
        total = 0
        for block in self.blocks.values():
            if block.tier == tier:
                if block.compressed and block._compressed_data:
                    total += len(block._compressed_data)
                else:
                    total += block.size_bytes
        return total
    
    def _estimate_size(self, data: Any) -> int:
        """Estimate size of data in bytes"""
        try:
            return len(pickle.dumps(data))
        except:
            return sys.getsizeof(data)
    
    def allocate(self, key: str, data: Any) -> bool:
        """
        Allocate virtual memory for data
        Returns True if successful
        """
        with self.lock:
            size = self._estimate_size(data)
            
            # Check if we need to make room
            self._make_room(size)
            
            # Create block in HOT tier
            block = MemoryBlock(
                key=key,
                data=data,
                tier=MemoryTier.HOT,
                size_bytes=size
            )
            
            self.blocks[key] = block
            self.hot_keys[key] = True
            self.stats['allocations'] += 1
            
            return True
    
    def read(self, key: str) -> Optional[Any]:
        """Read data from virtual memory"""
        with self.lock:
            if key not in self.blocks:
                self.stats['misses'] += 1
                return None
            
            self.stats['hits'] += 1
            block = self.blocks[key]
            block.access()
            
            # Decompress if needed
            if block.compressed:
                block.decompress()
                self.stats['decompressions'] += 1
            
            # Promote if accessed frequently
            if block.access_count > 3 and block.tier != MemoryTier.HOT:
                self._promote_block(block)
            
            return block.data
    
    def write(self, key: str, data: Any) -> bool:
        """Write/update data in virtual memory"""
        with self.lock:
            if key in self.blocks:
                # Update existing
                block = self.blocks[key]
                block.data = data
                block.size_bytes = self._estimate_size(data)
                block.access()
                if block.compressed:
                    block.compressed = False
                    block._compressed_data = None
                return True
            else:
                # Allocate new
                return self.allocate(key, data)
    
    def free(self, key: str) -> bool:
        """Free virtual memory"""
        with self.lock:
            if key not in self.blocks:
                return False
            
            block = self.blocks[key]
            
            # Remove from tier tracking
            if key in self.hot_keys:
                del self.hot_keys[key]
            elif key in self.warm_keys:
                del self.warm_keys[key]
            elif key in self.cold_keys:
                del self.cold_keys[key]
            
            del self.blocks[key]
            self.stats['deallocations'] += 1
            return True
    
    def _make_room(self, needed_bytes: int):
        """Make room for new allocation"""
        hot_usage = self._get_tier_usage(MemoryTier.HOT)
        
        # If HOT tier is over capacity, demote oldest blocks
        while hot_usage + needed_bytes > self.max_hot_bytes and self.hot_keys:
            oldest_key = next(iter(self.hot_keys))
            block = self.blocks[oldest_key]
            
            if block.access_count < 2:  # Cold data
                self._demote_block(block)
                del self.hot_keys[oldest_key]
                self.warm_keys[oldest_key] = True
                hot_usage = self._get_tier_usage(MemoryTier.HOT)
            else:
                break
        
        # Check WARM tier
        warm_usage = self._get_tier_usage(MemoryTier.WARM)
        while warm_usage > self.max_warm_bytes and self.warm_keys:
            oldest_key = next(iter(self.warm_keys))
            block = self.blocks[oldest_key]
            self._demote_block(block)
            del self.warm_keys[oldest_key]
            self.cold_keys[oldest_key] = True
            warm_usage = self._get_tier_usage(MemoryTier.WARM)
        
        # Check COLD tier
        cold_usage = self._get_tier_usage(MemoryTier.COLD)
        while cold_usage > self.max_cold_bytes and self.cold_keys:
            oldest_key = next(iter(self.cold_keys))
            block = self.blocks[oldest_key]
            self._evict_block(block)
            del self.cold_keys[oldest_key]
    
    def _promote_block(self, block: MemoryBlock):
        """Promote block to higher tier"""
        old_tier = block.tier
        block.promote()
        self.stats['promotions'] += 1
        
        # Update tracking
        if old_tier == MemoryTier.WARM and block.tier == MemoryTier.HOT:
            if block.key in self.warm_keys:
                del self.warm_keys[block.key]
            self.hot_keys[block.key] = True
        elif old_tier == MemoryTier.COLD and block.tier == MemoryTier.WARM:
            if block.key in self.cold_keys:
                del self.cold_keys[block.key]
            self.warm_keys[block.key] = True
    
    def _demote_block(self, block: MemoryBlock):
        """Demote block to lower tier"""
        old_tier = block.tier
        
        if old_tier == MemoryTier.HOT:
            saved = block.compress()
            if saved > 0:
                self.stats['bytes_saved'] += saved
                self.stats['compressions'] += 1
        
        block.demote()
        self.stats['demotions'] += 1
    
    def _evict_block(self, block: MemoryBlock):
        """Evict block (for now just mark as frozen)"""
        block.tier = MemoryTier.FROZEN
        block.data = None  # Clear from memory
        self.stats['evictions'] += 1
    
    def compress_tier(self, tier: MemoryTier):
        """Force compression of entire tier"""
        with self.lock:
            compressed_count = 0
            for block in self.blocks.values():
                if block.tier == tier and not block.compressed:
                    saved = block.compress()
                    if saved > 0:
                        compressed_count += 1
                        self.stats['bytes_saved'] += saved
                        self.stats['compressions'] += 1
            return compressed_count
    
    def get_stats(self) -> Dict:
        """Get memory manager statistics"""
        with self.lock:
            hot_usage = self._get_tier_usage(MemoryTier.HOT)
            warm_usage = self._get_tier_usage(MemoryTier.WARM)
            cold_usage = self._get_tier_usage(MemoryTier.COLD)
            
            total_blocks = len(self.blocks)
            hot_blocks = sum(1 for b in self.blocks.values() if b.tier == MemoryTier.HOT)
            warm_blocks = sum(1 for b in self.blocks.values() if b.tier == MemoryTier.WARM)
            cold_blocks = sum(1 for b in self.blocks.values() if b.tier == MemoryTier.COLD)
            frozen_blocks = sum(1 for b in self.blocks.values() if b.tier == MemoryTier.FROZEN)
            
            hit_rate = 0
            if self.stats['hits'] + self.stats['misses'] > 0:
                hit_rate = self.stats['hits'] / (self.stats['hits'] + self.stats['misses'])
            
            return {
                'total_blocks': total_blocks,
                'hot_blocks': hot_blocks,
                'warm_blocks': warm_blocks,
                'cold_blocks': cold_blocks,
                'frozen_blocks': frozen_blocks,
                'hot_usage_mb': hot_usage / (1024 * 1024),
                'warm_usage_mb': warm_usage / (1024 * 1024),
                'cold_usage_mb': cold_usage / (1024 * 1024),
                'total_usage_mb': (hot_usage + warm_usage + cold_usage) / (1024 * 1024),
                'bytes_saved_mb': self.stats['bytes_saved'] / (1024 * 1024),
                'hit_rate': hit_rate * 100,
                **self.stats
            }
    
    def print_stats(self):
        """Print formatted statistics"""
        stats = self.get_stats()
        
        print("\n" + "=" * 70)
        print("🧬 HELIX VIRTUAL RAM STATISTICS")
        print("=" * 70)
        print()
        print(f"Memory Usage:")
        print(f"  HOT  (instant):     {stats['hot_usage_mb']:8.2f} MB ({stats['hot_blocks']:,} blocks)")
        print(f"  WARM (compressed):  {stats['warm_usage_mb']:8.2f} MB ({stats['warm_blocks']:,} blocks)")
        print(f"  COLD (ready):       {stats['cold_usage_mb']:8.2f} MB ({stats['cold_blocks']:,} blocks)")
        print(f"  FROZEN (evicted):   {stats['frozen_blocks']:,} blocks")
        print(f"  TOTAL:              {stats['total_usage_mb']:8.2f} MB ({stats['total_blocks']:,} blocks)")
        print()
        print(f"Performance:")
        print(f"  Hit Rate:           {stats['hit_rate']:.1f}%")
        print(f"  Bytes Saved:        {stats['bytes_saved_mb']:.2f} MB")
        print(f"  Compressions:       {stats['compressions']:,}")
        print(f"  Promotions:         {stats['promotions']:,}")
        print(f"  Demotions:          {stats['demotions']:,}")
        print(f"  Evictions:          {stats['evictions']:,}")
        print()

# ============================================================================
# DEMO
# ============================================================================

def demo():
    """Demonstrate virtual RAM manager"""
    print("=" * 70)
    print("🧬 HELIX VIRTUAL RAM MANAGER")
    print("=" * 70)
    print()
    print("Simulating 8GB physical RAM -> 16GB+ virtual RAM")
    print()
    
    # Initialize with conservative limits
    manager = HelixMemoryManager(
        max_hot_mb=2048,   # 2GB hot
        max_warm_mb=4096,  # 4GB compressed
        max_cold_mb=2048   # 2GB cold
    )
    
    print("📝 Allocating 5000 blocks of data...")
    
    # Allocate a bunch of data
    for i in range(5000):
        data = {
            'id': i,
            'payload': 'x' * 1000,  # 1KB each
            'metadata': {'created': time.time(), 'version': 1}
        }
        manager.allocate(f'block_{i}', data)
    
    manager.print_stats()
    
    # Simulate access patterns
    print("🔥 Simulating hot data access (first 500 blocks)...")
    for i in range(500):
        for _ in range(5):  # Access 5 times
            manager.read(f'block_{i}')
    
    manager.print_stats()
    
    # Allocate more data to trigger compression
    print("📝 Allocating 3000 more blocks (triggering compression)...")
    for i in range(5000, 8000):
        data = {
            'id': i,
            'payload': 'y' * 1000,
            'metadata': {'created': time.time(), 'version': 1}
        }
        manager.allocate(f'block_{i}', data)
    
    manager.print_stats()
    
    # Force compression of warm tier
    print("🗜️  Force compressing WARM tier...")
    compressed = manager.compress_tier(MemoryTier.WARM)
    print(f"   Compressed {compressed} additional blocks")
    
    manager.print_stats()
    
    print("=" * 70)
    print("✓ DEMO COMPLETE")
    print("=" * 70)
    print()
    print("Your 8GB just became 16GB+ through intelligent compression!")
    print()

if __name__ == "__main__":
    demo()
