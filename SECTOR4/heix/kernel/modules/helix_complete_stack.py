"""
Helix Complete Memory Stack
Virtual RAM + Cache + Filesystem Integration
"""

import time
import hashlib
import pickle
import zlib
import os
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Optional, Dict, List
from enum import Enum
import threading


class MemoryTier(Enum):
    """Memory hierarchy"""
    L1_HOT = 0
    L2_WARM = 1
    L3_COMPRESSED = 2
    L4_COLD = 3
    L5_DISK = 4


@dataclass
class CacheBlock:
    """Unified cache/memory block"""
    key: str
    data: Any
    tier: MemoryTier
    size_bytes: int
    access_count: int = 0
    last_access: float = field(default_factory=time.time)
    compressed: bool = False
    dirty: bool = False
    pinned: bool = False
    _compressed_data: Optional[bytes] = None
    _hash: Optional[str] = None
    
    def __post_init__(self):
        if not self._hash:
            self._hash = hashlib.md5(str(self.key).encode()).hexdigest()[:16]
    
    def access(self):
        self.access_count += 1
        self.last_access = time.time()
    
    def compress(self) -> int:
        if not self.compressed and self.data is not None:
            try:
                serialized = pickle.dumps(self.data)
                self._compressed_data = zlib.compress(serialized, level=6)
                saved = self.size_bytes - len(self._compressed_data)
                self.compressed = True
                return max(0, saved)
            except:
                return 0
        return 0
    
    def decompress(self):
        if self.compressed and self._compressed_data:
            try:
                serialized = zlib.decompress(self._compressed_data)
                self.data = pickle.loads(serialized)
                self.compressed = False
                self._compressed_data = None
            except:
                pass


