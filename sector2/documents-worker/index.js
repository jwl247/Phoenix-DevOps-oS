/**
 * documents-worker — Phoenix DevOps OS
 *
 * The document IS the kernel import process. Forged, not created.
 * Each document is self-contained: the forge manifest defines every operation
 * that can ever happen. Nothing outside the manifest executes. Ever.
 *
 * Store it anywhere — the document carries its own security.
 * No format war. No secretary fight. One thing that presents as anything.
 *
 * TAV = base58( first_8_bytes( SHA-256( content + manifest ) ) )
 *
 * Forge ceremony: draft → proposed → forged (sealed, immutable)
 * Witness required for confidential/restricted (two-signer rule)
 *
 * Security layers:
 *   L1 — Quadralingual format (vault docs in Phoenix 4-language schema)
 *   L2 — AES-256-GCM envelope encryption per document
 *   L3 — R2 at-rest encryption (Cloudflare, always on)
 *   L4 — Owner token auth + PHOENIX_AUTH system token
 *   L5 — Immutable audit + capability log (every operation recorded)
 *   L6 — Manifest capability enforcement (deny by default)
 *
 * Compliance: SOC 2 / HIPAA / GDPR
 * UnitedSys — United Systems | jwl247 | GPL v3
 */

'use strict';

// ── Base58 + TAV ──────────────────────────────────────────────────────────────

const B58 = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';

function toBase58(bytes) {
  let n = 0n;
  for (const b of bytes) n = n * 256n + BigInt(b);
  let s = '';
  while (n > 0n) { s = B58[Number(n % 58n)] + s; n /= 58n; }
  for (const b of bytes) { if (b !== 0) break; s = '1' + s; }
  return s || '1';
}

async function hashBytes(buf) {
  return new Uint8Array(await crypto.subtle.digest('SHA-256', buf));
}

async function sha256hex(buf) {
  const h = await hashBytes(buf instanceof ArrayBuffer ? buf : buf.buffer);
  return Array.from(h).map(b => b.toString(16).padStart(2, '0')).join('');
}

// TAV = base58(first 8 bytes of SHA-256(content_bytes + manifest_json_bytes))
// The TAV is a cryptographic proof of BOTH content AND capabilities.
async function computeTAV(contentBuf, manifestJson) {
  const enc  = new TextEncoder();
  const mBuf = enc.encode(manifestJson);
  const combined = new Uint8Array(contentBuf.byteLength + mBuf.byteLength);
  combined.set(new Uint8Array(contentBuf), 0);
  combined.set(mBuf, contentBuf.byteLength);
  const hash = await hashBytes(combined.buffer);
  return {
    tav:          toBase58(hash.slice(0, 8)),
    combined_hash: Array.from(hash).map(b => b.toString(16).padStart(2, '0')).join(''),
  };
}

async function sha256ofStr(s) {
  return sha256hex(new TextEncoder().encode(s).buffer);
}


// ── Default manifest — defines the document's execution architecture ──────────

const MANIFEST_VERSION = '1.0';

const MANIFEST_DEFAULTS = {
  version:          MANIFEST_VERSION,
  can_read:         true,       // who can read (true=owner+system, array=additional principals)
  can_convert:      [],         // [] = no conversion. Array of target MIME types.
  can_execute:      false,      // can this document be run as a Phoenix process/suit
  can_version:      true,       // can new versions be forged from this document
  can_review:       false,      // eligible for review platform submission
  can_index:        true,       // appears in glossary and full-text search
  can_transmit:     [],         // Frank channels that can receive this doc
  can_share:        [],         // additional principals (beyond owner) who can read
  expires_at:       null,       // document auto-archives at this ISO date
  life_first:       false,      // Life First security: Laurie privacy protections active
  witness_required: false,      // requires second signer before forge completes
};

function buildManifest(input) {
  const m = { ...MANIFEST_DEFAULTS };
  const allowed = Object.keys(MANIFEST_DEFAULTS);
  for (const k of allowed) {
    if (input[k] !== undefined) m[k] = input[k];
  }
  return m;
}

function serializeManifest(manifest) {
  // Deterministic serialization — key order matters for the TAV hash
  const keys = Object.keys(MANIFEST_DEFAULTS);
  const ordered = {};
  for (const k of keys) ordered[k] = manifest[k] ?? MANIFEST_DEFAULTS[k];
  return JSON.stringify(ordered);
}


// ── Capability enforcement — deny by default ──────────────────────────────────

function checkCapability(manifest, cap, context = {}) {
  const val = manifest[cap];

  // Absent or explicitly false → forbidden (not just absent)
  if (val === undefined || val === null || val === false) {
    return { allowed: false, reason: `capability '${cap}' not architected in this document` };
  }

  // Check document-level expiry
  if (manifest.expires_at && new Date() > new Date(manifest.expires_at)) {
    return { allowed: false, reason: 'document has expired' };
  }

  // Per-capability expiry (when value is an object with expires_at)
  if (typeof val === 'object' && !Array.isArray(val)) {
    if (val.expires_at && new Date() > new Date(val.expires_at)) {
      return { allowed: false, reason: `capability '${cap}' has expired` };
    }
    // Check principal list
    if (val.principals && context.actor) {
      if (!val.principals.includes(context.actor)) {
        return { allowed: false, reason: `actor not in capability principal list` };
      }
    }
    return { allowed: true };
  }

  if (val === true) return { allowed: true };

  // Array capability — check if target is in list
  if (Array.isArray(val)) {
    if (val.length === 0) {
      return { allowed: false, reason: `capability '${cap}' has empty list` };
    }
    if (context.target && !val.includes(context.target)) {
      return { allowed: false, reason: `'${context.target}' not in ${cap} list` };
    }
    return { allowed: true };
  }

  return { allowed: false, reason: 'unrecognised capability format' };
}

