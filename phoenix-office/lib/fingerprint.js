// fingerprint.js — Phoenix Office
// Cross-platform hardware fingerprint for document authorship. Same
// double-hash algorithm as sector1/auth/phoenix_auth.py (SHA3-512 +
// BLAKE2b over combined signals, then SHA3-512 of the concatenation) —
// extended with a Windows signal collector, since phoenix_auth.py's own
// signals (/proc/cpuinfo, /etc/machine-id, DMI files) are Linux-only and
// won't run on the Windows dashboard box where Office documents are
// actually authored day to day. See DESIGN.md "Authorship = pluggable
// identity" for why Windows/Google sign-in exist alongside this rather
// than forcing hardware fingerprinting everywhere.

const { sha3_512Hex, blake2b512Hex } = require('./hash');
const { execFileSync } = require('child_process');

function safeRun(cmd, args) {
  try {
    return execFileSync(cmd, args, { timeout: 3000, windowsHide: true }).toString().trim() || 'unavailable';
  } catch (_) {
    return 'unavailable';
  }
}

function safePowerShell(command) {
  return safeRun('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', command]);
}

function getLinuxSignals() {
  return [
    safeRun('cat', ['/proc/cpuinfo']),
    safeRun('cat', ['/etc/machine-id']),
    safeRun('cat', ['/sys/class/dmi/id/board_serial']),
    safeRun('cat', ['/sys/class/dmi/id/product_uuid']),
    safeRun('lsblk', ['-o', 'NAME,SERIAL,SIZE']),
    safeRun('cat', ['/sys/class/net/eth0/address']),
    safeRun('cat', ['/proc/meminfo']),
    safeRun('uname', ['-r']),
    safeRun('cat', ['/sys/class/dmi/id/bios_version']),
  ];
}

function getWindowsSignals() {
  return [
    safePowerShell("(Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Cryptography').MachineGuid"),
    safePowerShell('(Get-CimInstance Win32_BIOS).SerialNumber'),
    safePowerShell('(Get-CimInstance Win32_Processor).ProcessorId'),
    safePowerShell('(Get-CimInstance Win32_BaseBoard).SerialNumber'),
    safePowerShell('(Get-CimInstance Win32_ComputerSystemProduct).UUID'),
    safePowerShell("(Get-CimInstance Win32_NetworkAdapterConfiguration -Filter 'IPEnabled=true' | Select-Object -First 1).MACAddress"),
    safePowerShell('(Get-CimInstance Win32_OperatingSystem).BuildNumber'),
    safePowerShell('(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory'),
    safePowerShell('(Get-CimInstance Win32_Processor).Name'),
  ];
}

function getSignals() {
  return process.platform === 'win32' ? getWindowsSignals() : getLinuxSignals();
}

// Identical shape to phoenix_auth.py's fingerprint(): sha3 = SHA3-512(combined),
// blake2b = BLAKE2b-512(combined), final = SHA3-512(sha3_hex + blake2b_hex).
function doubleHash(signals) {
  const combined = signals.join('|');
  const sha3 = sha3_512Hex(combined);
  const blake2b = blake2b512Hex(combined);
  return sha3_512Hex(sha3 + blake2b);
}

function machineFingerprint() {
  return doubleHash(getSignals());
}

module.exports = {
  machineFingerprint, doubleHash, getSignals, getWindowsSignals, getLinuxSignals,
  // exposed for identity.js — same safe-exec discipline (timeout, windowsHide,
  // never throw) reused to read a Windows SID
  safeRun, safePowerShell,
};