class HelixCache:
    """Multi-level cache with intelligent promotion/demotion"""
    
    def __init__(self, l1_size_mb: int = 128, l2_size_mb: int = 512, l3_size_mb: int = 1024):
        self.l1_max = l1_size_mb * 1024 * 1024
        self.l2_max = l2_size_mb * 1024 * 1024
        self.l3_max = l3_size_mb * 1024 * 1024
        
        self.l1_cache: OrderedDict[str, CacheBlock] = OrderedDict()
        self.l2_cache: OrderedDict[str, CacheBlock] = OrderedDict()
        self.l3_cache: OrderedDict[str, CacheBlock] = OrderedDict()
        
        self.stats = {
            'l1_hits': 0, 'l1_misses': 0,
            'l2_hits': 0, 'l2_misses': 0,
            'l3_hits': 0, 'l3_misses': 0,
            'promotions': 0, 'demotions': 0,
            'evictions': 0, 'compressions': 0
        }
        
        self.lock = threading.RLock()
    
    def get(self, key: str) -> Optional[Any]:
        with self.lock:
            # Check L1
            if key in self.l1_cache:
                self.stats['l1_hits'] += 1
                block = self.l1_cache[key]
                block.access()
                self.l1_cache.move_to_end(key)
                return block.data
            
            self.stats['l1_misses'] += 1
            
            # Check L2
            if key in self.l2_cache:
                self.stats['l2_hits'] += 1
                block = self.l2_cache[key]
                block.access()
                if block.access_count > 3:
                    self._promote_to_l1(key, block)
                else:
                    self.l2_cache.move_to_end(key)
                return block.data
            
            self.stats['l2_misses'] += 1
            
            # Check L3
            if key in self.l3_cache:
                self.stats['l3_hits'] += 1
                block = self.l3_cache[key]
                block.access()
                if block.compressed:
                    block.decompress()
                if block.access_count > 2:
                    self._promote_to_l2(key, block)
                else:
                    self.l3_cache.move_to_end(key)
                return block.data
            
            self.stats['l3_misses'] += 1
            return None
    
    def put(self, key: str, data: Any, size: int, pinned: bool = False):
        with self.lock:
            self.l2_cache.pop(key, None)
            self.l3_cache.pop(key, None)
            
            block = CacheBlock(
                key=key,
                data=data,
                tier=MemoryTier.L1_HOT,
                size_bytes=size,
                pinned=pinned
            )
            
            self._make_room_l1(size)
            self.l1_cache[key] = block
    
    def _get_tier_size(self, tier_dict: OrderedDict) -> int:
        total = 0
        for block in tier_dict.values():
            if block.compressed and block._compressed_data:
                total += len(block._compressed_data)
            else:
                total += block.size_bytes
        return total
    
    def _make_room_l1(self, needed: int):
        current_size = self._get_tier_size(self.l1_cache)
        while current_size + needed > self.l1_max and self.l1_cache:
            key, block = next(iter(self.l1_cache.items()))
            if block.pinned:
                self.l1_cache.move_to_end(key)
                continue
            self._demote_to_l2(key, block)
            current_size = self._get_tier_size(self.l1_cache)
    
    def _make_room_l2(self, needed: int):
        current_size = self._get_tier_size(self.l2_cache)
        while current_size + needed > self.l2_max and self.l2_cache:
            key, block = next(iter(self.l2_cache.items()))
            if block.pinned:
                self.l2_cache.move_to_end(key)
                continue
            self._demote_to_l3(key, block)
            current_size = self._get_tier_size(self.l2_cache)
    
    def _make_room_l3(self, needed: int):
        current_size = self._get_tier_size(self.l3_cache)
        while current_size + needed > self.l3_max and self.l3_cache:
            key, block = next(iter(self.l3_cache.items()))
            if block.pinned:
                self.l3_cache.move_to_end(key)
                continue
            del self.l3_cache[key]
            self.stats['evictions'] += 1
            current_size = self._get_tier_size(self.l3_cache)
    
    def _promote_to_l1(self, key: str, block: CacheBlock):
        self.l2_cache.pop(key, None)
        self._make_room_l1(block.size_bytes)
        block.tier = MemoryTier.L1_HOT
        self.l1_cache[key] = block
        self.stats['promotions'] += 1
    
    def _promote_to_l2(self, key: str, block: CacheBlock):
        self.l3_cache.pop(key, None)
        self._make_room_l2(block.size_bytes)
        block.tier = MemoryTier.L2_WARM
        self.l2_cache[key] = block
        self.stats['promotions'] += 1
    
    def _demote_to_l2(self, key: str, block: CacheBlock):
        self.l1_cache.pop(key, None)
        self._make_room_l2(block.size_bytes)
        block.tier = MemoryTier.L2_WARM
        self.l2_cache[key] = block
        self.stats['demotions'] += 1
    
    def _demote_to_l3(self, key: str, block: CacheBlock):
        self.l2_cache.pop(key, None)
        saved = block.compress()
        if saved > 0:
            self.stats['compressions'] += 1
        size = len(block._compressed_data) if block._compressed_data else block.size_bytes
        self._make_room_l3(size)
        block.tier = MemoryTier.L3_COMPRESSED
        self.l3_cache[key] = block
        self.stats['demotions'] += 1
    
    def get_stats(self) -> Dict:
        with self.lock:
            return {
                'l1_size_mb': self._get_tier_size(self.l1_cache) / (1024 * 1024),
                'l2_size_mb': self._get_tier_size(self.l2_cache) / (1024 * 1024),
                'l3_size_mb': self._get_tier_size(self.l3_cache) / (1024 * 1024),
                'l1_items': len(self.l1_cache),
                'l2_items': len(self.l2_cache),
                'l3_items': len(self.l3_cache),
                **self.stats
            }


class HelixMemoryManager:
    """Virtual RAM manager integrated with cache"""
    
    def __init__(self, cache: HelixCache = None, max_virtual_mb: int = 4096):
        self.cache = cache or HelixCache()
        self.max_virtual_bytes = max_virtual_mb * 1024 * 1024
        
        self.allocations: Dict[str, int] = {}
        self.total_allocated = 0
        
        self.stats = {
            'total_allocations': 0,
            'total_deallocations': 0,
            'peak_usage': 0
        }
        
        self.lock = threading.RLock()
    
    def malloc(self, key: str, data: Any) -> bool:
        with self.lock:
            size = len(pickle.dumps(data)) if data else 0
            
            if self.total_allocated + size > self.max_virtual_bytes:
                return False
            
            self.cache.put(key, data, size)
            self.allocations[key] = size
            self.total_allocated += size
            
            self.stats['total_allocations'] += 1
            self.stats['peak_usage'] = max(self.stats['peak_usage'], self.total_allocated)
            
            return True
    
    def free(self, key: str) -> bool:
        with self.lock:
            if key not in self.allocations:
                return False
            
            size = self.allocations.pop(key)
            self.total_allocated -= size
            self.stats['total_deallocations'] += 1
            
            return True
    
    def read(self, key: str) -> Optional[Any]:
        return self.cache.get(key)
    
    def write(self, key: str, data: Any) -> bool:
        with self.lock:
            if key in self.allocations:
                old_size = self.allocations[key]
                new_size = len(pickle.dumps(data)) if data else 0
                
                self.total_allocated = self.total_allocated - old_size + new_size
                self.allocations[key] = new_size
                self.cache.put(key, data, new_size)
                return True
            return False
    
    def get_stats(self) -> Dict:
        with self.lock:
            return {
                'allocated_mb': self.total_allocated / (1024 * 1024),
                'allocation_count': len(self.allocations),
                'cache': self.cache.get_stats(),
                **self.stats
            }
    
    def health_check(self) -> bool:
        return True


