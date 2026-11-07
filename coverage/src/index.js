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

export const VISITS = { office: ['Office visit', 130, 'office'], specialist: ['Specialist visit', 200, 'specialist'], pt_eval: ['Physical therapy evaluation', 180, 'pt'], pt: ['Physical therapy visit', 120, 'pt'], chiro: ['Chiropractic visit', 75, 'chiro'] };
const CAT = { office: 'Office visit', specialist: 'Specialist', pt: 'Physical therapy', chiro: 'Chiropractic' };
const M = (first, last, dob, result, details) => ({ first, last, dob, result, details });
export const DEMO_MEMBERS = {
  DEMO1001: M('JORDAN', 'LEE', '1985-04-12', { status: 'Active', plan: 'Demo Health PPO Gold', group: 'GRP-55120', start: '2026-01-01', end: '2026-12-31', network: 'In network', flags: [] },
    { dedTotal: 1500, dedRemaining: 1080, oopRemaining: 4090, coins: 0.2, copay: { office: 25, specialist: 50, pt: 40, chiro: 30 }, visits: { pt: { used: 8, limit: 20 }, chiro: { used: 3, limit: 20 } }, lang: 'en' }),
  DEMO1002: M('MARIA', 'GARCIA', '1972-09-30', { status: 'Inactive', plan: 'Demo Health HMO Silver', group: 'GRP-20981', start: '2025-01-01', end: '2026-06-30', network: '', items: [], flags: ['Coverage ended on 2026-06-30. Ask the patient for new insurance before the visit.'] },
    { lang: 'es' }),
  DEMO1003: M('SAM', 'PATEL', '1990-02-18', { status: 'Active', plan: 'Demo Health HMO Bronze', group: 'GRP-77310', start: '2026-03-01', end: '2026-12-31', network: 'In network', flags: ['High deductible not met: patient likely pays full cost of the visit.'] },
    { dedTotal: 7000, dedRemaining: 7000, oopRemaining: 9200, coins: 0.2, copay: {}, visits: { pt: { used: 14, limit: 20 } }, auth: { pt: { number: 'AUTH-55321', approved: 6, used: 4, expiresInDays: 9 } }, referral: { specialist: { required: true, onFile: false }, pt: { required: true, onFile: true } }, lang: 'en' }),
  DEMO1004: M('LUCIA', 'HERNANDEZ', '1968-11-03', { status: 'Active', plan: 'Demo Health PPO Silver', group: 'GRP-31877', start: '2026-01-01', end: '2026-12-31', network: 'In network', flags: [] },
    { dedTotal: 2000, dedRemaining: 0, oopRemaining: 2650, coins: 0.2, copay: { office: 30, specialist: 60, pt: 35, chiro: 35 }, visits: { pt: { used: 18, limit: 20 }, chiro: { used: 19, limit: 20 } }, lang: 'es' }),
  DEMO1005: M('DAVID', 'KIM', '1979-05-22', { status: 'Active', plan: 'Demo Health Choice Plus', group: 'GRP-60412', start: '2026-01-01', end: '2026-12-31', network: 'In network', flags: [] },
    { dedTotal: 1000, dedRemaining: 50, oopRemaining: 3100, coins: 0.1, copay: { office: 20, specialist: 40 }, visits: { pt: { used: 11, limit: 30 } }, auth: { pt: { number: 'AUTH-80917', approved: 12, used: 11, expiresInDays: 5 } }, lang: 'en' }),
  DEMO1006: M('AISHA', 'BROWN', '1995-08-14', { status: 'Active', plan: 'Demo Health PPO Platinum', group: 'GRP-11290', start: '2026-01-01', end: '2026-12-31', network: 'In network', flags: [] },
    { dedTotal: 500, dedRemaining: 0, oopRemaining: 1800, coins: 0.1, copay: { office: 15, specialist: 35, pt: 25, chiro: 25 }, visits: { pt: { used: 2, limit: 25 } }, lang: 'en' }),
};
export function itemsFrom(d) {
  if (!d || d.dedTotal == null) return [];
  const out = [['Deductible (individual)', money(d.dedTotal), d.dedRemaining ? `${money(d.dedTotal - d.dedRemaining)} met, ${money(d.dedRemaining)} remaining` : 'Met for this year']];
  if (d.oopRemaining != null) out.push(['Out-of-pocket remaining', money(d.oopRemaining), 'This year']);
  for (const [k, v] of Object.entries(d.copay || {})) out.push([`${CAT[k]} copay`, money(v), 'Per visit']);
  if (d.coins != null) out.push(['Coinsurance', `${Math.round(d.coins * 100)}%`, 'After deductible, when no copay applies']);
  for (const [k, v] of Object.entries(d.visits || {})) out.push([`${CAT[k]} visits`, `${v.limit} per year`, `${v.used} used`]);
  for (const [k, v] of Object.entries(d.auth || {})) out.push([`${CAT[k]}`, 'Prior authorization required', v.approved ? `${v.approved} visits approved (${v.number})` : 'None on file']);
  for (const [k, v] of Object.entries(d.referral || {})) if (v.required) out.push([`${CAT[k]} visit`, 'Referral required', v.onFile ? 'Referral on file' : 'No referral on file']);
  return out;
}
for (const m of Object.values(DEMO_MEMBERS)) if (!m.result.items) m.result.items = itemsFrom(m.details);
export function demoCheck(f) {
  const m = DEMO_MEMBERS[(f.memberId || '').trim().toUpperCase()];
  if (!m || m.last !== (f.lastName || '').trim().toUpperCase() || m.dob !== f.dob) return { status: 'Not found', plan: '', items: [], flags: ['No matching member. Check the name, date of birth and member ID.'] };
  return m.result;
}
const addDays = (d, n) => new Date(Date.parse(d) + n * 864e5).toISOString().slice(0, 10);
// Adds the cost estimate, visit limits, authorizations, referral and coverage-end alerts for one visit.
export function enrich(base, d, visitKey = 'office', today = new Date().toISOString().slice(0, 10)) {
  const visit = VISITS[visitKey] ? visitKey : 'office', [vname, allowed, cat] = VISITS[visit];
  const r = { ...base, flags: [...(base.flags || [])], visit, vname };
  if (!d) return r;
  const active = /active/i.test(base.status || '') && !/inactive/i.test(base.status || '');
  const lower = vname.toLowerCase();
  if (!active) r.estimate = { owe: allowed, how: `No active coverage: full self-pay price for a ${lower} (about ${money(allowed)}).` };
  else if (d.copay?.[cat] != null) r.estimate = { owe: d.copay[cat], how: `${money(d.copay[cat])} copay for a ${lower}.` };
  else if (d.dedRemaining != null) {
    const ded = Math.min(allowed, d.dedRemaining), co = Math.round((allowed - ded) * (d.coins || 0) * 100) / 100;
    let owe = ded + co; if (d.oopRemaining != null) owe = Math.min(owe, d.oopRemaining);
    r.estimate = { owe: Math.round(owe * 100) / 100, how: `${ded ? money(ded) + ' toward the deductible' : 'Deductible already met'}${co ? ` + ${Math.round(d.coins * 100)}% coinsurance (${money(co)})` : ''}, based on a typical allowed amount of ${money(allowed)}.` };
  }
  if (active) {
    const v = d.visits?.[cat];
    if (v) { const left = v.limit - v.used; r.visits = { ...v, left, label: CAT[cat] };
      if (left <= 0) r.flags.push(`No covered ${CAT[cat].toLowerCase()} visits left this year (${v.used} of ${v.limit} used). The patient would pay the full price.`);
      else if (left <= 3) r.flags.push(`Only ${left} covered ${CAT[cat].toLowerCase()} visit${left === 1 ? '' : 's'} left this year (${v.used} of ${v.limit} used).`); }
    const a = d.auth?.[cat];
    if (a) {
      if (!a.approved) { r.auth = { missing: true }; r.flags.push(`Prior authorization is required for this ${lower} and none is on file.`); }
      else { const left = a.approved - a.used, expires = addDays(today, a.expiresInDays); r.auth = { number: a.number, approved: a.approved, used: a.used, left, expires };
        if (left <= 0 || a.expiresInDays < 0) r.flags.push(`Authorization ${a.number} is used up or expired. Request a new one before this visit.`);
        else if (left <= 2 || a.expiresInDays <= 14) r.flags.push(`Authorization ${a.number}: ${left} visit${left === 1 ? '' : 's'} left, expires ${expires}. Request an extension soon.`); }
    }
    const ref = d.referral?.[cat];
    if (ref?.required && !ref.onFile) r.flags.push(`A referral is required for this ${lower} and none is on file. Get one from the primary care doctor before the visit.`);
    if (base.end) { const days = Math.round((Date.parse(base.end) - Date.parse(today)) / 864e5); if (days >= 0 && days <= 30) r.flags.push(`Coverage ends on ${base.end} (in ${days} days). Ask the patient about next year's insurance.`); }
  }
  r.lang = d.lang || 'en';
  return r;
}
const nice = (s) => (s ? s[0].toUpperCase() + s.slice(1).toLowerCase() : '');
export function patientMessage(r, first, lang) {
  const n = nice(first), ok = !/inactive|not found|error/i.test(r.status || ''), owe = r.estimate && ok ? money(r.estimate.owe) : null;
  if (lang === 'es') return ok ? `Hola ${n}, confirmamos su seguro (${r.plan}) para su próxima cita.${owe ? ` Monto estimado a pagar en la visita: ${owe}.` : ''} Si tiene preguntas, llámenos.` : `Hola ${n}, no pudimos confirmar su seguro para su próxima cita. Por favor traiga su tarjeta de seguro actual o llámenos antes de la visita.`;
  return ok ? `Hi ${n}, we've confirmed your insurance (${r.plan}) for your upcoming visit.${owe ? ` Estimated amount due at your visit: ${owe}.` : ''} Call us with any questions.` : `Hi ${n}, we couldn't confirm your insurance for your upcoming visit. Please bring your current insurance card or call us before your appointment.`;
}
export const SCHEDULE = [['08:00', 'DEMO1006', 'pt'], ['08:45', 'DEMO1003', 'pt'], ['09:30', 'DEMO1001', 'chiro'], ['10:15', 'DEMO1005', 'pt'], ['11:00', 'DEMO1004', 'pt'], ['13:30', 'DEMO1002', 'pt_eval']];
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
const CSS = `:root{--ink:#10314D;--mut:#4E6680;--line:#D3E2EF;--sky:#EEF6FC;--card:#fff;--care:#1A6BB0;--care-d:#13528A;--mint:#178A6A;--mint-bg:#E3F5EE;--amber:#A86C06;--amber-bg:#FFF3DA;--coral:#C2413A;--coral-bg:#FCE9E7}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;font:17px/1.55 "Atkinson Hyperlegible",system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--ink);background:var(--sky)}
a{color:var(--care)}
.bar{background:linear-gradient(90deg,#10314D,#1A6BB0);color:#fff}
.bar .in{max-width:1080px;margin:0 auto;padding:14px 22px;display:flex;align-items:center;gap:12px}
.logo{width:34px;height:34px;flex:none}.brand{font-size:20px;font-weight:700;letter-spacing:.2px}.brand small{display:block;font-weight:400;font-size:13px;opacity:.85}
.bar a{margin-left:auto;color:#fff;text-decoration:none;border:1px solid rgba(255,255,255,.5);padding:6px 14px;border-radius:999px;font-size:15px}
.bar a:hover{background:rgba(255,255,255,.12)}
.wrap{max-width:1080px;margin:0 auto;padding:22px}
.test{display:flex;gap:10px;align-items:flex-start;background:var(--amber-bg);border:1px solid #EBCB85;color:#6A4705;padding:10px 14px;border-radius:10px;margin-bottom:20px;font-size:15px}
.cols{display:grid;grid-template-columns:minmax(0,5fr) minmax(0,6fr);gap:22px;align-items:start}@media(max-width:860px){.cols{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px;box-shadow:0 1px 2px rgba(16,49,77,.05),0 8px 24px -16px rgba(16,49,77,.25)}
h1{font-size:24px;margin:0 0 4px}h2{font-size:20px;margin:0 0 4px}.sub{color:var(--mut);margin:0 0 18px;font-size:15px}
.step{display:flex;gap:10px;align-items:center;margin:18px 0 10px;color:var(--care-d);font-weight:700;font-size:15px}
.step i{font-style:normal;width:24px;height:24px;border-radius:50%;background:var(--care);color:#fff;display:grid;place-items:center;font-size:13px}
.field{margin-bottom:12px}.two{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media(max-width:480px){.two{grid-template-columns:1fr}}
label{display:block;font-size:15px;font-weight:700;margin-bottom:5px}
input,select{width:100%;padding:12px 13px;border:1.5px solid #B9CDE0;border-radius:10px;font:inherit;color:var(--ink);background:#fff;min-height:48px}
input:focus,select:focus{outline:3px solid #9CC9EE;outline-offset:1px;border-color:var(--care)}
.help{font-size:13px;color:var(--mut);margin-top:4px}
.btn{width:100%;margin-top:14px;background:var(--care);color:#fff;border:0;border-radius:10px;padding:14px 18px;font:inherit;font-size:18px;font-weight:700;cursor:pointer;min-height:52px}
.btn:hover{background:var(--care-d)}.btn:focus-visible{outline:3px solid #9CC9EE;outline-offset:2px}.btn[disabled]{opacity:.75;cursor:progress}
.demo{margin-top:18px;padding-top:16px;border-top:1px dashed var(--line)}.demo p{margin:0 0 8px;font-size:14px;color:var(--mut)}
.chips{display:flex;flex-wrap:wrap;gap:8px}.chip{border:1.5px solid #B9CDE0;background:var(--sky);color:var(--ink);border-radius:999px;padding:7px 13px;font:inherit;font-size:14px;cursor:pointer}
.chip:hover,.chip:focus-visible{border-color:var(--care);outline:none;background:#fff}
.chip b{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;vertical-align:1px}
.empty{text-align:center;color:var(--mut);padding:40px 16px}.empty svg{width:72px;height:72px;margin-bottom:8px}
.status{border-radius:14px;padding:20px 22px;display:flex;gap:16px;align-items:center;margin-bottom:16px}
.status .ic{width:52px;height:52px;border-radius:50%;display:grid;place-items:center;flex:none;color:#fff;font-size:26px;font-weight:700}
.status .t{font-size:24px;font-weight:700;line-height:1.2}.status .d{font-size:15px;margin-top:2px}
.s-ok{background:var(--mint-bg)}.s-ok .ic{background:var(--mint)}.s-ok .t{color:#0E6A50}
.s-warn{background:var(--amber-bg)}.s-warn .ic{background:var(--amber)}.s-warn .t{color:#7A4E03}
.s-bad{background:var(--coral-bg)}.s-bad .ic{background:var(--coral)}.s-bad .t{color:#9A2F29}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:0 0 16px}
.fact{background:var(--sky);border-radius:10px;padding:10px 12px}.fact span{display:block;font-size:13px;color:var(--mut)}.fact b{font-size:16px}
.flag{display:flex;gap:10px;background:var(--amber-bg);border-left:4px solid var(--amber);padding:10px 12px;border-radius:8px;margin:8px 0;font-size:15px}
.s-bad~.flag{background:var(--coral-bg);border-color:var(--coral)}
table{width:100%;border-collapse:collapse;margin-top:14px;font-size:15px}caption{text-align:left;font-weight:700;margin-bottom:6px}
th{background:var(--sky);text-align:left;padding:9px 10px;color:var(--mut);font-weight:700}td{padding:10px;border-top:1px solid var(--line);vertical-align:top}
td:nth-child(2){font-weight:700}td{overflow-wrap:anywhere}
@media(max-width:860px){.cols>section:not(.empty){order:-1}.cols>.empty{display:none}}
details{margin-top:14px;font-size:14px}pre{white-space:pre-wrap;font-size:12px;background:var(--sky);padding:10px;border-radius:8px;max-height:320px;overflow:auto}
.login{max-width:420px;margin:30px auto}.login .hero{text-align:center;margin-bottom:12px}.login .hero svg{width:64px;height:64px}
.err{background:var(--coral-bg);color:#9A2F29;border-radius:8px;padding:9px 12px;margin:0 0 12px;font-size:15px}
footer{text-align:center;color:var(--mut);font-size:13px;padding:10px 0 30px}
.bar .nav{margin-left:auto;display:flex;gap:8px;flex-wrap:wrap}.bar .nav a{margin-left:0}.bar .nav a.on{background:rgba(255,255,255,.2)}
.est{display:flex;flex-direction:column;background:linear-gradient(135deg,#E8F2FB,#F5FAFE);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:0 0 14px}.est span{font-size:14px;color:var(--mut)}.est b{font-size:30px;color:var(--care-d);line-height:1.2}.est small{font-size:14px;color:var(--mut)}
.meterw{margin:0 0 14px}.meterw .ml{font-size:15px;margin-bottom:6px}.meter{height:12px;background:#E3ECF4;border-radius:999px;overflow:hidden}.meter i{display:block;height:100%;background:var(--mint);border-radius:999px}.meter i.w{background:var(--amber)}.meter i.b{background:var(--coral)}
.msg{margin-top:16px;border:1.5px dashed #B9CDE0;border-radius:12px;padding:12px 14px;background:#FBFDFF}.msg .mh{font-size:13px;font-weight:700;color:var(--mut);text-transform:uppercase;letter-spacing:.4px}.msg p{margin:6px 0 10px}
.sum{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:18px}.sum .card{padding:16px}.sum span{display:block;font-size:14px;color:var(--mut)}.sum b{font-size:28px}
.pill{display:inline-block;border-radius:999px;padding:3px 10px;font-size:13px;font-weight:700;white-space:nowrap}.p-ok{background:var(--mint-bg);color:#0E6A50}.p-warn{background:var(--amber-bg);color:#7A4E03}.p-bad{background:var(--coral-bg);color:#9A2F29}
.sched td{vertical-align:middle}.sched td:nth-child(2){font-weight:700}.sched ul{margin:0;padding-left:18px;font-size:14px}
.topline{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:14px}.topline h1{margin:0}.topline form{margin:0}.topline .btn{width:auto;margin:0;padding:10px 16px;font-size:16px;min-height:44px}
@media(max-width:700px){.sched thead{display:none}.sched tr{display:block;border-top:1px solid var(--line);padding:8px 0}.sched td{display:block;border:0;padding:3px 0}}
@media (prefers-reduced-motion:no-preference){.status{animation:pop .35s ease-out}@keyframes pop{from{transform:scale(.98);opacity:.4}to{transform:none;opacity:1}}}`;
const LOGO = `<svg class="logo" viewBox="0 0 40 40" aria-hidden="true"><path d="M20 3 6 8v11c0 9 6 15.5 14 18 8-2.5 14-9 14-18V8z" fill="#fff" opacity=".95"/><path d="M17 13h6v5h5v6h-5v5h-6v-5h-5v-6h5z" fill="#1A6BB0"/></svg>`;
const CLIP = `<svg viewBox="0 0 72 72" aria-hidden="true"><rect x="14" y="10" width="44" height="54" rx="7" fill="#DCEBF7"/><rect x="25" y="5" width="22" height="11" rx="4" fill="#1A6BB0"/><path d="M23 30h26M23 39h26M23 48h16" stroke="#7FAAD0" stroke-width="4" stroke-linecap="round"/></svg>`;
const page = (title, body, env, authed, active = '') => new Response(`<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><meta name="theme-color" content="#10314D"><title>${title} | Coverage Check</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@400;700&display=swap" rel="stylesheet"><style>${CSS}</style></head><body>
<header class="bar"><div class="in">${LOGO}<div class="brand">Coverage Check<small>Insurance eligibility in seconds</small></div>${authed ? `<nav class="nav" aria-label="Main"><a href="/"${active === 'check' ? ' class="on" aria-current="page"' : ''}>Check coverage</a><a href="/schedule"${active === 'schedule' ? ' class="on" aria-current="page"' : ''}>Today\u2019s schedule</a><a href="/logout">Log out</a></nav>` : ''}</div></header><main class="wrap">
<div class="test" role="note"><span aria-hidden="true">\u26a0\ufe0f</span><div><b>Test mode.</b> ${env.STEDI_API_KEY ? 'Connected to the Stedi test sandbox (mock members) plus sample patients.' : 'Using sample patients.'} Do not enter real patient information.</div></div>${body}</main>
<footer>Coverage Check \u00b7 test mode (sample data only)</footer>
<script>document.querySelectorAll('[data-fill]').forEach(b=>b.addEventListener('click',()=>{const d=JSON.parse(b.dataset.fill);for(const k in d){const e=document.getElementById(k);if(e)e.value=d[k];}document.getElementById('memberId').focus();}));
document.querySelectorAll('[data-copy]').forEach(b=>b.addEventListener('click',()=>{navigator.clipboard&&navigator.clipboard.writeText(document.getElementById(b.dataset.copy).textContent);b.textContent='Copied \u2713';}));
document.querySelectorAll('form').forEach(f=>f.addEventListener('submit',()=>{const b=f.querySelector('.btn');if(b){b.disabled=true;b.dataset.t=b.textContent;b.textContent=b.dataset.busy||'Please wait\u2026';}}));</script></body></html>`, { headers: { 'content-type': 'text/html; charset=utf-8', 'x-frame-options': 'DENY', 'cache-control': 'no-store', 'referrer-policy': 'no-referrer' } });
const loginForm = (msg = '') => `<div class="login"><div class="card"><div class="hero"><svg viewBox="0 0 64 64" aria-hidden="true"><circle cx="32" cy="32" r="30" fill="#DCEBF7"/><path d="M32 12 18 17v10c0 9 6 15.5 14 18 8-2.5 14-9 14-18V17z" fill="#1A6BB0"/><path d="M29 22h6v5h5v6h-5v5h-6v-5h-5v-6h5z" fill="#fff"/></svg></div>
<h1 style="text-align:center">Welcome back</h1><p class="sub" style="text-align:center">Sign in to check a patient\u2019s insurance coverage.</p>
<form method="post" action="/login">${msg ? `<p class="err" role="alert">${esc(msg)}</p>` : ''}<div class="field"><label for="pw">Password</label><input id="pw" name="password" type="password" autocomplete="current-password" required autofocus></div>
<button class="btn" type="submit" data-busy="Signing in\u2026">Sign in</button></form></div></div>`;
const chip = (id, c, tag, visit, lang = '') => { const m = DEMO_MEMBERS[id]; return [c, `${nice(m.first)} ${nice(m.last)}`, tag, { firstName: nice(m.first), lastName: nice(m.last), dob: m.dob, memberId: id, payer: 'DEMO', ...(visit ? { visit } : {}), lang: lang || m.details.lang }]; };
const DEMO_CHIPS = [chip('DEMO1006', '#178A6A', 'all clear', 'pt'), chip('DEMO1001', '#178A6A', 'copay', 'chiro'), chip('DEMO1004', '#A86C06', 'visit limit \u00b7 Spanish', 'pt'), chip('DEMO1005', '#A86C06', 'authorization', 'pt'),
  chip('DEMO1003', '#A86C06', 'deductible \u00b7 referral', 'specialist'), chip('DEMO1002', '#C2413A', 'coverage ended', 'pt_eval')];
