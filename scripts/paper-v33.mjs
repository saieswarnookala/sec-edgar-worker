// Bot 19 "Dip bot v3.3" (VIRTUAL paper bot, no broker orders, from Nov 30 2026). Research only, not financial advice.
// v3.2 (bot 12: intraday dip buys + 5% target + the 3:45 pm v3.0 step) with "COMBO B" sizing from Sentinel round 9
// (scripts/sentinel_r9.py, data/r9_r2.json + data/r9_wf.json):
//   * strength sizing: 12-month momentum (close 5 days ago / close 257 days ago, ranked across today's S&P 500 members)
//     top third -> 1.5x a normal 10% slot, bottom third -> 0.5x, middle -> 1x
//   * skip earnings dips: no stock buy when an SEC 8-K with item 2.02 (earnings) was filed in the last 5 trading days
//     (a filing stamped after 15:45 in SEC's acceptance time counts from the next trading day, exactly as in the backtest)
//   * sector-wide dips: 1.5x when the median 5-day return of 3+ same-industry peers (2-digit SEC SIC code) is -5% or worse
//   ETF dips keep 1x. Slots are filled biggest dip first; each buy takes min(size, room left), like the backtest.
// Backtest 1999-2026 (v3.0 engine): live-like 21.9 -> 24.9%/yr, worst -24.7 -> -20.6%; realistic fills 16.6 -> 18.5%, -27.3 -> -24.1%.
// 2013-2026 only: realistic 17.8 -> 18.0% (most of the gain came from 2000-2009), so this runs on paper first.
// A twin (plain v3.2, same start day, same prices) runs in the same state file for a fair comparison.
import { readFileSync, existsSync } from 'node:fs';
import { decide, roundQty, VBOT_START, WEIGHT, SLOTS, MAX_HOLD, BUFFER } from './paper-dip.mjs';
import { POOL } from './clear-leader.mjs';

export const V33 = { hi: 1.5, lo: 0.5, sector: 1.5, sectorCut: -0.05, sectorPeers: 3, earnDays: 5, earnCutMin: 15 * 60 + 45, momFrom: 257, momTo: 5, minRoom: 0.02 };
const r2 = (x) => +x.toFixed(2);

// pandas-style percentile rank (average ties, rank / count) of 12-month momentum across members with data.
export function momRanks(closes, members) {
  const v = [];
  for (const s of members) { const c = closes[s] || []; if (c.length >= V33.momFrom && c.at(-V33.momFrom) > 0 && c.at(-V33.momTo) > 0) v.push([s, c.at(-V33.momTo) / c.at(-V33.momFrom) - 1]); }
  v.sort((a, b) => a[1] - b[1]);
  const out = {};
  for (let i = 0; i < v.length;) { let j = i; while (j + 1 < v.length && v[j + 1][1] === v[i][1]) j++; const rk = ((i + 1 + j + 1) / 2) / v.length; for (let k = i; k <= j; k++) out[v[k][0]] = rk; i = j + 1; }
  return out;
}
// filings: [[date 'YYYY-MM-DD', minutes (SEC acceptance time), 'items']] -> true when an earnings 8-K falls in today's 5-day dip window.
export function earningsInWindow(filings, today, days) {
  const ti = days.indexOf(today); if (ti < 0) return false;
  for (const [d, mins, it] of filings || []) {
    if (!String(it || '').split(',').some((x) => x === '2.02' || x === '12')) continue;
    let i = days.findIndex((x) => x >= d); if (i < 0) continue;
    if (days[i] === d && mins != null && mins > V33.earnCutMin) i += 1;
    if (i <= ti && ti <= i + V33.earnDays - 1) return true;
  }
  return false;
}
// median 5-day return of the stock's same-industry peers (today's price vs the close 5 trading days ago)
export function peerMedian(sym, sic2, members, closes, prices) {
  const g = sic2[sym]; if (!g) return null;
  const r = [];
  for (const x of members) { if (x === sym || sic2[x] !== g) continue; const c = closes[x] || []; if (c.length >= 5 && c.at(-5) > 0 && prices[x] > 0) r.push(prices[x] / c.at(-5) - 1); }
  if (r.length < V33.sectorPeers) return null;
  r.sort((a, b) => a - b); const m = r.length >> 1;
  return r.length % 2 ? r[m] : (r[m - 1] + r[m]) / 2;
}
// size multiplier + skip list for today's stock dip candidates
export function comboB({ scores, members, closes, prices, sic2 = {}, filings = {}, today, days }) {
  const mr = momRanks(closes, members), mult = {}, skipped = [], why = {};
  for (const s of Object.keys(scores)) {
    if (earningsInWindow(filings[s], today, days)) { skipped.push(s); why[s] = 'earnings 8-K in the 5-day window'; continue; }
    const rk = mr[s] ?? 0.5, pm = peerMedian(s, sic2, members, closes, prices);
    let m = rk >= 2 / 3 ? V33.hi : rk <= 1 / 3 ? V33.lo : 1;
    const sw = pm != null && pm <= V33.sectorCut; if (sw) m *= V33.sector;
    mult[s] = m; why[s] = `strength rank ${Math.round(rk * 100)}%${sw ? `, sector-wide dip (peers ${(pm * 100).toFixed(1)}%)` : ''} -> ${m}x`;
  }
  const kept = Object.fromEntries(Object.entries(scores).filter(([s]) => !skipped.includes(s)));
  return { scores: kept, mult, skipped, why };
}

