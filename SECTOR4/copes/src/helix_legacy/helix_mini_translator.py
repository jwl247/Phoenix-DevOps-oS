"""
Helix Translator Layer
Mini version that translates between app requests and Helix storage

INGRESS: App request → Helix language
EGRESS:  Helix data → App format

Think of it like a bilingual interpreter sitting between two people
who don't speak the same language.
"""

import time
import ctypes
import struct
from typing import Any, Optional, Dict, Tuple
from dataclasses import dataclass
from collections import defaultdict

# ============================================================================
# TRANSLATOR DATA STRUCTURES
# ============================================================================

@dataclass
class TranslationEntry:
    """Maps app pointer to Helix key"""
    app_pointer: int          # What app thinks is the address
    helix_key: str            # Where data actually lives in Helix
    size: int                 # How big is the allocation
    created_at: float         # When was it allocated
    last_access: float        # When was it last touched
    access_count: int = 0     # How many times accessed
    
    def access(self):
        """Record an access"""
        self.last_access = time.time()
        self.access_count += 1

# ============================================================================
# HELIX TRANSLATOR
# ============================================================================

class HelixTranslator:
    """
    Lightweight translator between app world and Helix world
    
    App World:         Helix World:
    - Pointers         → Keys
    - Raw bytes        → Cached blocks
    - File paths       → Cache entries
    - malloc/free      → allocate/deallocate
    
    This is the HANDSHAKE layer.
    """
    
    def __init__(self, helix_backend):
        """
        helix_backend: The actual HelixSystem instance
        """
        self.helix = helix_backend
        
        # Translation tables (the handshake maps)
        self.ptr_to_key: Dict[int, TranslationEntry] = {}
        self.key_to_ptr: Dict[str, int] = {}
        
        # Pointer allocation (we hand out fake pointers)
        self.next_fake_pointer = 0x10000000  # Start at safe high address
        
        # File descriptor translation
        self.fd_to_path: Dict[int, str] = {}
        self.path_to_fd: Dict[str, int] = {}
        self.next_fake_fd = 1000
        
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
    
    # ========================================================================
    # MEMORY TRANSLATION (malloc/free)
    # ========================================================================
    
    def translate_malloc(self, size: int) -> int:
        """
        INGRESS: App calls malloc(size)
        EGRESS:  Return fake pointer
        
        Translation:
        1. Generate Helix key
        2. Allocate in Helix backend
        3. Create fake pointer
        4. Map pointer → key
        5. Return pointer to app
        """
        self.stats['ingress_calls'] += 1
        self.stats['malloc_intercepts'] += 1
        
        # Step 1: Generate unique Helix key
        helix_key = f"mem_{self.next_fake_pointer:016x}_{size}"
        
        # Step 2: Allocate in Helix
        # (App data starts as empty, filled later with writes)
        data = bytearray(size)  # Initialize with zeros
        success = self.helix.memory.malloc(helix_key, bytes(data))
        
        if not success:
            return 0  # NULL pointer (allocation failed)
        
        # Step 3: Generate fake pointer for app
        fake_ptr = self.next_fake_pointer
        self.next_fake_pointer += 0x1000  # Increment by page size
        
        # Step 4: Create translation entry
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
        
        # Step 5: Return fake pointer
        return fake_ptr
    
    def translate_free(self, pointer: int) -> bool:
        """
        INGRESS: App calls free(pointer)
        EGRESS:  Memory released
        
        Translation:
        1. Look up pointer → key
        2. Free from Helix
        3. Remove translation
        """
        self.stats['ingress_calls'] += 1
        self.stats['free_intercepts'] += 1
        
        if pointer not in self.ptr_to_key:
            return False  # Invalid pointer
        
        # Step 1: Translate pointer to key
        entry = self.ptr_to_key[pointer]
        helix_key = entry.helix_key
        
        # Step 2: Free from Helix
        self.helix.memory.free(helix_key)
        
        # Step 3: Remove translation
        del self.ptr_to_key[pointer]
        del self.key_to_ptr[helix_key]
        
        self.stats['egress_calls'] += 1
        
        return True
    
    def translate_read(self, pointer: int, size: int, offset: int = 0) -> Optional[bytes]:
        """
        INGRESS: App reads from pointer
        EGRESS:  Return data from Helix
        
        Translation:
        1. Translate pointer → key
        2. Read from Helix cache
        3. Return data to app
        """
        self.stats['ingress_calls'] += 1
        self.stats['read_intercepts'] += 1
        
        if pointer not in self.ptr_to_key:
            return None  # Invalid pointer
        
        # Step 1: Translate
        entry = self.ptr_to_key[pointer]
        entry.access()
        
        # Step 2: Read from Helix
        data = self.helix.memory.read(entry.helix_key)
        
        if data is None:
            return None
        
        # Step 3: Return requested slice
        self.stats['egress_calls'] += 1
        
        if isinstance(data, bytes):
            return data[offset:offset+size]
        else:
            # Data might be in different format, convert
            return bytes(data)[offset:offset+size]
    
    def translate_write(self, pointer: int, data: bytes, offset: int = 0) -> bool:
        """
        INGRESS: App writes to pointer
        EGRESS:  Data stored in Helix
        
        Translation:
        1. Translate pointer → key
        2. Read existing data from Helix
        3. Modify at offset
        4. Write back to Helix
        """
        self.stats['ingress_calls'] += 1
        self.stats['write_intercepts'] += 1
        
        if pointer not in self.ptr_to_key:
            return False  # Invalid pointer
        
        # Step 1: Translate
        entry = self.ptr_to_key[pointer]
        entry.access()
        
        # Step 2: Read existing data
        existing = self.helix.memory.read(entry.helix_key)
        
        if existing is None:
            # First write, create buffer
            buffer = bytearray(entry.size)
        else:
            buffer = bytearray(existing)
        
        # Step 3: Modify at offset
        end = offset + len(data)
        buffer[offset:end] = data
        
        # Step 4: Write back
        success = self.helix.memory.write(entry.helix_key, bytes(buffer))
        
        self.stats['egress_calls'] += 1
        
        return success
    
    # ========================================================================
    # FILE TRANSLATION (open/read/write/close)
    # ========================================================================
    
    def translate_open(self, filepath: str, mode: str = 'r') -> int:
        """
        INGRESS: App opens file
        EGRESS:  Return fake file descriptor
        
        Translation:
        1. Generate fake FD
        2. Check if file in Helix cache
        3. If not, read from disk into cache
        4. Map FD → filepath
        5. Return FD
        """
        self.stats['ingress_calls'] += 1
        
        # Step 1: Generate fake FD
        fake_fd = self.next_fake_fd
        self.next_fake_fd += 1
        
        # Step 2-3: Helix FS handles caching
        # (Happens automatically when we read)
        
        # Step 4: Map FD → path
        self.fd_to_path[fake_fd] = filepath
        self.path_to_fd[filepath] = fake_fd
        
        self.stats['egress_calls'] += 1
        
        return fake_fd
    
    def translate_read_file(self, fd: int, size: int) -> Optional[bytes]:
        """
        INGRESS: App reads from file
        EGRESS:  Return data from Helix cache
        
        Translation:
        1. Translate FD → filepath
        2. Read from Helix FS cache
        3. Return data
        """
        self.stats['ingress_calls'] += 1
        
        if fd not in self.fd_to_path:
            return None
        
        # Step 1: Translate FD
        filepath = self.fd_to_path[fd]
        
        # Step 2: Read from Helix FS
        data = self.helix.fs.read_file(filepath)
        
        self.stats['egress_calls'] += 1
        
        # Step 3: Return requested size
        if data:
            return data[:size]
        return None
    
    def translate_write_file(self, fd: int, data: bytes) -> bool:
        """
        INGRESS: App writes to file
        EGRESS:  Data cached in Helix
        
        Translation:
        1. Translate FD → filepath
        2. Write to Helix FS cache
        """
        self.stats['ingress_calls'] += 1
        
        if fd not in self.fd_to_path:
            return False
        
        # Step 1: Translate FD
        filepath = self.fd_to_path[fd]
        
        # Step 2: Write to Helix FS
        self.helix.fs.write_file(filepath, data)
        
        self.stats['egress_calls'] += 1
        
        return True
    
    def translate_close(self, fd: int) -> bool:
        """
        INGRESS: App closes file
        EGRESS:  Clean up translation
        
        Translation:
        1. Translate FD → filepath
        2. Remove mapping
        """
        self.stats['ingress_calls'] += 1
        
        if fd not in self.fd_to_path:
            return False
        
        filepath = self.fd_to_path[fd]
        
        del self.fd_to_path[fd]
        del self.path_to_fd[filepath]
        
        self.stats['egress_calls'] += 1
        
        return True
    
    # ========================================================================
    # INSPECTION & DEBUGGING
    # ========================================================================
    
    def inspect_pointer(self, pointer: int) -> Optional[Dict]:
        """See what Helix key a pointer maps to"""
        if pointer not in self.ptr_to_key:
            return None
        
        entry = self.ptr_to_key[pointer]
        return {
            'app_pointer': hex(entry.app_pointer),
            'helix_key': entry.helix_key,
            'size': entry.size,
            'age': time.time() - entry.created_at,
            'last_access': time.time() - entry.last_access,
            'access_count': entry.access_count
        }
    
    def get_stats(self) -> Dict:
        """Get translator statistics"""
        return {
            'active_translations': len(self.ptr_to_key),
            'active_file_descriptors': len(self.fd_to_path),
            **self.stats
        }
    
    def print_stats(self):
        """Print translation statistics"""
        stats = self.get_stats()
        
        print("\n" + "=" * 70)
        print("🔄 HELIX TRANSLATOR STATISTICS")
        print("=" * 70)
        print()
        print(f"Active Translations:    {stats['active_translations']:,}")
        print(f"Active File Handles:    {stats['active_file_descriptors']:,}")
        print()
        print(f"Total Ingress Calls:    {stats['ingress_calls']:,}")
        print(f"Total Egress Calls:     {stats['egress_calls']:,}")
        print(f"Total Translations:     {stats['translations']:,}")
        print()
        print(f"malloc() intercepts:    {stats['malloc_intercepts']:,}")
        print(f"free() intercepts:      {stats['free_intercepts']:,}")
        print(f"read() intercepts:      {stats['read_intercepts']:,}")
        print(f"write() intercepts:     {stats['write_intercepts']:,}")
        print()

