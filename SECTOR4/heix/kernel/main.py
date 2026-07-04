#!/usr/bin/env python3
"""
Agnostic Universal Kernel - Main Entry Point

Usage:
    python main.py                  # Start kernel with dashboard
    python main.py --status         # Show kernel status
    python main.py --clone <path>   # Clone kernel to path
    python main.py --scan <path>    # Scan path for configs
"""

import sys
import os
import time
import json
import argparse
import signal

# Add kernel paths
KERNEL_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(KERNEL_ROOT, 'core'))
sys.path.insert(0, os.path.join(KERNEL_ROOT, 'modules'))
sys.path.insert(0, os.path.join(KERNEL_ROOT, 'dashboard'))

from agnostic_universal_kernel import AgnosticUniversalKernel
from dashboard import KernelDashboard


def print_banner():
    print("""
╔════════════════════════════════════════════════════════════════════╗
║                                                                    ║
║          🧠 AGNOSTIC UNIVERSAL KERNEL v7.3 🧠                      ║
║                                                                    ║
║   • Self-healing capabilities                                      ║
║   • Config scanning & cloning                                      ║
║   • Data temperature management                                    ║
║   • Helix memory stack (VRAM)                                      ║
║   • Micro kernel spawning                                          ║
║   • Web dashboard                                                   ║
║                                                                    ║
╚════════════════════════════════════════════════════════════════════╝
""")


def main():
    parser = argparse.ArgumentParser(
        description="Agnostic Universal Kernel",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                    Start kernel with dashboard
  python main.py --port 9000        Start on custom port
  python main.py --status           Show kernel status
  python main.py --clone /backup    Clone kernel to /backup
  python main.py --scan /etc        Scan /etc for configs
        """
    )
    
    parser.add_argument('--config', help='Path to configuration file')
    parser.add_argument('--port', type=int, default=8080, help='Dashboard port (default: 8080)')
    parser.add_argument('--status', action='store_true', help='Show kernel status and exit')
    parser.add_argument('--clone', metavar='PATH', help='Clone kernel to specified path')
    parser.add_argument('--scan', metavar='PATH', help='Scan directory for configs')
    parser.add_argument('--no-dashboard', action='store_true', help='Start without dashboard')
    parser.add_argument('--daemon', action='store_true', help='Run as daemon')
    
    args = parser.parse_args()
    
    print_banner()
    
    # Initialize kernel
    print("Initializing kernel...")
    kernel = AgnosticUniversalKernel(config_path=args.config)
    
    # Handle one-shot commands
    if args.status:
        status = kernel.get_kernel_status()
        print("\n📊 Kernel Status:")
        print(json.dumps(status, indent=2, default=str))
        return 0
    
    if args.clone:
        print(f"\n📋 Cloning kernel to: {args.clone}")
        success = kernel.clone_kernel(args.clone)
        print("✅ Clone successful" if success else "❌ Clone failed")
        return 0 if success else 1
    
    if args.scan:
        print(f"\n🔍 Scanning for configs in: {args.scan}")
        results = kernel.scan_and_clone_configs(args.scan)
        print(f"Found {results.get('configs_found', 0)} configs, cloned {results.get('configs_cloned', 0)}")
        return 0
    
    # Start kernel
    print("\nStarting kernel...")
    status = kernel.start()
    
    if not status:
        print("❌ Failed to start kernel")
        return 1
    
    print("✅ Kernel started successfully")
    print(f"   Version: {status.get('version')}")
    print(f"   Platform: {status.get('platform')}")
    print(f"   Micro Kernels: {status.get('micro_kernels')}")
    
    # Start dashboard
    dashboard = None
    if not args.no_dashboard:
        print(f"\n🌐 Starting dashboard on port {args.port}...")
        dashboard = KernelDashboard(kernel, port=args.port)
        dashboard.start()
        print(f"✅ Dashboard running at: http://localhost:{args.port}")
    
    # Setup signal handlers
    def shutdown_handler(signum, frame):
        print("\n\nShutting down...")
        if dashboard:
            dashboard.stop()
        kernel.shutdown()
        print("✅ Kernel shutdown complete")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)
    
    print("\n" + "="*60)
    print("🚀 KERNEL IS RUNNING")
    print("="*60)
    if not args.no_dashboard:
        print(f"\n👉 Open dashboard: http://localhost:{args.port}")
    print("\nPress Ctrl+C to shutdown")
    print("="*60 + "\n")
    
    # Keep running
    try:
        while kernel.running:
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown_handler(None, None)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