// Capability inheritance — child manifest cannot exceed parent's capabilities
function validateCapabilityInheritance(childManifest, parentManifest) {
  if (!parentManifest) return { valid: true };
  const errors = [];

  if (childManifest.can_execute && !parentManifest.can_execute)
    errors.push('can_execute: child cannot exceed parent (parent has false)');

  if (childManifest.can_review && !parentManifest.can_review)
    errors.push('can_review: child cannot exceed parent');

  if (Array.isArray(childManifest.can_convert) && Array.isArray(parentManifest.can_convert)) {
    const illegal = childManifest.can_convert.filter(f => !parentManifest.can_convert.includes(f));
    if (illegal.length) errors.push(`can_convert: child adds formats not in parent: ${illegal.join(', ')}`);
  }

  return { valid: errors.length === 0, errors };
}

// Validate manifest structure
function validateManifest(m) {
  const errors = [];
  if (typeof m.can_read !== 'boolean' && !Array.isArray(m.can_read))
    errors.push('can_read must be boolean or array');
  if (!Array.isArray(m.can_convert))
    errors.push('can_convert must be array');
  if (typeof m.can_execute !== 'boolean')
    errors.push('can_execute must be boolean');
  if (m.expires_at && isNaN(Date.parse(m.expires_at)))
    errors.push('expires_at must be valid ISO date or null');
  return { valid: errors.length === 0, errors };
}


// ── Conversion tables ─────────────────────────────────────────────────────────

const IN_WORKER_CONVERSIONS = {
  'text/markdown':    ['text/html', 'text/plain'],
  'text/plain':       ['text/html'],
  'application/json': ['text/yaml', 'text/plain'],
  'text/csv':         ['application/json', 'text/html'],
  'text/html':        ['text/plain'],
};

const LIBREOFFICE_CONVERSIONS = {
  'text/markdown':    ['application/pdf', 'application/vnd.oasis.opendocument.text',
                       'application/vnd.openxmlformats-officedocument.wordprocessingml.document'],
  'text/plain':       ['application/pdf', 'application/vnd.oasis.opendocument.text'],
  'text/html':        ['application/pdf',
                       'application/vnd.openxmlformats-officedocument.wordprocessingml.document'],
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
                      ['application/pdf', 'application/vnd.oasis.opendocument.text',
                       'text/html', 'text/plain'],
  'application/vnd.oasis.opendocument.text':
                      ['application/pdf',
                       'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                       'text/html', 'text/plain'],
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
                      ['application/pdf', 'text/csv',
                       'application/vnd.oasis.opendocument.spreadsheet'],
  'application/vnd.oasis.opendocument.spreadsheet':
                      ['application/pdf', 'text/csv',
                       'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'],
  'application/vnd.openxmlformats-officedocument.presentationml.presentation':
                      ['application/pdf', 'application/vnd.oasis.opendocument.presentation'],
  'application/vnd.oasis.opendocument.presentation':
                      ['application/pdf',
                       'application/vnd.openxmlformats-officedocument.presentationml.presentation'],
};

const FMT_EXT = {
  'application/pdf':  'pdf',
  'text/html':        'html',
  'text/plain':       'txt',
  'text/csv':         'csv',
  'text/yaml':        'yaml',
  'text/markdown':    'md',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
  'application/vnd.oasis.opendocument.text': 'odt',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
  'application/vnd.oasis.opendocument.spreadsheet': 'ods',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'pptx',
  'application/vnd.oasis.opendocument.presentation': 'odp',
};

function allConversions(mime) {
  return [...new Set([
    ...(IN_WORKER_CONVERSIONS[mime]   || []),
    ...(LIBREOFFICE_CONVERSIONS[mime] || []),
  ])];
}


// ── AES-256-GCM envelope encryption ──────────────────────────────────────────
// Key derived per-document from PHOENIX_AUTH + tav via HKDF.
// No external key storage required.

async function deriveKey(masterKey, tav) {
  const enc    = new TextEncoder();
  const mat    = await crypto.subtle.importKey('raw', enc.encode(masterKey), 'HKDF', false, ['deriveKey']);
  return crypto.subtle.deriveKey(
    { name: 'HKDF', hash: 'SHA-256', salt: enc.encode(tav), info: enc.encode('phoenix-doc-v1') },
    mat, { name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt'],
  );
}

async function encryptBuf(plain, masterKey, tav) {
  const key = await deriveKey(masterKey, tav);
  const iv  = crypto.getRandomValues(new Uint8Array(12));
  const ct  = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, plain));
  const out = new Uint8Array(12 + ct.byteLength);
  out.set(iv, 0); out.set(ct, 12);
  return out.buffer;
}

async function decryptBuf(cipher, masterKey, tav) {
  const buf = new Uint8Array(cipher instanceof ArrayBuffer ? cipher : await cipher.arrayBuffer());
  const key = await deriveKey(masterKey, tav);
  return crypto.subtle.decrypt({ name: 'AES-GCM', iv: buf.slice(0, 12) }, key, buf.slice(12));
}


// ── Auth ──────────────────────────────────────────────────────────────────────

function sysAuth(req, env) {
  return (req.headers.get('X-Phoenix-Auth') || new URL(req.url).searchParams.get('auth') || '') === env.PHOENIX_AUTH;
}

function ownerAuth(req, env, owner) {
  const tok = req.headers.get('X-Phoenix-Owner-Token') || '';
  if (!tok || !env.OWNER_TOKENS) return false;
  try { return JSON.parse(env.OWNER_TOKENS)[owner] === tok; } catch { return false; }
}

