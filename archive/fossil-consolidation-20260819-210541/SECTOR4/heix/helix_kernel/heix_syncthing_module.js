/*
 * heix_syncthing_module.js - The "Hands" of SysGem-E
 * Provides a persistent event loop to listen for Orchestrator packets.
 */

const readline = require('readline');

// Standardized Interface for stdin/stdout communication
const rl = readline.createInterface({
  input: process.stdin,
  terminal: false
});

// Diagnostic: Signals to the Agnostic Layer that the engine is ready
console.log("📟 [SyncEngine] Heartbeat established. Awaiting Quadralingual Packets...");

// The Event Loop: This keeps the process alive indefinitely
rl.on('line', (line) => {
  try {
    // Unravel the JSON packet sent by AgnosticLayer.py
    const packet = JSON.parse(line);
    
    // Logic for the 'snapshot' intent
    if (packet.intent === 'snapshot') {
      const targetDir = packet.data.directory || "default_path";
      console.log(`✅ [SyncEngine] Snapshotting Target: ${targetDir}`);
      
      // Future: Insert your actual Syncthing API/CLI calls here
      console.log(`📟 [SyncEngine] Sync state: STABLE`);
    }
    
    // Add more intents (e.g., 'revert', 'sync') as needed
    
  } catch (e) {
    console.error("❌ [SyncEngine] Failed to parse packet: " + e.message);
  }
});

// Graceful Shutdown: Triggers if AgnosticLayer closes the pipe
process.stdin.on('end', () => {
  console.log("⚠️ [SyncEngine] Orchestrator disconnected. Shutting down.");
  process.exit(0);
});
