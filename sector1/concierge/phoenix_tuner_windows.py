#!/usr/bin/env python3
"""
Phoenix Performance Tuner v1.0 — WINDOWS
One-shot OS optimizer for Jerry's Windows dev machine.
Targets: AI dev workload (Ollama, WSL, Claude Code, VS Code, PowerShell).

Run as Administrator:
  python phoenix_tuner_windows.py --apply
  python phoenix_tuner_windows.py --status
  python phoenix_tuner_windows.py --reset

Phoenix DevOps OS | jwl247 | GPL v3
"""

import ctypes
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

LOG = Path(os.environ.get("APPDATA", "C:\\ProgramData")) / "Phoenix" / "tuner.log"


# ── Helpers ───────────────────────────────────────────────────────────────────

def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _log(msg: str):
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().isoformat()
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{ts} [TUNER] {msg}\n")
    except Exception:
        pass
    print(msg)


def _ps(script: str, timeout: int = 30) -> tuple[int, str, str]:
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True, text=True, timeout=timeout,
        encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()


def _reg_get(path: str, name: str) -> str | None:
    rc, out, _ = _ps(f'(Get-ItemProperty -Path "HKLM:\\{path}" -Name "{name}" -ErrorAction SilentlyContinue)."{name}"')
    return out if rc == 0 and out else None


def _reg_set(path: str, name: str, value: str, kind: str = "DWord") -> bool:
    script = f"""
$p = "HKLM:\\{path}"
if (-not (Test-Path $p)) {{ New-Item -Path $p -Force | Out-Null }}
Set-ItemProperty -Path $p -Name "{name}" -Value {value} -Type {kind}
"""
    rc, _, err = _ps(script)
    if rc != 0:
        _log(f"  FAIL reg {name}: {err}")
    return rc == 0


def _reg_reset(path: str, name: str, default_val: str, kind: str = "DWord") -> bool:
    return _reg_set(path, name, default_val, kind)


# ── Power plan ────────────────────────────────────────────────────────────────

POWER_HIGH_PERF = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"  # High Performance GUID
POWER_BALANCED   = "381b4222-f694-41f0-9685-ff5bb260df2e"  # Balanced GUID (reset)


def _get_active_power_plan() -> str:
    rc, out, _ = _ps("powercfg /getactivescheme")
    if rc == 0 and out:
        parts = out.split("GUID: ")
        if len(parts) > 1:
            return parts[1].split()[0].strip()
    return ""


def apply_power_plan():
    _log("\n[1/5] Power plan → High Performance")
    current = _get_active_power_plan()
    if current.lower() == POWER_HIGH_PERF.lower():
        _log(f"  OK  already on High Performance")
        return
    rc, out, err = _ps(f"powercfg /setactive {POWER_HIGH_PERF}")
    if rc == 0:
        _log(f"  SET High Performance")
    else:
        # Some machines don't have this GUID — create it
        rc2, _, _ = _ps(f"powercfg /duplicatescheme {POWER_BALANCED} {POWER_HIGH_PERF}")
        rc3, _, _ = _ps(f"powercfg /setactive {POWER_HIGH_PERF}")
        _log(f"  SET High Performance (created)") if rc3 == 0 else _log(f"  FAIL: {err}")


# ── Registry memory tuning ────────────────────────────────────────────────────

# DisablePagingExecutive=1: keeps kernel code/data in RAM (not paged out)
# LargeSystemCache=0:       optimizes RAM for programs, not filesystem cache (server=1)
# IoPageLockLimit:          allows more I/O pages to stay locked (AI model loading)

MEM_REG_PATH = "SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Memory Management"

MEM_TUNING = [
    ("DisablePagingExecutive", "1",          "0",   "keep kernel in RAM"),
    ("LargeSystemCache",       "0",          "0",   "optimize for programs not file cache"),
    ("IoPageLockLimit",        "67108864",   "0",   "allow 64MB locked I/O pages for model loading"),
]


def apply_memory_registry():
    _log("\n[2/5] Memory registry tuning")
    for name, perf_val, _, desc in MEM_TUNING:
        cur = _reg_get(MEM_REG_PATH, name)
        if str(cur) == str(perf_val):
            _log(f"  OK  {name} = {perf_val}  ({desc})")
            continue
        if _reg_set(MEM_REG_PATH, name, perf_val):
            _log(f"  SET {name} = {perf_val}  ({desc})")
        else:
            _log(f"  FAIL {name}")


# ── Processor scheduling ──────────────────────────────────────────────────────
# Win32PrioritySeparation:
#   0x26 (38) = Programs, variable, short quanta  — best for desktop + AI
#   0x18 (24) = Background, fixed, long quanta    — default on some editions

PRIORITY_REG_PATH = "SYSTEM\\CurrentControlSet\\Control\\PriorityControl"
PRIORITY_PROGRAMS = "38"  # 0x26
PRIORITY_DEFAULT  = "2"   # Windows default


def apply_processor_scheduling():
    _log("\n[3/5] Processor scheduling → Programs")
    cur = _reg_get(PRIORITY_REG_PATH, "Win32PrioritySeparation")
    if str(cur) == PRIORITY_PROGRAMS:
        _log(f"  OK  Win32PrioritySeparation = {PRIORITY_PROGRAMS}")
        return
    if _reg_set(PRIORITY_REG_PATH, "Win32PrioritySeparation", PRIORITY_PROGRAMS):
        _log(f"  SET Win32PrioritySeparation = {PRIORITY_PROGRAMS}  (programs, short quanta)")


