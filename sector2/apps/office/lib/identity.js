// identity.js — Phoenix Office, Module 5 (2026-09-07)
// UnitedSys — United Systems | jwl247 | GPL-3.0
//
// Pluggable author identity. DESIGN.md "Authorship = pluggable identity,
// Phoenix's own always sovereign": every custody handoff records WHICH
// verified identity did it, resolved to one canonical author_id that can
// carry several linked credentials.
//
//   fingerprint  the hardware fingerprint (fingerprint.js). Always works.
//                Zero network, zero account, and it NEVER needs the D1
//                office_authors table — this is the sovereign anchor.
//   windows      the OS account's SID. No new sign-in flow.
//   google       an OpenID sub, via the OAuth 2.0 device-authorization
//                flow (no embedded browser). Optional; needs a client id.
//
// The canonical author_id is DERIVED from a credential (deterministic,
// offline). The D1 table only *links* alternate credentials to an existing
// author_id — so a person who forges on their Phoenix box and signs on a
// second machine with Google still resolves to one identity, but nothing
// breaks if D1 is unreachable.
//
// document.js is unchanged — its handoff functions already take an opaque
// identity string in `by`. Module 6 (the UI) calls resolveAuthor() and
// passes the returned author_id into createDocument / fillField / sign.
//
//   const { resolveAuthor, workerAuthStore } = require('./lib/identity');
//   const store = workerAuthStore({ workerUrl, auth });          // optional
//   const me = await resolveAuthor({ prefer: 'windows', store }); // or 'fingerprint'
//   let doc = document.createDocument({ fieldNames, authorFingerprint: me.author_id, counterparty });

const crypto = require('crypto');
const { machineFingerprint, safeRun } = require('./fingerprint');

const CRED_TYPES = ['fingerprint', 'windows', 'google'];
const GOOGLE_DEVICE_CODE_URL = 'https://oauth2.googleapis.com/device/code';
const GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token';

// ── credential collection ────────────────────────────────────────────────────

// Current Windows user's SID, or null off-Windows / on failure. Uses
// fingerprint.js's safeRun (timeout, windowsHide, never throws).
function windowsSid() {
  if (process.platform !== 'win32') return null;
  const out = safeRun('powershell.exe', [
    '-NoProfile', '-NonInteractive', '-Command',
    '[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value',
  ]);
  const m = /^S-1-\d+(-\d+)+$/m.exec((out || '').trim());
  return m ? m[0] : null;
}

// Build the { type, value } credential for one type. Returns null if that
// credential isn't available here (e.g. 'windows' off-Windows, or 'google'
// with no id token supplied).
function credentialFor(type, opts = {}) {
  switch (type) {
    case 'fingerprint':
      return { type, value: machineFingerprint() };
    case 'windows': {
      const sid = windowsSid();
      return sid ? { type, value: sid } : null;
    }
    case 'google': {
      if (!opts.googleIdToken) return null;
      const claims = googleSubFromIdToken(opts.googleIdToken, opts);
      return claims && claims.sub ? { type, value: claims.sub, email: claims.email || null } : null;
    }
    default:
      throw new Error(`unknown credential type: ${type}`);
  }
}

// ── canonical author_id ──────────────────────────────────────────────────────

// Deterministic, offline. The same credential always yields the same id.
// Prefix marks which credential seeded it (informational only).
function deriveAuthorId(credential) {
  if (!credential || !credential.type || !credential.value) {
    throw new Error('deriveAuthorId needs a { type, value } credential');
  }
  const h = crypto.createHash('sha3-512')
    .update(`${credential.type}|${credential.value}`, 'utf8')
    .digest('hex');
  return `a_${credential.type[0]}${h.slice(0, 30)}`;
}

// ── resolve ──────────────────────────────────────────────────────────────────

// Resolve the acting author to a canonical author_id.
//   opts.prefer        'fingerprint' (default) | 'windows' | 'google'
//   opts.googleIdToken  id_token from the device-code flow (for prefer:'google')
//   opts.store          { lookup(type,value)->author_id|null, link(row)->row }
//                       — usually workerAuthStore(); omit for offline/sovereign
//   opts.fallback       try the remaining types if `prefer` is unavailable
//                       (default true; order fingerprint -> windows -> google)
// Returns { author_id, credential:{type,value}, source:'d1'|'derived', linked:bool }.
// Never throws for an unreachable/failing store — degrades to 'derived'.
async function resolveAuthor(opts = {}) {
  const prefer = opts.prefer || 'fingerprint';
  if (!CRED_TYPES.includes(prefer)) throw new Error(`prefer must be one of ${CRED_TYPES.join(', ')}`);

  const order = opts.fallback === false
    ? [prefer]
    : [prefer, ...CRED_TYPES.filter(t => t !== prefer)];

  let credential = null;
  for (const t of order) {
    credential = credentialFor(t, opts);
    if (credential) break;
  }
  if (!credential) {
    // fingerprint is always available, so this only happens if prefer is
    // pinned with fallback:false to a type that isn't here
    throw new Error(`no '${prefer}' credential available on this machine`);
  }

  const store = opts.store;
  if (store && typeof store.lookup === 'function') {
    let found = null;
    try { found = await store.lookup(credential.type, credential.value); }
    catch (_) { found = null; } // unreachable store -> sovereign fallback
    if (found) {
      return { author_id: found, credential, source: 'd1', linked: true };
    }
  }

  const author_id = deriveAuthorId(credential);
  let linked = false;
  if (store && typeof store.link === 'function') {
    try {
      await store.link({ author_id, credential_type: credential.type, credential_value: credential.value });
      linked = true;
    } catch (_) { linked = false; } // best effort — resolution still stands
  }
  return { author_id, credential, source: 'derived', linked };
}

