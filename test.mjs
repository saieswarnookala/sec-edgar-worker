import assert from 'node:assert/strict';
import worker, { flowSeries } from './src/worker.js';

let pass = 0;
const t = async (name, fn) => { try { await fn(); pass++; console.log('ok  ', name); } catch (e) { console.log('FAIL', name, '\n   ', e.message); process.exitCode = 1; } };

// ----- synthetic LULU-like data (52/53-week fiscal year ending ~Feb 1) -----
const F = (start, end, val, form, filed) => ({ start, end, val, form, filed, fy: 2025, fp: 'X', accn: 'a' });
const I = (end, val, form, filed) => ({ end, val, form, filed, fy: 2025, fp: 'X', accn: 'a' });

const FY24 = ['2024-01-29', '2025-02-02'];
const FY25 = ['2025-02-03', '2026-02-01'];
const Q = {
  q1: ['2025-02-03', '2025-05-04'], q2: ['2025-05-05', '2025-08-03'], q3: ['2025-08-04', '2025-11-02'],
  q1n: ['2026-02-02', '2026-05-03'], q2n: ['2026-05-04', '2026-08-02'],
};

const concepts = {
  RevenueFromContractWithCustomerExcludingAssessedTax: { USD: [
    F(...FY24, 10588, '10-K', '2025-03-27'),
    F(...Q.q1, 2371, '10-Q', '2025-06-05'),
    F(...Q.q2, 2525, '10-Q', '2025-09-04'), F(Q.q1[0], Q.q2[1], 4896, '10-Q', '2025-09-04'),
    F(...Q.q3, 2566, '10-Q', '2025-12-04'), F(Q.q1[0], Q.q3[1], 7462, '10-Q', '2025-12-04'),
    F(...FY25, 11100, '10-K', '2026-03-26'),
    F(...FY25, 11100, '10-K', '2026-03-26'), // dup
    F(...Q.q1n, 2450, '10-Q', '2026-06-04'),
    F(...Q.q2n, 2600, '10-Q', '2026-09-03'), F(Q.q1n[0], Q.q2n[1], 5050, '10-Q', '2026-09-03'),
  ] },
  NetIncomeLoss: { USD: [
    F(...FY24, 1814, '10-K', '2025-03-27'),
    F(...Q.q1, 314, '10-Q', '2025-06-05'), F(...Q.q2, 371, '10-Q', '2025-09-04'),
    F(...Q.q3, 351, '10-Q', '2025-12-04'), F(...FY25, 1700, '10-K', '2026-03-26'),
    F(...FY25, 1710, '10-K/A', '2026-05-01'), // restated, later filed wins
    F(...Q.q1n, 300, '10-Q', '2026-06-04'), F(...Q.q2n, 320, '10-Q', '2026-09-03'),
  ] },
  GrossProfit: { USD: [F(...FY25, 6300, '10-K', '2026-03-26'), F(...Q.q2n, 1450, '10-Q', '2026-09-03')] },
  OperatingIncomeLoss: { USD: [F(...FY25, 2400, '10-K', '2026-03-26'), F(...Q.q2n, 450, '10-Q', '2026-09-03')] },
  // cash flow: YTD only
  NetCashProvidedByUsedInOperatingActivities: { USD: [
    F(...FY24, 2300, '10-K', '2025-03-27'),
    F(...Q.q1, 100, '10-Q', '2025-06-05'),
    F(Q.q1[0], Q.q2[1], 400, '10-Q', '2025-09-04'),
    F(Q.q1[0], Q.q3[1], 700, '10-Q', '2025-12-04'),
    F(...FY25, 2000, '10-K', '2026-03-26'),
    F(...Q.q1n, 150, '10-Q', '2026-06-04'),
    F(Q.q1n[0], Q.q2n[1], 500, '10-Q', '2026-09-03'),
  ] },
  PaymentsToAcquirePropertyPlantAndEquipment: { USD: [
    F(...FY25, 700, '10-K', '2026-03-26'), F(Q.q1[0], Q.q3[1], 500, '10-Q', '2025-12-04'),
    F(Q.q1n[0], Q.q2n[1], 360, '10-Q', '2026-09-03'), F(...Q.q1n, 170, '10-Q', '2026-06-04'),
  ] },
  Assets: { USD: [I('2026-02-01', 7600, '10-K', '2026-03-26'), I('2026-08-02', 7900, '10-Q', '2026-09-03')] },
  AssetsCurrent: { USD: [I('2026-02-01', 3800, '10-K', '2026-03-26')] },
  LiabilitiesCurrent: { USD: [I('2026-02-01', 1700, '10-K', '2026-03-26')] },
  StockholdersEquity: { USD: [I('2026-02-01', 4300, '10-K', '2026-03-26'), I('2026-08-02', 4500, '10-Q', '2026-09-03')] },
  CashAndCashEquivalentsAtCarryingValue: { USD: [I('2026-02-01', 1500, '10-K', '2026-03-26')] },
  OperatingLeaseLiabilityNoncurrent: { USD: [I('2026-02-01', 1300, '10-K', '2026-03-26')] },
  OperatingLeaseLiabilityCurrent: { USD: [I('2026-02-01', 290, '10-K', '2026-03-26')] },
  CommonStockSharesOutstanding: { shares: [I('2026-02-01', 120, '10-K', '2026-03-26')] },
  WeightedAverageNumberOfDilutedSharesOutstanding: { shares: [F(...Q.q2n, 119, '10-Q', '2026-09-03')] },
};

