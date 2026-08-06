#!/usr/bin/env python3
"""
CoPES Security Runtime
jwl247 / Jerry Leftwich / GPL v3

Import this to get the running rotator instance.
Called at CoPES boot — before Phoenix loads on top.
"""

from guardian_rotator import GuardianRotator, GuardianID
from guardian_alpha import GuardianAlpha
from guardian_beta  import GuardianBeta
from guardian_gamma import GuardianGamma
from guardian_delta import GuardianDelta

# Global rotator instance
rotator = GuardianRotator(
    min_interval=180,   # 3 minutes minimum
    max_interval=600    # 10 minutes maximum
)

# Register all four guardians
rotator.register(GuardianID.ALPHA, GuardianAlpha(rotator))
rotator.register(GuardianID.BETA,  GuardianBeta(rotator))
rotator.register(GuardianID.GAMMA, GuardianGamma(rotator))
rotator.register(GuardianID.DELTA, GuardianDelta(rotator))

def boot():
    """Call at CoPES startup"""
    rotator.start()
    print("🔥 CoPES Guardian Rotation — ARMED")
    print(f"   Active: {rotator.status()['active_guardian']}")
    print(f"   Rotation interval: {rotator.min_interval}-{rotator.max_interval}s (randomized)")
    print(f"   Honeypots: 3 active")
    return rotator

if __name__ == "__main__":
    boot()
    import time
    try:
        while True:
            time.sleep(30)
            print(f"[STATUS] {rotator.status()}")
    except KeyboardInterrupt:
        rotator.stop()
