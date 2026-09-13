// hash.js — Phoenix Office
// SHA3-512 and BLAKE2b-512, everywhere Office runs.
//
// Why this file exists: Office's tamper-evidence, the TAV address system
// (CLAUDE.md), and authorship parity with sector1/auth/phoenix_auth.py all
// depend on SHA3-512 + BLAKE2b-512 specifically. Node's own crypto (OpenSSL 3)
// has both — but the Phoenix dashboard runs Office inside Electron, whose
// crypto is backed by BoringSSL, which supports NEITHER. `crypto.createHash
// ('sha3-512')` throws "Digest method not supported" in the Electron main
// process, which took the whole app down the first time it was opened from
// the dashboard (2026-09-10).
//
// So: try the native implementation first (Node CLI, tests, bash-adjacent
// contexts — fast, and a live cross-check against OpenSSL), and fall back to
// a vendored pure-JS implementation (BoringSSL / Electron). The vendored code
// is @noble/hashes 1.7.1 (MIT, audited, zero-dependency) — see
// lib/vendor/noble-hashes/. Its output is byte-identical to OpenSSL's for
// both algorithms (verified across test vectors; the test suite re-checks it
// on every run).
//
// No npm install step — the vendored files are committed, matching Phoenix's
// "deterministic, prefetched" stance (CLAUDE.md).

'use strict';

const crypto = require('crypto');

let nativeSha3 = null;   // null = untested, true/false = known
let nativeBlake2 = null;

let noble = null;
function loadNoble() {
  if (noble) return noble;
  const { sha3_512 } = require('./vendor/noble-hashes/sha3.js');
  const { blake2b } = require('./vendor/noble-hashes/blake2b.js');
  const { bytesToHex } = require('./vendor/noble-hashes/utils.js');
  noble = { sha3_512, blake2b, bytesToHex };
  return noble;
}

function toBytes(input) {
  if (Buffer.isBuffer(input)) return input;
  if (input instanceof Uint8Array) return input;
  return Buffer.from(String(input), 'utf8');
}

function sha3_512Hex(input) {
  const bytes = toBytes(input);
  if (nativeSha3 !== false) {
    try {
      const h = crypto.createHash('sha3-512').update(bytes).digest('hex');
      nativeSha3 = true;
      return h;
    } catch (_) {
      nativeSha3 = false;
    }
  }
  const n = loadNoble();
  return n.bytesToHex(n.sha3_512(bytes));
}

function blake2b512Hex(input) {
  const bytes = toBytes(input);
  if (nativeBlake2 !== false) {
    try {
      const h = crypto.createHash('blake2b512').update(bytes).digest('hex');
      nativeBlake2 = true;
      return h;
    } catch (_) {
      nativeBlake2 = false;
    }
  }
  const n = loadNoble();
  return n.bytesToHex(n.blake2b(bytes, { dkLen: 64 }));
}

// true when the native (OpenSSL) path is in use for both — the tests use this
// to assert the vendored fallback still matches on machines that have both.
function usingNative() {
  return { sha3: nativeSha3 === true, blake2: nativeBlake2 === true };
}

module.exports = { sha3_512Hex, blake2b512Hex, usingNative };
