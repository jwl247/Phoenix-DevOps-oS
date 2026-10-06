// Discord bridge: signature gate, every command path, and REST failure handling.
import { webcrypto } from 'node:crypto';
import { verifyDiscordRequest, handleInteraction, DiscordRest, MAX_REPLY } from '../worker/discord.mjs';

const subtle = webcrypto.subtle;
let pass = 0, fail = 0;
const ok = (label, cond) => { if (cond) pass++; else { fail++; console.log('FAIL', label); } };
const rejects = async (label, fn, re) => {
  try { await fn(); fail++; console.log('FAIL (accepted)', label); }
  catch (e) { if (re && !re.test(e.message)) { fail++; console.log('FAIL (wrong error)', label, e.message); } else pass++; }
};
const hex = (b) => Buffer.from(b).toString('hex');

// ── signature gate ──
const kp = await subtle.generateKey({ name: 'Ed25519' }, true, ['sign', 'verify']);
const pub = hex(await subtle.exportKey('raw', kp.publicKey));
const now = Math.floor(Date.now() / 1000);
const signed = async (body, ts = String(now), key = kp.privateKey) => new Request('https://x/discord/interactions', {
  method: 'POST', body,
  headers: { 'x-signature-timestamp': ts, 'x-signature-ed25519': hex(await subtle.sign('Ed25519', key, new TextEncoder().encode(ts + body))) },
});
const ping = JSON.stringify({ type: 1 });
ok('valid signature parses', (await verifyDiscordRequest(await signed(ping), pub)).type === 1);
await rejects('unsigned', () => verifyDiscordRequest(new Request('https://x', { method: 'POST', body: ping }), pub), /unsigned/);
await rejects('stale timestamp (replay)', async () => verifyDiscordRequest(await signed(ping, String(now - 600)), pub), /stale/);
const other = await subtle.generateKey({ name: 'Ed25519' }, true, ['sign', 'verify']);
await rejects('signed by someone else', async () => verifyDiscordRequest(await signed(ping, String(now), other.privateKey), pub), /signature/);
const good = await signed(ping);
const swapped = new Request(good.url, { method: 'POST', body: JSON.stringify({ type: 2 }), headers: good.headers });
await rejects('body swapped after signing', () => verifyDiscordRequest(swapped, pub), /signature/);

// ── commands, against fake forum deps ──
const members = new Map([['d-linked', { id: 7, name: 'jw', rank: 'owner' }], ['d-banned', { id: 9, name: 'x', rank: 'member', banned: true }]]);
const codes = new Map([['ABCD2345', 7]]);
const threads = new Map([['dc-1', { id: 41, title: 'romeo.py v2', locked: false }], ['dc-locked', { id: 42, locked: true }]]);
const posts = [];
const deps = {
  memberByDiscord: async (id) => members.get(id) || null,
  consumeLinkCode: async (code, did) => {
    if (!codes.has(code)) return { ok: false, reason: 'code expired or already used' };
    codes.delete(code); const m = { id: 7, name: 'jw', rank: 'owner' }; members.set(did, m); return { ok: true, member: m };
  },
  threadByDiscordChannel: async (c) => threads.get(c) || null,
  addPost: async (p) => { posts.push(p); return { id: posts.length }; },
  threadUrl: (id) => `https://review.example/t/${id}`,
};
const cmd = (name, options, { user = 'd-new', channel = 'dc-1' } = {}) =>
  handleInteraction({ type: 2, id: 'int-' + Math.random(), channel_id: channel, member: { user: { id: user, username: 'u' } }, data: { name, options } }, deps);

ok('PING → PONG', (await handleInteraction({ type: 1 }, deps)).type === 1);
let r = await cmd('reply', [{ name: 'text', value: 'hi' }]);
ok('unlinked member cannot reply', /not linked/.test(r.data.content) && r.data.flags === 64 && posts.length === 0);
r = await cmd('link', [{ name: 'code', value: 'bad' }]);
ok('malformed code refused', /not valid/.test(r.data.content));
r = await cmd('link', [{ name: 'code', value: 'ABCD2345' }]);
ok('link with a real code', /Linked to forum member \*\*jw\*\*/.test(r.data.content));
r = await cmd('link', [{ name: 'code', value: 'ABCD2345' }], { user: 'd-thief' });
ok('code works once only', /expired or already used/.test(r.data.content));
r = await cmd('reply', [{ name: 'text', value: '  looks good, ship it  ' }]);
ok('linked member replies → forum post', posts.length === 1 && posts[0].threadId === 41 && posts[0].memberId === 7 && posts[0].body === 'looks good, ship it' && posts[0].source === 'discord');
ok('reply is public in Discord, mentions disabled', r.data.flags === undefined && r.data.allowed_mentions.parse.length === 0 && /t\/41#p1/.test(r.data.content));
r = await cmd('reply', [{ name: 'text', value: 'x' }], { channel: 'random-channel' });
ok('reply outside a mirrored thread refused', /inside a thread/.test(r.data.content) && posts.length === 1);
r = await cmd('reply', [{ name: 'text', value: 'x' }], { channel: 'dc-locked' });
ok('locked thread refused', /locked/.test(r.data.content) && posts.length === 1);
r = await cmd('reply', [{ name: 'text', value: 'x' }], { user: 'd-banned' });
ok('banned member refused', /cannot post/.test(r.data.content) && posts.length === 1);
r = await cmd('reply', [{ name: 'text', value: 'y'.repeat(MAX_REPLY + 1) }]);
ok('oversize reply refused', /Too long/.test(r.data.content) && posts.length === 1);
r = await cmd('thread', []);
ok('/thread gives the forum link', r.data.content === 'https://review.example/t/41');

// ── REST client: never throws, retries one 429 ──
const calls = [];
const fakeFetch = async (url, init) => {
  calls.push({ url, init });
  if (calls.length === 1) return new Response(JSON.stringify({ retry_after: 0.01 }), { status: 429 });
  if (url.endsWith('/threads')) return new Response(JSON.stringify({ id: 'dc-new' }), { status: 201 });
  return new Response(JSON.stringify({ id: 'm1' }), { status: 200 });
};
const rest = new DiscordRest('tok', { fetchImpl: fakeFetch });
const t = await rest.openThread('chan', 'x'.repeat(150), 'first');
ok('openThread retries a 429 then succeeds', t.ok && t.threadId === 'dc-new' && calls.length === 3);
ok('bot token in the header, not the URL', calls.every((c) => c.init.headers.Authorization === 'Bot tok' && !c.url.includes('tok')));
ok('thread title clipped to 100', JSON.parse(calls[1].init.body).name.length === 100);
const down = new DiscordRest('tok', { fetchImpl: async () => { throw new Error('ECONNRESET'); } });
ok('Discord down → error value, no throw', (await down.say('c', 'x')).ok === false);
ok('no token → refuses cleanly', (await new DiscordRest('').say('c', 'x')).error.includes('not set'));

console.log(fail ? `${fail} FAILED, ${pass} passed` : `all ${pass} Discord bridge checks pass`);
process.exit(fail ? 1 : 0);
