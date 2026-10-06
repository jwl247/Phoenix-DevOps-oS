// discord.mjs — two-way Discord bridge for the Phoenix Review forum.
// Phoenix DevOps OS | jwl247 | GPL v3
//
// OUT (forum → Discord): every forum thread gets a mirror thread in a Discord
//   channel; new posts, review verdicts and rank-ups are posted there by the bot
//   over Discord's REST API (bot token = worker secret DISCORD_BOT_TOKEN).
// IN (Discord → forum): Discord sends slash commands to POST /discord/interactions.
//   Every request is Ed25519-signed by Discord; unsigned/stale requests are refused.
//     /link code:<code>   tie your Discord account to your forum account (code is
//                         shown on the site after a passkey sign-in, 10 min, once)
//     /reply text:<text>  reply to the forum thread this Discord thread mirrors
//     /thread             link to the forum thread
//
// Why slash commands and not "any message in the channel": plain channel messages
// only arrive over Discord's Gateway websocket, which a Worker can't hold open
// without a Durable Object babysitting a socket. Slash commands come as signed
// HTTPS — no socket, no missed messages, and every post is an explicit act by a
// linked member. Identity stays the passkey account: Discord is a door, not the
// lock. If Discord goes away, the forum keeps working.

const te = new TextEncoder();
export const MAX_SKEW_S = 300;          // refuse interactions older than 5 minutes (replay)
export const MAX_REPLY = 4000;

const hexToBytes = (h) => {
  if (typeof h !== 'string' || !/^([0-9a-f]{2})+$/i.test(h)) throw new Error('bad hex');
  return new Uint8Array(h.match(/../g).map((x) => parseInt(x, 16)));
};

/** Verify Discord's Ed25519 signature. Returns the parsed interaction or throws. */
export async function verifyDiscordRequest(req, publicKeyHex, nowS = Math.floor(Date.now() / 1000)) {
  const sig = req.headers.get('x-signature-ed25519');
  const ts = req.headers.get('x-signature-timestamp');
  if (!sig || !ts) throw new Error('unsigned');
  if (!/^\d+$/.test(ts) || Math.abs(nowS - Number(ts)) > MAX_SKEW_S) throw new Error('stale');
  const body = await req.text();
  const key = await crypto.subtle.importKey('raw', hexToBytes(publicKeyHex), { name: 'Ed25519' }, false, ['verify']);
  const ok = await crypto.subtle.verify('Ed25519', key, hexToBytes(sig), te.encode(ts + body));
  if (!ok) throw new Error('bad signature');
  return JSON.parse(body);
}

const ephemeral = (content) => ({ type: 4, data: { content, flags: 64, allowed_mentions: { parse: [] } } });
const opt = (i, name) => (i.data?.options || []).find((o) => o.name === name)?.value;

/**
 * Handle a verified interaction. `deps` is the forum's side (D1 in the worker,
 * fakes in tests):
 *   memberByDiscord(discordId)            → { id, name, rank, banned } | null
 *   consumeLinkCode(code, discordId, discordName) → { ok, member?, reason? }
 *   threadByDiscordChannel(channelId)     → { id, title, locked, board } | null
 *   addPost({ threadId, memberId, body, source:'discord', discordMessageRef })
 *   threadUrl(threadId)                   → absolute URL
 */
