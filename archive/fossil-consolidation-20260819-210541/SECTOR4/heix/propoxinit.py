#!/usr/bin/env python3
# 💎 GemIIIDev - Sacrifice Game: BALL FACTORY v1.0
# Role: Generates and drops "Intent Balls" into the Magnet Index.
# "Turning named zipcodes into hardware snaps."

import os
import json
import time
import hashlib
from pathlib import Path

# Paths
ROOT = Path("/opt/SacrificeGame")
INDEX = ROOT / "magnet_index"

class BallFactory:
    def __init__(self):
        INDEX.mkdir(parents=True, exist_ok=True)
        print("🎾 BALL FACTORY: Ready to fire intents.")

    def _generate_sha1_fragment(self, intent_name):
        """Generates the 4-3-3-3 hex string for the PCS."""
        full_sha = hashlib.sha1(f"{intent_name}{time.time()}".encode()).hexdigest().upper()
        # Format: Prob1(4)-Prob2(3)-Prob3(3)-Prob4(3)
        return f"{full_sha[0:4]}-{full_sha[4:7]}-{full_sha[7:10]}-{full_sha[10:13]}"

    def drop_ball(self, zipcode, intent_name, action="SNAP"):
        """
        Creates the Proximity Collection String (PCS) and drops the ball.
        PCS Format: [Zipcode]-[Prob1]-[Prob2]-[Prob3]-[Prob4]
        """
        sha_fragment = self._generate_sha1_fragment(intent_name)
        pcs = f"{str(zipcode).zfill(5)}-{sha_fragment}"
        
        ball_data = {
            "header": {
                "identity": "PROXIMITY_INTENT",
                "origin": "BALL_FACTORY_CLI",
                "timestamp": time.time()
            },
            "payload": {
                "zipcode": zipcode,
                "intent": intent_name,
                "sha": pcs,
                "action": action
            }
        }

        filename = f"ball_{int(time.time())}_{intent_name.lower()}.json"
        ball_path = INDEX / filename

        with open(ball_path, 'w') as f:
            json.dump(ball_data, f, indent=2)
        
        print(f"🚀 BALL DROPPED: {filename}")
        print(f"   └─ PCS: {pcs}")
        return ball_path

if __name__ == "__main__":
    import sys
    factory = BallFactory()
    
    if len(sys.argv) < 3:
        print("Usage: python3 BallFactory.py [zipcode] [intent_name]")
        print("Example: python3 BallFactory.py 90210 SOUL_AWAKEN")
    else:
        factory.drop_ball(sys.argv[1], sys.argv[2])
