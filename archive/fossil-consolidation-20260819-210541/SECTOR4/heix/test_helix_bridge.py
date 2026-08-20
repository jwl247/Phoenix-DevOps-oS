import json
import time
from AgnosticLayer import AgnosticLayer

def run_system_test():
    print("🧬 HEix7.3GIII - Integrated System Test Initiated")
    print("-" * 50)
    
    # 1. Initialize the Nervous System
    # This loads libhelix.so and initializes the Python VMMU [cite: 1, 4]
    al = AgnosticLayer()
    
    # 2. Ignite the Independent Modules
    # We must start the JS engine so the 'SyncEngine' is no longer 'offline'
    print("🚀 Igniting Independent Modules...")
    al.start_js_module("SyncEngine", "heix_syncthing_module.js")
    
    # Give the subprocess (Node.js) a moment to stabilize on its PID
    time.sleep(1.5) 
    
    # 3. Create Quadralingual Packets
    # Packet A: Virtual Memory Allocation [cite: 1]
    memory_packet = {
        "target": "mem",
        "intent": "malloc",
        "payload": {"size": 2 * 1024 * 1024}
    }
    
    # Packet B: Distribution/Sync Intent
    sync_packet = {
        "target": "js",
        "intent": "snapshot",
        "payload": {"directory": "~/ENCOMPASS-E"}
    }

    # 4. Unravel Packets through the Agnostic Layer
    print("\n📦 Processing Memory Packet...")
    ptr = al.unravel_packet(json.dumps(memory_packet))
    
    if ptr:
        print(f"🧠 VMMU success! Virtual Pointer: {hex(ptr)}")
    
    print("\n📦 Processing Sync Packet...")
    # This will now reach the 'SyncEngine' because it is online
    success = al.unravel_packet(json.dumps(sync_packet))
    
    if success:
        print("✅ Sync Intent routed to JavaScript module.")
    else:
        print("❌ Sync routing failed.")
        # Add this to test_helix_bridge.py after the sync failure
        stdout, stderr = al.get_js_module_output("SyncEngine")
        print(f"📟 JS Output: {stdout}")
        print(f"❌ JS Error: {stderr}")

    print("\n" + "="*50)
    print("TEST COMPLETE: System tiers are communicating.")

if __name__ == "__main__":
    run_system_test()
