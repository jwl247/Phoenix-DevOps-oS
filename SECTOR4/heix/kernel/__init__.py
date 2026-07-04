# Agnostic Universal Kernel Package
"""
Agnostic Universal Kernel v7.3

A self-healing, OS-agnostic kernel that provides:
- Config scanning and cloning
- Data temperature management
- Helix memory stack (virtual RAM)
- Micro kernel spawning
- Web dashboard
- API integration

Usage:
    from kernel import AgnosticUniversalKernel, KernelDashboard
    
    kernel = AgnosticUniversalKernel()
    kernel.start()
    
    dashboard = KernelDashboard(kernel, port=8080)
    dashboard.start()
"""

from .core import (
    AgnosticUniversalKernel,
    AgnosticLayer,
    ConfigScanner,
    HelixTranslator,
    DataTemperature,
    KernelHealth,
    MicroKernelConfig
)

from .modules import (
    HelixMemoryManager,
    VRRAM,
    HelixCompleteStack,
    HelixCache,
    HelixFS
)

from .dashboard import KernelDashboard

__version__ = '7.3'
__all__ = [
    'AgnosticUniversalKernel',
    'AgnosticLayer',
    'ConfigScanner',
    'HelixTranslator',
    'DataTemperature',
    'KernelHealth',
    'MicroKernelConfig',
    'HelixMemoryManager',
    'VRRAM',
    'HelixCompleteStack',
    'HelixCache',
    'HelixFS',
    'KernelDashboard'
]
