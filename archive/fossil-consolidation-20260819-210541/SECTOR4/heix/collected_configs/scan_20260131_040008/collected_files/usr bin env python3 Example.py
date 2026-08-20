#!/usr/bin/env python3
"""
Example Python modules that the C kernel can load
Put these in ./modules/ directory
"""

# ============================================================================
# modules/hello.py
# ============================================================================
"""
Simple hello world module
"""

def run(input_data):
    """Main entry point called by the kernel"""
    return f"Hello! The kernel sent me: {input_data}"


# ============================================================================
# modules/memory.py
# ============================================================================
"""
Memory management module - shows system memory
"""

import psutil

def run(input_data):
    """Report memory statistics"""
    mem = psutil.virtual_memory()
    
    report = f"""
Memory Statistics:
  Total:     {mem.total / (1024**3):.2f} GB
  Available: {mem.available / (1024**3):.2f} GB
  Used:      {mem.used / (1024**3):.2f} GB
  Percent:   {mem.percent}%
"""
    return report


# ============================================================================
# modules/sysinfo.py
# ============================================================================
"""
System information module
"""

import platform
import sys

def run(input_data):
    """Report system information"""
    
    info = f"""
System Information:
  OS:           {platform.system()}
  Release:      {platform.release()}
  Machine:      {platform.machine()}
  Python:       {sys.version.split()[0]}
  
Kernel says:    {input_data}
"""
    return info


# ============================================================================
# modules/calculator.py
# ============================================================================
"""
Simple calculator module - shows module can do real work
"""

def run(input_data):
    """Evaluate simple math expressions"""
    try:
        # Safe eval for simple math
        result = eval(input_data, {"__builtins__": {}}, {})
        return f"Result: {result}"
    except:
        return "Error: Invalid expression"


# ============================================================================
# modules/file_processor.py
# ============================================================================
"""
File processing module - reads and processes files
"""

import os
import json

def run(input_data):
    """Process files from a directory"""
    if not os.path.exists(input_data):
        return f"Directory not found: {input_data}"
    
    files = os.listdir(input_data)
    json_files = [f for f in files if f.endswith('.json')]
    
    report = f"Found {len(json_files)} JSON files in {input_data}:\n"
    
    for f in json_files[:5]:  # Show first 5
        path = os.path.join(input_data, f)
        try:
            with open(path, 'r') as fp:
                data = json.load(fp)
                report += f"  ✓ {f} - {len(str(data))} bytes\n"
        except:
            report += f"  ✗ {f} - parse error\n"
    
    return report