const STEDI_CHIPS = [['#178A6A', 'John Doe (UHC)', 'sandbox', { firstName: 'John', lastName: 'Doe', dob: '1970-01-01', memberId: 'UHC202649', payer: '87726' }]];
const checkForm = (f = {}, env) => `<form class="card" method="post" action="/check"><h1>Check insurance coverage</h1><p class="sub">Enter the patient\u2019s details exactly as they appear on their insurance card.</p>
<div class="step"><i>1</i>Insurance</div>
<div class="field"><label for="payer">Insurance company</label><select id="payer" name="payer">${PAYERS.map(([id, n]) => `<option value="${id}"${f.payer === id ? ' selected' : ''}>${esc(n)}</option>`).join('')}</select></div>
<div class="field"><label for="memberId">Member ID</label><input id="memberId" name="memberId" value="${esc(f.memberId)}" autocomplete="off" required><div class="help">Printed on the front of the insurance card.</div></div>
<div class="step"><i>2</i>Patient</div>
<div class="two"><div class="field"><label for="firstName">First name</label><input id="firstName" name="firstName" value="${esc(f.firstName)}" autocomplete="off" required></div>
<div class="field"><label for="lastName">Last name</label><input id="lastName" name="lastName" value="${esc(f.lastName)}" autocomplete="off" required></div></div>
<div class="field"><label for="dob">Date of birth</label><input id="dob" name="dob" type="date" value="${esc(f.dob)}" required></div>
<div class="step"><i>3</i>Visit</div>
<div class="two"><div class="field"><label for="visit">Type of visit</label><select id="visit" name="visit">${Object.entries(VISITS).map(([k, [n]]) => `<option value="${k}"${(f.visit || 'office') === k ? ' selected' : ''}>${esc(n)}</option>`).join('')}</select></div>
<div class="field"><label for="lang">Patient message</label><select id="lang" name="lang"><option value="en"${f.lang === 'es' ? '' : ' selected'}>English</option><option value="es"${f.lang === 'es' ? ' selected' : ''}>Espa\u00f1ol</option></select></div></div>
<button class="btn" type="submit" data-busy="Checking coverage\u2026">Check coverage</button>
<div class="demo"><p>No patient handy? Try a sample patient:</p><div class="chips">${(env.STEDI_API_KEY ? [...STEDI_CHIPS, ...DEMO_CHIPS] : DEMO_CHIPS).map(([c, n, t, d]) => `<button type="button" class="chip" data-fill='${esc(JSON.stringify(d))}'><b style="background:${c}"></b>${esc(n)} <span style="color:var(--mut)">\u00b7 ${esc(t)}</span></button>`).join('')}</div></div></form>`;
export function statusKind(r) { const s = (r.status || '').toLowerCase(); if (/inactive|not found|error|terminated/.test(s)) return 'bad'; if (/active/.test(s) && !(r.flags || []).length) return 'ok'; if (/active/.test(s)) return 'warn'; return 'warn'; }
const HEAD = { ok: ['\u2713', 'Patient is covered', 'Coverage is active. Details below.'], warn: ['!', 'Covered, but check the notes', 'Coverage is active, with things to review before the visit.'], bad: ['\u2715', 'Not covered', 'Coverage could not be confirmed.'] };
export function resultHtml(r) {
  const k = statusKind(r), [ic, t, d] = HEAD[k];
  const title = /not found/i.test(r.status || '') ? 'Patient not found' : /error/i.test(r.status || '') ? 'Could not check coverage' : t;
  const facts = [['Plan', r.plan], ['Group', r.group], ['Coverage start', r.start], ['Coverage end', r.end], ['Network', r.network]].filter(([, v]) => v);
  return `<section class="card" aria-live="polite"><div class="status s-${k}"><div class="ic" aria-hidden="true">${ic}</div><div><div class="t">${esc(title)}</div><div class="d">${esc(r.status)} \u00b7 ${esc(d)}</div></div></div>
${facts.length ? `<div class="facts">${facts.map(([a, b]) => `<div class="fact"><span>${a}</span><b>${esc(b)}</b></div>`).join('')}</div>` : ''}
${r.estimate ? `<div class="est"><span>Estimated patient cost \u00b7 ${esc(r.vname || 'visit')}</span><b>${money(r.estimate.owe)}</b><small>${esc(r.estimate.how)}</small></div>` : ''}
${r.visits ? (() => { const v = r.visits, pct = Math.min(100, Math.round((v.used / v.limit) * 100)), c = v.left <= 0 ? 'b' : v.left <= 3 ? 'w' : ''; return `<div class="meterw"><div class="ml"><b>${esc(v.label)} visits:</b> ${v.used} of ${v.limit} used \u00b7 <b>${Math.max(0, v.left)} left</b> this year</div><div class="meter" role="img" aria-label="${v.used} of ${v.limit} visits used"><i class="${c}" style="width:${pct}%"></i></div></div>`; })() : ''}
${r.auth && !r.auth.missing ? `<div class="facts"><div class="fact"><span>Authorization</span><b>${esc(r.auth.number)}</b></div><div class="fact"><span>Approved visits</span><b>${r.auth.used} of ${r.auth.approved} used</b></div><div class="fact"><span>Expires</span><b>${esc(r.auth.expires)}</b></div></div>` : ''}
${(r.flags || []).map((x) => `<div class="flag"><span aria-hidden="true">\u26a0\ufe0f</span><div>${esc(x)}</div></div>`).join('')}
${r.items?.length ? `<table><caption>What the plan covers</caption><tr><th scope="col">Benefit</th><th scope="col">Amount</th><th scope="col">Details</th></tr>${r.items.map(([a, b, c]) => `<tr><td>${esc(a)}</td><td>${esc(b)}</td><td>${esc(c)}</td></tr>`).join('')}</table>` : ''}
${r.message ? `<div class="msg"><div class="mh">Message for the patient \u00b7 ${r.msgLang === 'es' ? 'Espa\u00f1ol' : 'English'}</div><p id="pmsg">${esc(r.message)}</p><button type="button" class="chip" data-copy="pmsg">Copy message</button></div>` : ''}
${r.raw ? `<details><summary>Show raw response (technical)</summary><pre>${esc(JSON.stringify(r.raw, null, 2))}</pre></details>` : ''}</section>`;
}
const emptyPanel = `<section class="card empty">${CLIP}<h2>Results will appear here</h2><p class="sub" style="margin:0">Fill in the form and press <b>Check coverage</b>.</p></section>`;
const todayCT = () => new Date().toLocaleDateString('en-CA', { timeZone: 'America/Chicago' });
const nowCT = () => new Date().toLocaleTimeString('en-US', { timeZone: 'America/Chicago', hour: 'numeric', minute: '2-digit' });
export async function runCheck(f, env, today = todayCT()) {
  let r;
  try { r = env.STEDI_API_KEY && f.payer !== 'DEMO' ? await stediCheck(f, env) : demoCheck(f); } catch (e) { r = { status: 'Error', items: [], flags: ['Could not reach the eligibility service. Try again.'] }; }
  const m = DEMO_MEMBERS[(f.memberId || '').trim().toUpperCase()];
  const found = !/not found|error/i.test(r.status || '');
  r = enrich(r, found && m && (f.payer === 'DEMO' || !env.STEDI_API_KEY) ? m.details : null, f.visit, today);
  if (found) { r.msgLang = f.lang || r.lang || 'en'; r.message = patientMessage(r, f.firstName, r.msgLang); }
  return r;
}
const pillOf = (r) => { const k = statusKind(r); return `<span class="pill p-${k}">${k === 'ok' ? 'Covered' : k === 'warn' ? 'Check notes' : 'Not covered'}</span>`; };
export function schedulePage(today = todayCT(), checkedAt = nowCT()) {
  const rows = SCHEDULE.map(([time, id, visit]) => { const m = DEMO_MEMBERS[id]; return { time, id, visit, name: `${nice(m.first)} ${nice(m.last)}`, r: enrich(m.result, m.details, visit, today) }; });
  const attention = rows.filter((x) => statusKind(x.r) !== 'ok').length;
  const collect = rows.filter((x) => statusKind(x.r) !== 'bad').reduce((a, x) => a + (x.r.estimate?.owe || 0), 0);
  return `<div class="topline"><div><h1>Today\u2019s schedule</h1><p class="sub" style="margin:4px 0 0">${esc(today)} \u00b7 every patient re-checked at ${esc(checkedAt)}. In the live version this runs automatically each morning before the clinic opens.</p></div>
<form method="post" action="/schedule"><button class="btn" type="submit" data-busy="Re-checking\u2026">Re-check everyone now</button></form></div>
<div class="sum"><div class="card"><span>Patients today</span><b>${rows.length}</b></div><div class="card"><span>Need attention</span><b style="color:${attention ? 'var(--amber)' : 'var(--mint)'}">${attention}</b></div><div class="card"><span>To collect at check-in</span><b>${money(collect)}</b></div></div>
<section class="card"><table class="sched"><caption>Check-in list</caption><thead><tr><th scope="col">Time</th><th scope="col">Patient</th><th scope="col">Visit</th><th scope="col">Coverage</th><th scope="col">Collect today</th><th scope="col">Needs attention</th></tr></thead><tbody>
${rows.map((x) => `<tr><td>${esc(x.time)}</td><td><a href="/check?member=${x.id}&visit=${x.visit}">${esc(x.name)}</a></td><td>${esc(VISITS[x.visit][0])}</td><td>${pillOf(x.r)}</td><td>${statusKind(x.r) === 'bad' ? '\u2014 (no coverage)' : money(x.r.estimate?.owe)}</td><td>${x.r.flags.length ? `<ul>${x.r.flags.map((f) => `<li>${esc(f)}</li>`).join('')}</ul>` : 'Nothing \u2014 all clear'}</td></tr>`).join('')}
</tbody></table></section>`;
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
    if (url.pathname === '/schedule') return page('Today\u2019s schedule', schedulePage(), env, true, 'schedule');
    if (url.pathname === '/check') {
      let f;
      if (req.method === 'POST') { const fd = await req.formData(); f = Object.fromEntries(['payer', 'memberId', 'firstName', 'lastName', 'dob', 'visit', 'lang'].map((k) => [k, String(fd.get(k) || '').trim().slice(0, 80)])); }
      else { const id = (url.searchParams.get('member') || '').toUpperCase(), m = DEMO_MEMBERS[id]; if (!m) return new Response(null, { status: 302, headers: { location: '/' } });
        f = { payer: 'DEMO', memberId: id, firstName: nice(m.first), lastName: nice(m.last), dob: m.dob, visit: url.searchParams.get('visit') || 'office', lang: m.details.lang }; }
      const r = await runCheck(f, env);
      return page('Result', `<div class="cols">${checkForm(f, env)}${resultHtml(r)}</div>`, env, true, 'check');
    }
    return page('Check coverage', `<div class="cols">${checkForm({}, env)}${emptyPanel}</div>`, env, true, 'check');
  },
};
