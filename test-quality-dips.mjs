// node test-quality-dips.mjs — offline checks for scripts/build-quality-dips.mjs (fake data, no network)
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import * as Q from './scripts/build-quality-dips.mjs';

let fails = 0;
const ok = (c, m) => { console.log((c ? 'ok   ' : 'FAIL ') + m); if (!c) fails++; };
const near = (a, b, tol = 1e-9) => Math.abs(a - b) <= tol;
const C = Q.COST;

const days = [];
for (let t = Date.parse('2016-01-04'); days.length < 320; t += 86400000) { const w = new Date(t).getUTCDay(); if (w && w < 6) days.push(new Date(t).toISOString().slice(0, 10)); }
// closes from daily % changes; open = previous close unless overridden
const series = (changes, opens = {}) => { let c = 100; return days.map((d, i) => { const o = opens[i] ?? c; c = c * (1 + (changes[i] ?? 0)); return { d, o, c }; }); };
const rising = (i) => 0.005;
const flatBil = days.map((d) => ({ d, c: 100 }));
const cal = days;

// ---- 1) one clean dip: signal at close 261, buy open 262, exit signal close 262, sell open 263
{
  const ch = days.map(rising); ch[260] = -0.03; ch[261] = -0.03; ch[262] = 0.05;
  const A = series(ch);
  A[262].o = A[261].c * 0.99; A[263].o = A[262].c * 1.01; // gap down at entry, gap up at exit
  const run = Q.backtest({ bars: { A }, cal, bil: flatBil });
  const t = run.trades[0];
  ok(run.trades.length === 1, 'one dip -> one trade');
  ok(t && t.entry_d === days[262] && t.exit_d === days[263] && t.hold === 1, 'entry next open after signal, exit next open after close > SMA5');
  const ret = (A[263].o * (1 - C)) / (A[262].o * (1 + C)) - 1;
  ok(t && near(t.ret, ret), `trade return uses opens and 0.02% per side (${(ret * 100).toFixed(3)}%)`);
  ok(near(run.pts.at(-1).eq, 0.8 + 0.2 * (1 + ret)), 'equity = 80% cash + 20% position (flat BIL)');
  ok(near(run.pts.find((p) => p.d === days[262]).eq, 0.8 + (0.2 * A[262].c) / (A[262].o * (1 + C))), 'position marked to market at the close');
}

// ---- 2) seven simultaneous signals -> only 5 slots, lowest RSI first
{
  const bars = {};
  for (let k = 0; k < 7; k++) { const ch = days.map(rising); ch[260] = 0.001 * (7 - k); ch[261] = -0.1; bars['S' + k] = series(ch); }
  const run = Q.backtest({ bars, cal, bil: flatBil });
  const first = run.trades.filter((t) => t.entry_d === days[262]).map((t) => t.sym).sort().concat(run.open.filter((p) => p.entry_d === days[262]).map((p) => p.sym)).sort();
  ok(first.length === 5, 'max 5 positions');
  ok(first.join() === 'S2,S3,S4,S5,S6', 'smallest prior up-move (lowest RSI) wins the slots: ' + first.join());
}

// ---- 3) dip that keeps sliding -> time exit after 10 trading days
{
  const ch = days.map((x, i) => (i < 260 ? 0.005 : -0.003)); ch[260] = -0.03; ch[261] = -0.03;
  const B = series(ch);
  const run = Q.backtest({ bars: { B }, cal, bil: flatBil });
  const t = run.trades[0];
  ok(t && t.entry_d === days[262] && t.exit_d === days[272] && t.hold === 10, `10-day time exit (exit ${t?.exit_d}, hold ${t?.hold})`);
  ok(run.trades.length >= 2 && run.trades[1].entry_d === days[273], 're-entry allowed the day after the exit fills');
}

// ---- 4) no signals: idle cash earns BIL exactly; 5) gate blocks everything
{
  const bil = days.map((d, i) => ({ d, c: 100 * 1.0001 ** i }));
  const A = series(days.map(rising));
  const run = Q.backtest({ bars: { A }, cal: cal.slice(200), bil });
  ok(run.trades.length === 0 && near(run.pts.at(-1).eq, bil.at(-1).c / bil[200].c, 1e-12), 'no trades -> equity tracks BIL');
  const ch = days.map(rising); ch[260] = -0.03; ch[261] = -0.03;
  const gated = Q.backtest({ bars: { A: series(ch) }, cal, bil: flatBil, allowed: () => false });
  ok(gated.trades.length === 0 && gated.open.length === 0, 'quality gate blocks entries');
  const onSig = Q.backtest({ bars: { A: series(ch) }, cal, bil: flatBil, allowed: (s, d) => d === days[261] });
  const onFill = Q.backtest({ bars: { A: series(ch) }, cal, bil: flatBil, allowed: (s, d) => d === days[262] });
  ok(onSig.trades.length + onSig.open.length === 1 && onFill.trades.length + onFill.open.length === 0, 'gate is checked on the signal date, not the fill date');
}

