// node site/test.mjs — offline tests for the website Worker (auth, sessions, admin, access control, data shapes)
import assert from 'node:assert/strict';
let pass = 0;
const t = async (name, fn) => { try { await fn(); pass++; console.log('ok  ', name); } catch (e) { console.log('FAIL', name, '\n   ', e.message); process.exitCode = 1; } };

// --- minimal Workers environment ---
class KV {
  constructor() { this.m = new Map(); }
  async get(k, type) { const e = this.m.get(k); if (!e || (e.exp && e.exp < Date.now())) return null; return type === 'json' ? JSON.parse(e.v) : e.v; }
  async put(k, v, o = {}) { this.m.set(k, { v, meta: o.metadata, exp: o.expirationTtl ? Date.now() + o.expirationTtl * 1000 : 0 }); }
  async delete(k) { this.m.delete(k); }
  async list({ prefix = '' } = {}) { return { keys: [...this.m.entries()].filter(([k]) => k.startsWith(prefix)).map(([name, e]) => ({ name, metadata: e.meta })), list_complete: true }; }
}
globalThis.caches = { default: { match: async () => undefined, put: async () => {} } };
const ASSETS = { fetch: async (req) => { const p = new URL(req.url).pathname; return new Response('<html>' + p + '</html>', { status: 200, headers: { 'content-type': p.endsWith('.csv') ? 'text/csv' : 'text/html' } }); } };
const env = { AUTH: new KV(), CACHE: new KV(), ASSETS, ADMIN_PASSWORD: 'root-pass-123456', SEC_USER_AGENT: 'Test test@example.com' };
const ctx = { waitUntil: () => {} };
const { default: worker } = await import('./src/index.js');
const A = await import('./src/auth.js');
const B = 'https://sentinel.example.workers.dev';
const call = (path, { method = 'GET', body, cookie, headers = {} } = {}) => worker.fetch(new Request(B + path, { method, redirect: 'manual',
  headers: { ...(body ? { 'content-type': 'application/json' } : {}), ...(cookie ? { Cookie: cookie } : {}), ...headers }, body: body ? JSON.stringify(body) : undefined }), env, ctx);
const W = { 'X-Sentinel': '1', Origin: B };
const sid = (res) => (/sid=([a-f0-9]{64})/.exec(res.headers.get('Set-Cookie') || '') || [])[1];