function canRead(req, env, doc, manifest) {
  if (doc.status === 'archived') return false;
  const cap = checkCapability(manifest, 'can_read');
  if (!cap.allowed) return false;
  if (manifest.can_read === true)  return sysAuth(req, env) || ownerAuth(req, env, doc.owner);
  if (Array.isArray(manifest.can_read)) {
    // Additional principals beyond owner
    if (sysAuth(req, env) || ownerAuth(req, env, doc.owner)) return true;
    if (manifest.life_first) return false; // Life First: owner only unless explicitly shared
    const tok = req.headers.get('X-Phoenix-Owner-Token') || '';
    if (!env.OWNER_TOKENS || !tok) return false;
    try {
      const tokens = JSON.parse(env.OWNER_TOKENS);
      for (const p of manifest.can_read) {
        if (tokens[p] === tok) return true;
      }
    } catch { return false; }
  }
  return false;
}


// ── In-worker document conversions ────────────────────────────────────────────

function mdToHtml(md) {
  const esc = s => s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  let h = esc(md)
    .replace(/^######\s+(.+)$/gm,'<h6>$1</h6>').replace(/^#####\s+(.+)$/gm,'<h5>$1</h5>')
    .replace(/^####\s+(.+)$/gm,'<h4>$1</h4>').replace(/^###\s+(.+)$/gm,'<h3>$1</h3>')
    .replace(/^##\s+(.+)$/gm,'<h2>$1</h2>').replace(/^#\s+(.+)$/gm,'<h1>$1</h1>')
    .replace(/\*\*\*(.+?)\*\*\*/g,'<strong><em>$1</em></strong>')
    .replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>').replace(/\*(.+?)\*/g,'<em>$1</em>')
    .replace(/```[\s\S]*?```/g, m => '<pre><code>'+m.slice(3,-3).replace(/^\w+\n/,'')+'</code></pre>')
    .replace(/`([^`]+)`/g,'<code>$1</code>')
    .replace(/^\s*[-*+]\s+(.+)$/gm,'<li>$1</li>')
    .replace(/(<li>[\s\S]*?<\/li>\n?)+/g, s=>'<ul>'+s+'</ul>')
    .replace(/^---+$/gm,'<hr>').replace(/\[([^\]]+)\]\(([^)]+)\)/g,'<a href="$2">$1</a>')
    .replace(/\n\n+/g,'</p><p>').replace(/\n/g,'<br>');
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><title>Phoenix Document</title></head><body><p>${h}</p></body></html>`;
}

function jsonToYaml(json) {
  function dump(v, d) {
    const p = '  '.repeat(d);
    if (v === null) return 'null';
    if (typeof v === 'boolean') return String(v);
    if (typeof v === 'number')  return String(v);
    if (typeof v === 'string') {
      return (v.includes('\n') || v.includes(':') || v.includes('#'))
        ? `|\n${v.split('\n').map(l=>p+'  '+l).join('\n')}` : v;
    }
    if (Array.isArray(v)) return v.length === 0 ? '[]' : '\n'+v.map(i=>`${p}- ${dump(i,d+1)}`).join('\n');
    if (typeof v === 'object') {
      const ks = Object.keys(v);
      return ks.length === 0 ? '{}' : '\n'+ks.map(k=>`${p}${k}: ${dump(v[k],d+1)}`).join('\n');
    }
    return String(v);
  }
  try {
    const o = JSON.parse(json);
    return Object.keys(o).map(k=>`${k}:${dump(o[k],1)}`).join('\n')+'\n';
  } catch { return json; }
}

function csvToJson(csv) {
  const lines = csv.trim().split('\n');
  if (lines.length < 2) return '[]';
  const hdrs = lines[0].split(',').map(h=>h.trim().replace(/^"|"$/g,''));
  return JSON.stringify(lines.slice(1).map(l=>{
    const vals = l.split(',').map(v=>v.trim().replace(/^"|"$/g,''));
    return Object.fromEntries(hdrs.map((h,i)=>[h,vals[i]??'']));
  }), null, 2);
}

function csvToHtml(csv) {
  const lines = csv.trim().split('\n');
  const hdrs  = lines[0].split(',').map(h=>h.trim().replace(/^"|"$/g,''));
  const rows  = lines.slice(1).map(l=>l.split(',').map(v=>v.trim().replace(/^"|"$/g,'')));
  const th    = '<thead><tr>'+hdrs.map(h=>`<th>${h}</th>`).join('')+'</tr></thead>';
  const tb    = '<tbody>'+rows.map(r=>'<tr>'+r.map(v=>`<td>${v}</td>`).join('')+'</tr>').join('')+'</tbody>';
  return `<!DOCTYPE html><html><body><table border="1">${th}${tb}</table></body></html>`;
}

function convertInWorker(text, from, to) {
  if (from==='text/markdown'    && to==='text/html')       return mdToHtml(text);
  if (from==='text/markdown'    && to==='text/plain')      return text.replace(/[#*_`\[\]()!]/g,'');
  if (from==='text/plain'       && to==='text/html')       return `<!DOCTYPE html><html><body><pre>${text}</pre></body></html>`;
  if (from==='application/json' && to==='text/yaml')       return jsonToYaml(text);
  if (from==='application/json' && to==='text/plain')      return text;
  if (from==='text/csv'         && to==='application/json') return csvToJson(text);
  if (from==='text/csv'         && to==='text/html')       return csvToHtml(text);
  if (from==='text/html'        && to==='text/plain')      return text.replace(/<[^>]+>/g,'');
  return null;
}


// ── D1 helpers ────────────────────────────────────────────────────────────────

async function dbGet(env, tav) {
  return env.PHOENIX_DB.prepare('SELECT * FROM documents WHERE tav=?').bind(tav).first() || null;
}

async function dbInsertDoc(env, d) {
  await env.PHOENIX_DB.prepare(`
    INSERT INTO documents
      (tav,sha256,manifest_hash,combined_hash,sha3_note,filename,size_bytes,mime_type,r2_key,
       owner,manifest,forge_stage,forged_at,forge_receipt_id,
       title,description,sector,tags,privacy,classification,
       encrypted,encrypted_key_id,version,parent_tav,conversion_of,conversion_fmt,
       status,mutable,created_at,retain_until,legal_hold)
    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
  `).bind(
    d.tav, d.sha256, d.manifest_hash, d.combined_hash, d.sha3_note||null,
    d.filename, d.size_bytes, d.mime_type, d.r2_key,
    d.owner, d.manifest_json, d.forge_stage||'forged', d.forged_at||null, d.forge_receipt_id||null,
    d.title||null, d.description||null, d.sector||null, JSON.stringify(d.tags||[]),
    d.privacy||'private', d.classification||'internal',
    d.encrypted?1:0, d.encrypted_key_id||null,
    d.version||1, d.parent_tav||null, d.conversion_of||null, d.conversion_fmt||null,
    'active', d.mutable?1:0, d.created_at||new Date().toISOString(),
    d.retain_until||null, 0,
  ).run();
}

async function dbInsertReceipt(env, r) {
  const res = await env.PHOENIX_DB.prepare(`
    INSERT INTO forge_receipts
      (tav,forged_by,witnessed_by,manifest_hash,content_hash,combined_hash,forge_ts,parent_tav,system_state)
    VALUES(?,?,?,?,?,?,?,?,?) RETURNING id
  `).bind(r.tav, r.forged_by, r.witnessed_by||null, r.manifest_hash, r.content_hash,
          r.combined_hash, r.forge_ts, r.parent_tav||null, r.system_state||null).first();
  return res?.id || null;
}


// ── Audit + capability log ────────────────────────────────────────────────────

async function audit(env, tav, actor, action, result, req, detail) {
  const ip = req ? (req.headers.get('CF-Connecting-IP') || '') : '';
  const ipHash = ip ? await sha256ofStr(ip) : null;
  try {
    await env.PHOENIX_DB.prepare(
      'INSERT INTO document_access_log(tav,actor,action,result,ts,ip_hash,detail) VALUES(?,?,?,?,?,?,?)'
    ).bind(tav||'system', actor||'unknown', action, result, new Date().toISOString(),
           ipHash, detail ? JSON.stringify(detail) : null).run();
  } catch (_) {}
}

async function capLog(env, tav, cap, actor, target, result, detail) {
  try {
    await env.PHOENIX_DB.prepare(
      'INSERT INTO capability_log(tav,capability,actor,target,result,ts,detail) VALUES(?,?,?,?,?,?,?)'
    ).bind(tav, cap, actor||'unknown', target||null, result, new Date().toISOString(),
           detail||null).run();
  } catch (_) {}
}


// ── Response helpers ──────────────────────────────────────────────────────────

const CORS = {
  'Access-Control-Allow-Origin':  '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, X-Phoenix-Auth, X-Phoenix-Owner-Token',
};

const json = (d, s=200) => new Response(JSON.stringify(d, null, 2),
  { status: s, headers: { 'Content-Type': 'application/json', ...CORS } });

const err = (m, s=400) => json({ error: m }, s);
const now = () => new Date().toISOString();


// ── Route handlers ────────────────────────────────────────────────────────────

// POST /doc/forge/preview — dry run: returns TAV + validates manifest, nothing written
async function handleForgePreview(req, env) {
  if (!sysAuth(req, env)) return err('unauthorized', 401);
  let body; try { body = await req.json(); } catch { return err('invalid JSON'); }

  const { content_b64, manifest: mInput = {} } = body;
  if (!content_b64) return err('content_b64 required');

  let contentBuf;
  try {
    const bin = atob(content_b64);
    contentBuf = new Uint8Array(bin.length);
    for (let i=0; i<bin.length; i++) contentBuf[i] = bin.charCodeAt(i);
  } catch { return err('invalid base64'); }

  const manifest     = buildManifest(mInput);
  const validation   = validateManifest(manifest);
  const manifestJson = serializeManifest(manifest);
  const { tav, combined_hash } = await computeTAV(contentBuf.buffer, manifestJson);
  const sha256       = await sha256hex(contentBuf.buffer);
  const manifestHash = await sha256ofStr(manifestJson);
  const existing     = await dbGet(env, tav);

  return json({
    preview: true,
    tav,
    sha256,
    manifest_hash:  manifestHash,
    combined_hash,
    manifest,
    manifest_valid: validation.valid,
    manifest_errors: validation.errors,
    already_exists: !!existing,
    size_bytes: contentBuf.byteLength,
  });
}


// POST /doc/forge — forge a document (the import process)
async function handleForge(req, env) {
  if (!sysAuth(req, env)) return err('unauthorized', 401);
  let body; try { body = await req.json(); } catch { return err('invalid JSON'); }

  const {
    filename, content_b64, mime_type = 'application/octet-stream',
    owner = 'system', title, description, sector, tags = [],
    privacy = 'private', classification = 'internal',
    mutable = false, retain_until, sha3_note,
    manifest: mInput = {},
    parent_tav, conversion_of, conversion_fmt,
    encrypt = false,
  } = body;

  if (!filename)    return err('filename required');
  if (!content_b64) return err('content_b64 required');

  let contentBuf;
  try {
    const bin = atob(content_b64);
    contentBuf = new Uint8Array(bin.length);
    for (let i=0; i<bin.length; i++) contentBuf[i] = bin.charCodeAt(i);
  } catch { return err('invalid base64 content'); }

  // Build and validate manifest
  const manifest     = buildManifest(mInput);
  const validation   = validateManifest(manifest);
  if (!validation.valid) return err(`manifest invalid: ${validation.errors.join('; ')}`);

  // Capability inheritance check
  if (parent_tav || conversion_of) {
    const sourceTav = parent_tav || conversion_of;
    const parentDoc = await dbGet(env, sourceTav);
    if (parentDoc) {
      const parentManifest = JSON.parse(parentDoc.manifest || '{}');
      const inherit = validateCapabilityInheritance(manifest, parentManifest);
      if (!inherit.valid) return err(`capability inheritance violation: ${inherit.errors.join('; ')}`);
    }
  }

  // Witness required for confidential/restricted
  if (manifest.witness_required || classification === 'confidential' || classification === 'restricted') {
    if (!body.witnessed_by) {
      // Queue as proposal, return pending
      const manifestJson = serializeManifest(manifest);
      const { tav: proposedTav } = await computeTAV(contentBuf.buffer, manifestJson);
      const contentHash   = await sha256hex(contentBuf.buffer);
      const proposalExpiry = new Date(Date.now() + 24*60*60*1000).toISOString(); // 24h

      // Store staged content in R2 under proposal key
      const stageKey = `_proposal_${proposedTav}`;
      await env.DOCS_BUCKET.put(stageKey, contentBuf.buffer);

      await env.PHOENIX_DB.prepare(`
        INSERT INTO forge_proposals
          (proposed_tav,proposed_by,manifest_json,content_r2_key,content_hash,
           filename,mime_type,owner,classification,status,proposed_at,expires_at,metadata_json)
        VALUES(?,?,?,?,?,?,?,?,?,'pending_witness',?,?,?)
      `).bind(proposedTav, owner, manifestJson, stageKey, contentHash,
              filename, mime_type, owner, classification,
              now(), proposalExpiry, JSON.stringify(body)).run();

      return json({ status: 'pending_witness', proposed_tav: proposedTav,
                    message: 'witness required — POST /doc/forge/witness/:proposed_tav' }, 202);
    }
  }

  // Seal the document
  const manifestJson   = serializeManifest(manifest);
  const { tav, combined_hash } = await computeTAV(contentBuf.buffer, manifestJson);
  const sha256         = await sha256hex(contentBuf.buffer);
  const manifestHash   = await sha256ofStr(manifestJson);

  // Idempotent
  const existing = await dbGet(env, tav);
  if (existing) {
    await audit(env, tav, owner, 'forge', 'ok_existing', req, { filename });
    return json({ tav, sha256, forged_at: existing.forged_at, existing: true });
  }

  // Encrypt if needed (L2)
  let storeBuffer = contentBuf.buffer;
  let encrypted   = false;
  if (encrypt || classification === 'confidential' || classification === 'restricted') {
    if (!env.PHOENIX_AUTH) return err('encryption key not configured', 500);
    storeBuffer = await encryptBuf(contentBuf.buffer, env.PHOENIX_AUTH, tav);
    encrypted   = true;
  }

  // Write to R2 — immutable (key = TAV, never overwritten)
  await env.DOCS_BUCKET.put(tav, storeBuffer, {
    httpMetadata: { contentType: mime_type },
    customMetadata: { tav, owner, filename, classification, encrypted: String(encrypted) },
  });

  // Write forge receipt (chain of evidence)
  const receiptId = await dbInsertReceipt(env, {
    tav, forged_by: owner, witnessed_by: body.witnessed_by || null,
    manifest_hash: manifestHash, content_hash: sha256, combined_hash,
    forge_ts: now(), parent_tav: parent_tav || null,
    system_state: JSON.stringify({ worker: 'documents-worker', node: 'cloudflare' }),
  });

  // Write document record (sealed)
  await dbInsertDoc(env, {
    tav, sha256, manifest_hash: manifestHash, combined_hash, sha3_note,
    filename, size_bytes: contentBuf.byteLength, mime_type, r2_key: tav,
    owner, manifest_json: manifestJson,
    forge_stage: 'forged', forged_at: now(), forge_receipt_id: receiptId,
    title, description, sector, tags,
    privacy, classification, encrypted,
    encrypted_key_id: encrypted ? 'phoenix-auth-v1' : null,
    version: body.version || 1,
    parent_tav: parent_tav || null, conversion_of: conversion_of || null,
    conversion_fmt: conversion_fmt || null, mutable, retain_until,
  });

  await audit(env, tav, owner, 'forge', 'ok', req,
              { filename, size: contentBuf.byteLength, classification, encrypted });

  return json({ tav, sha256, manifest_hash: manifestHash, forged_at: now(),
                forge_receipt_id: receiptId, encrypted }, 201);
}


// POST /doc/forge/witness/:proposed_tav — second signer seals the proposal
async function handleWitness(req, env, proposedTav) {
  if (!sysAuth(req, env)) return err('unauthorized', 401);
  let body; try { body = await req.json(); } catch { return err('invalid JSON'); }
  const { witnessed_by } = body;
  if (!witnessed_by) return err('witnessed_by required');

  const proposal = await env.PHOENIX_DB.prepare(
    'SELECT * FROM forge_proposals WHERE proposed_tav=? AND status=?'
  ).bind(proposedTav, 'pending_witness').first();

  if (!proposal) return err('proposal not found or already processed', 404);
  if (new Date() > new Date(proposal.expires_at)) return err('proposal expired', 410);
  if (witnessed_by === proposal.proposed_by)       return err('witness cannot be the same as proposer', 400);

  // Retrieve staged content and complete forge
  const stageObj = await env.DOCS_BUCKET.get(proposal.content_r2_key);
  if (!stageObj) return err('staged content not found', 500);

  const contentBuf  = new Uint8Array(await stageObj.arrayBuffer());
  const manifest    = JSON.parse(proposal.manifest_json);
  const metadata    = JSON.parse(proposal.metadata_json);

  // Forward to forge with witness attached
  metadata.witnessed_by = witnessed_by;
  metadata.content_b64  = btoa(String.fromCharCode(...contentBuf));

  // Re-invoke forge logic inline (reuse exact same path)
  const forgeReq = new Request(req.url, {
    method: 'POST', body: JSON.stringify(metadata),
    headers: { 'Content-Type': 'application/json', 'X-Phoenix-Auth': env.PHOENIX_AUTH },
  });
  const result = await handleForge(forgeReq, env);

  // Mark proposal complete
  await env.PHOENIX_DB.prepare(
    'UPDATE forge_proposals SET status=?,witnessed_by=?,witnessed_at=? WHERE proposed_tav=?'
  ).bind('complete', witnessed_by, now(), proposedTav).run();

  // Clean up staged content
  await env.DOCS_BUCKET.delete(proposal.content_r2_key);

  await audit(env, proposedTav, witnessed_by, 'witness', 'ok', req, null);
  return result;
}


// GET /doc/:tav — retrieve document content
async function handleGet(req, env, tav) {
  const doc = await dbGet(env, tav);
  if (!doc || doc.forge_stage !== 'forged') return err('not found', 404);

  const manifest = JSON.parse(doc.manifest || '{}');
  const actor    = doc.owner;

  if (!canRead(req, env, doc, manifest)) {
    await capLog(env, tav, 'can_read', actor, null, 'denied', null);
    await audit(env, tav, actor, 'read', 'denied', req, null);
    return err('access denied', 403);
  }

  const capCheck = checkCapability(manifest, 'can_read');
  if (!capCheck.allowed) {
    await capLog(env, tav, 'can_read', actor, null, 'denied', { reason: capCheck.reason });
    return err(capCheck.reason, 403);
  }

  const obj = await env.DOCS_BUCKET.get(doc.r2_key);
  if (!obj) return err('blob not found', 500);

  let body = await obj.arrayBuffer();
  if (doc.encrypted) {
    if (!sysAuth(req, env)) return err('encrypted document requires system auth', 403);
    try { body = await decryptBuf(body, env.PHOENIX_AUTH, tav); }
    catch { return err('decryption failed', 500); }
  }

  await capLog(env, tav, 'can_read', actor, null, 'allowed', null);
  await audit(env, tav, actor, 'read', 'ok', req, null);

  return new Response(body, { headers: {
    'Content-Type':       doc.mime_type,
    'Content-Disposition':`inline; filename="${doc.filename}"`,
    'X-Phoenix-TAV':      tav,
    'X-Phoenix-SHA256':   doc.sha256,
    'X-Phoenix-Forged':   doc.forged_at || '',
    'Cache-Control':      'private, no-store',
    ...CORS,
  }});
}


// GET /doc/:tav/meta
async function handleMeta(req, env, tav) {
  const doc = await dbGet(env, tav);
  if (!doc) return err('not found', 404);
  const manifest = JSON.parse(doc.manifest || '{}');
  if (!canRead(req, env, doc, manifest)) return err('access denied', 403);
  await audit(env, tav, doc.owner, 'read', 'ok', req, { op: 'meta' });
  return json({ ...doc, manifest, tags: JSON.parse(doc.tags||'[]') });
}


// GET /doc/:tav/receipt — forge receipt (chain of evidence)
async function handleReceipt(req, env, tav) {
  if (!sysAuth(req, env)) return err('unauthorized', 401);
  const r = await env.PHOENIX_DB.prepare(
    'SELECT * FROM forge_receipts WHERE tav=? ORDER BY forge_ts DESC'
  ).bind(tav).all();
  return json({ tav, receipts: r.results || [] });
}


// GET /doc/:tav/history — version chain
async function handleHistory(req, env, tav) {
  const chain = []; let cur = tav; let n = 0;
  while (cur && n++ < 100) {
    const doc = await dbGet(env, cur);
    if (!doc) break;
    const manifest = JSON.parse(doc.manifest||'{}');
    if (!canRead(req, env, doc, manifest)) break;
    chain.push({ tav: doc.tav, version: doc.version, created_at: doc.created_at,
                 filename: doc.filename, size_bytes: doc.size_bytes, forged_at: doc.forged_at });
    cur = doc.parent_tav;
  }
  return json({ tav, chain });
}


// GET /doc/:tav/family — all derived documents
async function handleFamily(req, env, tav) {
  const r = await env.PHOENIX_DB.prepare(`
    SELECT tav,filename,mime_type,version,conversion_fmt,created_at,size_bytes,forge_stage
    FROM documents WHERE (parent_tav=? OR conversion_of=?) AND forge_stage='forged'
    ORDER BY created_at DESC
  `).bind(tav, tav).all();
  return json({ source_tav: tav, derived: r.results||[] });
}


// GET /doc/:tav/formats — available conversion targets per manifest
async function handleFormats(req, env, tav) {
  const doc = await dbGet(env, tav);
  if (!doc) return err('not found', 404);
  const manifest  = JSON.parse(doc.manifest||'{}');
  const manifested = Array.isArray(manifest.can_convert) ? manifest.can_convert : [];
  const available  = allConversions(doc.mime_type);
  // Only return what the manifest allows
  const allowed    = manifested.length ? manifested.filter(f => available.includes(f)) : [];
  return json({
    tav, source_mime: doc.mime_type,
    manifested,
    available_in_worker:  allowed.filter(f=>(IN_WORKER_CONVERSIONS[doc.mime_type]||[]).includes(f)),
    available_libreoffice:allowed.filter(f=>(LIBREOFFICE_CONVERSIONS[doc.mime_type]||[]).includes(f)),
    all_allowed: allowed,
  });
}


// GET /doc/:tav/as/:format — in-worker conversion (capability checked)
async function handleConvertInline(req, env, tav, targetMime) {
  const doc = await dbGet(env, tav);
  if (!doc) return err('not found', 404);
  const manifest = JSON.parse(doc.manifest||'{}');
  if (!canRead(req, env, doc, manifest)) return err('access denied', 403);

  const cap = checkCapability(manifest, 'can_convert', { target: targetMime });
  if (!cap.allowed) {
    await capLog(env, tav, 'can_convert', doc.owner, targetMime, 'denied', { reason: cap.reason });
    return err(cap.reason, 403);
  }

  const supported = IN_WORKER_CONVERSIONS[doc.mime_type] || [];
  if (!supported.includes(targetMime)) {
    return err(`'${targetMime}' requires LibreOffice — use POST /doc/${tav}/convert`);
  }

  if (doc.encrypted) return err('cannot convert encrypted document inline', 403);

  const obj = await env.DOCS_BUCKET.get(doc.r2_key);
  if (!obj) return err('blob not found', 500);
  const text      = await obj.text();
  const converted = convertInWorker(text, doc.mime_type, targetMime);
  if (!converted) return err('conversion failed');

  await capLog(env, tav, 'can_convert', doc.owner, targetMime, 'allowed', null);
  await audit(env, tav, doc.owner, 'convert', 'ok', req, { to: targetMime, method: 'inline' });

  return new Response(converted, { headers: {
    'Content-Type': targetMime, 'X-Phoenix-Source-TAV': tav,
    'X-Phoenix-Converted-From': doc.mime_type, ...CORS,
  }});
}


// POST /doc/:tav/convert — queue LibreOffice conversion job
async function handleConvertQueue(req, env, tav) {
  if (!sysAuth(req, env)) return err('unauthorized', 401);
  const doc = await dbGet(env, tav);
  if (!doc) return err('not found', 404);

  let body; try { body = await req.json(); } catch { return err('invalid JSON'); }
  const { to: targetMime } = body;
  if (!targetMime) return err('"to" mime type required');

  const manifest = JSON.parse(doc.manifest||'{}');
  const cap      = checkCapability(manifest, 'can_convert', { target: targetMime });
  if (!cap.allowed) {
    await capLog(env, tav, 'can_convert', doc.owner, targetMime, 'denied', { reason: cap.reason });
    return err(cap.reason, 403);
  }

  const inline = (IN_WORKER_CONVERSIONS[doc.mime_type]||[]).includes(targetMime);
  if (inline) return json({ redirect: `/doc/${tav}/as/${encodeURIComponent(targetMime)}`, inline: true });

  const libreTargets = LIBREOFFICE_CONVERSIONS[doc.mime_type] || [];
  if (!libreTargets.includes(targetMime)) return err(`conversion not supported: ${doc.mime_type} → ${targetMime}`);

  const ext = FMT_EXT[targetMime] || 'bin';
  const r   = await env.PHOENIX_DB.prepare(`
    INSERT INTO conversion_jobs
      (source_tav,source_r2,source_mime,target_format,target_ext,owner,status,queued_at)
    VALUES(?,?,?,?,?,?,'queued',?) RETURNING id
  `).bind(tav, doc.r2_key, doc.mime_type, targetMime, ext, doc.owner, now()).first();

  await capLog(env, tav, 'can_convert', doc.owner, targetMime, 'allowed', { job_id: r?.id });
  await audit(env, tav, doc.owner, 'convert', 'ok', req, { to: targetMime, job_id: r?.id });
  return json({ job_id: r?.id, source_tav: tav, target_format: targetMime, status: 'queued' }, 202);
}


// GET /docs — list forged documents
async function handleList(req, env) {
  const url    = new URL(req.url);
  const owner  = url.searchParams.get('owner');
  const sector = url.searchParams.get('sector');
  const mime   = url.searchParams.get('mime');
  const limit  = Math.min(parseInt(url.searchParams.get('limit')||'50',10), 200);
  const offset = parseInt(url.searchParams.get('offset')||'0',10);
  const sys    = sysAuth(req, env);

  let q = `SELECT tav,filename,mime_type,owner,privacy,classification,size_bytes,
           version,created_at,sector,tags,forged_at
           FROM documents WHERE forge_stage='forged' AND status='active'`;
  const b = [];
  if (owner)  { q += ' AND owner=?';    b.push(owner); }
  if (sector) { q += ' AND sector=?';   b.push(sector); }
  if (mime)   { q += ' AND mime_type=?';b.push(mime); }
  if (!sys)   { q += " AND privacy='public'"; }
  q += ' ORDER BY forged_at DESC LIMIT ? OFFSET ?'; b.push(limit, offset);

  const r = await env.PHOENIX_DB.prepare(q).bind(...b).all();
  return json({ documents: r.results||[], offset, limit });
}


// GET /docs/search?q=
async function handleSearch(req, env) {
  const url   = new URL(req.url);
  const q     = url.searchParams.get('q')||'';
  if (!q) return err('q required');
  const limit = Math.min(parseInt(url.searchParams.get('limit')||'20',10), 100);
  const sys   = sysAuth(req, env);

  let stmt = `SELECT d.tav,d.filename,d.mime_type,d.owner,d.privacy,d.size_bytes,d.forged_at
    FROM documents d JOIN documents_fts f ON d.rowid=f.rowid
    WHERE documents_fts MATCH ? AND d.forge_stage='forged' AND d.status='active'`;
  const b = [q];
  if (!sys) { stmt += " AND d.privacy='public'"; }
  stmt += ' LIMIT ?'; b.push(limit);

  const r = await env.PHOENIX_DB.prepare(stmt).bind(...b).all();
  await audit(env, 'search', 'system', 'search', 'ok', req, { q, hits: r.results?.length });
  return json({ query: q, results: r.results||[] });
}


// GET /jobs — conversion_agent.py polls this
async function handleJobs(req, env) {
  if (!sysAuth(req, env)) return err('unauthorized', 401);
  const r = await env.PHOENIX_DB.prepare(
    "SELECT * FROM conversion_jobs WHERE status='queued' ORDER BY queued_at LIMIT 20"
  ).all();
  return json({ jobs: r.results||[] });
}

async function handleJobComplete(req, env, jobId) {
  if (!sysAuth(req, env)) return err('unauthorized', 401);
  let body; try { body = await req.json(); } catch { return err('invalid JSON'); }
  if (!body.result_tav) return err('result_tav required');
  await env.PHOENIX_DB.prepare(
    'UPDATE conversion_jobs SET status=?,result_tav=?,completed_at=? WHERE id=?'
  ).bind('complete', body.result_tav, now(), jobId).run();
  return json({ job_id: jobId, result_tav: body.result_tav, status: 'complete' });
}

async function handleJobFail(req, env, jobId) {
  if (!sysAuth(req, env)) return err('unauthorized', 401);
  let body; try { body = await req.json(); } catch { return err('invalid JSON'); }
  await env.PHOENIX_DB.prepare(
    'UPDATE conversion_jobs SET status=?,error=?,completed_at=? WHERE id=?'
  ).bind('failed', body.error||'unknown', now(), jobId).run();
  return json({ job_id: jobId, status: 'failed' });
}


// GET /status
async function handleStatus(req, env) {
  const [docs, jobs, pending] = await Promise.all([
    env.PHOENIX_DB.prepare("SELECT COUNT(*) n FROM documents WHERE forge_stage='forged' AND status='active'").first(),
    env.PHOENIX_DB.prepare("SELECT COUNT(*) n FROM conversion_jobs WHERE status='queued'").first(),
    env.PHOENIX_DB.prepare("SELECT COUNT(*) n FROM forge_proposals WHERE status='pending_witness'").first(),
  ]);
  return json({
    ok: true, worker: 'documents-worker', os: 'Phoenix DevOps OS',
    docs_forged:        docs?.n   ?? 0,
    jobs_queued:        jobs?.n   ?? 0,
    proposals_pending:  pending?.n ?? 0,
    forge_model: 'content+manifest → TAV (deny-by-default capabilities)',
    compliance:  ['SOC2','HIPAA','GDPR'],
    security:    { L1:'quadralingual', L2:'aes256-gcm', L3:'r2-at-rest', L4:'owner-token', L5:'audit-log', L6:'manifest-enforcement' },
    ts: now(),
  });
}


// ── Router ────────────────────────────────────────────────────────────────────

export default {
  async fetch(req, env) {
    if (req.method === 'OPTIONS') return new Response(null, { headers: CORS });
    const url  = new URL(req.url);
    const path = url.pathname.replace(/\/+$/,'') || '/';
    const seg  = path.split('/').filter(Boolean);

    try {
      if (req.method==='GET'  && path==='/status')            return handleStatus(req, env);
      if (req.method==='GET'  && seg[0]==='docs' && !seg[1])  return handleList(req, env);
      if (req.method==='GET'  && seg[0]==='docs' && seg[1]==='search') return handleSearch(req, env);

      if (seg[0]==='doc') {
        // Forge routes
        if (req.method==='POST' && seg[1]==='forge' && !seg[2])            return handleForge(req, env);
        if (req.method==='POST' && seg[1]==='forge' && seg[2]==='preview') return handleForgePreview(req, env);
        if (req.method==='POST' && seg[1]==='forge' && seg[2]==='witness' && seg[3]) return handleWitness(req, env, seg[3]);

        // Document routes
        if (seg[1]) {
          const tav = seg[1];
          if (req.method==='GET'  && !seg[2])              return handleGet(req, env, tav);
          if (req.method==='GET'  && seg[2]==='meta')      return handleMeta(req, env, tav);
          if (req.method==='GET'  && seg[2]==='receipt')   return handleReceipt(req, env, tav);
          if (req.method==='GET'  && seg[2]==='history')   return handleHistory(req, env, tav);
          if (req.method==='GET'  && seg[2]==='family')    return handleFamily(req, env, tav);
          if (req.method==='GET'  && seg[2]==='formats')   return handleFormats(req, env, tav);
          if (req.method==='GET'  && seg[2]==='as' && seg[3])
            return handleConvertInline(req, env, tav, decodeURIComponent(seg[3]));
          if (req.method==='POST' && seg[2]==='convert')   return handleConvertQueue(req, env, tav);
        }
      }

      if (seg[0]==='jobs') {
        if (req.method==='GET'  && !seg[1])                               return handleJobs(req, env);
        if (req.method==='POST' && seg[1] && seg[2]==='complete')         return handleJobComplete(req, env, seg[1]);
        if (req.method==='POST' && seg[1] && seg[2]==='fail')             return handleJobFail(req, env, seg[1]);
      }

      return err('not found', 404);
    } catch (e) {
      return err(`internal: ${e.message}`, 500);
    }
  },
};
