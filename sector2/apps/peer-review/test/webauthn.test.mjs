// Passkey verifier against a software authenticator: the happy path, then
// every way an attacker or a broken client could get it wrong.
import { verifyRegistration, verifyAuthentication } from '../worker/webauthn.mjs';
import { SoftAuthenticator } from './softauthn.mjs';

const rpId = 'review.example', origin = 'https://review.example';
let pass = 0, fail = 0;
const ok = (label, cond) => { if (cond) pass++; else { fail++; console.log('FAIL', label); } };
const rejects = async (label, fn, re) => {
  try { await fn(); fail++; console.log('FAIL (accepted)', label); }
  catch (e) { if (re && !re.test(e.message)) { fail++; console.log('FAIL (wrong error)', label, e.message); } else pass++; }
};

const a = new SoftAuthenticator({ rpId, origin });
const reg = await a.create('chal-1');
const cred = await verifyRegistration(reg.response, { challenge: 'chal-1', origin, rpId });
ok('registration returns ES256 key', cred.alg === -7 && cred.jwk.crv === 'P-256' && cred.credentialId === reg.id);

await rejects('registration: wrong challenge', () => verifyRegistration(reg.response, { challenge: 'other', origin, rpId }), /challenge/);
await rejects('registration: wrong origin', () => verifyRegistration(reg.response, { challenge: 'chal-1', origin: 'https://evil.example', rpId }), /origin/);
await rejects('registration: other site', () => verifyRegistration(reg.response, { challenge: 'chal-1', origin, rpId: 'evil.example' }), /different site/);
const noUv = new SoftAuthenticator({ rpId, origin, uv: false });
const regNoUv = await noUv.create('chal-2');
await rejects('registration: no fingerprint/PIN', () => verifyRegistration(regNoUv.response, { challenge: 'chal-2', origin, rpId }), /verification/);

const stored = { alg: cred.alg, jwk: cred.jwk, signCount: cred.signCount };
const as1 = await a.get('chal-3');
const r1 = await verifyAuthentication(as1.response, stored, { challenge: 'chal-3', origin, rpId });
ok('sign-in verifies, counter advances', r1.signCount === 1);
stored.signCount = r1.signCount;

await rejects('sign-in: replayed (same counter)', () => verifyAuthentication(as1.response, stored, { challenge: 'chal-3', origin, rpId }), /counter/);
const as2 = await a.get('chal-4');
await rejects('sign-in: wrong challenge', () => verifyAuthentication(as2.response, stored, { challenge: 'chal-x', origin, rpId }), /challenge/);
const phish = await a.get('chal-5', { origin: 'https://review-example.evil' });
await rejects('sign-in: phishing origin', () => verifyAuthentication(phish.response, stored, { challenge: 'chal-5', origin, rpId }), /origin/);
const as3 = await a.get('chal-6');
const tampered = { ...as3.response, clientDataJSON: Buffer.from(JSON.stringify({ type: 'webauthn.get', challenge: 'chal-6', origin, crossOrigin: false, extra: 1 })).toString('base64url') };
await rejects('sign-in: tampered clientData', () => verifyAuthentication(tampered, stored, { challenge: 'chal-6', origin, rpId }), /signature/);
const other = new SoftAuthenticator({ rpId, origin }); await other.create('x');
const forged = await other.get('chal-7');
await rejects('sign-in: someone else\'s key', () => verifyAuthentication(forged.response, stored, { challenge: 'chal-7', origin, rpId }), /signature/);
const as4 = await a.get('chal-8');
const r4 = await verifyAuthentication(as4.response, stored, { challenge: 'chal-8', origin, rpId });
ok('legit sign-in after the attacks still works', r4.signCount > stored.signCount);

console.log(fail ? `${fail} FAILED, ${pass} passed` : `all ${pass} passkey checks pass`);
process.exit(fail ? 1 : 0);
