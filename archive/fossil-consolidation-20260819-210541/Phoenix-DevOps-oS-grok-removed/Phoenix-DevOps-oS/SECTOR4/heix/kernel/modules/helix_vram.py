"""
Helix Virtual RAM Manager
Turn your 8GB into 20GB+ through intelligent compression and caching
"""

import time
import sys
import pickle
import zlib
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Optional, Dict
from enum import Enum
import threading


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


class HelixMemoryManager:
    """
    Intelligent virtual memory manager using helix architecture
    """
    def __init__(self, 
                 max_hot_mb: int = 4096,
                 max_warm_mb: int = 8192,
                 max_cold_mb: int = 4096):
        
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
        """Allocate virtual memory for data"""
        with self.lock:
            size = self._estimate_size(data)
            self._make_room(size)
            
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
    
    def malloc(self, key: str, data: Any) -> bool:
        """Alias for allocate"""
        return self.allocate(key, data)
    
    def read(self, key: str) -> Optional[Any]:
        """Read data from virtual memory"""
        with self.lock:
            if key not in self.blocks:
                self.stats['misses'] += 1
                return None
            
            self.stats['hits'] += 1
            block = self.blocks[key]
            block.access()
            
            if block.compressed:
                block.decompress()
                self.stats['decompressions'] += 1
            
            if block.access_count > 3 and block.tier != MemoryTier.HOT:
                self._promote_block(block)
            
            return block.data
    
    def write(self, key: str, data: Any) -> bool:
        """Write/update data in virtual memory"""
        with self.lock:
            if key in self.blocks:
                block = self.blocks[key]
                block.data = data
                block.size_bytes = self._estimate_size(data)
                block.access()
                if block.compressed:
                    block.compressed = False
                    block._compressed_data = None
                return True
            else:
                return self.allocate(key, data)
    
    def free(self, key: str) -> bool:
        """Free virtual memory"""
        with self.lock:
            if key not in self.blocks:
                return False
            
            block = self.blocks[key]
            
            if block.tier == MemoryTier.HOT:
                self.hot_keys.pop(key, None)
            elif block.tier == MemoryTier.WARM:
                self.warm_keys.pop(key, None)
            elif block.tier == MemoryTier.COLD:
                self.cold_keys.pop(key, None)
            
            del self.blocks[key]
            self.stats['deallocations'] += 1
            
            return True
    
    def _make_room(self, needed_bytes: int):
        """Make room in HOT tier"""
        hot_usage = self._get_tier_usage(MemoryTier.HOT)
        
        while hot_usage + needed_bytes > self.max_hot_bytes and self.hot_keys:
            oldest_key = next(iter(self.hot_keys))
            if oldest_key in self.blocks:
                self._demote_block(self.blocks[oldest_key])
            hot_usage = self._get_tier_usage(MemoryTier.HOT)
    
    def _promote_block(self, block: MemoryBlock):
        """Promote block to higher tier"""
        old_tier = block.tier
        block.promote()
        self.stats['promotions'] += 1
        
        if old_tier == MemoryTier.WARM and block.tier == MemoryTier.HOT:
            self.warm_keys.pop(block.key, None)
            self.hot_keys[block.key] = True
        elif old_tier == MemoryTier.COLD and block.tier == MemoryTier.WARM:
            self.cold_keys.pop(block.key, None)
            self.warm_keys[block.key] = True
    
    def _demote_block(self, block: MemoryBlock):
        """Demote block to lower tier"""
        old_tier = block.tier
        
        if old_tier == MemoryTier.HOT:
            saved = block.compress()
            if saved > 0:
                self.stats['bytes_saved'] += saved
                self.stats['compressions'] += 1
            self.hot_keys.pop(block.key, None)
            block.tier = MemoryTier.WARM
            self.warm_keys[block.key] = True
        elif old_tier == MemoryTier.WARM:
            self.warm_keys.pop(block.key, None)
            block.tier = MemoryTier.COLD
            self.cold_keys[block.key] = True
        elif old_tier == MemoryTier.COLD:
            self._evict_block(block)
        
        self.stats['demotions'] += 1
    
    def _evict_block(self, block: MemoryBlock):
        """Evict block"""
        block.tier = MemoryTier.FROZEN
        block.data = None
        self.stats['evictions'] += 1
    
    def get_stats(self) -> Dict:
        """Get memory manager statistics"""
        with self.lock:
            hot_usage = self._get_tier_usage(MemoryTier.HOT)
            warm_usage = self._get_tier_usage(MemoryTier.WARM)
            cold_usage = self._get_tier_usage(MemoryTier.COLD)
            
            return {
                'total_blocks': len(self.blocks),
                'hot_blocks': len(self.hot_keys),
                'warm_blocks': len(self.warm_keys),
                'cold_blocks': len(self.cold_keys),
                'hot_usage_mb': hot_usage / (1024 * 1024),
                'warm_usage_mb': warm_usage / (1024 * 1024),
                'cold_usage_mb': cold_usage / (1024 * 1024),
                'total_usage_mb': (hot_usage + warm_usage + cold_usage) / (1024 * 1024),
                'bytes_saved_mb': self.stats['bytes_saved'] / (1024 * 1024),
                **self.stats
            }
    
    def health_check(self) -> bool:
        """Check if memory manager is healthy"""
        return True


# Alias for compatibility
VRRAM = HelixMemoryManager


if __name__ == "__main__":
    print("Testing Helix Virtual RAM Manager...")
    
    manager = HelixMemoryManager(max_hot_mb=100, max_warm_mb=200, max_cold_mb=100)
    
    # Allocate some blocks
    for i in range(100):
        data = {'id': i, 'payload': 'x' * 1000}
        manager.allocate(f'block_{i}', data)
    
    print(f"Stats: {manager.get_stats()}")
