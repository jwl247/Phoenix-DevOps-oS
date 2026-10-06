// webauthn.mjs — passkey (WebAuthn) verification for the Peer Review worker.
// Phoenix DevOps OS | jwl247 | GPL v3
//
// Self-sovereign sign-in: the person's own device (fingerprint / face / PIN)
// holds the private key; this worker keeps only the public key. No identity
// vendor in the loop (CLAUDE.md vendor rule — GitHub is Microsoft).
//
// Supports ES256 (-7, P-256: phones, security keys, most platforms) and
// RS256 (-257: some Windows Hello setups). Attestation statements are not
// trusted or required (we don't need to know the device make, only that the
// same key signs later), so any "fmt" is accepted and the credential's public
// key is what gets pinned.

const te = new TextEncoder();

// ── base64url ────────────────────────────────────────────────────────────────
export function b64url(bytes) {
  const b = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  let s = '';
  for (let i = 0; i < b.length; i++) s += String.fromCharCode(b[i]);
  return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
export function fromB64url(str) {
  if (typeof str !== 'string' || !/^[A-Za-z0-9_-]*$/.test(str)) throw new Error('bad base64url');
  const s = atob(str.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((str.length + 3) % 4));
  const out = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i);
  return out;
}
export function randomB64url(n = 32) { return b64url(crypto.getRandomValues(new Uint8Array(n))); }

// ── minimal CBOR decoder (what WebAuthn uses) ────────────────────────────────
export function cborDecode(bytes, start = 0) {
  let p = start;
  const u8 = bytes;
  const dv = new DataView(u8.buffer, u8.byteOffset, u8.byteLength);
  function len(info) {
    if (info < 24) return info;
    if (info === 24) return u8[p++];
    if (info === 25) { const v = dv.getUint16(p); p += 2; return v; }
    if (info === 26) { const v = dv.getUint32(p); p += 4; return v; }
    if (info === 27) { const hi = dv.getUint32(p), lo = dv.getUint32(p + 4); p += 8; return hi * 2 ** 32 + lo; }
    throw new Error('CBOR: indefinite lengths not supported');
  }
  function item() {
    if (p >= u8.length) throw new Error('CBOR: truncated');
    const ib = u8[p++], major = ib >> 5, info = ib & 31;
    switch (major) {
      case 0: return len(info);
      case 1: return -1 - len(info);
      case 2: { const n = len(info); const v = u8.slice(p, p + n); if (v.length !== n) throw new Error('CBOR: truncated bytes'); p += n; return v; }
      case 3: { const n = len(info); const v = new TextDecoder().decode(u8.subarray(p, p + n)); p += n; return v; }
      case 4: { const n = len(info); const a = []; for (let i = 0; i < n; i++) a.push(item()); return a; }
      case 5: { const n = len(info); const m = new Map(); for (let i = 0; i < n; i++) { const k = item(); m.set(k, item()); } return m; }
      case 6: len(info); return item();              // tag: ignore, return content
      case 7:
        if (info === 20) return false;
        if (info === 21) return true;
        if (info === 22 || info === 23) return null;
        throw new Error('CBOR: unsupported simple/float');
    }
    throw new Error('CBOR: bad major type');
  }
  const value = item();
  return { value, end: p };
}

// ── authenticator data ───────────────────────────────────────────────────────
export function parseAuthData(ad) {
  if (ad.length < 37) throw new Error('authenticatorData too short');
  const dv = new DataView(ad.buffer, ad.byteOffset, ad.byteLength);
  const out = {
    rpIdHash: ad.slice(0, 32),
    flags: ad[32],
    up: !!(ad[32] & 0x01),
    uv: !!(ad[32] & 0x04),
    at: !!(ad[32] & 0x40),
    signCount: dv.getUint32(33),
  };
  if (out.at) {
    if (ad.length < 55) throw new Error('attested credential data truncated');
    const credLen = dv.getUint16(53);
    out.credentialId = ad.slice(55, 55 + credLen);
    const { value } = cborDecode(ad, 55 + credLen);
    out.cose = value;
  }
  return out;
}

// ── COSE key → JWK + verify algorithm ────────────────────────────────────────
export function coseToJwk(cose) {
  if (!(cose instanceof Map)) throw new Error('COSE key is not a map');
  const kty = cose.get(1), alg = cose.get(3);
  if (kty === 2 && alg === -7 && cose.get(-1) === 1) {
    return { alg: -7, jwk: { kty: 'EC', crv: 'P-256', x: b64url(cose.get(-2)), y: b64url(cose.get(-3)), ext: true } };
  }
  if (kty === 3 && alg === -257) {
    return { alg: -257, jwk: { kty: 'RSA', n: b64url(cose.get(-1)), e: b64url(cose.get(-2)), alg: 'RS256', ext: true } };
  }
  throw new Error(`unsupported passkey algorithm (kty ${kty}, alg ${alg}) — ES256 or RS256 only`);
}