// The 3:45 pm step with per-stock sizes: same sells/parking as decide(), buys filled one by one with min(10% x mult, room left).
export function decideSized(args) {
  const { equity, prices, held, state, scores, etfScores = {}, mult = {}, weight = WEIGHT, park, parkHeld, stockMaxHold = MAX_HOLD } = args;
  const base = decide({ ...args, scores: {}, etfScores: {}, park: null, parkHeld: {} });     // sells + kept positions only
  const keep = base.keep, keptVal = keep.reduce((a, p) => a + held[p.symbol] * (prices[p.symbol] || 0), 0);
  let room = Math.max(0, 1 - keptVal / equity);
  const cands = Object.entries(scores).filter(([s]) => !POOL.includes(s) && !keep.some((p) => p.symbol === s) && prices[s] > 0)
    .sort((a, b) => a[1] - b[1]).slice(0, Math.max(0, SLOTS - keep.length));
  const etfC = Object.entries(etfScores).filter(([s]) => prices[s] && !keep.some((p) => p.symbol === s) && !cands.some(([c]) => c === s))
    .sort((a, b) => a[1] - b[1]).slice(0, Math.max(0, SLOTS - keep.length - cands.length)).map(([s, r]) => [s, r, 'etf']);
  const buys = [];
  for (const [s, ex, kind] of [...cands, ...etfC]) {
    if (room < V33.minRoom) break;
    const m = kind ? 1 : (mult[s] ?? 1), w = Math.min(weight * m, room), qty = roundQty((w * equity) / prices[s], true);
    if (qty > 0 && qty * prices[s] >= 0.995) { buys.push({ symbol: s, qty, dip_pct: +(ex * 100).toFixed(1), mult: m, ...(kind ? { kind } : {}) }); room -= (qty * prices[s]) / equity; }
  }
  const stockVal = keptVal + buys.reduce((a, b) => a + b.qty * prices[b.symbol], 0), parkTrades = [];
  for (const [s, q] of Object.entries(parkHeld)) if (q > 0 && s !== park) parkTrades.push({ symbol: s, qty: q, side: 'sell', reason: 'switch parking' });
  if (park && prices[park]) {
    const target = Math.max(0, roundQty((equity * (1 - BUFFER) - stockVal) / prices[park], true)), cur = parkHeld[park] || 0, delta = roundQty(Math.abs(target - cur), true) * Math.sign(target - cur);
    if (Math.abs(delta) * prices[park] > Math.max(equity * 0.005, 1)) parkTrades.push({ symbol: park, qty: Math.abs(delta), side: delta > 0 ? 'buy' : 'sell', reason: 'resize parking' });
  }
  return { sells: base.sells, buys, keep, parkTrades, stockVal };
}
// virtual account version of decideSized (mirrors paper-dip.mjs virtualStep)
export function v33Step({ vs, today, days, prices, closes, scores, park, etfScores = {}, mult = {} }) {
  vs = { cash: VBOT_START, positions: [], park: {}, trades: [], ...vs };
  const px = (s, fb) => prices[s] || fb || 0;
  const held = Object.fromEntries(vs.positions.map((p) => [p.symbol, p.qty]));
  const equity = vs.cash + vs.positions.reduce((a, p) => a + p.qty * px(p.symbol, p.entry_px), 0) + Object.entries(vs.park).reduce((a, [s, q]) => a + q * px(s), 0);
  const d = decideSized({ today, days, state: { positions: vs.positions }, held, equity, prices, closes, scores, etfScores, mult, park, parkHeld: { ...vs.park }, fractional: true, minOrderUsd: 1 });
  const done = [];
  for (const t of d.parkTrades.filter((x) => x.side === 'sell')) { vs.cash += t.qty * px(t.symbol); vs.park[t.symbol] = +((vs.park[t.symbol] || 0) - t.qty).toFixed(6); if (vs.park[t.symbol] <= 1e-6) delete vs.park[t.symbol]; done.push(`SELL ${t.symbol} (${t.reason})`); }
  for (const s of d.sells) {
    const p = vs.positions.find((x) => x.symbol === s.symbol); vs.cash += s.qty * px(s.symbol);
    vs.trades.push({ symbol: s.symbol, kind: p.kind || 'stock', entry_date: p.entry_date, exit_date: today, ret_pct: r2((px(s.symbol) / p.entry_px - 1) * 100), reason: s.reason, ...(p.mult ? { mult: p.mult } : {}) });
    done.push(`SELL ${s.symbol} (${s.reason})`);
  }
  vs.positions = vs.positions.filter((p) => !d.sells.some((s) => s.symbol === p.symbol));
  for (const b of d.buys) { vs.cash -= b.qty * px(b.symbol); vs.positions.push({ symbol: b.symbol, ...(b.kind ? { kind: b.kind } : {}), entry_date: today, qty: b.qty, entry_px: px(b.symbol), dip_pct: b.dip_pct, mult: b.mult, size_pct: +(100 * b.qty * px(b.symbol) / equity).toFixed(1) }); done.push(`BUY $${(b.qty * px(b.symbol)).toFixed(0)} ${b.symbol}${b.kind === 'etf' ? ' ETF' : ''} (dip ${b.dip_pct}%, ${b.mult}x)`); }
  for (const t of d.parkTrades.filter((x) => x.side === 'buy')) { vs.cash -= t.qty * px(t.symbol); vs.park[t.symbol] = +((vs.park[t.symbol] || 0) + t.qty).toFixed(6); done.push(`BUY ${t.symbol} (parking)`); }
  vs.trades = vs.trades.slice(-300);
  return { vs, equity: r2(equity), done };
}

