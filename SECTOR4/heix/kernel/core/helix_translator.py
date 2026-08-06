"""
Helix Translator Layer
Mini version that translates between app requests and Helix storage

INGRESS: App request → Helix language
EGRESS:  Helix data → App format
"""

import time
from typing import Any, Optional, Dict
from dataclasses import dataclass

@dataclass
class TranslationEntry:
    """Maps app pointer to Helix key"""
    app_pointer: int
    helix_key: str
    size: int
    created_at: float
    last_access: float
    access_count: int = 0
    
    def access(self):
        """Record an access"""
        self.last_access = time.time()
        self.access_count += 1


class HelixTranslator:
    """
    Lightweight translator between app world and Helix world
    """
    
    def __init__(self, helix_backend=None):
        self.helix = helix_backend
        
        # Translation tables
        self.ptr_to_key: Dict[int, TranslationEntry] = {}
        self.key_to_ptr: Dict[str, int] = {}
        
        # Pointer allocation
        self.next_fake_pointer = 0x10000000
        
        # File descriptor translation
        self.fd_to_path: Dict[int, str] = {}
        self.path_to_fd: Dict[str, int] = {}
        self.next_fake_fd = 1000
        
        # Internal storage (for standalone mode)
        self._memory_store: Dict[str, bytes] = {}
        self._file_store: Dict[str, bytes] = {}
        
        # Stats
        self.stats = {
            'ingress_calls': 0,
            'egress_calls': 0,
            'translations': 0,
            'malloc_intercepts': 0,
            'free_intercepts': 0,
            'read_intercepts': 0,
            'write_intercepts': 0,
        }
    
    def translate_malloc(self, size: int) -> int:
        """INGRESS: App calls malloc(size), EGRESS: Return fake pointer"""
        self.stats['ingress_calls'] += 1
        self.stats['malloc_intercepts'] += 1
        
        helix_key = f"mem_{self.next_fake_pointer:016x}_{size}"
        data = bytearray(size)
        
        # Store in internal or helix backend
        if self.helix and hasattr(self.helix, 'memory'):
            self.helix.memory.malloc(helix_key, bytes(data))
        else:
            self._memory_store[helix_key] = bytes(data)
        
        fake_ptr = self.next_fake_pointer
        self.next_fake_pointer += 0x1000
        
        entry = TranslationEntry(
            app_pointer=fake_ptr,
            helix_key=helix_key,
            size=size,
            created_at=time.time(),
            last_access=time.time()
        )
        
        self.ptr_to_key[fake_ptr] = entry
        self.key_to_ptr[helix_key] = fake_ptr
        
        self.stats['egress_calls'] += 1
        self.stats['translations'] += 1
        
        return fake_ptr
    
    def translate_free(self, pointer: int) -> bool:
        """INGRESS: App calls free(pointer)"""
        self.stats['ingress_calls'] += 1
        self.stats['free_intercepts'] += 1
        
        if pointer not in self.ptr_to_key:
            return False
        
        entry = self.ptr_to_key[pointer]
        helix_key = entry.helix_key
        
        if self.helix and hasattr(self.helix, 'memory'):
            self.helix.memory.free(helix_key)
        else:
            self._memory_store.pop(helix_key, None)
        
        del self.ptr_to_key[pointer]
        del self.key_to_ptr[helix_key]
        
        self.stats['egress_calls'] += 1
        return True
    
    def translate_read(self, pointer: int, size: int, offset: int = 0) -> Optional[bytes]:
        """INGRESS: App reads from pointer"""
        self.stats['ingress_calls'] += 1
        self.stats['read_intercepts'] += 1
        
        if pointer not in self.ptr_to_key:
            return None
        
        entry = self.ptr_to_key[pointer]
        entry.access()
        
        if self.helix and hasattr(self.helix, 'memory'):
            data = self.helix.memory.read(entry.helix_key)
        else:
            data = self._memory_store.get(entry.helix_key)
        
        if data is None:
            return None
        
        self.stats['egress_calls'] += 1
        return data[offset:offset + size]
    
    def translate_write(self, pointer: int, data: bytes, offset: int = 0) -> bool:
        """INGRESS: App writes to pointer"""
        self.stats['ingress_calls'] += 1
        self.stats['write_intercepts'] += 1
        
        if pointer not in self.ptr_to_key:
            return False
        
        entry = self.ptr_to_key[pointer]
        entry.access()
        
        if self.helix and hasattr(self.helix, 'memory'):
            existing = self.helix.memory.read(entry.helix_key) or bytearray(entry.size)
            if isinstance(existing, bytes):
                existing = bytearray(existing)
            existing[offset:offset + len(data)] = data
            self.helix.memory.write(entry.helix_key, bytes(existing))
        else:
            existing = bytearray(self._memory_store.get(entry.helix_key, bytearray(entry.size)))
            existing[offset:offset + len(data)] = data
            self._memory_store[entry.helix_key] = bytes(existing)
        
        self.stats['egress_calls'] += 1
        return True
    
    def translate_open(self, filepath: str, mode: str = "r") -> int:
        """INGRESS: App opens file"""
        self.stats['ingress_calls'] += 1
        
        if filepath in self.path_to_fd:
            return self.path_to_fd[filepath]
        
        fake_fd = self.next_fake_fd
        self.next_fake_fd += 1
        
        self.fd_to_path[fake_fd] = filepath
        self.path_to_fd[filepath] = fake_fd
        
        self.stats['egress_calls'] += 1
        self.stats['translations'] += 1
        
        return fake_fd
    
    def translate_close(self, fd: int) -> bool:
        """INGRESS: App closes file"""
        self.stats['ingress_calls'] += 1
        
        if fd not in self.fd_to_path:
            return False
        
        filepath = self.fd_to_path[fd]
        del self.fd_to_path[fd]
        del self.path_to_fd[filepath]
        
        self.stats['egress_calls'] += 1
        return True
    
    def translate_read_file(self, fd: int, size: int) -> Optional[bytes]:
        """INGRESS: App reads from file"""
        self.stats['ingress_calls'] += 1
        self.stats['read_intercepts'] += 1
        
        if fd not in self.fd_to_path:
            return None
        
        filepath = self.fd_to_path[fd]
        
        if self.helix and hasattr(self.helix, 'fs'):
            data = self.helix.fs.read_file(filepath)
        else:
            data = self._file_store.get(filepath)
        
        self.stats['egress_calls'] += 1
        return data[:size] if data else None
    
    def translate_write_file(self, fd: int, data: bytes) -> bool:
        """INGRESS: App writes to file"""
        self.stats['ingress_calls'] += 1
        self.stats['write_intercepts'] += 1
        
        if fd not in self.fd_to_path:
            return False
        
        filepath = self.fd_to_path[fd]
        
        if self.helix and hasattr(self.helix, 'fs'):
            self.helix.fs.write_file(filepath, data)
        else:
            self._file_store[filepath] = data
        
        self.stats['egress_calls'] += 1
        return True
    
    def get_stats(self) -> Dict:
        """Get translator statistics"""
        return {
            'active_translations': len(self.ptr_to_key),
            'active_file_descriptors': len(self.fd_to_path),
            **self.stats
        }
    
    def health_check(self) -> bool:
        """Check if translator is healthy"""
        return True


if __name__ == "__main__":
    translator = HelixTranslator()
    
    print("Testing Helix Translator...")
    
    # Test malloc
    ptr = translator.translate_malloc(1024)
    print(f"✓ malloc(1024) -> {hex(ptr)}")
    
    # Test write
    success = translator.translate_write(ptr, b"Hello World!")
    print(f"✓ write -> {success}")
    
    # Test read
    data = translator.translate_read(ptr, 12)
    print(f"✓ read -> {data}")
    
    # Test free
    success = translator.translate_free(ptr)
    print(f"✓ free -> {success}")
    
    print(f"\nStats: {translator.get_stats()}")