class HelixFS:
    """Filesystem cache layer"""
    
    def __init__(self, memory: HelixMemoryManager = None):
        self.memory = memory or HelixMemoryManager()
        self.file_cache: Dict[str, str] = {}
        self.file_metadata: Dict[str, Dict] = {}
        
        self.stats = {
            'file_reads': 0,
            'file_writes': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'disk_reads': 0,
            'disk_writes': 0
        }
        
        self.lock = threading.RLock()
    
    def read_file(self, filepath: str) -> Optional[bytes]:
        with self.lock:
            self.stats['file_reads'] += 1
            cache_key = f"file:{filepath}"
            
            cached = self.memory.read(cache_key)
            if cached is not None:
                self.stats['cache_hits'] += 1
                return cached
            
            self.stats['cache_misses'] += 1
            
            if not os.path.exists(filepath):
                return None
            
            try:
                with open(filepath, 'rb') as f:
                    data = f.read()
                
                self.stats['disk_reads'] += 1
                self.memory.malloc(cache_key, data)
                self.file_cache[filepath] = cache_key
                self.file_metadata[filepath] = {
                    'size': len(data),
                    'mtime': os.path.getmtime(filepath),
                    'cached_at': time.time()
                }
                
                return data
            except:
                return None
    
    def write_file(self, filepath: str, data: bytes, write_through: bool = True):
        with self.lock:
            self.stats['file_writes'] += 1
            cache_key = f"file:{filepath}"
            
            self.memory.malloc(cache_key, data)
            self.file_cache[filepath] = cache_key
            
            if write_through:
                try:
                    os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
                    with open(filepath, 'wb') as f:
                        f.write(data)
                    self.stats['disk_writes'] += 1
                except:
                    pass
            
            self.file_metadata[filepath] = {
                'size': len(data),
                'mtime': time.time(),
                'cached_at': time.time()
            }
    
    def get_stats(self) -> Dict:
        return {
            'cached_files': len(self.file_cache),
            **self.stats
        }
    
    def health_check(self) -> bool:
        return True


class HelixCompleteStack:
    """Complete Helix memory stack"""
    
    def __init__(self, l1_cache_mb: int = 128, l2_cache_mb: int = 512, l3_cache_mb: int = 1024, virtual_ram_mb: int = 4096):
        self.cache = HelixCache(l1_cache_mb, l2_cache_mb, l3_cache_mb)
        self.memory = HelixMemoryManager(self.cache, virtual_ram_mb)
        self.fs = HelixFS(self.memory)
        self.start_time = time.time()
    
    def get_stats(self) -> Dict:
        uptime = time.time() - self.start_time
        return {
            'uptime': uptime,
            'cache': self.cache.get_stats(),
            'memory': self.memory.get_stats(),
            'filesystem': self.fs.get_stats()
        }
    
    def health_check(self) -> bool:
        return True


if __name__ == "__main__":
    print("Testing Helix Complete Stack...")
    
    stack = HelixCompleteStack(l1_cache_mb=64, l2_cache_mb=256, l3_cache_mb=512, virtual_ram_mb=2048)
    
    # Test memory
    for i in range(100):
        data = {'id': i, 'payload': 'x' * 500}
        stack.memory.malloc(f'block_{i}', data)
    
    print(f"Stats: {stack.get_stats()}")