// ---- SEC data (needs SEC_USER_AGENT) ----
// 2-digit SIC + CIK: data/sec_events_sic.json (backtest file) + data/paper_v33_sec.json (members added since, filled on demand)
export const SEC_CACHE = 'data/paper_v33_sec.json';
export function loadSecMeta() {
  const meta = {};
  if (existsSync('data/sec_events_sic.json')) for (const [t, v] of Object.entries(JSON.parse(readFileSync('data/sec_events_sic.json', 'utf8')).tickers)) meta[t] = { cik: v.cik, sic: v.sic || '' };
  const extra = existsSync(SEC_CACHE) ? JSON.parse(readFileSync(SEC_CACHE, 'utf8')) : { tickers: {} };
  for (const [t, v] of Object.entries(extra.tickers || {})) if (!meta[t]?.cik) meta[t] = v;
  return { meta, extra };
}
const secKey = (s) => s.replace('.', '-');
export async function secJson(url, ua, fetchFn = fetch) {
  for (let a = 0; a < 3; a++) {
    try { const r = await fetchFn(url, { headers: { 'User-Agent': ua, Accept: 'application/json' } }); if (r.status === 404) return null; if (r.ok) return await r.json(); } catch {}
    await new Promise((res) => setTimeout(res, 800 * 2 ** a));
  }
  return null;
}
// recent 8-K filings in the backtest's format, from SEC's submissions feed
export function parse8k(sub) {
  const r = sub?.filings?.recent || {}, out = [];
  (r.form || []).forEach((f, i) => {
    if (f !== '8-K' && f !== '8-K/A') return;
    const items = (r.items?.[i] || '').replace(/ /g, ''), a = r.acceptanceDateTime?.[i] || '', m = /T(\d\d):(\d\d)/.exec(a);
    if (items) out.push([m ? a.slice(0, 10) : r.filingDate[i], m ? +m[1] * 60 + +m[2] : 999, items]);
  });
  return out.sort((x, y) => (x[0] < y[0] ? -1 : 1)).slice(-30);
}
// fills meta for members missing from the backtest file (CIK from SEC's ticker list, SIC from submissions); returns sic2 + changed flag
export async function ensureSecMeta({ members, meta, extra, ua, fetchFn = fetch, max = 60 }) {
  const missing = members.filter((s) => !meta[s]?.cik || !meta[s]?.sic);
  let changed = false;
  if (missing.length && ua) {
    const list = await secJson('https://www.sec.gov/files/company_tickers.json', ua, fetchFn), byT = {};
    for (const v of Object.values(list || {})) byT[v.ticker] = v.cik_str;
    for (const s of missing.slice(0, max)) {
      const cik = meta[s]?.cik || byT[secKey(s)]; if (!cik) continue;
      const sub = await secJson(`https://data.sec.gov/submissions/CIK${String(cik).padStart(10, '0')}.json`, ua, fetchFn);
      meta[s] = { cik, sic: sub?.sic || '' }; extra.tickers = { ...(extra.tickers || {}), [s]: meta[s] }; changed = true;
      await new Promise((res) => setTimeout(res, 120));
    }
  }
  const sic2 = Object.fromEntries(members.filter((s) => meta[s]?.sic).map((s) => [s, String(meta[s].sic).slice(0, 2)]));
  return { sic2, changed, missing: missing.length };
}
// 8-K filings for today's stock candidates, cached for the day (refreshed at the 3:45 pm step)
export async function filingsFor({ syms, meta, cache, today, refresh, ua, fetchFn = fetch, max = 80 }) {
  if (cache?.day !== today) cache = { day: today, f: {} };
  let fetched = 0, errors = 0;
  for (const s of syms) {
    if (!refresh && s in cache.f) continue;
    if (fetched >= max) break;
    const cik = meta[s]?.cik; if (!cik || !ua) { cache.f[s] = null; continue; }
    const sub = await secJson(`https://data.sec.gov/submissions/CIK${String(cik).padStart(10, '0')}.json`, ua, fetchFn); fetched++;
    if (sub) cache.f[s] = parse8k(sub); else { errors++; if (!(s in cache.f)) cache.f[s] = null; }
    await new Promise((res) => setTimeout(res, 120));
  }
  return { cache, fetched, errors };
}

