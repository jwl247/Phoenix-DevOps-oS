// softauthn.mjs — a software WebAuthn authenticator for tests.
// Produces the exact bytes a phone/security key sends (CBOR attestation
// object, authenticator data, clientDataJSON, DER ECDSA signature), so the
// worker's verifier is tested against real-format input, not hand-made JSON.
import { webcrypto, createHash } from 'node:crypto';
const subtle = webcrypto.subtle;
const b64url = (b) => Buffer.from(b).toString('base64url');

function cborEncode(v) {
  const head = (major, n) => {
    if (n < 24) return Buffer.from([(major << 5) | n]);
    if (n < 256) return Buffer.from([(major << 5) | 24, n]);
    if (n < 65536) { const b = Buffer.alloc(3); b[0] = (major << 5) | 25; b.writeUInt16BE(n, 1); return b; }
    const b = Buffer.alloc(5); b[0] = (major << 5) | 26; b.writeUInt32BE(n, 1); return b;
  };
  if (typeof v === 'number') return v >= 0 ? head(0, v) : head(1, -1 - v);
  if (typeof v === 'string') { const s = Buffer.from(v); return Buffer.concat([head(3, s.length), s]); }
  if (v instanceof Uint8Array) return Buffer.concat([head(2, v.length), Buffer.from(v)]);
  if (v instanceof Map) return Buffer.concat([head(5, v.size), ...[...v].flatMap(([k, x]) => [cborEncode(k), cborEncode(x)])]);
  if (Array.isArray(v)) return Buffer.concat([head(4, v.length), ...v.map(cborEncode)]);
  throw new Error('cbor: unsupported');
}

function rawToDer(raw) {
  const int = (b) => { let i = 0; while (i < b.length - 1 && b[i] === 0) i++; let x = b.subarray(i); if (x[0] & 0x80) x = Buffer.concat([Buffer.from([0]), x]); return Buffer.concat([Buffer.from([0x02, x.length]), x]); };
  const r = int(Buffer.from(raw.subarray(0, 32))), s = int(Buffer.from(raw.subarray(32)));
  return Buffer.concat([Buffer.from([0x30, r.length + s.length]), r, s]);
}

export class SoftAuthenticator {
  constructor({ rpId, origin, uv = true, counter = 0 }) { Object.assign(this, { rpId, origin, uv, counter }); }
  async create(challenge) {
    this.keys = await subtle.generateKey({ name: 'ECDSA', namedCurve: 'P-256' }, true, ['sign', 'verify']);
    const jwk = await subtle.exportKey('jwk', this.keys.publicKey);
    this.credId = webcrypto.getRandomValues(new Uint8Array(32));
    const cose = new Map([[1, 2], [3, -7], [-1, 1], [-2, Buffer.from(jwk.x, 'base64url')], [-3, Buffer.from(jwk.y, 'base64url')]]);
    const authData = this.authData(0x45, Buffer.concat([Buffer.alloc(16), Buffer.from([0, 32]), Buffer.from(this.credId), cborEncode(cose)]));
    const clientDataJSON = Buffer.from(JSON.stringify({ type: 'webauthn.create', challenge, origin: this.origin, crossOrigin: false }));
    const att = cborEncode(new Map([['fmt', 'none'], ['attStmt', new Map()], ['authData', authData]]));
    return { id: b64url(this.credId), rawId: b64url(this.credId), type: 'public-key',
      response: { clientDataJSON: b64url(clientDataJSON), attestationObject: b64url(att) } };
  }
  authData(flags, extra = Buffer.alloc(0)) {
    const rpHash = createHash('sha256').update(this.rpId).digest();
    const f = this.uv ? flags : flags & ~0x04;
    const cnt = Buffer.alloc(4); cnt.writeUInt32BE(this.counter);
    return Buffer.concat([rpHash, Buffer.from([f]), cnt, extra]);
  }
  async get(challenge, { origin = this.origin, counterStep = 1 } = {}) {
    this.counter += counterStep;
    const authData = this.authData(0x05);
    const clientDataJSON = Buffer.from(JSON.stringify({ type: 'webauthn.get', challenge, origin, crossOrigin: false }));
    const signed = Buffer.concat([authData, createHash('sha256').update(clientDataJSON).digest()]);
    const raw = new Uint8Array(await subtle.sign({ name: 'ECDSA', hash: 'SHA-256' }, this.keys.privateKey, signed));
    return { id: b64url(this.credId), rawId: b64url(this.credId), type: 'public-key',
      response: { clientDataJSON: b64url(clientDataJSON), authenticatorData: b64url(authData), signature: b64url(rawToDer(raw)) } };
  }
}