const tickers = JSON.stringify({ fields: ['cik', 'name', 'ticker', 'exchange'], data: [
  [320193, 'Apple Inc.', 'AAPL', 'Nasdaq'],
  [999999, 'LULU', 'LLX', 'NYSE'],               // name equals the ticker we search: must be skipped
  [888888, 'Weird [Co], Inc.', 'WRD', 'NYSE'],     // brackets in name
  [1397187, 'lululemon athletica inc.', 'LULU', 'Nasdaq'],
  [1067983, 'BERKSHIRE HATHAWAY INC', 'BRK-B', 'NYSE'],
] });

let fetchLog = [];
globalThis.fetch = async (url, init) => {
  fetchLog.push(url);
  assert.ok(init?.headers?.['User-Agent'], 'User-Agent header missing');
  if (url.endsWith('company_tickers_exchange.json')) return new Response(tickers);
  if (url.includes('/submissions/')) return new Response(JSON.stringify({ cik: '1397187', sic: '2300', sicDescription: 'Apparel & Other Finishd Prods of Fabrics & Similar Matl', fiscalYearEnd: '0201', name: 'lululemon athletica inc.' }));
  const m = url.match(/us-gaap\/(\w+)\.json$/);
  if (m && concepts[m[1]]) return new Response(JSON.stringify({ tag: m[1], units: concepts[m[1]] }));
  return new Response('not found', { status: 404 });
};

const env = { SEC_USER_AGENT: 'Test test@example.com', ACCESS_TOKEN: 'tok123' };
const call = (body, path = '/mcp/tok123', method = 'POST') =>
  worker.fetch(new Request('https://x.workers.dev' + path, { method, body: body ? JSON.stringify(body) : undefined, headers: { 'Content-Type': 'application/json' } }), env);
const tool = async (name, args) => {
  const r = await call({ jsonrpc: '2.0', id: 9, method: 'tools/call', params: { name, arguments: args } });
  const j = await r.json();
  return j.result;
};

await t('health', async () => { const r = await call(null, '/health', 'GET'); assert.equal(r.status, 200); });
await t('wrong token → 404', async () => { const r = await call({ jsonrpc: '2.0', id: 1, method: 'ping' }, '/mcp/nope'); assert.equal(r.status, 404); });
await t('GET on mcp → 405', async () => { const r = await call(null, '/mcp/tok123', 'GET'); assert.equal(r.status, 405); });
await t('initialize', async () => {
  const j = await (await call({ jsonrpc: '2.0', id: 1, method: 'initialize', params: { protocolVersion: '2025-06-18' } })).json();
  assert.equal(j.result.protocolVersion, '2025-06-18'); assert.ok(j.result.capabilities.tools);
});
await t('notification → 202', async () => { const r = await call({ jsonrpc: '2.0', method: 'notifications/initialized' }); assert.equal(r.status, 202); });
await t('tools/list', async () => {
  const j = await (await call({ jsonrpc: '2.0', id: 2, method: 'tools/list' })).json();
  assert.deepEqual(j.result.tools.map((x) => x.name), ['get_universe', 'get_screen', 'get_financials', 'lookup_company']);
});
await t('batch', async () => {
  const j = await (await call([{ jsonrpc: '2.0', id: 1, method: 'ping' }, { jsonrpc: '2.0', method: 'notifications/x' }])).json();
  assert.equal(j.length, 1);
});
await t('unknown method', async () => { const j = await (await call({ jsonrpc: '2.0', id: 3, method: 'foo' })).json(); assert.equal(j.error.code, -32601); });

await t('lookup_company skips name match, finds LULU', async () => {
  const r = await tool('lookup_company', { symbol: 'lulu' });
  const d = r.structuredContent;
  assert.equal(d.cik, '0001397187'); assert.equal(d.sic, '2300'); assert.equal(d.fiscal_year_end, '02-01'); assert.equal(d.exchange, 'Nasdaq');
});
await t('lookup BRK.B normalizes to BRK-B', async () => { const r = await tool('lookup_company', { symbol: 'BRK.B' }); assert.equal(r.structuredContent.cik, '0001067983'); });
await t('lookup unknown → isError', async () => { const r = await tool('lookup_company', { symbol: 'ZZZZ' }); assert.equal(r.isError, true); });