await t('signed-out page redirects to /login (with next)', async () => {
  const r = await call('/?symbol=AAPL#trading');
  assert.equal(r.status, 302); assert.match(r.headers.get('Location'), /\/login\?next=%2F%3Fsymbol%3DAAPL/);
});
await t('signed-out data and API calls get 401, nothing leaks', async () => {
  for (const p of ['/data/etf_monthly_long.csv', '/api/data/prices?symbol=SPY', '/api/me', '/api/admin/users', '/index.html']) {
    const r = await call(p); assert.ok(r.status === 401 || r.status === 302, p + ' -> ' + r.status);
  }
});
await t('login page and theme are public', async () => {
  assert.equal((await call('/login')).status, 200); assert.equal((await call('/theme.css')).status, 200);
});
await t('login needs the X-Sentinel header and same origin', async () => {
  assert.equal((await call('/api/login', { method: 'POST', body: { username: 'admin', password: 'root-pass-123456' } })).status, 400);
  assert.equal((await call('/api/login', { method: 'POST', body: { username: 'admin', password: 'root-pass-123456' }, headers: { 'X-Sentinel': '1', Origin: 'https://evil.example' } })).status, 400);
});
let adminCookie;
await t('main admin signs in with the ADMIN_PASSWORD secret; cookie is HttpOnly + Secure', async () => {
  const r = await call('/api/login', { method: 'POST', body: { username: 'Admin', password: 'root-pass-123456' }, headers: W });
  assert.equal(r.status, 200); const c = r.headers.get('Set-Cookie'); assert.match(c, /HttpOnly/); assert.match(c, /Secure/); assert.match(c, /SameSite=Lax/);
  adminCookie = 'sid=' + sid(r);
  const me = await (await call('/api/me', { cookie: adminCookie })).json(); assert.deepEqual(me, { name: 'admin', role: 'admin' });
});
await t('wrong password -> 401 with a generic message', async () => {
  const r = await call('/api/login', { method: 'POST', body: { username: 'admin', password: 'nope' }, headers: W });
  assert.equal(r.status, 401); assert.equal((await r.json()).error, 'Wrong username or password.');
});
await t('admin creates a viewer; password is stored hashed, never in plain text', async () => {
  const r = await call('/api/admin/users', { method: 'POST', cookie: adminCookie, headers: W, body: { username: 'ravi', password: 'ravi-secret-pw', role: 'viewer' } });
  assert.equal(r.status, 200);
  const raw = await env.AUTH.get('user:ravi');
  assert.ok(!raw.includes('ravi-secret-pw')); const rec = JSON.parse(raw); assert.equal(rec.iterations, A.ITERATIONS); assert.ok(rec.salt && rec.hash);
});
await t('admin API rejects writes without the header', async () => {
  assert.equal((await call('/api/admin/users', { method: 'POST', cookie: adminCookie, body: { username: 'x1x', password: '1234567890' } })).status, 400);
});
await t('weak passwords and bad usernames are refused', async () => {
  assert.equal((await call('/api/admin/users', { method: 'POST', cookie: adminCookie, headers: W, body: { username: 'bob', password: 'short' } })).status, 400);
  assert.equal((await call('/api/admin/users', { method: 'POST', cookie: adminCookie, headers: W, body: { username: 'Bad Name!', password: '1234567890' } })).status, 400);
  assert.equal((await call('/api/admin/users', { method: 'POST', cookie: adminCookie, headers: W, body: { username: 'admin', password: '1234567890ab' } })).status, 400);
});
let raviCookie;
await t('viewer signs in and can open the dashboard and data files', async () => {
  const r = await call('/api/login', { method: 'POST', body: { username: 'ravi', password: 'ravi-secret-pw' }, headers: W });
  assert.equal(r.status, 200); raviCookie = 'sid=' + sid(r);
  assert.equal((await call('/', { cookie: raviCookie })).status, 200);
  assert.equal((await call('/data/etf_monthly_long.csv', { cookie: raviCookie })).status, 200);
});
await t('viewer cannot reach the admin page or API', async () => {
  assert.equal((await call('/admin', { cookie: raviCookie })).status, 302);
  assert.equal((await call('/api/admin/users', { cookie: raviCookie })).status, 403);
  assert.equal((await call('/api/admin/users', { method: 'POST', cookie: raviCookie, headers: W, body: { username: 'evil', password: '1234567890ab', role: 'admin' } })).status, 403);
});
await t('password reset signs the user out everywhere', async () => {
  await call('/api/admin/users', { method: 'POST', cookie: adminCookie, headers: W, body: { username: 'ravi', password: 'new-password-99' } });
  assert.equal((await call('/api/me', { cookie: raviCookie })).status, 401);
  assert.equal((await call('/api/login', { method: 'POST', body: { username: 'ravi', password: 'ravi-secret-pw' }, headers: W })).status, 401);
  assert.equal((await call('/api/login', { method: 'POST', body: { username: 'ravi', password: 'new-password-99' }, headers: W })).status, 200);
});
await t('5 wrong passwords lock the account for 15 minutes', async () => {
  for (let i = 0; i < 5; i++) await call('/api/login', { method: 'POST', body: { username: 'ravi', password: 'wrong' + i }, headers: W });
  const r = await call('/api/login', { method: 'POST', body: { username: 'ravi', password: 'new-password-99' }, headers: W });
  assert.equal(r.status, 429);
});
await t('removing a user ends their access', async () => {
  await env.AUTH.delete('fail:ravi');
  const r = await call('/api/login', { method: 'POST', body: { username: 'ravi', password: 'new-password-99' }, headers: { ...W } });
  const c = 'sid=' + sid(r);
  assert.equal((await call('/api/admin/users', { method: 'DELETE', cookie: adminCookie, headers: W, body: { username: 'ravi' } })).status, 200);
  assert.equal((await call('/api/me', { cookie: c })).status, 401);
});
await t('logout deletes the session', async () => {
  const r = await call('/api/login', { method: 'POST', body: { username: 'admin', password: 'root-pass-123456' }, headers: { ...W, 'CF-Connecting-IP': '10.0.0.9' } });
  const c = 'sid=' + sid(r);
  assert.equal((await call('/api/logout', { method: 'POST', cookie: c })).status, 200);
  assert.equal((await call('/api/me', { cookie: c })).status, 401);
});
await t('security headers on every page', async () => {
  const r = await call('/', { cookie: adminCookie });
  assert.match(r.headers.get('Content-Security-Policy'), /frame-ancestors 'none'/); assert.equal(r.headers.get('X-Frame-Options'), 'DENY');
});
await t('data API rejects bad tickers', async () => {
  assert.equal((await call('/api/data/prices?symbol=%3Cscript%3E', { cookie: adminCookie })).status, 400);
});
await t('prices feed returns the dashboard text format (mocked Alpaca)', async () => {
  const real = globalThis.fetch;
  globalThis.fetch = async (u) => String(u).includes('alpaca') ? Response.json({ bars: { LULU: [{ t: '2026-10-22T04:00:00Z', o: 1, h: 2, l: 0.5, c: 1.5, v: 10 }, { t: '2026-10-23T04:00:00Z', o: 2, h: 3, l: 1, c: 2.5, v: 20 }] } }) : real(u);
  const e2 = { ...env, APCA_API_KEY_ID: 'k', APCA_API_SECRET_KEY: 's' };
  const r = await worker.fetch(new Request(B + '/api/data/prices?symbol=LULU', { headers: { Cookie: adminCookie } }), e2, ctx);
  globalThis.fetch = real;
  const txt = await r.text(); const L = txt.split('\n');
  assert.equal(L[0], 'datetime;open;high;low;close;volume'); assert.equal(L[1].split(';')[0], '2026-10-23');
});
console.log(`\n${pass} passed`);
