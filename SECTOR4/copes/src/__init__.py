"""
CoPES Source Package

This makes Helix cleanly importable:
    from src import helix
    from src.helix import HelixSystem, HelixCache, HelixMemoryManager, HelixFS
"""

from . import helix

__all__ = ["helix"]