# ── Visual effects ────────────────────────────────────────────────────────────
# UserPreferencesMask controls visual effects. 0x9012 = Adjust for best performance.
# Only applies to the current user (HKCU).

VFX_REG_PATH = "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\VisualEffects"
VFX_PERF     = "2"   # Adjust for best performance
VFX_BALANCED = "3"   # Let Windows choose


def apply_visual_effects():
    _log("\n[4/5] Visual effects → performance")
    script = """
$p = "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\VisualEffects"
if (-not (Test-Path $p)) { New-Item -Path $p -Force | Out-Null }
Set-ItemProperty -Path $p -Name "VisualFXSetting" -Value 2 -Type DWord
Write-Host "SET"
"""
    rc, out, err = _ps(script)
    if rc == 0:
        _log(f"  SET VisualFXSetting = 2  (best performance)")
    else:
        _log(f"  FAIL: {err}")


# ── Clear standby list ────────────────────────────────────────────────────────
# Frees RAM that Windows holds in "Standby" (cached but not actively used).
# Immediate effect — no reboot needed. Uses NtSetSystemInformation.

def clear_standby_list():
    _log("\n[5/5] Clear memory standby list")
    script = """
$signature = @"
[DllImport("ntdll.dll")] public static extern uint NtSetSystemInformation(int SystemInformationClass, IntPtr SystemInformation, int SystemInformationLength);
"@
$ntdll = Add-Type -MemberDefinition $signature -Name "ntdll" -Namespace Win32 -PassThru
# SystemMemoryListInformation = 80, MemoryFlushModifiedList = 3
$p = [System.Runtime.InteropServices.Marshal]::AllocHGlobal(4)
[System.Runtime.InteropServices.Marshal]::WriteInt32($p, 4)
$result = $ntdll::NtSetSystemInformation(80, $p, 4)
[System.Runtime.InteropServices.Marshal]::FreeHGlobal($p)
Write-Host "NtSetSystemInformation result: 0x$($result.ToString('X'))"
"""
    rc, out, err = _ps(script, timeout=15)
    if rc == 0 and "0x0" in out:
        _log(f"  SET standby list cleared")
    else:
        _log(f"  INFO: {out or err}  (may need admin or not supported)")


# ── Status ────────────────────────────────────────────────────────────────────

def show_status():
    print("\n" + "="*60)
    print("PHOENIX TUNER STATUS — WINDOWS")
    print("="*60)

    print(f"\nPower plan:")
    cur = _get_active_power_plan()
    tag = "TUNED" if cur.lower() == POWER_HIGH_PERF.lower() else "DEFAULT"
    print(f"  [{tag}]  active GUID = {cur}")

    print(f"\nMemory registry ({MEM_REG_PATH}):")
    for name, perf_val, default_val, desc in MEM_TUNING:
        cur = _reg_get(MEM_REG_PATH, name) or "not set"
        tag = "TUNED" if str(cur) == str(perf_val) else "DEFAULT"
        print(f"  [{tag:7s}]  {name} = {cur}  ({desc})")

    print(f"\nProcessor scheduling:")
    cur = _reg_get(PRIORITY_REG_PATH, "Win32PrioritySeparation") or "?"
    tag = "TUNED" if str(cur) == PRIORITY_PROGRAMS else "DEFAULT"
    print(f"  [{tag}]  Win32PrioritySeparation = {cur}")

    print("\n" + "="*60)
    print("NOTE: Memory registry changes require REBOOT to take effect.")
    print("="*60)


# ── Reset ─────────────────────────────────────────────────────────────────────

def reset_all():
    _log("Resetting to Windows defaults...")
    _ps(f"powercfg /setactive {POWER_BALANCED}")
    _log(f"  RESET power plan → Balanced")
    for name, _, default_val, _ in MEM_TUNING:
        _reg_reset(MEM_REG_PATH, name, default_val)
        _log(f"  RESET {name} = {default_val}")
    _reg_reset(PRIORITY_REG_PATH, "Win32PrioritySeparation", PRIORITY_DEFAULT)
    _log(f"  RESET Win32PrioritySeparation = {PRIORITY_DEFAULT}")
    _log("Done — REBOOT to finalize registry resets.")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    if not is_admin():
        print("ERROR: Run as Administrator — right-click PowerShell → Run as Administrator")
        sys.exit(1)

    cmd = sys.argv[1] if len(sys.argv) > 1 else "--help"

    if cmd == "--apply":
        _log("="*60)
        _log("PHOENIX TUNER — APPLY")
        _log("="*60)
        apply_power_plan()
        apply_memory_registry()
        apply_processor_scheduling()
        apply_visual_effects()
        clear_standby_list()
        _log("\nDone.")
        _log("Power plan + visual effects: IMMEDIATE")
        _log("Memory registry changes:     REBOOT REQUIRED")
    elif cmd == "--status":
        show_status()
    elif cmd == "--reset":
        reset_all()
    else:
        print("Usage (run as Administrator):")
        print("  python phoenix_tuner_windows.py --apply   # apply performance profile")
        print("  python phoenix_tuner_windows.py --status  # show current values")
        print("  python phoenix_tuner_windows.py --reset   # restore defaults")
        print("")
        print("What it does:")
        print("  1. Power plan → High Performance (immediate)")
        print("  2. Registry: DisablePagingExecutive=1, IoPageLockLimit=64MB (reboot)")
        print("  3. Processor scheduling → Programs / short quanta (reboot)")
        print("  4. Visual effects → Best performance (immediate)")
        print("  5. Clear memory standby list (immediate, frees cached RAM)")


if __name__ == "__main__":
    main()
