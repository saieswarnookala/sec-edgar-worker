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
    if (path === '/api/timers') {   // last time the Cloudflare timer started each bot (shown on the Paper bots tab)
      const out = {};
      for (const wf of ['paper-dip.yml', 'paper-drift.yml', 'paper-v32.yml']) { try { out[wf] = JSON.parse((await env.CACHE.get('timer:last:' + wf)) || 'null'); } catch { out[wf] = null; } }
      return json(out);
    }

    // ---- admin ----
    if (path === '/admin' || path.startsWith('/api/admin/')) {
      if (s.role !== 'admin') return path === '/admin' ? Response.redirect(new URL('/', url).toString(), 302) : json({ error: 'Admins only' }, 403);
      if (path === '/admin') return withHeaders(await asset(env, request, '/admin.html'), { 'cache-control': 'no-store' });
      if (path === '/api/admin/timer-test' && method === 'POST') {   // start the dip workflow once now (outside market hours it just exits)
        if (!sameOrigin(request)) return json({ error: 'Bad request' }, 400);
        return json(await dispatch('paper-dip.yml', { dry_run: '0', force: '0' }, 'admin-test', env, fetch));
      }
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
    ctx.waitUntil(runTimer(event.cron, env, fetch, new Date(event.scheduledTime || Date.now())));
  },
};

export const TIMERS = {
  '5 11 * * MON-FRI': ['paper-drift.yml', { dry_run: '0' }],          // 6:05 ET in winter / 7:05 ET in summer (pre-market)
  '35 12 * * MON-FRI': ['paper-drift.yml', { dry_run: '0' }],         // backup: 7:35 / 8:35 ET
  // Market-hours clock (Nov 19): ONE cron line every 5 min, 14:00-20:55 UTC (= 10:00 am-3:55 pm ET in winter, 9:00-... in summer);
  // marketJobs() picks what to start at each tick (Cloudflare free plan: 5 cron triggers per account, all used).
  '*/5 14-20 * * MON-FRI': 'market',
  // Screener refresh: 21:45 UTC (4:45 pm ET winter, 5:45 summer) after the close, backup 23:45 UTC. GitHub's own schedule ran 4-6 h late.
  '45 21,23 * * *': 'evening',                                        // screener every evening + month-end Clear Leader final decision (eveningJobs)
  // INDIA (one line, no daylight saving in India): 02:45 UTC = 8:15 am IST morning status; 09:20 / 09:40 UTC = 2:50 / 3:10 pm IST before-close run.
  // indiaJobs() picks by time; other ticks of this line do nothing. GitHub's own schedule ran the morning message 8-10 h late (Nov 24). 5 of 5 free cron triggers used.
  '20,40,45 2,9 * * MON-FRI': 'india',
};
// What the market clock starts at a given UTC time (bots check NY time and Alpaca's calendar themselves; off-window runs exit at once):
//  * paper-dip.yml: :25 and :40 of 16,17 (12:25/12:40 pm ET half days) and 19,20 UTC (3:25/3:40 pm ET summer/winter)
//  * paper-v32.yml (bot 12, v3.2): every 15 min + :50/:55 retries for its once-a-day 3:45 step
export function marketJobs(when) {
  const h = when.getUTCHours(), m = when.getUTCMinutes(), jobs = [];
  if ([25, 40].includes(m) && [16, 17, 19, 20].includes(h)) jobs.push(['paper-dip.yml', { dry_run: '0', force: '0' }]);
  if ([0, 15, 30, 45, 50, 55].includes(m)) jobs.push(['paper-v32.yml', { dry_run: '0', phase: '' }]);
  if (when.getUTCDate() >= 25 && [5, 35].includes(m) && [19, 20].includes(h)) jobs.push(['clear-leader-alert.yml', { mode: 'auto' }]);
  if (m === 30 && [19, 20].includes(h)) jobs.push(['paper-crypto.yml', { dry_run: '0', notify: '1', mode: 'decide' }]);   // crypto bot 15: 3:30 pm ET decision (EDT 19:30 / EST 20:30 UTC; the script checks the ET window)   // month-end heads-up ~3:05 pm ET (script checks NY time, sends once)
  return jobs;
}
export function eveningJobs(when) {
  const jobs = [['screen.yml', {}], ['paper-india-mom.yml', { dry_run: '0', notify: '1' }], ['paper-crypto.yml', { dry_run: '0', notify: '1' }]];   // crypto paper bot 15: after the US close (4:45 / 6:45 pm ET); skips non-trading days itself   // India momentum + Alpha 50 paper bots: 3:15 / 5:15 am IST, NSE archive surely out, before the 9:15 open (they catch up missed days)
  if (when.getUTCDate() >= 25) jobs.push(['clear-leader-alert.yml', { mode: 'auto' }]);   // month-end final decision after the close
  return jobs;
}
export function indiaJobs(when) {
  const h = when.getUTCHours(), m = when.getUTCMinutes();
  if (h === 2 && m === 45) return [['paper-india.yml', { bot: 'morning', force: '', notify: 'yes' }]];
  if (h === 9 && (m === 20 || m === 40)) return [['paper-india.yml', { bot: 'B', force: '', notify: 'yes' }]];
  return [];
}
export async function runTimer(cron, env, fetchFn = fetch, when = new Date()) {
  const t = TIMERS[cron];
  if (!t) return { skipped: cron };
  if (typeof t === 'string') { const out = []; for (const [wf, inputs] of ({ market: marketJobs, india: indiaJobs, evening: eveningJobs })[t](when)) out.push(await dispatch(wf, inputs, cron, env, fetchFn)); return out; }
  return dispatch(t[0], t[1], cron, env, fetchFn);
}
async function dispatch(wf, inputs, cron, env, fetchFn) {
  if (!env.GH_DISPATCH_TOKEN) { const o = { cron, workflow: wf, error: 'GH_DISPATCH_TOKEN secret not set', at: new Date().toISOString() }; try { if (env.CACHE) await env.CACHE.put('timer:last:' + wf, JSON.stringify(o), { expirationTtl: 60 * 60 * 24 * 14 }); } catch {} return o; }
  const r = await fetchFn(`https://api.github.com/repos/saieswarnookala/sec-edgar-worker/actions/workflows/${wf}/dispatches`, {
    method: 'POST',
    headers: { authorization: `token ${env.GH_DISPATCH_TOKEN}`, accept: 'application/vnd.github+json', 'user-agent': 'sentinel-timer', 'content-type': 'application/json' },
    body: JSON.stringify({ ref: 'main', inputs }),
  });
  const out = { cron, workflow: wf, status: r.status, at: new Date().toISOString() };
  if (r.status >= 300) { try { out.error = (await r.text()).slice(0, 200); } catch {} }
  try { if (env.CACHE) await env.CACHE.put('timer:last:' + wf, JSON.stringify(out), { expirationTtl: 60 * 60 * 24 * 14 }); } catch {}
  return out;
}
