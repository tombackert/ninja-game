// Rendezvous for online play (docs/online-connectivity-brainstorm.md).
//
// The host's server registers its presence (friend code, name, level,
// candidate addresses) every few seconds; a friend who knows the code asks
// to join with its own candidates, and the host picks the request up with
// its next presence call. Then both sides punch UDP holes to each other's
// candidates; game traffic never passes through here.
//
// One Durable Object holds all state, so a join is seen by the host's next
// call (Workers KV is eventually consistent, too slow for a handshake).
// Presence and joins live in memory and expire; only the hash of each
// code's token is stored (trust on first use: the first caller of a code
// owns it).

const PRESENCE_TTL_MS = 15_000; // hosts refresh every ~2 s
const JOIN_TTL_MS = 20_000;
const MAX_BODY_BYTES = 4096;
const MAX_CANDIDATES = 8;
const MAX_ENTRIES = 2000;
const CODE_RE = /^[0-9A-HJKMNP-TV-Z]{4}-[0-9A-HJKMNP-TV-Z]{4}$/;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/") {
      return new Response("ninja-game rendezvous\n", { headers: { "content-type": "text/plain" } });
    }
    if (!url.pathname.startsWith("/v1/")) {
      return json({ error: "not found" }, 404);
    }
    const stub = env.RENDEZVOUS.get(env.RENDEZVOUS.idFromName("global"));
    return stub.fetch(request);
  },
};

export class Rendezvous {
  constructor(ctx, env) {
    this.ctx = ctx;
    this.presence = new Map(); // code -> {name, version, level, candidates, expires}
    this.joins = new Map(); // host code -> [{from, name, version, candidates, expires}]
  }

  async fetch(request) {
    if (request.method !== "POST") {
      return json({ error: "POST only" }, 405);
    }
    const text = await request.text();
    if (text.length > MAX_BODY_BYTES) {
      return json({ error: "request too large" }, 413);
    }
    let body;
    try {
      body = JSON.parse(text);
    } catch {
      return json({ error: "invalid JSON" }, 400);
    }
    const now = Date.now();
    this.expire(now);
    switch (new URL(request.url).pathname) {
      case "/v1/host":
        return this.host(body, now);
      case "/v1/unhost":
        return this.unhost(body);
      case "/v1/status":
        return this.status(body);
      case "/v1/join":
        return this.join(body, now);
      default:
        return json({ error: "not found" }, 404);
    }
  }

  // Register or refresh presence; returns the join requests waiting for this host.
  async host(body, now) {
    const code = body.code;
    if (!(await this.authorized(code, body.token))) {
      return json({ error: "code belongs to someone else" }, 403);
    }
    const candidates = cleanCandidates(body.candidates);
    if (!this.presence.has(code) && this.presence.size >= MAX_ENTRIES) {
      return json({ error: "busy" }, 503);
    }
    this.presence.set(code, {
      name: cleanName(body.name),
      version: Number(body.version) || 0,
      level: Number(body.level) || 0,
      candidates,
      expires: now + PRESENCE_TTL_MS,
    });
    const joins = (this.joins.get(code) || []).map(({ expires, ...join }) => join);
    this.joins.delete(code);
    return json({ ok: true, joins });
  }

  async unhost(body) {
    if (!(await this.authorized(body.code, body.token))) {
      return json({ error: "code belongs to someone else" }, 403);
    }
    this.presence.delete(body.code);
    this.joins.delete(body.code);
    return json({ ok: true });
  }

  // Who of these codes is hosting right now (no addresses).
  status(body) {
    const codes = Array.isArray(body.codes) ? body.codes.slice(0, 50) : [];
    const friends = {};
    for (const code of codes) {
      if (typeof code !== "string" || !CODE_RE.test(code)) continue;
      const p = this.presence.get(code);
      friends[code] = p ? { hosting: true, name: p.name, level: p.level, version: p.version } : { hosting: false };
    }
    return json({ ok: true, friends });
  }

  // A friend asks to join: queue its candidates for the host, answer with the host's.
  async join(body, now) {
    if (!CODE_RE.test(String(body.to))) {
      return json({ error: "invalid code" }, 400);
    }
    if (!(await this.authorized(body.from, body.token))) {
      return json({ error: "code belongs to someone else" }, 403);
    }
    const host = this.presence.get(body.to);
    if (!host) {
      return json({ error: "offline" }, 404);
    }
    const queue = (this.joins.get(body.to) || []).filter((j) => j.from !== body.from);
    if (queue.length >= 8) {
      return json({ error: "busy" }, 503);
    }
    queue.push({
      from: body.from,
      name: cleanName(body.name),
      version: Number(body.version) || 0,
      candidates: cleanCandidates(body.candidates),
      expires: now + JOIN_TTL_MS,
    });
    this.joins.set(body.to, queue);
    return json({
      ok: true,
      host: { name: host.name, level: host.level, version: host.version, candidates: host.candidates },
    });
  }

  // Trust on first use: the first token seen for a code owns it.
  async authorized(code, token) {
    if (typeof code !== "string" || !CODE_RE.test(code) || typeof token !== "string" || token.length < 16) {
      return false;
    }
    const hash = await sha256(token);
    const key = "token:" + code;
    const stored = await this.ctx.storage.get(key);
    if (stored === undefined) {
      await this.ctx.storage.put(key, hash);
      return true;
    }
    return stored === hash;
  }

  expire(now) {
    for (const [code, p] of this.presence) {
      if (p.expires < now) this.presence.delete(code);
    }
    for (const [code, queue] of this.joins) {
      const alive = queue.filter((j) => j.expires >= now);
      if (alive.length) this.joins.set(code, alive);
      else this.joins.delete(code);
    }
  }
}

function cleanCandidates(list) {
  if (!Array.isArray(list)) return [];
  const out = [];
  for (const c of list.slice(0, MAX_CANDIDATES)) {
    if (!Array.isArray(c) || c.length !== 3) continue;
    const [kind, host, port] = c;
    if (!["lan", "v6", "v4"].includes(kind)) continue;
    if (typeof host !== "string" || host.length > 64 || !/^[0-9a-fA-F:.]+$/.test(host)) continue;
    if (!Number.isInteger(port) || port < 1 || port > 65535) continue;
    out.push([kind, host, port]);
  }
  return out;
}

function cleanName(name) {
  return typeof name === "string" ? name.slice(0, 24) : "";
}

async function sha256(text) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { "content-type": "application/json" } });
}
