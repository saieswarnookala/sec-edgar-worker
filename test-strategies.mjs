// node test-strategies.mjs — offline checks for scripts/build-strategies.mjs (synthetic data, no network)
import * as S from './scripts/build-strategies.mjs';
let fails = 0;
const ok = (c, m) => { console.log((c ? 'ok   ' : 'FAIL ') + m); if (!c) fails++; };
const near = (a, b, tol = 1e-6) => Math.abs(a - b) <= tol;

// seeded synthetic market, 2016-01-04 .. 2026-10-09
let seed = 7; const rnd = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
const gauss = () => Math.sqrt(-2 * Math.log(rnd() + 1e-12)) * Math.cos(2 * Math.PI * rnd());
const days = [];
for (let t = Date.parse('2016-01-04'); t <= Date.parse('2026-10-09'); t += 86400000) { const w = new Date(t).getUTCDay(); if (w && w < 6) days.push(new Date(t).toISOString().slice(0, 10)); }
const bars = { _source: 'synthetic' };
for (const s of [...S.ETFS, S.CASH]) { let c = 100; const v = s === S.CASH ? 0.0002 : 0.012; bars[s] = days.map((d) => { const o = c * (1 + gauss() * v * 0.3); c = o * (1 + 0.0003 + gauss() * v); return { d, o, c }; }); }

// yearly(): compounding the yearly returns must equal the total
const pts = [{ d: '2020-06-30', eq: 1 }, { d: '2020-12-31', eq: 1.1 }, { d: '2021-12-31', eq: 0.99 }, { d: '2022-03-31', eq: 1.2 }];
const y = S.yearly(pts);
ok(y.length === 3 && near(y[0].ret, 0.1) && near(y[1].ret, -0.1) && near(y[2].ret, 1.2 / 0.99 - 1), 'yearly returns per calendar year');
ok(y[0].partial && !y[1].partial && y[2].partial, 'partial first/last years flagged');
ok(near(S.curveStats(pts).max_dd, 0.1), 'max drawdown from equity marks');

const res = S.assemble(bars, new Date('2026-10-10T00:00:00Z'));
ok(res.strategies.map((s) => s.id).join() === 'momentum,spy10,dip,trend10', '4 strategies in order');
for (const s of res.strategies) {
  const comp = s.yearly.reduce((e, x) => e * (1 + x.ret / 100), 1) - 1;
  ok(Math.abs(comp * 100 - s.total) < 0.1, `${s.id}: yearly returns compound to the total (${s.total}%)`);
  ok(s.curve[0].equity === 10000 && Math.abs(s.curve.at(-1).equity / 100 - 100 - s.total) < 0.1, `${s.id}: growth curve starts at $10,000 and ends at the total`);
  ok(s.yearly.every((x) => x.spy != null), `${s.id}: every year has a SPY comparison`);
}
const dip = res.strategies.find((s) => s.id === 'dip');
const D = S.dipRun(bars);
const tradeTotal = D.taken.reduce((e, t) => e * (1 + t.pct), 1) - 1;
ok(Math.abs(tradeTotal * 100 - dip.total) < 0.05, 'dip: daily mark-to-market ends at the trade-by-trade total');
ok(dip.max_dd >= dip.max_dd_trades - 1e-9, 'dip: daily drawdown is at least the trade-to-trade drawdown');
ok(D.taken.every((t, i) => i === 0 || t.entry_d > D.taken[i - 1].exit_d), 'dip: never holds two positions at once');
const csv = S.toCsv(res).trim().split('\n');
ok(csv[0] === 'strategy,kind,period,value,spy,partial' && csv.length > 400, `CSV written (${csv.length - 1} rows)`);
console.log(fails ? `\n${fails} FAILED` : '\nall passed');
process.exitCode = fails ? 1 : 0;

// dividends added back: $1 dividend on a $100 stock -> earlier prices scaled by 0.99
{
  const rows = [{ d: '2020-01-02', o: 100, c: 100 }, { d: '2020-01-03', o: 99, c: 99 }, { d: '2020-01-06', o: 99, c: 100 }];
  const adj = S.applyDividends(rows, [{ d: '2020-01-03', amt: 1 }]);
  ok(near(adj[0].c, 99) && near(adj[1].c, 99) && near(adj[2].c, 100), 'dividend back-adjustment (total return)');
  const res2 = await S.loadBars(['SPY'], { sources: [['A', async () => { throw new Error('blocked'); }], ['B', async () => ({ SPY: Array.from({ length: 400 }, (_, i) => ({ d: 'x' + i, o: 1, c: 1 })), _source: 'B' })]] });
  ok(res2._source === 'B' && res2._notes[0].includes('A failed'), 'falls back to the next price source and notes why');
  if (fails) process.exitCode = 1;
}