function derToRaw(der) {
  // ECDSA signature: SEQUENCE { INTEGER r, INTEGER s } → 64-byte r||s
  let p = 0;
  if (der[p++] !== 0x30) throw new Error('bad ECDSA signature');
  if (der[p] & 0x80) p += 1 + (der[p] & 0x7f); else p++;
  const out = new Uint8Array(64);
  for (let k = 0; k < 2; k++) {
    if (der[p++] !== 0x02) throw new Error('bad ECDSA signature');
    let n = der[p++];
    while (n > 32 && der[p] === 0) { p++; n--; }
    if (n > 32) throw new Error('bad ECDSA signature');
    out.set(der.subarray(p, p + n), k * 32 + (32 - n));
    p += n;
  }
  return out;
}

async function verifySig(alg, jwk, signature, data) {
  if (alg === -7) {
    const key = await crypto.subtle.importKey('jwk', jwk, { name: 'ECDSA', namedCurve: 'P-256' }, false, ['verify']);
    return crypto.subtle.verify({ name: 'ECDSA', hash: 'SHA-256' }, key, derToRaw(signature), data);
  }
  if (alg === -257) {
    const key = await crypto.subtle.importKey('jwk', jwk, { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' }, false, ['verify']);
    return crypto.subtle.verify('RSASSA-PKCS1-v1_5', key, signature, data);
  }
  return false;
}

const eq = (a, b) => a.length === b.length && a.every((v, i) => v === b[i]);
const sha256 = async (bytes) => new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));

function checkClientData(clientDataJSON, type, challenge, origin) {
  let cd;
  try { cd = JSON.parse(new TextDecoder().decode(clientDataJSON)); } catch { throw new Error('clientDataJSON is not JSON'); }
  if (cd.type !== type) throw new Error(`wrong ceremony type (${cd.type})`);
  if (cd.challenge !== challenge) throw new Error('challenge mismatch');
  if (cd.origin !== origin) throw new Error(`origin mismatch (${cd.origin})`);
  if (cd.crossOrigin === true) throw new Error('cross-origin ceremonies are refused');
  return cd;
}

/** Verify a registration (navigator.credentials.create) response. */
export async function verifyRegistration(resp, { challenge, origin, rpId }) {
  const clientDataJSON = fromB64url(resp.clientDataJSON);
  checkClientData(clientDataJSON, 'webauthn.create', challenge, origin);
  const { value: att } = cborDecode(fromB64url(resp.attestationObject));
  if (!(att instanceof Map) || !(att.get('authData') instanceof Uint8Array)) throw new Error('bad attestationObject');
  const ad = parseAuthData(att.get('authData'));
  if (!eq(ad.rpIdHash, await sha256(te.encode(rpId)))) throw new Error('passkey is for a different site');
  if (!ad.up) throw new Error('user presence not confirmed');
  if (!ad.uv) throw new Error('user verification (fingerprint/PIN) is required');
  if (!ad.at || !ad.credentialId) throw new Error('no credential in response');
  const { alg, jwk } = coseToJwk(ad.cose);
  return { credentialId: b64url(ad.credentialId), alg, jwk, signCount: ad.signCount };
}

/** Verify a sign-in (navigator.credentials.get) response against a stored credential. */
export async function verifyAuthentication(resp, stored, { challenge, origin, rpId }) {
  const clientDataJSON = fromB64url(resp.clientDataJSON);
  checkClientData(clientDataJSON, 'webauthn.get', challenge, origin);
  const authData = fromB64url(resp.authenticatorData);
  const ad = parseAuthData(authData);
  if (!eq(ad.rpIdHash, await sha256(te.encode(rpId)))) throw new Error('passkey is for a different site');
  if (!ad.up) throw new Error('user presence not confirmed');
  if (!ad.uv) throw new Error('user verification (fingerprint/PIN) is required');
  const signed = new Uint8Array(authData.length + 32);
  signed.set(authData, 0);
  signed.set(await sha256(clientDataJSON), authData.length);
  const ok = await verifySig(stored.alg, stored.jwk, fromB64url(resp.signature), signed);
  if (!ok) throw new Error('signature does not verify');
  // A counter that goes backwards means a cloned authenticator. 0/0 = device
  // doesn't count (most synced passkeys), which is allowed.
  if ((ad.signCount !== 0 || stored.signCount !== 0) && ad.signCount <= stored.signCount) {
    throw new Error('sign counter went backwards — possible cloned passkey');
  }
  return { signCount: ad.signCount };
}