export async function handleInteraction(i, deps) {
  if (i.type === 1) return { type: 1 };                              // PING
  if (i.type !== 2) return ephemeral('Unsupported interaction.');
  const user = i.member?.user || i.user;
  if (!user?.id) return ephemeral('No Discord user on this interaction.');
  const cmd = i.data?.name;

  if (cmd === 'link') {
    const code = String(opt(i, 'code') || '').trim();
    if (!/^[A-Z0-9]{8}$/.test(code)) return ephemeral('That code is not valid. Get a fresh one from your profile page on the forum.');
    const r = await deps.consumeLinkCode(code, user.id, user.global_name || user.username || user.id);
    return ephemeral(r.ok ? `Linked to forum member **${r.member.name}**. You can now use /reply in mirrored threads.`
                          : `Not linked: ${r.reason}.`);
  }

  const thread = i.channel_id ? await deps.threadByDiscordChannel(i.channel_id) : null;
  if (cmd === 'thread') {
    return ephemeral(thread ? deps.threadUrl(thread.id) : 'This channel does not mirror a forum thread.');
  }

  if (cmd === 'reply') {
    if (!thread) return ephemeral('Use /reply inside a thread the bot created for a forum thread.');
    const member = await deps.memberByDiscord(user.id);
    if (!member) return ephemeral('Your Discord account is not linked. Sign in on the forum, open your profile, and use /link with the code it shows.');
    if (member.banned) return ephemeral('Your forum account cannot post.');
    if (thread.locked) return ephemeral('That thread is locked.');
    const text = String(opt(i, 'text') || '').trim();
    if (!text) return ephemeral('Nothing to post.');
    if (text.length > MAX_REPLY) return ephemeral(`Too long (${text.length} characters, max ${MAX_REPLY}). Post it on the site instead.`);
    const post = await deps.addPost({ threadId: thread.id, memberId: member.id, body: text, source: 'discord', discordMessageRef: i.id });
    return { type: 4, data: { content: `**${member.name}** (${member.rank}) replied on the forum:\n${text}\n<${deps.threadUrl(thread.id)}#p${post.id}>`, allowed_mentions: { parse: [] } } };
  }
  return ephemeral(`Unknown command /${cmd}.`);
}

/** Slash command definitions — PUT once to /applications/{app}/commands (scripts/register-discord.mjs). */
export const COMMANDS = [
  { name: 'link', description: 'Link your Discord account to your Phoenix Review forum account', type: 1,
    options: [{ name: 'code', description: 'The 8-character code from your forum profile', type: 3, required: true, min_length: 8, max_length: 8 }] },
  { name: 'reply', description: 'Reply to the forum thread this Discord thread mirrors', type: 1,
    options: [{ name: 'text', description: 'Your reply', type: 3, required: true, max_length: MAX_REPLY }] },
  { name: 'thread', description: 'Link to the forum thread this Discord thread mirrors', type: 1 },
];

/** Outbound REST. Failures are returned, never thrown: Discord being down must not break the forum. */
export class DiscordRest {
  constructor(token, { base = 'https://discord.com/api/v10', fetchImpl = fetch } = {}) {
    this.token = token; this.base = base; this.fetch = fetchImpl;
  }
  async call(method, path, body) {
    if (!this.token) return { ok: false, status: 0, error: 'DISCORD_BOT_TOKEN not set' };
    for (let attempt = 0; attempt < 2; attempt++) {
      let r;
      try {
        r = await this.fetch(this.base + path, {
          method,
          headers: { Authorization: `Bot ${this.token}`, 'Content-Type': 'application/json', 'User-Agent': 'PhoenixReview (https://github.com/jwl247, 1.0)' },
          body: body ? JSON.stringify(body) : undefined,
        });
      } catch (e) { return { ok: false, status: 0, error: String(e.message || e) }; }
      if (r.status === 429 && attempt === 0) {
        const j = await r.json().catch(() => ({}));
        const wait = Math.min(5, Number(j.retry_after) || 1);   // one short retry only; the outbox catches the rest
        await new Promise((res) => setTimeout(res, wait * 1000));
        continue;
      }
      const data = r.status === 204 ? null : await r.json().catch(() => null);
      return r.ok ? { ok: true, status: r.status, data } : { ok: false, status: r.status, error: JSON.stringify(data).slice(0, 300) };
    }
    return { ok: false, status: 429, error: 'rate limited' };
  }
  /** Start a mirror thread in a text channel with a first message. Returns the Discord thread id. */
  async openThread(channelId, title, firstMessage) {
    const t = await this.call('POST', `/channels/${channelId}/threads`, { name: title.slice(0, 100), type: 11, auto_archive_duration: 10080 });
    if (!t.ok) return t;
    const m = await this.say(t.data.id, firstMessage);
    return m.ok ? { ok: true, threadId: t.data.id } : { ...m, threadId: t.data.id };
  }
  say(channelId, content) {
    return this.call('POST', `/channels/${channelId}/messages`, { content: content.slice(0, 2000), allowed_mentions: { parse: [] } });
  }
}
