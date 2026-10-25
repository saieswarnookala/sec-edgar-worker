// Username + password auth for the Sentinel website.
// Users live in KV (AUTH) as user:<name>; sessions as sess:<token> with a 7-day TTL.
// The first admin is the ADMIN_USERNAME / ADMIN_PASSWORD Worker secret pair (no KV record).
const enc = new TextEncoder();
export const ITERATIONS = 8000;           // PBKDF2-SHA256; ~4 ms, safely inside the Workers free-plan 10 ms CPU limit (stored per user, so it can be raised later)
const SESSION_TTL = 7 * 86400;
const MAX_FAILS = 5, FAIL_WINDOW = 900;   // 5 wrong passwords per user -> 15 min lock
const MAX_IP_FAILS = 20;
export const NAME_RE = /^[a-z0-9._-]{3,32}$/;

const b64 = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf)));
const unb64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
const hex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');

export function safeEqual(a, b) {
  const A = enc.encode(String(a)), B = enc.encode(String(b));
  if (A.length !== B.length) return false;
  if (crypto.subtle.timingSafeEqual) return crypto.subtle.timingSafeEqual(A, B);
  let d = 0; for (let i = 0; i < A.length; i++) d |= A[i] ^ B[i]; return d === 0;
}
export async function hashPassword(password, saltB64, iterations = ITERATIONS) {
  const salt = saltB64 ? unb64(saltB64) : crypto.getRandomValues(new Uint8Array(16));
  const key = await crypto.subtle.importKey('raw', enc.encode(password), 'PBKDF2', false, ['deriveBits']);
  const bits = await crypto.subtle.deriveBits({ name: 'PBKDF2', hash: 'SHA-256', salt, iterations }, key, 256);
  return { salt: b64(salt), hash: b64(bits), iterations };
}
const sha256 = async (s) => hex(await crypto.subtle.digest('SHA-256', enc.encode(String(s))));

export function adminName(env) { return String(env.ADMIN_USERNAME || 'admin').toLowerCase(); }

export async function getUser(env, name) { return env.AUTH.get('user:' + name, 'json'); }

export async function putUser(env, { name, password, role }) {
  if (!NAME_RE.test(name)) throw new Error('Username: 3–32 characters, lowercase letters, numbers, dot, dash or underscore.');
  if (name === adminName(env)) throw new Error('That name is reserved for the main admin.');
  if (!password || password.length < 10) throw new Error('Password must be at least 10 characters.');
  if (!['viewer', 'admin'].includes(role)) role = 'viewer';
  const old = await getUser(env, name);
  const h = await hashPassword(password);
  const rec = { name, role, ...h, pwv: (old?.pwv || 0) + 1, created: old?.created || new Date().toISOString(), updated: new Date().toISOString() };
  await env.AUTH.put('user:' + name, JSON.stringify(rec), { metadata: { role, created: rec.created, updated: rec.updated } });
  return { name, role, created: rec.created, updated: rec.updated, existed: !!old };
}
export async function deleteUser(env, name) { await env.AUTH.delete('user:' + name); }
export async function listUsers(env) {
  const out = [];
  let cursor;
  do {
    const page = await env.AUTH.list({ prefix: 'user:', cursor });
    for (const k of page.keys) out.push({ name: k.name.slice(5), ...(k.metadata || {}) });
    cursor = page.list_complete ? null : page.cursor;
  } while (cursor);
  return out.sort((a, b) => (a.name < b.name ? -1 : 1));
}

async function failCount(env, key) { return Number((await env.AUTH.get(key)) || 0); }
async function bump(env, key) { const n = (await failCount(env, key)) + 1; await env.AUTH.put(key, String(n), { expirationTtl: FAIL_WINDOW }); return n; }

// Returns { ok, status, error, token, user }
export async function login(env, nameIn, password, ip) {
  const name = String(nameIn || '').trim().toLowerCase();
  const fk = 'fail:' + name, ik = 'failip:' + (ip || 'unknown');
  if ((await failCount(env, fk)) >= MAX_FAILS || (await failCount(env, ik)) >= MAX_IP_FAILS)
    return { ok: false, status: 429, error: 'Too many wrong passwords. Try again in 15 minutes.' };
  let user = null;
  if (name && name === adminName(env) && env.ADMIN_PASSWORD) {
    if (safeEqual(await sha256(password), await sha256(env.ADMIN_PASSWORD))) user = { name, role: 'admin', pwv: 0, root: true };
  } else if (NAME_RE.test(name)) {
    const rec = await getUser(env, name);
    if (rec) {
      const h = await hashPassword(String(password || ''), rec.salt, rec.iterations || ITERATIONS);
      if (safeEqual(h.hash, rec.hash)) user = { name, role: rec.role, pwv: rec.pwv };
    } else {
      await hashPassword(String(password || '')); // same work whether or not the user exists
    }
  }
  if (!user) { await bump(env, fk); await bump(env, ik); return { ok: false, status: 401, error: 'Wrong username or password.' }; }
  await env.AUTH.delete(fk);
  const token = hex(crypto.getRandomValues(new Uint8Array(32)));
  await env.AUTH.put('sess:' + token, JSON.stringify({ name: user.name, role: user.role, pwv: user.pwv, root: !!user.root, created: Date.now() }), { expirationTtl: SESSION_TTL });
  return { ok: true, token, user: { name: user.name, role: user.role } };
}

export async function session(env, request) {
  const m = /(?:^|;\s*)sid=([a-f0-9]{64})/.exec(request.headers.get('Cookie') || '');
  if (!m) return null;
  const s = await env.AUTH.get('sess:' + m[1], 'json');
  if (!s) return null;
  if (!s.root) { // the account must still exist with the same password version
    const rec = await getUser(env, s.name);
    if (!rec || rec.pwv !== s.pwv) { await env.AUTH.delete('sess:' + m[1]); return null; }
    s.role = rec.role;
  } else if (s.name !== adminName(env) || !env.ADMIN_PASSWORD) return null;
  return { ...s, token: m[1] };
}
export async function logout(env, token) { if (token) await env.AUTH.delete('sess:' + token); }
export const sessionCookie = (token) => `sid=${token}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${SESSION_TTL}`;
export const clearCookie = 'sid=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0';