// ---- 6) report: yearly returns compound to the total; periods present
{
  const ch = days.map(rising); ch[260] = -0.03; ch[261] = -0.03; ch[262] = 0.05;
  const run = Q.backtest({ bars: { A: series(ch) }, cal, bil: flatBil });
  const spy = Q.spyRun(series(days.map(rising)), cal).pts;
  const r = Q.report('test', run, spy);
  const comp = r.yearly.reduce((e, y) => e * (1 + y.ret / 100), 1) - 1;
  ok(Math.abs(comp * 100 - r.total) < 0.02 && r.trades === 1 && r.win_rate === 100 && r.periods['2016-2020'], 'report: yearly compounds to total, trade stats, periods');
}

// ---- 7) quality: point-in-time 10-K filtering, 3-year profits, ranking
{
  const fy = (y, val, filed, form = '10-K') => ({ start: `${y}-01-01`, end: `${y}-12-31`, val, filed, form, fp: 'FY' });
  const inst = (y, val, filed) => ({ end: `${y}-12-31`, val, filed, form: '10-K', fp: 'FY' });
  const cf = (ni, eq, ltd = []) => ({ facts: { 'us-gaap': { NetIncomeLoss: { units: { USD: ni } }, StockholdersEquity: { units: { USD: eq } }, LongTermDebt: { units: { USD: ltd } } } } });
  // X: FY2015 10-K filed 2016-02-20, so test year 2016 must still see FY2014 as latest
  const X = Q.extractFacts(cf(
    [fy(2012, 5, '2013-02-20'), fy(2013, 6, '2014-02-20'), fy(2014, 7, '2015-02-20'), fy(2015, -1, '2016-02-20'), fy(2015, 99, '2016-01-15', '10-Q')],
    [inst(2014, 70, '2015-02-20'), inst(2015, 60, '2016-02-20')], [inst(2014, 35, '2015-02-20')]));
  const q16 = Q.qualityInputs(X, 2016), q17 = Q.qualityInputs(X, 2017);
  ok(q16.fy_end === '2014-12-31' && q16.pos3 && near(q16.roe, 0.1) && near(q16.de, 0.5), '2016 uses only 10-Ks filed before 2016-01-01 (FY2014: ROE 10%, D/E 0.5)');
  ok(q17.fy_end === '2015-12-31' && !q17.pos3, '2017 sees the FY2015 loss -> fails 3-year profit test');
  const old = Q.qualityInputs(X, 2020);
  ok(old.reason === 'stale 10-K', 'stale filer is excluded');
  // ranking: 10 eligible, ROE 1..10%, D/E = 0.1*k for k odd, 2.0 for k even; plus one with negative equity
  const inputs = {}, sectors = {};
  for (let k = 1; k <= 10; k++) inputs['T' + k] = { fy_end: '2015-12-31', pos3: true, eq: 100, roe: k / 100, de: k % 2 ? 0.1 * k : 2 };
  inputs.NEG = { fy_end: '2015-12-31', pos3: true, eq: -5, roe: 2, de: -1 };
  sectors.T9 = 'Financials'; sectors.T10 = 'Financials';
  const r = Q.rankQuality(inputs, sectors);
  // top 40% ROE = T7..T10; D/E median of {0.1,.3,.5,.7,.9,2,2,2,2,2} = (0.9+2)/2 = 1.45 -> T7, T9 pass
  ok(r.quality.join() === 'T7,T9', 'top 40% ROE and D/E below median: ' + r.quality.join());
  ok(r.stats.eligible === 10 && r.stats.financials_quality === 1 && r.stats.financials_eligible === 2, 'negative equity excluded; financials counted');
}

