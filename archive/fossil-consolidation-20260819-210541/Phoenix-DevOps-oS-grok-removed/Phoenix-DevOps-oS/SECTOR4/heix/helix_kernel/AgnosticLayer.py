import os
import subprocess
import json
import threading
import queue
import sys
import ctypes

# 1. SUBSYSTEM IMPORTS
# Ensure complete_pkg.py is in the same directory
try:
    import complete_pkg as vmmu
except ImportError:
    print("❌ Critical Error: VMMU (complete_pkg.py) not found.")
    sys.exit(1)

# 2. HARDWARE BRIDGE LINK (C-Kernel Bridge)
# This links your Python logic to the libhelix.so compiled from libhelix.c
try:
    # Use absolute path to ensure the service can find it
    lib_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'libhelix.so')
    lib = ctypes.CDLL(lib_path)
    
    # Explicitly define the types for the hardware sync function
    # helix_mem_sync(uint64_t ptr, size_t size, int tier)
    lib.helix_mem_sync.argtypes = [ctypes.c_uint64, ctypes.c_size_t, ctypes.c_int]
    lib.helix_mem_sync.restype = ctypes.c_int
except Exception as e:
    print(f"⚠️ Kernel Bridge Warning: Could not link libhelix.so: {e}")

def enqueue_output(out, q):
    """Background thread to capture module logs without blocking the kernel."""
    for line in iter(out.readline, ''):
        if line:
            q.put(line)
    out.close()

class AgnosticLayer:
    def __init__(self):
        self.active_modules = {}
        self.node_path = "/usr/bin/node"
        self.module_dir = os.path.dirname(os.path.abspath(__file__))
        
        # 3. KERNEL HANDSHAKE
        # Registers this process as the Master Core in the C-Bridge
        if 'lib' in globals():
            lib.helix_init()
            lib.helix_register(b"HEIX_KERNEL_CORE")
        
        # 4. VMMU INITIALIZATION
        vmmu.init_vmmu()
        self._log_event("info", "HEix Kernel Core & VMMU Online.")

    def _log_event(self, event_type, message):
        icons = {"info": "📘", "success": "✅", "warning": "⚠️", "error": "❌", "mem": "🧠", "diag": "📟"}
        print(f"{icons.get(event_type, '📝')} [AgnosticLayer:{event_type.upper()}] {message}")

    # ═══════════════════════════════════════════════════════════════
    # THE UNRAVELER (Logic to translate Packets to Hardware/Subsystems)
    # ═══════════════════════════════════════════════════════════════

    def unravel_packet(self, raw_packet):
        """Primary System Call interface for Quadralingual Packets."""
        try:
            packet = json.loads(raw_packet)
            target = packet.get("target")
            intent = packet.get("intent")
            payload = packet.get("payload", {})

            if target == "mem":
                return self._route_to_memory(intent, payload)
            elif target == "js":
                # Routes directly to the independent SyncEngine process
                return self.send_js_module_command("SyncEngine", {"intent": intent, "data": payload})
            else:
                self._log_event("warning", f"Unknown target: {target}")
                return False
        except Exception as e:
            self._log_event("error", f"Unraveling failed: {e}")
            return False

    def _route_to_memory(self, intent, payload):
        """The Bridge between Virtual RAM (Python) and Physical RAM (C)."""
        if intent == "malloc":
            size = payload.get("size", 1024)
            
            # Step A: Allocate in the Virtual VMMU
            ptr = vmmu.helix_malloc(size)
            
            # Step B: Synchronize with the Hardware Bridge
            if 'lib' in globals() and ptr:
                # 0 = HOT tier (Immediate Priority)
                sync_status = lib.helix_mem_sync(ctypes.c_uint64(ptr), ctypes.c_size_t(size), 0)
                if sync_status == 0:
                    self._log_event("diag", f"Hardware Sync: {hex(ptr)} verified.")
                else:
                    self._log_event("warning", f"Hardware Sync failed for {hex(ptr)}")

            self._log_event("mem", f"Allocated {size} bytes at {hex(ptr)}")
            return ptr
        return False

    # ═══════════════════════════════════════════════════════════════
    # MODULE MANAGEMENT (The 'Hands')
    # ═══════════════════════════════════════════════════════════════

    def start_js_module(self, module_name, js_file_path):
        full_js_path = os.path.join(self.module_dir, js_file_path)
        try:
            process = subprocess.Popen(
                [self.node_path, full_js_path],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1
            )
            q_stdout = queue.Queue()
            threading.Thread(target=enqueue_output, args=(process.stdout, q_stdout), daemon=True).start()
            self.active_modules[module_name] = {"process": process, "stdout_q": q_stdout}
            self._log_event("success", f"Module {module_name} isolated on PID: {process.pid}")
            return True
        except Exception as e:
            self._log_event("error", f"Startup Failed: {e}")
            return False

    def send_js_module_command(self, module_name, command_dict):
        if module_name not in self.active_modules:
            self._log_event("error", f"Module {module_name} is offline.")
            return False
        
        proc_info = self.active_modules[module_name]
        proc = proc_info["process"]
        
        if proc.poll() is not None:
            self._log_event("error", f"Module {module_name} has crashed.")
            return False

        try:
            proc.stdin.write(json.dumps(command_dict) + "\n")
            proc.stdin.flush()
            return True
        except BrokenPipeError:
            self._log_event("error", "Broken Pipe: SyncEngine disconnected.")
            return False

    def get_js_module_output(self, module_name):
        """Fetches pending logs from the module's stdout queue."""
        if module_name not in self.active_modules:
            return "Offline", ""
        
        q = self.active_modules[module_name]["stdout_q"]
        output = []
        try:
            while True:
                output.append(q.get_nowait().strip())
        except queue.Empty:
            pass
        return "\n".join(output), ""

# Entry point for stand-alone execution
if __name__ == "__main__":
    kernel = AgnosticLayer()
    # Keep the kernel alive
    try:
        while True:
            pass
    except KeyboardInterrupt:
        print("\n🛑 Kernel Shutdown Initiated.")
