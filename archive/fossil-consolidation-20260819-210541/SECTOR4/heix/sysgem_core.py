"""
Life First OS: System Core (HTg2b Edition)
Status: EXPERIMENTAL | Mode: DUAL-TRANSLATOR
Target: Global Versioning & Thermal Sync Baseline
"""

import time
import os
from HTg2b import HTg2b

# ============================================================================
# MOCK HELIX BACKEND (To be replaced by the C-Kernel/Double Helix later)
# ============================================================================
class MockMemory:
    def malloc(self, key, data): return True
    def free(self, key): return True

class MockHelix:
    def __init__(self):
        self.memory = MockMemory()

# ============================================================================
# SYSTEM CORE
# ============================================================================
class SystemCore:
    def __init__(self):
        print("--- INITIALIZING LIFE FIRST OS (HTg2b BASELINE) ---")
        
        # 1. Initialize Helix Backend
        self.helix = MockHelix()
        
        # 2. Initialize Dual HTg2b Translators
        # Ingress: Handles the 'Great Lie' for the App
        self.ingress = HTg2b(self.helix)
        
        # Egress: Shares the same map to handle Sync/2TB logic
        self.egress = HTg2b(self.helix)
        self.egress.ptr_to_key = self.ingress.ptr_to_key # THE HANDSHAKE
        
        self.is_running = True
        self.pulse_count = 0

    def pulse(self):
        """The Heartbeat of the System"""
        self.pulse_count += 1
        
        # --- INGRESS LOGIC ---
        # (This is where your drop_zone or LD_PRELOAD hooks would feed)
        
        # --- EGRESS LOGIC (The Sync Watcher) ---
        # Translator B watches for Version DNA changes to trigger 2TB Sync
        for ptr, entry in self.egress.ptr_to_key.items():
            if entry.thermal_state == "HOT":
                # This is a clone or active data needing sync to Google Drive
                self.process_sync(entry)

    def process_sync(self, entry):
        """Simulates the Real-Time Sync to the 2TB Deep Freeze"""
        # In the future, this moves data to self.egress.cold_storage_path
        print(f"[SYNC-PULSE] Version {hex(entry.version_id)} of {entry.helix_key} marked for Sync.")
        # Once synced, we can drop the temperature to WARM
        entry.thermal_state = "WARM"

    def run(self):
        """Main Operational Loop"""
        print("CORE PULSE OPERATIONAL. WAITING FOR VERSIONED DATA...")
        try:
            while self.is_running:
                self.pulse()
                time.sleep(1) # Experimental pulse rate
                
                # Test Trigger: Every 5 pulses, simulate a Malloc and Clone
                if self.pulse_count == 2:
                    print("\n[TEST] TRIGGERING MALLOC...")
                    ptr = self.ingress.translate_malloc(1024)
                    self.ingress.audit_map()
                
                if self.pulse_count == 5:
                    print("\n[TEST] TRIGGERING CLONE (REAL-TIME SYNC)...")
                    # We clone the last allocated pointer
                    last_ptr = list(self.ingress.ptr_to_key.keys())[-1]
                    self.ingress.translate_clone(last_ptr)
                    self.ingress.audit_map()
                    
                if self.pulse_count > 10:
                    print("\n--- TEST COMPLETE: SYSTEM STABLE ---")
                    break
        except KeyboardInterrupt:
            self.is_running = False

# ============================================================================
# START SYSTEM
# ============================================================================
if __name__ == "__main__":
    core = SystemCore()
    core.run()
