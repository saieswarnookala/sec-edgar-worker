import assert from 'node:assert/strict';
import worker, { makeSession, validSession, demoCheck, summarizeStedi, resultHtml } from './src/index.js';
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
assert.ok(res.includes('High deductible') && res.includes('Demo mode'));
assert.ok((await (await post('/check', { payer: 'DEMO', memberId: 'DEMO1001', firstName: 'x', lastName: 'Lee', dob: '1985-04-12' })).text()).includes('Sign in')); // no cookie -> blocked
console.log('coverage portal tests passed');