// Attach another credential (a Windows SID, a Google sub) to an author_id
// that already exists — so future resolveAuthor() calls with that
// credential return the same identity. Needs a store.
async function linkCredential({ authorId, type, value, store }) {
  if (!authorId) throw new Error('linkCredential needs authorId');
  if (!CRED_TYPES.includes(type)) throw new Error(`type must be one of ${CRED_TYPES.join(', ')}`);
  if (!value) throw new Error('linkCredential needs value');
  if (!store || typeof store.link !== 'function') throw new Error('linkCredential needs a store with link()');
  return store.link({ author_id: authorId, credential_type: type, credential_value: value });
}

// ── D1-backed store (talks to office-notify-worker /author routes) ────────────

function workerAuthStore({ workerUrl, auth, fetchImpl } = {}) {
  if (!workerUrl) throw new Error('workerAuthStore needs workerUrl');
  const f = fetchImpl || (typeof fetch === 'function' ? fetch : null);
  if (!f) throw new Error('no fetch available — pass fetchImpl on older Node');
  const base = String(workerUrl).replace(/\/+$/, '');
  const headers = auth ? { Authorization: `Bearer ${auth}` } : {};

  return {
    async lookup(type, value) {
      const res = await f(`${base}/author/${encodeURIComponent(type)}/${encodeURIComponent(value)}`, { headers });
      if (res.status === 404) return null;
      if (!res.ok) throw new Error(`office-notify-worker ${res.status}`);
      const body = await res.json();
      return body.author_id || null;
    },
    async link(row) {
      const res = await f(`${base}/author/link`, {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify(row),
      });
      const text = await res.text();
      if (!res.ok) throw new Error(`office-notify-worker ${res.status}: ${text.slice(0, 200)}`);
      return JSON.parse(text);
    },
  };
}

// ── Google device-authorization flow (RFC 8628) ──────────────────────────────
// No embedded browser: the user opens a URL on any device and types a
// short code. Needs a Google OAuth client (console.cloud.google.com,
// "TV and Limited Input" type). Without a client id, the google path is
// simply unavailable and fingerprint/windows still work.

async function googleDeviceCodeStart({ clientId, scope, fetchImpl } = {}) {
  if (!clientId) throw new Error('googleDeviceCodeStart needs clientId');
  const f = fetchImpl || fetch;
  const res = await f(GOOGLE_DEVICE_CODE_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ client_id: clientId, scope: scope || 'openid email' }).toString(),
  });
  if (!res.ok) throw new Error(`google device/code ${res.status}: ${(await res.text()).slice(0, 200)}`);
  return res.json(); // { device_code, user_code, verification_url, expires_in, interval }
}

// One poll. Throws Error with .code === 'authorization_pending' | 'slow_down'
// while the user hasn't finished; 'access_denied' | 'expired_token' are
// terminal. On success returns { id_token, access_token, ... }.
async function googleDeviceCodePoll({ clientId, clientSecret, deviceCode, fetchImpl } = {}) {
  if (!clientId || !deviceCode) throw new Error('googleDeviceCodePoll needs clientId and deviceCode');
  const f = fetchImpl || fetch;
  const params = {
    client_id: clientId,
    device_code: deviceCode,
    grant_type: 'urn:ietf:params:oauth:grant-type:device_code',
  };
  if (clientSecret) params.client_secret = clientSecret; // Google requires this even for the "public" device flow
  const res = await f(GOOGLE_TOKEN_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams(params).toString(),
  });
  const body = await res.json().catch(() => ({}));
  if (res.ok) return body;
  const e = new Error(body.error_description || body.error || `google token ${res.status}`);
  e.code = body.error || 'unknown';
  throw e;
}

// Decode + sanity-check a Google id_token. The token came straight from
// Google's token endpoint over TLS in response to our own device_code, so
// decoding is enough to bind identity; full JWKS signature verification is
// a hardening step (noted in PLAN-modules-3-6.md). We still check aud/iss/exp.
function googleSubFromIdToken(idToken, opts = {}) {
  if (typeof idToken !== 'string' || idToken.split('.').length !== 3) {
    throw new Error('not a JWT');
  }
  const payload = JSON.parse(Buffer.from(idToken.split('.')[1], 'base64url').toString('utf8'));
  if (opts.clientId && payload.aud !== opts.clientId) {
    throw new Error('id_token aud does not match clientId');
  }
  if (payload.iss !== 'accounts.google.com' && payload.iss !== 'https://accounts.google.com') {
    throw new Error(`unexpected id_token iss: ${payload.iss}`);
  }
  if (opts.checkExpiry !== false && typeof payload.exp === 'number' && payload.exp * 1000 < Date.now()) {
    throw new Error('id_token expired');
  }
  return {
    sub: payload.sub,
    email: payload.email || null,
    email_verified: payload.email_verified === true || payload.email_verified === 'true',
    name: payload.name || null,
  };
}

module.exports = {
  CRED_TYPES,
  windowsSid, credentialFor, deriveAuthorId,
  resolveAuthor, linkCredential, workerAuthStore,
  googleDeviceCodeStart, googleDeviceCodePoll, googleSubFromIdToken,
};