# ============================================================================
# DEMO
# ============================================================================

def demo():
    """Demonstrate the translator layer"""
    print("=" * 70)
    print("🔄 HELIX TRANSLATOR LAYER DEMO")
    print("=" * 70)
    print()
    print("This mini translator sits between apps and Helix")
    print("INGRESS: App request → Helix storage")
    print("EGRESS:  Helix data → App format")
    print()
    
    # Import the Helix backend (from previous artifact)
    # For this demo, we'll use a mock
    class MockHelix:
        def __init__(self):
            self.memory_store = {}
            self.file_store = {}
            
            class MockMemory:
                def __init__(self, store):
                    self.store = store
                
                def malloc(self, key, data):
                    self.store[key] = data
                    return True
                
                def free(self, key):
                    self.store.pop(key, None)
                    return True
                
                def read(self, key):
                    return self.store.get(key)
                
                def write(self, key, data):
                    self.store[key] = data
                    return True
            
            class MockFS:
                def __init__(self, store):
                    self.store = store
                
                def read_file(self, path):
                    return self.store.get(path)
                
                def write_file(self, path, data):
                    self.store[path] = data
            
            self.memory = MockMemory(self.memory_store)
            self.fs = MockFS(self.file_store)
    
    # Initialize
    helix = MockHelix()
    translator = HelixTranslator(helix)
    
    print("TEST 1: Memory Translation (malloc/write/read/free)")
    print("-" * 70)
    
    # App thinks it's calling malloc
    ptr1 = translator.translate_malloc(1024)
    print(f"✓ malloc(1024) → pointer {hex(ptr1)}")
    
    # App writes data
    data = b"Hello from the app!"
    success = translator.translate_write(ptr1, data)
    print(f"✓ write({hex(ptr1)}, data) → {success}")
    
    # App reads data back
    read_data = translator.translate_read(ptr1, len(data))
    print(f"✓ read({hex(ptr1)}, {len(data)}) → {read_data}")
    
    # Inspect what's happening behind the scenes
    info = translator.inspect_pointer(ptr1)
    print(f"\n  Behind the scenes:")
    print(f"  App pointer:  {info['app_pointer']}")
    print(f"  Helix key:    {info['helix_key']}")
    print(f"  Access count: {info['access_count']}")
    
    # App frees memory
    success = translator.translate_free(ptr1)
    print(f"\n✓ free({hex(ptr1)}) → {success}")
    print()
    
    print("TEST 2: File Translation (open/write/read/close)")
    print("-" * 70)
    
    # App opens file
    fd = translator.translate_open("/tmp/test.txt", "w")
    print(f"✓ open('/tmp/test.txt') → fd {fd}")
    
    # App writes to file
    file_data = b"File contents from app"
    success = translator.translate_write_file(fd, file_data)
    print(f"✓ write(fd {fd}, data) → {success}")
    
    # App reads from file
    read_data = translator.translate_read_file(fd, 100)
    print(f"✓ read(fd {fd}, 100) → {read_data}")
    
    # App closes file
    success = translator.translate_close(fd)
    print(f"✓ close(fd {fd}) → {success}")
    print()
    
    print("TEST 3: Multiple Allocations (stress test)")
    print("-" * 70)
    
    pointers = []
    for i in range(100):
        ptr = translator.translate_malloc(512)
        data = f"Block {i}".encode()
        translator.translate_write(ptr, data)
        pointers.append(ptr)
    
    print(f"✓ Allocated 100 blocks")
    
    # Read some back
    for i in [0, 50, 99]:
        data = translator.translate_read(pointers[i], 20)
        print(f"  Block {i}: {data}")
    
    # Free all
    for ptr in pointers:
        translator.translate_free(ptr)
    
    print(f"✓ Freed 100 blocks")
    print()
    
    # Final stats
    translator.print_stats()
    
    print("=" * 70)
    print("✓ TRANSLATOR DEMO COMPLETE")
    print("=" * 70)
    print()
    print("The translator successfully:")
    print("  ✓ Translated app pointers ↔ Helix keys")
    print("  ✓ Translated file descriptors ↔ Helix cache")
    print("  ✓ Handled ingress/egress transparently")
    print("  ✓ Apps never knew Helix existed")
    print()
    print("Next step: Build LD_PRELOAD wrapper around this!")
    print()

if __name__ == "__main__":
    demo()
