// Sentinel website: the Claude dashboard as a private site with username + password logins.
import * as A from './auth.js';
import { handleData } from './data.js';

const SEC_HEADERS = {
  'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'same-origin',
  'X-Frame-Options': 'DENY',
  'Strict-Transport-Security': 'max-age=31536000',
};
const withHeaders = (res, extra = {}) => {
  const r = new Response(res.body, res);
  for (const [k, v] of Object.entries({ ...SEC_HEADERS, ...extra })) r.headers.set(k, v);
  return r;
};
const json = (x, status = 200, headers = {}) => withHeaders(new Response(JSON.stringify(x), { status, headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' } }), headers);
const asset = (env, request, path) => env.ASSETS.fetch(new Request(new URL(path, request.url), { method: 'GET' }));
const PUBLIC = new Set(['/login', '/login.html', '/favicon.svg', '/theme.css']);

// Writes (POST/DELETE) must come from our own pages: same-origin + a custom header.
function sameOrigin(request) {
  const o = request.headers.get('Origin');
  return request.headers.get('X-Sentinel') === '1' && (!o || o === new URL(request.url).origin);
}
async function body(request) { try { return await request.json(); } catch { return {}; } }

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;
    const method = request.method;

    if (!env.AUTH) return new Response('AUTH storage is not configured', { status: 500 });

    // ---- public ----
    if (path === '/api/login' && method === 'POST') {
      if (!sameOrigin(request)) return json({ error: 'Bad request' }, 400);
      const b = await body(request);
      const r = await A.login(env, b.username, b.password, request.headers.get('CF-Connecting-IP'));
      if (!r.ok) return json({ error: r.error }, r.status);
      return json({ ok: true, user: r.user }, 200, { 'Set-Cookie': A.sessionCookie(r.token) });
    }
    if (PUBLIC.has(path)) return withHeaders(await asset(env, request, path === '/login' ? '/login.html' : path), { 'cache-control': path.endsWith('.html') || path === '/login' ? 'no-store' : 'public, max-age=3600' });

    // ---- everything else needs a session ----
    const s = await A.session(env, request);
    if (!s) {
      if (path.startsWith('/api/') || path.startsWith('/data/')) return json({ error: 'Not signed in' }, 401);
      return Response.redirect(new URL('/login?next=' + encodeURIComponent(path + url.search + url.hash), url).toString(), 302);
    }
    if (path === '/api/logout' && method === 'POST') { await A.logout(env, s.token); return json({ ok: true }, 200, { 'Set-Cookie': A.clearCookie }); }
    if (path === '/api/me') return json({ name: s.name, role: s.role });

    if (path.startsWith('/api/data/')) return withHeaders(await handleData(request, env, ctx, path.slice(10)));

    // ---- admin ----
    if (path === '/admin' || path.startsWith('/api/admin/')) {
      if (s.role !== 'admin') return path === '/admin' ? Response.redirect(new URL('/', url).toString(), 302) : json({ error: 'Admins only' }, 403);
      if (path === '/admin') return withHeaders(await asset(env, request, '/admin.html'), { 'cache-control': 'no-store' });
      if (path === '/api/admin/users' && method === 'GET') return json({ users: await A.listUsers(env), you: s.name, root: A.adminName(env) });
      if (path === '/api/admin/users' && (method === 'POST' || method === 'DELETE')) {
        if (!sameOrigin(request)) return json({ error: 'Bad request' }, 400);
        const b = await body(request);
        const name = String(b.username || '').trim().toLowerCase();
        try {
          if (method === 'POST') return json({ ok: true, user: await A.putUser(env, { name, password: String(b.password || ''), role: b.role }) });
          if (name === s.name) return json({ error: 'You can’t delete your own account.' }, 400);
          await A.deleteUser(env, name); return json({ ok: true });
        } catch (e) { return json({ error: e.message }, 400); }
      }
      return json({ error: 'Not found' }, 404);
    }

    // ---- static app + data files ----
    if (method !== 'GET' && method !== 'HEAD') return json({ error: 'Method not allowed' }, 405);
    const res = await env.ASSETS.fetch(request);
    const html = (res.headers.get('content-type') || '').includes('text/html');
    return withHeaders(res, { 'cache-control': html || path.startsWith('/data/') ? 'private, no-cache' : 'private, max-age=3600' });
  },

  // Cloudflare cron timer: GitHub's own schedules skip or delay runs, so we start the paper-trading bots from here.
  // Each bot runs at most once a day, so the backup times are harmless.
  async scheduled(event, env, ctx) {
    ctx.waitUntil(runTimer(event.cron, env));
  },
};

export const TIMERS = {
  '5 11 * * 1-5': ['paper-drift.yml', { dry_run: '0' }],          // 6:05 ET in winter / 7:05 ET in summer (pre-market)
  '35 12 * * 1-5': ['paper-drift.yml', { dry_run: '0' }],         // backup: 7:35 / 8:35 ET
  '25 19,20 * * 1-5': ['paper-dip.yml', { dry_run: '0', force: '0' }],   // 3:25 pm ET (summer 19:25 UTC, winter 20:25 UTC); off-window hour exits
  '40 19,20 * * 1-5': ['paper-dip.yml', { dry_run: '0', force: '0' }],   // backup: 3:40 pm ET (GitHub can take ~10 min to start a run)
  '25 16,17 * * 1-5': ['paper-dip.yml', { dry_run: '0', force: '0' }],   // 12:25 pm ET for 1 pm half days; the bot exits on normal days
  '40 16,17 * * 1-5': ['paper-dip.yml', { dry_run: '0', force: '0' }],   // backup 12:40 pm ET
};
export async function runTimer(cron, env, fetchFn = fetch) {
  const t = TIMERS[cron];
  if (!t) return { skipped: cron };
  if (!env.GH_DISPATCH_TOKEN) return { error: 'GH_DISPATCH_TOKEN secret not set' };
  const [wf, inputs] = t;
  const r = await fetchFn(`https://api.github.com/repos/saieswarnookala/sec-edgar-worker/actions/workflows/${wf}/dispatches`, {
    method: 'POST',
    headers: { authorization: `token ${env.GH_DISPATCH_TOKEN}`, accept: 'application/vnd.github+json', 'user-agent': 'sentinel-timer', 'content-type': 'application/json' },
    body: JSON.stringify({ ref: 'main', inputs }),
  });
  const out = { cron, workflow: wf, status: r.status, at: new Date().toISOString() };
  try { if (env.CACHE) await env.CACHE.put('timer:last:' + wf, JSON.stringify(out), { expirationTtl: 60 * 60 * 24 * 14 }); } catch {}
  return out;
}