let fin;
await t('get_financials returns rows', async () => {
  fetchLog = [];
  const r = await tool('get_financials', { symbol: 'LULU' });
  assert.ok(!r.isError, r.content?.[0]?.text);
  fin = r.structuredContent;
  assert.ok(fetchLog.length <= 46, 'subrequests ' + fetchLog.length);
  console.log('      subrequests used:', fetchLog.length);
});
const row = (p, d) => fin.rows.find((x) => x.period === p && x.date === d);
await t('annual FY25 + restatement wins', async () => {
  const a = row('annual', '2026-02-01');
  assert.equal(a.revenue, 11100); assert.equal(a.net_income, 1710); assert.equal(a.gross_profit, 6300);
});
await t('Q4 revenue derived = FY - 9M', async () => { assert.equal(row('quarterly', '2026-02-01').revenue, 11100 - 7462); });
await t('cash flow quarters from YTD', async () => {
  assert.equal(row('quarterly', '2025-05-04').operating_cf, 100);
  assert.equal(row('quarterly', '2025-08-03').operating_cf, 300);
  assert.equal(row('quarterly', '2025-11-02').operating_cf, 300);
  assert.equal(row('quarterly', '2026-02-01').operating_cf, 1300);
  assert.equal(row('quarterly', '2026-08-02').operating_cf, 350);
});
await t('capex positive and derived', async () => {
  assert.equal(row('quarterly', '2026-02-01').capex, 200);
  assert.equal(row('quarterly', '2026-08-02').capex, 190);
});
await t('direct quarter not overwritten by derivation', async () => { assert.equal(row('quarterly', '2025-08-03').revenue, 2525); });
await t('balance + leases + no-debt company', async () => {
  const a = row('annual', '2026-02-01');
  assert.equal(a.total_assets, 7600); assert.equal(a.equity, 4300); assert.equal(a.cash, 1500);
  assert.equal(a.leases, 1590); assert.equal(a.borrowings, 0); assert.equal(a.debt_total, 1590); assert.equal(a.long_term_debt, 0);
});
await t('shares: outstanding else diluted', async () => {
  assert.equal(row('annual', '2026-02-01').shares, 120);
  assert.equal(row('quarterly', '2026-08-02').shares, 119);
});
await t('rows sorted newest first per period', async () => {
  const q = fin.rows.filter((x) => x.period === 'quarterly').map((x) => x.date);
  assert.deepEqual(q, [...q].sort().reverse());
  assert.equal(fin.fiscal_year_end, '02-01');
});
await t('KV cache hit skips SEC', async () => {
  const store = new Map();
  const kenv = { ...env, CACHE: { get: async (k) => (store.has(k) ? JSON.parse(store.get(k)) : null), put: async (k, v) => store.set(k, v) } };
  const req = () => worker.fetch(new Request('https://x/mcp/tok123', { method: 'POST', body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name: 'get_financials', arguments: { symbol: 'LULU' } } }) }), kenv);
  await req(); fetchLog = [];
  const j = await (await req()).json();
  assert.equal(fetchLog.length, 0); assert.equal(j.result.structuredContent.cached, true);
});
await t('REST debug endpoint', async () => {
  const r = await call(null, '/api/tok123/financials?symbol=LULU', 'GET');
  assert.equal(r.status, 200); assert.ok((await r.json()).rows.length > 0);
});
await t('flowSeries ignores odd periods', async () => {
  const s = flowSeries([F('2025-01-01', '2025-02-15', 5, '10-Q', '2025-03-01')]);
  assert.equal(s.quarterly.size, 0); assert.equal(s.annual.size, 0);
});

await t('get_screen reads SCREEN_URL', async () => {
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (url) => url === 'https://raw.example/screen.json' ? new Response(JSON.stringify({ rows: [{ bucket: 'Mega', symbol: 'X' }] })) : new Response('nf', { status: 404 });
  const e2 = { ...env, SCREEN_URL: 'https://raw.example/screen.json' };
  const r = await worker.fetch(new Request('https://x/mcp/tok123', { method: 'POST', body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name: 'get_screen', arguments: {} } }) }), e2);
  const j = await r.json();
  assert.equal(j.result.structuredContent.rows[0].symbol, 'X');
  const r2 = await worker.fetch(new Request('https://x/mcp/tok123', { method: 'POST', body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name: 'get_screen', arguments: {} } }) }), env);
  assert.equal((await r2.json()).result.isError, true);
  globalThis.fetch = async (url) => url === 'https://raw.example/universe.json' ? new Response('{"rows":[{"symbol":"U"}]}') : new Response('nf', { status: 404 });
  const r4 = await worker.fetch(new Request('https://x/mcp/tok123', { method: 'POST', body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name: 'get_universe', arguments: {} } }) }), e2);
  assert.equal(JSON.parse((await r4.json()).result.content[0].text).rows[0].symbol, 'U');
  const kenv = { ...env, CACHE: { get: async (k) => (k === 'screen' ? { rows: [{ bucket: 'Mid', symbol: 'KV' }] } : null) } };
  const r3 = await worker.fetch(new Request('https://x/mcp/tok123', { method: 'POST', body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/call', params: { name: 'get_screen', arguments: {} } }) }), kenv);
  assert.equal((await r3.json()).result.structuredContent.rows[0].symbol, 'KV');
  globalThis.fetch = realFetch;
});

console.log(`\n${pass} passed`);
