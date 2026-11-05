// Earnings drift backtest (post-earnings-announcement drift). Research only, no orders.
// Events: SEC 8-K filings with Item 2.02 (earnings release) for CURRENT S&P 500 members (survivorship bias).
// Reaction day: accepted before 09:30 ET -> same day, else next trading day (SEC acceptance clock treated as ET).
// Reaction = stock close/prev close minus SPY close/prev close on the reaction day. "strong" = close in top half of day range.
// Buy next day's open, hold HOLD trading days, sell at close. Up to N equal slots (1/N of equity), biggest reactions first, long only.
// Costs 0.05% per side. Idle cash earns 0. Prices: Alpaca daily SIP, adjustment=all (dividends included, SPY too).
import { writeFileSync, readFileSync, mkdirSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { stats } from './orb-research.mjs';
export const THRS = [0.03, 0.05, 0.08, 0.1], HOLDS = [10, 20, 40, 60], NS = [10, 20], CLOSES = ['any', 'strong'], COST = 0.0005;
export const COMBOS = [];
for (const th of THRS) for (const h of HOLDS) for (const n of NS) for (const cl of CLOSES) COMBOS.push({ key: `thr${th * 100}|hold${h}|n${n}|${cl}`, th, h, n, cl });
export const PER = { p2016_20: (d) => d <= '2020-12-31', p2021_24: (d) => d > '2020-12-31' && d <= '2024-12-31', p2025_26: (d) => d > '2024-12-31' };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export function reactionIndex(dates, day, min) {
  let lo = 0, hi = dates.length; while (lo < hi) { const m = (lo + hi) >> 1; if (dates[m] < day) lo = m + 1; else hi = m; }
  if (lo < dates.length && dates[lo] === day && min >= 570) lo++;
  return lo < dates.length ? lo : -1;
}
// signals[t] = [{s, r, strong}] sorted by r desc, entries at the open of day t. O/C: {sym: arrays aligned to dates}.
export function simulate(dates, O, C, signals, c, t0, log = null) {
  let cash = 1, pos = [], n = 0, wins = 0, sumR = 0; const curve = [];
  for (let t = t0; t < dates.length; t++) {
    const eq = cash + pos.reduce((a, p) => a + p.val, 0);
    for (const x of (signals[t] || [])) {
      if (x.r < c.th || (c.cl === 'strong' && !x.strong)) continue;
      if (pos.length >= c.n) break; if (pos.some((p) => p.s === x.s)) continue;
      const o = O[x.s]?.[t]; if (!o) continue;
      const alloc = Math.min(eq / c.n, cash); if (alloc <= 1e-9) break;
      cash -= alloc; pos.push({ t, s: x.s, sh: (alloc * (1 - COST)) / o, alloc, exitT: t + c.h - 1, val: alloc * (1 - COST) });
    }
    for (const p of pos) { const cl = C[p.s]?.[t]; if (cl) p.val = p.sh * cl; }
    pos = pos.filter((p) => { if (t < p.exitT && t < dates.length - 1) return true; const v = p.val * (1 - COST); cash += v; const r = v / p.alloc - 1; n++; if (r > 0) wins++; sumR += r; if (log) log.push({ s: p.s, d: dates[p.t], ret: +(r * 100).toFixed(2), pnl: v - p.alloc }); return false; });
    curve.push([dates[t], cash + pos.reduce((a, p) => a + p.val, 0)]);
  }
  return { curve, trades: n, wins, sumR };
}
export async function getJson(url, headers, tries = 6) {
  for (let a = 0; ; a++) {
    try { const r = await fetch(url, { headers }); if (r.ok) return await r.json(); if (r.status === 404) return null; if (r.status === 400 || a >= tries) throw new Error(`${r.status} ${url.slice(0, 200)}`); }
    catch (e) { if (a >= tries || /^400/.test(e.message)) throw e; }
    await sleep(1500 * 2 ** a);
  }
}
export async function daily(symbols, start, end) {
  const H = { 'APCA-API-KEY-ID': process.env.APCA_API_KEY_ID, 'APCA-API-SECRET-KEY': process.env.APCA_API_SECRET_KEY }, out = {}, bad = [];
  const ok = symbols.filter((s) => /^[A-Z]{1,6}(\.[A-Z]{1,2})?$/.test(s)); bad.push(...symbols.filter((s) => !ok.includes(s)));
  const batch = async (list) => {
    let tok = null;
    try {
      do { const p = new URLSearchParams({ symbols: list.join(','), timeframe: '1Day', start, end, limit: '10000', adjustment: 'all', feed: 'sip' }); if (tok) p.set('page_token', tok);
        const j = await getJson('https://data.alpaca.markets/v2/stocks/bars?' + p, H, 4); for (const [s, a] of Object.entries(j?.bars || {})) (out[s] ||= []).push(...a); tok = j?.next_page_token; await sleep(300); } while (tok);
    } catch (e) {
      if (!/^400/.test(e.message)) throw e;
      if (list.length === 1) { bad.push(list[0]); return; }
      for (const k of list) delete out[k];
      const h = Math.ceil(list.length / 2); await batch(list.slice(0, h)); await batch(list.slice(h));
    }
  };
  for (let i = 0; i < ok.length; i += 200) await batch(ok.slice(i, i + 200));
  if (bad.length) console.log('alpaca skipped symbols', bad.length, bad.slice(0, 20).join(','));
  return out;
}
export function parse8k(pages) {
  const ev = [];
  for (const r of pages) for (let i = 0; i < (r.form || []).length; i++) {
    if (r.form[i] !== '8-K' || !/(^|,)\s*2\.02\s*(,|$)/.test(r.items?.[i] || '') || r.filingDate[i] < '2016-01-01') continue;
    const a = r.acceptanceDateTime?.[i] || '', m = /T(\d\d):(\d\d)/.exec(a);
    ev.push({ day: m ? a.slice(0, 10) : r.filingDate[i], min: m ? +m[1] * 60 + +m[2] : 999 });
  }
  return ev;
}
export async function events8k(cik, ua) {
  const H = { 'User-Agent': ua }, j = await getJson(`https://data.sec.gov/submissions/CIK${String(cik).padStart(10, '0')}.json`, H); if (!j) return [];
  const pages = [j.filings.recent];
  for (const f of j.filings.files || []) { if ((f.filingTo || '9999') < '2016-01-01') continue; await sleep(130); const x = await getJson(`https://data.sec.gov/submissions/${f.name}`, H); if (x) pages.push(x); }
  return parse8k(pages);
}

async function main(out = 'data') {
  const ua = process.env.SEC_USER_AGENT; if (!ua) throw new Error('SEC_USER_AGENT missing');
  const tick = JSON.parse(readFileSync('data/sp500_tickers.json', 'utf8')).tickers.filter((t) => t.cik);
  const bars = await daily([...tick.map((t) => t.symbol), 'SPY'], '2016-01-01T00:00:00Z', new Date(Date.now() - 3600e3).toISOString());
  console.log('daily symbols', Object.keys(bars).length);
  const dates = bars.SPY.map((b) => b.t.slice(0, 10)), idx = Object.fromEntries(dates.map((d, i) => [d, i])), N = dates.length;
  const O = {}, C = {}, R = {}, Hh = {}, L = {};
  for (const [s, a] of Object.entries(bars)) {
    const o = Array(N).fill(null), c = Array(N).fill(null), h = Array(N).fill(null), l = Array(N).fill(null);
    for (const b of a) { const i = idx[b.t.slice(0, 10)]; if (i == null) continue; o[i] = b.o; c[i] = b.c; h[i] = b.h; l[i] = b.l; }
    R[s] = [...c]; for (let i = 1; i < N; i++) if (c[i] == null) c[i] = c[i - 1]; O[s] = o; C[s] = c; Hh[s] = h; L[s] = l;
  }
  const signals = [], failed = []; let nEv = 0, nSig = 0;
  for (const t of tick) {
    const s = t.symbol; if (!C[s]) continue; let ev;
    try { ev = await events8k(t.cik, ua); } catch (e) { failed.push(s); continue; } await sleep(130);
    const seen = new Set();
    for (const e of ev) {
      const k = reactionIndex(dates, e.day, e.min); if (k < 1 || k + 1 >= N || seen.has(k)) continue; seen.add(k); nEv++;
      const c0 = R[s][k], c1 = R[s][k - 1]; if (!c0 || !c1 || c0 < 5) continue;
      const r = c0 / c1 - 1 - (C.SPY[k] / C.SPY[k - 1] - 1); if (r < THRS[0]) continue; nSig++;
      const h = Hh[s][k], l = L[s][k]; (signals[k + 1] ||= []).push({ s, r, strong: h > l ? (c0 - l) / (h - l) >= 0.5 : false });
    }
  }
  for (const x of signals) if (x) x.sort((a, b) => b.r - a.r);
  console.log('earnings events', nEv, 'signals >= 3%', nSig, 'sec failed', failed.length);
  const t0 = dates.findIndex((d) => d >= '2016-07-01'), toR = (cv) => cv.slice(1).map(([d, e], i) => [d, e / cv[i][1] - 1]);
  const spyR = toR(dates.slice(t0).map((d, i) => [d, C.SPY[t0 + i]])), P = Object.keys(PER);
  const spy = Object.fromEntries(Object.entries(PER).map(([k, f]) => [k, stats(spyR.filter(([d]) => f(d)))])); spy.all = stats(spyR);
  const rows = COMBOS.map((c) => {
    const r = simulate(dates, O, C, signals, c, t0), rr = toR(r.curve);
    const row = { key: c.key, trades: r.trades, win_rate: +(100 * r.wins / Math.max(r.trades, 1)).toFixed(1), avg_trade_pct: +(100 * r.sumR / Math.max(r.trades, 1)).toFixed(2), all: stats(rr) };
    for (const [k, f] of Object.entries(PER)) row[k] = stats(rr.filter(([d]) => f(d)));
    row.beats = P.filter((k) => row[k] && row[k].cagr > spy[k].cagr); return row;
  });
  const minSh = (x) => Math.min(...P.map((k) => x[k]?.sharpe ?? -9));
  rows.sort((a, b) => minSh(b) - minSh(a));
  const pct = Object.fromEntries(P.map((k) => [k, +(100 * rows.filter((x) => x.beats.includes(k)).length / rows.length).toFixed(1)]));
  pct.every_period = +(100 * rows.filter((x) => x.beats.length === P.length).length / rows.length).toFixed(1);
  pct.full_period = +(100 * rows.filter((x) => x.all && x.all.cagr > spy.all.cagr).length / rows.length).toFixed(1);
  const res = { generated: new Date().toISOString(), notes: ['Current S&P 500 members (survivorship bias).', 'Earnings dates from SEC 8-K Item 2.02 filings.', 'Ranked by worst-period Sharpe.'], events: nEv, signals: nSig, sec_failed: failed, spy, pct_beating_spy: pct, top10: rows.slice(0, 10), all: rows };
  mkdirSync(out, { recursive: true }); writeFileSync(`${out}/earnings_drift.json`, JSON.stringify(res, null, 1));
  console.log('SPY', JSON.stringify(spy)); console.log('% beating SPY', JSON.stringify(pct));
  for (const x of rows.slice(0, 10)) console.log(x.key.padEnd(26), 'all', x.all?.cagr, P.map((k) => `${k} ${x[k]?.cagr}% dd${x[k]?.max_dd}`).join(' | '), 'trades', x.trades, 'win', x.win_rate);
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main(process.argv[2] || 'data').catch((e) => { console.error(e); process.exit(1); });
