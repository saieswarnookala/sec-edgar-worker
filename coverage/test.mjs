import assert from 'node:assert/strict';
import worker, { makeSession, validSession, demoCheck, summarizeStedi, resultHtml, enrich, patientMessage, schedulePage, DEMO_MEMBERS } from './src/index.js';
const env = { PORTAL_PASSWORD: 'test-pass-123' }, S = 'test-pass-123:session';
// sessions
const tok = await makeSession(S); assert.ok(await validSession(S, tok)); assert.ok(!(await validSession('other', tok)));
assert.ok(!(await validSession(S, await makeSession(S, Date.now() - 9 * 3600e3)))); assert.ok(!(await validSession(S, 'junk')));
// demo lookups
assert.equal(demoCheck({ memberId: 'demo1001', lastName: 'Lee', dob: '1985-04-12' }).status, 'Active');
assert.equal(demoCheck({ memberId: 'DEMO1002', lastName: 'Garcia', dob: '1972-09-30' }).status, 'Inactive');
assert.equal(demoCheck({ memberId: 'DEMO1001', lastName: 'Lee', dob: '1985-04-13' }).status, 'Not found');
// stedi summary
const s = summarizeStedi({ planStatus: [{ status: 'Active Coverage', planDetails: 'Choice Plus' }], planInformation: { groupNumber: 'G1' }, planDateInformation: { planBegin: '20260101' },
  benefitsInformation: [{ name: 'Co-Payment', benefitAmount: '25', serviceTypes: ['Professional (Physician) Visit - Office'], inPlanNetworkIndicator: 'Yes' }, { name: 'Co-Insurance', benefitPercent: '0.2' }] });
assert.equal(s.status, 'Active Coverage'); assert.equal(s.items[0][1], '$25'); assert.equal(s.items[1][1], '20%');
assert.equal(summarizeStedi({ errors: [{ code: '72', description: 'Invalid member ID' }] }).status, 'Error');
// html escapes
assert.ok(resultHtml({ status: 'Active', plan: '<script>x</script>', items: [] }).includes('&lt;script&gt;'));
// full flow through the worker
const get = (p, c) => worker.fetch(new Request('https://x' + p, { headers: c ? { cookie: c } : {} }), env);
const post = (p, data, c) => worker.fetch(new Request('https://x' + p, { method: 'POST', body: new URLSearchParams(data), headers: { 'content-type': 'application/x-www-form-urlencoded', ...(c ? { cookie: c } : {}) } }), env);
assert.ok((await (await get('/')).text()).includes('Sign in'));
assert.ok((await (await post('/login', { password: 'nope' })).text()).includes('Wrong password'));
const ok = await post('/login', { password: 'test-pass-123' }); assert.equal(ok.status, 302);
const ck = ok.headers.get('set-cookie').split(';')[0];
assert.ok((await (await get('/', ck)).text()).includes('Check insurance coverage'));
const res = await (await post('/check', { payer: 'DEMO', memberId: 'DEMO1003', firstName: 'Sam', lastName: 'Patel', dob: '1990-02-18' }, ck)).text();
assert.ok(res.includes('High deductible') && res.includes('Test mode'));
assert.ok((await (await post('/check', { payer: 'DEMO', memberId: 'DEMO1001', firstName: 'x', lastName: 'Lee', dob: '1985-04-12' })).text()).includes('Sign in')); // no cookie -> blocked
// features: cost estimate, visit limits, authorizations, referrals, Spanish message, schedule
const E = (id, v) => enrich(DEMO_MEMBERS[id].result, DEMO_MEMBERS[id].details, v, '2026-11-08');
assert.equal(E('DEMO1001', 'chiro').estimate.owe, 30);                       // copay
assert.equal(E('DEMO1003', 'office').estimate.owe, 130);                     // full allowed amount into the deductible
assert.equal(E('DEMO1005', 'pt').estimate.owe, 57);                          // $50 deductible + 10% of $70
assert.ok(E('DEMO1004', 'pt').flags.some((f) => f.includes('Only 2 covered')));
assert.ok(E('DEMO1005', 'pt').flags.some((f) => f.includes('AUTH-80917') && f.includes('1 visit left')));
assert.ok(E('DEMO1003', 'specialist').flags.some((f) => f.includes('referral is required')));
assert.ok(!E('DEMO1003', 'pt').flags.some((f) => f.includes('referral is required')));   // referral on file for PT
assert.equal(E('DEMO1006', 'pt').flags.length, 0);                            // all clear
assert.ok(enrich(DEMO_MEMBERS.DEMO1001.result, DEMO_MEMBERS.DEMO1001.details, 'office', '2026-12-10').flags.some((f) => f.includes('Coverage ends')));
assert.ok(patientMessage(E('DEMO1004', 'pt'), 'LUCIA', 'es').startsWith('Hola Lucia') && patientMessage(E('DEMO1004', 'pt'), 'LUCIA', 'es').includes('$35'));
assert.ok(patientMessage(E('DEMO1002', 'pt'), 'maria', 'en').includes("couldn't confirm"));
const sp = schedulePage('2026-11-08', '7:00 AM'); assert.ok(sp.includes('Check-in list') && sp.includes('$267'), sp.match(/To collect[^$]*\$[\d,.]+/)?.[0]);
const rh = resultHtml(E('DEMO1005', 'pt')); assert.ok(rh.includes('Estimated patient cost') && rh.includes('11 of 30 used') && rh.includes('AUTH-80917'));
// routes
assert.ok((await (await get('/schedule', ck)).text()).includes('Today\u2019s schedule'));
assert.ok((await (await get('/schedule')).text()).includes('Sign in'));   // protected
const fromSched = await (await get('/check?member=DEMO1004&visit=pt', ck)).text(); assert.ok(fromSched.includes('Hola Lucia') && fromSched.includes('18 of 20 used'));
console.log('coverage portal tests passed');