// ---- 8) Wikipedia table parser
{
  const rows = Array.from({ length: 410 }, (_, i) => `<tr>\n<td><a rel="nofollow" class="external text" href="x">T${i}</a></td>\n<td><a href="/wiki/X">Co ${i} &amp; Sons</a><sup>[1]</sup></td>\n<td>${i % 10 ? 'Industrials' : 'Financials'}</td>\n<td>Sub</td>\n<td>City</td>\n<td>2000-01-01</td>\n<td>${String(1000 + i).padStart(10, '0')}</td>\n<td>1900</td>\n</tr>`);
  rows.push('<tr>\n<td><a href="x">BRK.B</a></td>\n<td>Berkshire</td>\n<td>Financials</td><td>a</td><td>b</td><td>c</td><td>0001067983</td><td>1839</td></tr>');
  const html = `<html><table class="wikitable"><tr><th>x</th></tr></table><table class="wikitable sortable" id="constituents">\n<tbody><tr>\n<th>Symbol</th>\n<th>Security</th>\n<th>GICS Sector</th>\n<th>GICS Sub-Industry</th>\n<th>Headquarters Location</th>\n<th>Date added</th>\n<th>CIK</th>\n<th>Founded</th>\n</tr>\n${rows.join('\n')}</tbody></table><table id="changes"><tr><td>ZZZ</td></tr></table></html>`;
  const t = Q.parseSp500Html(html);
  ok(t.length === 411 && t[0].symbol === 'T0' && t[0].name === 'Co 0 & Sons' && t[0].sector === 'Financials' && t[0].cik === 1000, 'parses symbol, name, sector, CIK');
  ok(t.at(-1).symbol === 'BRK.B' && !t.some((x) => x.symbol === 'ZZZ'), 'keeps class shares, ignores other tables');
}

// ---- 9) universe fallback
{
  const dir = mkdtempSync(join(tmpdir(), 'qd-'));
  const fail = async () => ({ ok: false, status: 503, text: async () => '' });
  let err = '';
  try { await Q.loadUniverse(dir, {}, [], fail); } catch (e) { err = e.message; }
  ok(/does not exist yet/.test(err), 'Wikipedia down + no saved file -> clear error');
  const saved = { fetched: '2026-11-01T00:00:00Z', tickers: Array.from({ length: 450 }, (_, i) => ({ symbol: 'S' + i })) };
  writeFileSync(join(dir, 'sp500_tickers.json'), JSON.stringify(saved));
  const notes = [];
  const t = await Q.loadUniverse(dir, {}, notes, fail);
  ok(t.length === 450 && /using saved/.test(notes[0]), 'Wikipedia down -> falls back to saved data/sp500_tickers.json');
}

// ---- 10) Alpaca: SIP refused -> IEX, pagination, failing symbol skipped and listed
{
  const calls = [];
  const resp = (status, body) => ({ ok: status === 200, status, json: async () => body, text: async () => JSON.stringify(body), headers: { get: () => null } });
  const fetchFn = async (url) => {
    const p = new URL(url).searchParams; calls.push(p.get('feed') + ':' + p.get('symbols') + ':' + (p.get('page_token') || ''));
    if (p.get('feed') === 'sip') return resp(403, { message: 'subscription does not permit querying recent SIP data' });
    if (p.get('symbols').includes('BAD')) return resp(422, { message: 'invalid symbol: BAD' });
    if (!p.get('page_token')) return resp(200, { bars: { AAA: [{ t: '2016-01-05T05:00:00Z', o: 1, c: 2 }] }, next_page_token: 'n1' });
    return resp(200, { bars: { AAA: [{ t: '2016-01-04T05:00:00Z', o: 1, c: 1 }], BBB: [{ t: '2016-01-04T05:00:00Z', o: 3, c: 4 }] } });
  };
  const r = await Q.alpacaDaily(['AAA', 'BBB', 'BAD'], { env: { APCA_API_KEY_ID: 'k', APCA_API_SECRET_KEY: 's' }, fetchFn, pauseMs: 0, log: () => {} });
  ok(r.feed === 'iex' && calls[0].startsWith('sip:'), 'SIP refused -> switches to IEX');
  ok(r.bars.AAA.map((b) => b.d).join() === '2016-01-04,2016-01-05' && r.bars.BBB.length === 1, 'pages merged and sorted by date');
  ok(r.failed.length === 1 && r.failed[0].symbol === 'BAD' && r.bars.BAD.length === 0, 'bad symbol skipped and listed, others kept');
}

console.log(fails ? `\n${fails} FAILED` : '\nall ok');
process.exit(fails ? 1 : 0);
