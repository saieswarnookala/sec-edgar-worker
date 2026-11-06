// Coverage Check portal (TEST / DEMO ONLY - never enter real patient data).
// Login -> form (payer, name, DOB, member ID) -> eligibility check.
// Mode: STEDI_API_KEY set -> Stedi test-mode eligibility API (mock requests only); else built-in demo members.
const PAYERS = [['60054', 'Aetna'], ['87726', 'UnitedHealthcare'], ['62308', 'Cigna'], ['BCBSF', 'Florida Blue (BCBS)'], ['CMSMED', 'Medicare'], ['DEMO', 'Demo Health Plan']];
const STEDI_URL = 'https://healthcare.us.stedi.com/2024-04-01/change/medicalnetwork/eligibility/v3';
const enc = new TextEncoder();
const b64u = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
async function hmac(key, msg) { const k = await crypto.subtle.importKey('raw', enc.encode(key), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']); return b64u(await crypto.subtle.sign('HMAC', k, enc.encode(msg))); }
export async function makeSession(secret, now = Date.now()) { const exp = now + 8 * 3600e3; return `${exp}.${await hmac(secret, 'cov:' + exp)}`; }
export async function validSession(secret, tok, now = Date.now()) { if (!tok) return false; const [exp, sig] = tok.split('.'); if (!exp || +exp < now) return false; return sig === (await hmac(secret, 'cov:' + exp)); }
function safeEq(a, b) { if (a.length !== b.length) return false; let d = 0; for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i); return d === 0; }
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const money = (v) => (v == null || v === '' ? '' : '$' + Number(v).toLocaleString('en-US', { maximumFractionDigits: 2 }));

export const DEMO_MEMBERS = {
  DEMO1001: { first: 'JORDAN', last: 'LEE', dob: '1985-04-12', result: { status: 'Active', plan: 'Demo Health PPO Gold', group: 'GRP-55120', start: '2026-01-01', end: '2026-12-31', network: 'In network', items: [['Deductible (individual)', '$1,500', '$420 met, $1,080 remaining'], ['Out-of-pocket max', '$5,000', '$910 met'], ['Office visit copay', '$25', 'Primary care'], ['Specialist copay', '$50', 'No referral needed'], ['Coinsurance', '20%', 'After deductible']], flags: [] } },
  DEMO1002: { first: 'MARIA', last: 'GARCIA', dob: '1972-09-30', result: { status: 'Inactive', plan: 'Demo Health HMO Silver', group: 'GRP-20981', start: '2025-01-01', end: '2026-06-30', network: '', items: [], flags: ['Coverage ended on 2026-06-30. Ask the patient for new insurance before the visit.'] } },
  DEMO1003: { first: 'SAM', last: 'PATEL', dob: '1990-02-18', result: { status: 'Active', plan: 'Demo Health HMO Bronze', group: 'GRP-77310', start: '2026-03-01', end: '2026-12-31', network: 'In network', items: [['Deductible (individual)', '$7,000', '$0 met, $7,000 remaining'], ['Specialist visit', 'Referral required', 'From primary care doctor'], ['Physical therapy', 'Prior authorization required', '20 visits per year']], flags: ['High deductible not met: patient likely pays full cost of the visit.', 'Referral required for specialists.'] } },
};
export function demoCheck(f) {
  const m = DEMO_MEMBERS[(f.memberId || '').trim().toUpperCase()];
  if (!m || m.last !== (f.lastName || '').trim().toUpperCase() || m.dob !== f.dob) return { status: 'Not found', plan: '', items: [], flags: ['No matching member. Check the name, date of birth and member ID.'] };
  return m.result;
}
// Turn a Stedi (legacy JSON 271) response into the same summary shape. Unknown fields are kept in raw.
export function summarizeStedi(j) {
  if (j.errors?.length) return { status: 'Error', plan: '', items: [], flags: j.errors.map((e) => `${e.code || ''} ${e.description || e.message || JSON.stringify(e)}`.trim()) };
  const ps = (j.planStatus || [])[0] || {}, info = j.planInformation || {}, dates = j.planDateInformation || {};
  const items = [];
  for (const b of (j.benefitsInformation || []).slice(0, 40)) {
    const what = b.name || b.code; let val = b.benefitAmount != null ? money(b.benefitAmount) : b.benefitPercent != null ? `${Math.round(+b.benefitPercent * 100)}%` : '';
    const note = [b.coverageLevel, b.timeQualifier, (b.serviceTypes || []).slice(0, 2).join(', '), b.inPlanNetworkIndicator].filter(Boolean).join(' | ');
    if (what && (val || note)) items.push([what, val || '-', note]);
  }
  const flags = [];
  if (/inactive/i.test(ps.status || '')) flags.push('Coverage is not active.');
  if ((j.benefitsInformation || []).some((b) => /prior auth|precertification/i.test(JSON.stringify(b)))) flags.push('Some services need prior authorization.');
  return { status: ps.status || (j.benefitsInformation ? 'See benefits' : 'Unknown'), plan: ps.planDetails || info.groupDescription || '', group: info.groupNumber || '', start: dates.planBegin || dates.eligibilityBegin || '', end: dates.planEnd || '', items, flags };
}
async function stediCheck(f, env) {
  const body = { controlNumber: String(Math.floor(1e8 + Math.random() * 9e8)), tradingPartnerServiceId: f.payer, provider: { organizationName: 'Demo Clinic', npi: env.PROVIDER_NPI || '1999999984' },
    subscriber: { firstName: f.firstName, lastName: f.lastName, dateOfBirth: (f.dob || '').replace(/-/g, ''), memberId: f.memberId }, encounter: { serviceTypeCodes: ['30'] } };
  const r = await fetch(STEDI_URL, { method: 'POST', headers: { Authorization: env.STEDI_API_KEY, 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({ errors: [{ description: `HTTP ${r.status}` }] }));
  if (!r.ok && !j.errors) j.errors = [{ code: r.status, description: j.message || 'Request failed' }];
  return { ...summarizeStedi(j), raw: j };
}
const CSS = `:root{--ink:#16324F;--mut:#5A6E83;--line:#D5DEE7;--bg:#F2F5F8;--ok:#2A8C78;--bad:#B4442F;--warn:#9A6A12}
*{box-sizing:border-box}body{margin:0;font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:var(--ink);background:var(--bg)}
.top{background:#fff;border-bottom:1px solid var(--line);padding:14px 24px;display:flex;justify-content:space-between;align-items:center}
.top b{font-size:18px}.top a{color:var(--mut)}.wrap{max-width:860px;margin:0 auto;padding:24px}
.test{background:#FFF4D6;border:1px solid #E8CF8A;color:#6B4E0A;padding:10px 14px;border-radius:6px;margin-bottom:20px;font-size:14px}
form.card,.card{background:#fff;border:1px solid var(--line);border-radius:8px;padding:20px;margin-bottom:20px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}@media(max-width:640px){.grid{grid-template-columns:1fr}}
label{display:block;font-size:14px;color:var(--mut);margin-bottom:4px}input,select{width:100%;padding:9px 10px;border:1px solid var(--line);border-radius:6px;font:inherit;color:var(--ink);background:#fff}
input:focus,select:focus,button:focus{outline:2px solid #2A8C78;outline-offset:1px}
button{margin-top:16px;background:var(--ink);color:#fff;border:0;border-radius:6px;padding:10px 18px;font:inherit;cursor:pointer}
.st{font-size:22px;font-weight:700}.Active{color:var(--ok)}.Inactive,.Error,.Not{color:var(--bad)}
table{width:100%;border-collapse:collapse;margin-top:12px}td,th{text-align:left;padding:8px;border-top:1px solid var(--line);font-size:15px;vertical-align:top}th{color:var(--mut);font-weight:600}
.flag{color:var(--warn);margin:6px 0}.hint{font-size:14px;color:var(--mut)}details{margin-top:12px}pre{white-space:pre-wrap;font-size:12px;background:var(--bg);padding:10px;border-radius:6px;max-height:320px;overflow:auto}`;
const page = (title, body, env, authed) => new Response(`<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><title>${title}</title><style>${CSS}</style></head><body>
<div class="top"><b>Coverage Check</b>${authed ? '<a href="/logout">Log out</a>' : ''}</div><div class="wrap">
<div class="test"><b>Test system.</b> ${env.STEDI_API_KEY ? 'Connected to the Stedi test sandbox (mock members only).' : 'Demo mode with built-in fake members.'} Do not enter real patient information.</div>${body}</div></body></html>`, { headers: { 'content-type': 'text/html; charset=utf-8', 'x-frame-options': 'DENY', 'cache-control': 'no-store' } });
const loginForm = (msg = '') => `<form class="card" method="post" action="/login" style="max-width:380px"><h2 style="margin-top:0">Sign in</h2>${msg ? `<p class="flag">${esc(msg)}</p>` : ''}
<label for="pw">Password</label><input id="pw" name="password" type="password" autocomplete="current-password" required autofocus><button type="submit">Sign in</button></form>`;
const checkForm = (f = {}, env) => `<form class="card" method="post" action="/check"><h2 style="margin-top:0">Check insurance coverage</h2><div class="grid">
<div><label for="payer">Insurance company</label><select id="payer" name="payer">${PAYERS.map(([id, n]) => `<option value="${id}"${f.payer === id ? ' selected' : ''}>${esc(n)}</option>`).join('')}</select></div>
<div><label for="memberId">Member ID</label><input id="memberId" name="memberId" value="${esc(f.memberId)}" required></div>
<div><label for="firstName">First name</label><input id="firstName" name="firstName" value="${esc(f.firstName)}" required></div>
<div><label for="lastName">Last name</label><input id="lastName" name="lastName" value="${esc(f.lastName)}" required></div>
<div><label for="dob">Date of birth</label><input id="dob" name="dob" type="date" value="${esc(f.dob)}" required></div></div>
<button type="submit">Check coverage</button>
${env.STEDI_API_KEY ? '<p class="hint">Sandbox: use a mock member from Stedi\u2019s list, e.g. UnitedHealthcare, John Doe, 1970-01-01, member UHC202649.</p>' : '<p class="hint">Demo members (any insurance): Jordan Lee, 1985-04-12, DEMO1001 (active) \u00b7 Maria Garcia, 1972-09-30, DEMO1002 (ended) \u00b7 Sam Patel, 1990-02-18, DEMO1003 (high deductible).</p>'}</form>`;
export function resultHtml(r) {
  const cls = (r.status || '').split(' ')[0];
  return `<div class="card"><div class="st ${esc(cls)}">${esc(r.status)}</div>${r.plan ? `<div>${esc(r.plan)}${r.group ? ` \u00b7 Group ${esc(r.group)}` : ''}</div>` : ''}
${r.start || r.end ? `<div class="hint">Coverage dates: ${esc(r.start || '?')} to ${esc(r.end || '?')}${r.network ? ` \u00b7 ${esc(r.network)}` : ''}</div>` : ''}
${(r.flags || []).map((x) => `<p class="flag">\u26a0 ${esc(x)}</p>`).join('')}
${r.items?.length ? `<table><tr><th>Benefit</th><th>Amount</th><th>Details</th></tr>${r.items.map(([a, b, c]) => `<tr><td>${esc(a)}</td><td>${esc(b)}</td><td>${esc(c)}</td></tr>`).join('')}</table>` : ''}
${r.raw ? `<details><summary>Raw response</summary><pre>${esc(JSON.stringify(r.raw, null, 2))}</pre></details>` : ''}</div>`;
}
const cookie = (req) => Object.fromEntries((req.headers.get('cookie') || '').split(';').map((c) => c.trim().split('=')).filter((x) => x[0]));
export default {
  async fetch(req, env) {
    const url = new URL(req.url), secret = (env.PORTAL_PASSWORD || '') + ':session';
    if (!env.PORTAL_PASSWORD) return page('Setup', '<div class="card">Set the PORTAL_PASSWORD secret to enable sign-in.</div>', env, false);
    if (url.pathname === '/logout') return new Response(null, { status: 302, headers: { location: '/', 'set-cookie': 'cov=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Strict' } });
    if (url.pathname === '/login' && req.method === 'POST') {
      const pw = String((await req.formData()).get('password') || '');
      if (!safeEq(pw, env.PORTAL_PASSWORD)) { await new Promise((r) => setTimeout(r, 600)); return page('Sign in', loginForm('Wrong password.'), env, false); }
      return new Response(null, { status: 302, headers: { location: '/', 'set-cookie': `cov=${await makeSession(secret)}; Path=/; Max-Age=28800; HttpOnly; Secure; SameSite=Strict` } });
    }
    if (!(await validSession(secret, cookie(req).cov))) return page('Sign in', loginForm(), env, false);
    if (url.pathname === '/check' && req.method === 'POST') {
      const fd = await req.formData(), f = Object.fromEntries(['payer', 'memberId', 'firstName', 'lastName', 'dob'].map((k) => [k, String(fd.get(k) || '').trim().slice(0, 80)]));
      let r; try { r = env.STEDI_API_KEY ? await stediCheck(f, env) : demoCheck(f); } catch (e) { r = { status: 'Error', items: [], flags: ['Could not reach the eligibility service. Try again.'] }; }
      return page('Result', checkForm(f, env) + resultHtml(r), env, true);
    }
    return page('Coverage Check', checkForm({}, env), env, true);
  },
};
