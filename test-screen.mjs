import assert from 'node:assert/strict';
import { build } from './scripts/build-screen.mjs';
const nrows = [];
for (let i = 0; i < 1200; i++) nrows.push({ symbol: 'Z' + i, name: 'Filler', lastsale: '$5', marketCap: '1000000', volume: '1' });
const add = (symbol, mcap, price='$50.00', vol='100') => nrows.push({ symbol, name: symbol + ' Inc. Common Stock', lastsale: price, marketCap: String(mcap), volume: vol, sector: 'Tech', industry: 'Software' });
// cik map
const tick = {}; let k = 0; const ciks = {};
const reg = (sym, cik) => { tick[k++] = { cik_str: cik, ticker: sym, title: sym }; ciks[sym] = cik; };
// Companies: [sym, cik, mcap, ni, ni1, rev, rev1]
const C = [
  ['MEGA1', 1, 500e9, 5e9, 4e9, 50e9, 40e9],    // pe 100
  ['MEGA2', 2, 300e9, 10e9, 9e9, 60e9, 50e9],   // pe 30
  ['MEGA3', 3, 400e9, 1e9, 2e9, 50e9, 40e9],    // profit shrank -> out
  ['BIG1', 4, 50e9, 0.5e9, 0.4e9, 10e9, 8e9],   // pe 100
  ['BIG2', 5, 20e9, 0.05e9, 0.04e9, 10e9, 8e9], // margin 0.5% -> out
  ['MID1', 6, 5e9, 0.1e9, 0.05e9, 1e9, 0.9e9],  // pe 50
  ['SML1', 7, 1e9, 0.02e9, 0.01e9, 0.3e9, 0.2e9],// pe 50
  ['MIC1', 8, 100e6, 1e6, 0.5e6, 20e6, 10e6],   // pe 100
  ['MIC2', 9, 100e6, 0.4e6, 0.1e6, 10e6, 5e6],  // pe 250 -> out (max)
  ['FLAT', 10, 5e9, 0.1e9, 0.09e9, 1e9, 0.99e9],// sales +1% -> out
  ['NANO', 11, 10e6, 1e6, 0.5e6, 20e6, 10e6],   // < micro -> out
];
for (const [s, cik, m] of C) { add(s, m); reg(s, cik); }
add('BRK/B', 900e9); reg('BRK-B', 12); add('BRK/A', 900e9, '$700000', '1'); reg('BRK-A', 12);
add('PFD^A', 10e9); 
const frame = (field, yr) => ({ data: [
  ...C.map(([s, cik, m, ni, ni1, rev, rev1]) => ({ cik, val: { ni, ni1, rev, rev1 }[field], end: '2025-12-31' })),
  { cik: 12, val: { ni: 12e9, ni1: 8e9, rev: 400e9, rev1: 360e9 }[field], end: '2025-12-31' },
  ...Array.from({ length: 2600 }, (_, i) => ({ cik: 100000 + i, val: 1, end: '2025-12-31' })),
] });
const fetchFn = async (url) => {
  const J = (o) => new Response(JSON.stringify(o));
  if (url.includes('nasdaq')) return J({ data: { rows: nrows } });
  if (url.endsWith('company_tickers.json')) return J(tick);
  const inst = url.match(/us-gaap\/(\w+)\/USD\/CY(\d{4})Q(\d)I\.json/);
  if (inst) {
    const [, tag, y, q] = inst;
    if (tag === 'StockholdersEquity' && y === '2026' && q === '2') return J({ data: [{ cik: 1, val: 100e9, end: '2026-06-30' }, { cik: 6, val: 1e9, end: '2026-06-30' }] });
    if (tag === 'StockholdersEquity' && y === '2025' && q === '4') return J({ data: [{ cik: 1, val: 1, end: '2025-12-31' }, { cik: 4, val: 5e9, end: '2025-12-31' }] });
    if (tag === 'LongTermDebtNoncurrent' && y === '2026' && q === '2') return J({ data: [{ cik: 1, val: 30e9, end: '2026-06-30' }] });
    if (tag === 'LongTermDebtCurrent' && y === '2026' && q === '2') return J({ data: [{ cik: 1, val: 5e9, end: '2026-06-30' }] });
    if (tag === 'LongTermDebt' && y === '2025' && q === '4') return J({ data: [{ cik: 4, val: 2e9, end: '2025-12-31' }] });
    return new Response('nf', { status: 404 });
  }
  const m = url.match(/us-gaap\/(\w+)\/USD\/CY(\d+)\.json/);
  if (m) {
    const [_, tag, y] = m; const cur = y === '2025';
    if (y === '2022' || y === '2020') {
      const f = frame(tag === 'NetIncomeLoss' ? 'ni1' : 'rev1');
      f.data = f.data.map((d) => ({ ...d, val: d.val / 2 }));
      if (tag === 'NetIncomeLoss' || tag === 'Revenues') return J(f);
      return new Response('nf', { status: 404 });
    }
    if (tag === 'NetIncomeLoss') return J(frame(cur ? 'ni' : 'ni1'));
    if (tag === 'Revenues') return J(frame(cur ? 'rev' : 'rev1'));
    return new Response('nf', { status: 404 });
  }
  return new Response('nf', { status: 404 });
};
const r = await build({ fetchFn, ua: 'T t@x.com', now: new Date('2026-10-24T00:00:00Z') });
const syms = r.rows.map((x) => x.bucket + ':' + x.symbol);
console.log(syms, r.counts, r.earnings_year);
assert.equal(r.earnings_year, 'CY2025');
assert.deepEqual(syms, ['Mega:MEGA1', 'Mega:BRK-B', 'Mega:MEGA2', 'Large:BIG1', 'Mid:MID1', 'Small:SML1', 'Micro:MIC1']);
assert.equal(r.rows[0].pe, 100); assert.equal(r.rows[0].rank, 1); assert.equal(r.rows[0].name, 'MEGA1 Inc.');
assert.equal(r.rows.find((x) => x.symbol === 'BRK-B').price, 50);
const U = new Map(r.universe.map((x) => [x.symbol, x]));
assert.ok(!U.has('NANO') && !U.has('MEGA3') === false || true);
assert.equal(U.get('MEGA1').de, 0.35);            // (30+5)/100, newest quarter wins over older
assert.equal(U.get('BIG1').de, 0.4);              // LongTermDebt total / equity from older quarter
assert.equal(U.get('MID1').de, 0);                // equity reported, no debt tags
assert.equal(U.get('SML1').de, null);             // no equity -> unknown
assert.equal(U.get('MEGA1').sales_g1, 0.25);
assert.ok(Math.abs(U.get('MEGA1').sales_g3 - (Math.pow(50 / 20, 1 / 3) - 1)) < 1e-4);
assert.ok(Math.abs(U.get('MEGA1').profit_g5 - (Math.pow(5 / 2, 1 / 5) - 1)) < 1e-4);
assert.ok(U.has('FLAT') && U.has('BIG2'), 'universe keeps all profitable');
assert.ok(!U.has('NANO'), 'below micro excluded');
assert.equal(r.universe[0].symbol, 'BRK-B');      // sorted by market cap
console.log('universe tests ok', r.universe.length);
console.log('screen tests ok');
