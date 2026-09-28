"""
Helix Translator Layer
Translates between app requests and the real Helix memory manager
(HelixMemoryManager in helix_vram.py — Strand A/RAM + Strand B/disk relief,
the same one paging.py and the kernel share).

INGRESS: App request  -> Helix key
EGRESS:  Helix data   -> App format

Think of it like a bilingual interpreter sitting between two people
who don't speak the same language. Wired to her real backend, not a mock:
malloc/read/write/free below call HelixMemoryManager.allocate/read/write/free
directly, so data really lives in RAM until she relieves it to Strand B under
pressure, same as everything else that goes through her.
"""

import os
import sys
import time
from typing import Any, Optional, Dict
from dataclasses import dataclass

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

from helix_vram import HelixMemoryManager, HelixFullError

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
    
    def __init__(self, helix_backend: Optional[HelixMemoryManager] = None):
        """
        helix_backend: a real HelixMemoryManager. Pass the shared instance the
        rest of the process already uses (paging.py, etc.) when one exists --
        a fresh one here starts her own Dandelion ticker thread. Only left
        default-constructible for standalone use/testing.
        """
        self.helix = helix_backend if helix_backend is not None else HelixMemoryManager()
        
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
        try:
            self.helix.allocate(helix_key, bytes(data))
        except HelixFullError:
            return 0  # NULL pointer -- Strand A and Strand B both full

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
        self.helix.free(helix_key)

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
        data = self.helix.read(entry.helix_key)

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
        existing = self.helix.read(entry.helix_key)

        if existing is None:
            # First write, create buffer
            buffer = bytearray(entry.size)
        else:
            buffer = bytearray(existing)

        # Step 3: Modify at offset
        end = offset + len(data)
        buffer[offset:end] = data

        # Step 4: Write back
        success = self.helix.write(entry.helix_key, bytes(buffer))

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
        2. Map FD -> filepath (the filepath itself is her key; lazily
           allocated on first write, read() answers None until then)
        3. Return FD
        """
        self.stats['ingress_calls'] += 1

        # Step 1: Generate fake FD
        fake_fd = self.next_fake_fd
        self.next_fake_fd += 1

        # Step 2: Map FD → path
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

        # Step 2: Read from Helix (filepath is the key)
        data = self.helix.read(filepath)

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

        # Step 2: Write to Helix (filepath is the key; write() allocates
        # on first use, same as a real HelixMemoryManager.write() call)
        self.helix.write(filepath, data)

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
# SELF-TEST -- exercises the real HelixMemoryManager, not a mock
# ============================================================================

def _selftest():
    """Round-trips real data through the real backend and asserts the
    results, instead of narrating a scripted demo. Non-zero exit on failure."""
    helix = HelixMemoryManager(use_kernel=False)  # standalone: no kernel needed
    translator = HelixTranslator(helix)

    # Memory: malloc/write/read/free
    ptr = translator.translate_malloc(1024)
    assert ptr != 0, "malloc returned NULL"
    payload = b"Hello from the app!"
    assert translator.translate_write(ptr, payload), "write failed"
    assert translator.translate_read(ptr, len(payload)) == payload, "read mismatch"
    info = translator.inspect_pointer(ptr)
    assert info is not None and info["helix_key"].startswith("mem_"), "inspect_pointer wrong"
    assert info["access_count"] >= 1, "touch() should have counted the read"
    assert translator.translate_free(ptr), "free failed"
    assert translator.translate_read(ptr, len(payload)) is None, "read after free should miss"

    # Files: open/write/read/close, filepath is the key
    fd = translator.translate_open("/tmp/test.txt", "w")
    file_data = b"File contents from app"
    assert translator.translate_write_file(fd, file_data)
    assert translator.translate_read_file(fd, len(file_data)) == file_data
    assert translator.translate_close(fd)

    # Volume: 100 real allocations through Strand A, read back, freed
    pointers = [translator.translate_malloc(512) for _ in range(100)]
    for i, p in enumerate(pointers):
        translator.translate_write(p, f"Block {i}".encode())
    for i in (0, 50, 99):
        expected = f"Block {i}".encode()
        # malloc'd 512 bytes; write() only overwrote the first len(expected) of
        # them, so read() back exactly that many, not the full 512-byte slot.
        assert translator.translate_read(pointers[i], len(expected)) == expected
    for p in pointers:
        translator.translate_free(p)

    print("helix_translator self-test: PASS")
    print("translator stats:", translator.get_stats())
    print("backend stats:   ", helix.get_stats())
    helix.close()


if __name__ == "__main__":
    _selftest()