// One run of bot 19 (called from scripts/paper-v32.mjs right after bot 12, with the same market data).
// st is mutated in place: { start_day, vs (v3.3), twin (plain v3.2 from the same day), history, checks, sec_day }.
export async function runV33({ st, g, today, days, ph, park, ny, dry, v32Intraday, virtualStep, ua = process.env.SEC_USER_AGENT, fetchFn = fetch }) {
  const { prices, closes, members = [] } = g, scores = Object.fromEntries(Object.entries(g.scores || {}).filter(([s]) => !POOL.includes(s))), etfScores = g.etfScores || {};
  st.start_day ||= today;
  const { meta, extra } = loadSecMeta();
  const sm = await ensureSecMeta({ members, meta, extra, ua, fetchFn });
  if (sm.changed && !dry) { extra.built = today; (await import('node:fs')).writeFileSync(SEC_CACHE, JSON.stringify(extra)); }
  const fl = await filingsFor({ syms: Object.keys(scores), meta, cache: st.sec_day, today, refresh: ph === 'final', ua, fetchFn });
  st.sec_day = fl.cache;
  const cb = comboB({ scores, members, closes, prices, sic2: sm.sic2, filings: fl.cache.f, today, days });
  const check = { at: new Date().toISOString(), ny_time: `${ny.hour}:${ny.minute}`, phase: ph, stock_signals: Object.keys(scores).length, skipped_earnings: cb.skipped, sizes: cb.why, park: park || 'CASH',
    sec: { ua: !!ua, filings_fetched: fl.fetched, errors: fl.errors, no_8k_data: Object.keys(scores).filter((s) => fl.cache.f[s] == null), members_without_sic: members.length - Object.keys(sm.sic2).length } };
  if (ph === 'intraday') {
    const r = v32Intraday({ vs: st.vs, today, days, prices, scores: cb.scores, etfScores, park, mult: cb.mult });
    const tw = v32Intraday({ vs: st.twin, today, days, prices, scores, etfScores, park });
    st.vs = r.vs; st.twin = tw.vs; Object.assign(check, { equity: r.equity, twin_equity: tw.equity, orders: r.done, twin_orders: tw.done });
  } else {
    const r = v33Step({ vs: st.vs, today, days, prices, closes, scores: cb.scores, park, etfScores, mult: cb.mult });
    const tw = virtualStep({ vs: st.twin, today, days, prices, closes, scores, park, scale: 1, etfScores });
    st.vs = r.vs; st.twin = tw.vs; Object.assign(check, { equity: r.equity, twin_equity: tw.equity, orders: r.done, twin_orders: tw.done });
    const todays = (st.checks || []).filter((c) => c.at.slice(0, 10) === check.at.slice(0, 10) && c.phase === 'intraday');
    st.history = [...(st.history || []), { today, equity: r.equity, twin_equity: tw.equity, spy: prices.SPY, park: park || 'CASH', stock_signals: Object.keys(scores).length, skipped_earnings: cb.skipped,
      intraday_checks: todays.length, intraday_orders: todays.flatMap((c) => (c.orders || []).map((o) => `${c.ny_time} ${o}`)), twin_intraday_orders: todays.flatMap((c) => (c.twin_orders || []).map((o) => `${c.ny_time} ${o}`)),
      orders: r.done, twin_orders: tw.done }].slice(-400);
  }
  st.checks = [...(st.checks || []), check].slice(-200); st.updated = check.at;
  return check;
}
