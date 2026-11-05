// Merger arbitrage via investable funds (MNA, ARB) vs T-bills (BIL), SPY, bonds (AGG). Research only. Not financial advice.
import { writeFileSync, mkdirSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export const SYMS = ['MNA', 'ARB', 'BIL', 'SPY', 'AGG'];
export function stats(pts) {
  let pk = 0, dd = 0; const yr = {}, mo = {};
  for (const [d, c] of pts) { pk = Math.max(pk, c); dd = Math.max(dd, 1 - c / pk); yr[d.slice(0, 4)] = c; mo[d.slice(0, 7)] = c; }
  const yrs = (Date.parse(pts.at(-1)[0]) - Date.parse(pts[0][0])) / 31557600000, tot = pts.at(-1)[1] / pts[0][1];
  let prev = pts[0][1]; const yearly = {}; for (const [y, c] of Object.entries(yr)) { yearly[y] = +((c / prev - 1) * 100).toFixed(2); prev = c; }
  let pm = pts[0][1], worst = 0; for (const c of Object.values(mo)) { worst = Math.min(worst, c / pm - 1); pm = c; }
  const rets = pts.slice(1).map(([, c], i) => c / pts[i][1] - 1), mu = rets.reduce((a, b) => a + b, 0) / rets.length;
  const sd = Math.sqrt(rets.reduce((a, b) => a + (b - mu) ** 2, 0) / rets.length);
  return { start: pts[0][0], end: pts.at(-1)[0], cagr: +((tot ** (1 / yrs) - 1) * 100).toFixed(2), total: +((tot - 1) * 100).toFixed(1), max_dd: +(dd * 100).toFixed(2), vol: +(sd * Math.sqrt(252) * 100).toFixed(2), worst_month: +(worst * 100).toFixed(2), yearly };
}
export function retMap(pts) { const m = {}; for (let i = 1; i < pts.length; i++) m[pts[i][0]] = pts[i][1] / pts[i - 1][1] - 1; return m; }
export function corr(a, b) {
  const ds = Object.keys(a).filter((d) => d in b), x = ds.map((d) => a[d]), y = ds.map((d) => b[d]);
  const mx = x.reduce((s, v) => s + v, 0) / x.length, my = y.reduce((s, v) => s + v, 0) / y.length; let sxy = 0, syy = 0, sxx = 0;
  for (let i = 0; i < x.length; i++) { sxy += (x[i] - mx) * (y[i] - my); sxx += (x[i] - mx) ** 2; syy += (y[i] - my) ** 2; }
  return { corr: +(sxy / Math.sqrt(sxx * syy)).toFixed(2), beta_to_spy: +(sxy / syy).toFixed(2) };
}
export function crash(pts, a, b) { const w = pts.filter(([d]) => d >= a && d <= b); if (w.length < 2) return null; let pk = w[0][1], dd = 0; for (const [, c] of w) { pk = Math.max(pk, c); dd = Math.max(dd, 1 - c / pk); } return { ret: +((w.at(-1)[1] / w[0][1] - 1) * 100).toFixed(2), max_drop: +(dd * 100).toFixed(2) }; }
async function bars(symbols, start) {
  const H = { 'APCA-API-KEY-ID': process.env.APCA_API_KEY_ID, 'APCA-API-SECRET-KEY': process.env.APCA_API_SECRET_KEY }, out = {}; let tok = null;
  const p = new URLSearchParams({ symbols: symbols.join(','), timeframe: '1Day', start, end: new Date(Date.now() - 3600e3).toISOString(), adjustment: 'all', feed: 'sip', limit: '10000' });
  do { if (tok) p.set('page_token', tok); const r = await fetch('https://data.alpaca.markets/v2/stocks/bars?' + p, { headers: H }); if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
    const j = await r.json(); for (const [s, a] of Object.entries(j.bars || {})) (out[s] ||= []).push(...a); tok = j.next_page_token; await sleep(300); } while (tok);
  return out;
}
async function main(outDir = 'data') {
  const b = await bars(SYMS, '2016-01-01T00:00:00Z'), S = {};
  for (const s of SYMS) if (b[s]?.length) S[s] = b[s].map((x) => [x.t.slice(0, 10), x.c]);
  const windows = { since_2016: S.MNA[0][0], since_ARB_launch: S.ARB ? S.ARB[0][0] : null, last_3y: new Date(Date.now() - 3 * 365.25 * 86400e3).toISOString().slice(0, 10) };
  const res = { generated: new Date().toISOString(), notes: ['Prices adjusted for dividends (total return). Fund fees already included in fund prices.', 'MNA = IQ Merger Arbitrage ETF, ARB = AltShares Merger Arbitrage ETF, BIL = T-bills, AGG = US bonds.'], windows: {}, correlation: {}, crashes: {} };
  for (const [w, st] of Object.entries(windows)) { if (!st) continue; res.windows[w] = {}; for (const s of Object.keys(S)) { const pts = S[s].filter(([d]) => d >= st); if (pts.length > 50) res.windows[w][s] = stats(pts); } }
  const spy = retMap(S.SPY); for (const s of Object.keys(S)) res.correlation[s] = corr(retMap(S[s]), spy);
  for (const [k, [a, z]] of Object.entries({ covid_2020: ['2020-02-19', '2020-03-23'], bear_2022: ['2022-01-03', '2022-10-12'], tariff_2025: ['2025-02-19', '2025-04-08'] })) { res.crashes[k] = {}; for (const s of Object.keys(S)) res.crashes[k][s] = crash(S[s], a, z); }
  mkdirSync(outDir, { recursive: true }); writeFileSync(`${outDir}/merger_arb.json`, JSON.stringify(res, null, 1));
  for (const [w, v] of Object.entries(res.windows)) { console.log('\n==', w); for (const [s, x] of Object.entries(v)) console.log(s.padEnd(4), x.start, 'cagr', x.cagr, 'dd', x.max_dd, 'vol', x.vol, JSON.stringify(x.yearly)); }
  console.log('corr', JSON.stringify(res.correlation)); console.log('crashes', JSON.stringify(res.crashes));
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main(process.argv[2] || 'data').catch((e) => { console.error(e); try { mkdirSync('data', { recursive: true }); writeFileSync('data/merger_arb_error.txt', String(e.stack || e)); } catch {} process.exit(1); });
