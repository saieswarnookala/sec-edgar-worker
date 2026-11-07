// India earnings drift backtest (Nifty 100, CURRENT members -> hindsight bias).
// Events: NSE quarterly results broadcast times. Reaction = stock minus Nifty on the first session after the news.
// Buy next open, hold N sessions, equal slots, long only. Costs 0.15%/side (STT, stamp, charges, slippage).
import { writeFileSync, mkdirSync, existsSync } from 'node:fs';
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const COST = 0.0015, START = '2016-01-01';
const GRID = { thr: [3, 5, 8], hold: [20, 40, 60], slots: [5, 10] };
const PERIODS = [['2016-01-01', '2020-12-31'], ['2021-01-01', '2024-12-31'], ['2025-01-01', '2026-12-31']];
let cookie = '';
const LOG = [];
async function nse(url) {
  for (let a = 0; a < 4; a++) {
    try {
      const r = await fetch(url, { headers: { 'user-agent': UA, accept: 'application/json, text/plain, */*', 'accept-language': 'en-US,en;q=0.9', referer: 'https://www.nseindia.com/companies-listing/corporate-filings-financial-results', cookie } });
      const sc = r.headers.getSetCookie?.() || []; if (sc.length) cookie = [...new Map([...cookie.split('; ').filter(Boolean), ...sc.map((c) => c.split(';')[0])].map((c) => [c.split('=')[0], c])).values()].join('; ');
      if (r.status === 200) { const t = await r.text(); try { return JSON.parse(t); } catch { if (!url.includes('/api/')) return t; } }
    } catch {}
    await sleep(2000 * (a + 1)); await fetch('https://www.nseindia.com/', { headers: { 'user-agent': UA } }).then((r) => { const sc = r.headers.getSetCookie?.() || []; if (sc.length) cookie = sc.map((c) => c.split(';')[0]).join('; '); }).catch(() => {});
  }
  return null;
}
const MON = { Jan: '01', Feb: '02', Mar: '03', Apr: '04', May: '05', Jun: '06', Jul: '07', Aug: '08', Sep: '09', Oct: '10', Nov: '11', Dec: '12' };
export function parseNseTime(s) { const m = /^(\d{2})-(\w{3})-(\d{4})(?: (\d{2}):(\d{2}))?/.exec(s || ''); if (!m || !MON[m[2]]) return null; return { date: `${m[3]}-${MON[m[2]]}-${m[1]}`, mins: m[4] ? +m[4] * 60 + +m[5] : null }; }
// first session reacting to news: same day if released before 15:30 on a session day, else next session
export function reactionIndex(dates, ev) {
  let i = dates.findIndex((d) => d >= ev.date); if (i < 0) return -1;
  if (dates[i] === ev.date && ev.mins != null && ev.mins >= 15 * 60 + 30) i++;
  return i < dates.length ? i : -1;
}
async function yahoo(sym) {
  const p1 = Math.floor(Date.parse('2015-06-01') / 1000), p2 = Math.floor(Date.now() / 1000);
  for (let a = 0; a < 3; a++) {
    try {
      const r = await fetch(`https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(sym)}?period1=${p1}&period2=${p2}&interval=1d&events=div%2Csplit`, { headers: { 'user-agent': UA } });
      if (r.ok) { const j = await r.json(), res = j.chart?.result?.[0]; if (!res?.timestamp) return null; const q = res.indicators.quote[0], adj = res.indicators.adjclose?.[0]?.adjclose || q.close; const out = {};
        res.timestamp.forEach((t, k) => { const c = q.close[k], o = q.open[k], ac = adj[k]; if (c > 0 && o > 0 && ac > 0) { const d = new Date((t + 19800) * 1000).toISOString().slice(0, 10); out[d] = { o: o * ac / c, c: ac }; } }); return out; }
      if (r.status === 404) return null;
    } catch {}
    await sleep(1500 * (a + 1));
  }
  return null;
}
export function simulate(days, px, events, { thr, hold, slots }) {
  // events: [{sym, ri (reaction day idx), react}] ; entry at open of ri+1, exit at open of ri+1+hold
  const byEntry = new Map(); for (const e of events) if (e.react * 100 >= thr) { const k = e.ri + 1; if (!byEntry.has(k)) byEntry.set(k, []); byEntry.get(k).push(e); }
  let cash = 1, pos = []; const eq = [], trades = [];
  for (let i = 0; i < days.length; i++) {
    const d = days[i];
    for (const p of pos.filter((p) => p.exitI === i)) { const o = px[p.sym][d]?.o ?? p.last; cash += p.sh * o * (1 - COST); trades.push(o / p.entry - 1 - 2 * COST); }
    pos = pos.filter((p) => p.exitI !== i);
    const cands = (byEntry.get(i) || []).sort((a, b) => b.react - a.react);
    for (const e of cands) {
      if (pos.length >= slots || pos.some((p) => p.sym === e.sym)) continue; const o = px[e.sym][d]?.o; if (!o) continue;
      const total = cash + pos.reduce((s, p) => s + p.sh * p.last, 0), amt = Math.min(cash, total / slots); if (amt <= 0) continue;
      cash -= amt; pos.push({ sym: e.sym, sh: (amt * (1 - COST)) / o, entry: o, last: o, exitI: Math.min(i + hold, days.length - 1) });
    }
    for (const p of pos) { const c = px[p.sym][d]?.c; if (c) p.last = c; }
    eq.push(cash + pos.reduce((s, p) => s + p.sh * p.last, 0));
  }
  return { eq, trades };
}
export function stats(days, eq, from = days[0], to = days[days.length - 1]) {
  const i0 = days.findIndex((d) => d >= from), i1 = days.findLastIndex((d) => d <= to); if (i0 < 0 || i1 <= i0) return null;
  const yrs = (Date.parse(days[i1]) - Date.parse(days[i0])) / 31557600000; let pk = eq[i0], dd = 0;
  for (let i = i0; i <= i1; i++) { pk = Math.max(pk, eq[i]); dd = Math.min(dd, eq[i] / pk - 1); }
  return { cagr: +((Math.pow(eq[i1] / eq[i0], 1 / yrs) - 1) * 100).toFixed(1), dd: +(dd * 100).toFixed(1) };
}
async function main() {
  await fetch('https://www.nseindia.com/', { headers: { 'user-agent': UA } }).then((r) => { cookie = (r.headers.getSetCookie?.() || []).map((c) => c.split(';')[0]).join('; '); });
  await nse('https://www.nseindia.com/companies-listing/corporate-filings-financial-results');
  const uni = {};
  for (const [k, name] of [['nifty100', 'NIFTY 100']]) {
    const j = await nse(`https://www.nseindia.com/api/equity-stockIndices?index=${encodeURIComponent(name)}`);
    uni[k] = (j?.data || []).map((x) => x.symbol).filter((s) => s && !/^NIFTY/.test(s));
    if (!uni[k].length) { // fallback: niftyindices.com constituents CSV
      try { const t = await (await fetch('https://www.niftyindices.com/IndexConstituent/ind_nifty100list.csv', { headers: { 'user-agent': UA } })).text();
        uni[k] = t.split(/\r?\n/).slice(1).map((l) => l.split(',')[2]).filter((x) => x && /^[A-Z0-9&-]+$/.test(x)); LOG.push('members from niftyindices csv'); } catch (e) { LOG.push('csv fail ' + e.message); }
    }
    LOG.push(`${k}: ${uni[k].length} members`); console.log(k, uni[k].length, 'members'); await sleep(1500);
  }
  if (!uni.nifty100.length) throw new Error('could not load index members from NSE');
  const all = [...uni.nifty100];
  const bench = await yahoo('^NSEI'), beesRaw = await yahoo('NIFTYBEES.NS'); if (!bench) throw new Error('no Nifty data from Yahoo'); LOG.push('nifty days ' + Object.keys(bench).length + ', bees ' + (beesRaw ? Object.keys(beesRaw).length : 0));
  const days = Object.keys(bench).sort().filter((d) => d >= START);
  const px = {}, evs = {}; let nEv = 0, noPx = [], noEv = [];
  for (const [n, s] of all.entries()) {
    const p = await yahoo(s + '.NS'); if (!p) { noPx.push(s); continue; } px[s] = p;
    const j = await nse(`https://www.nseindia.com/api/corporates-financial-results?index=equities&symbol=${encodeURIComponent(s)}&period=Quarterly`);
    const arr = Array.isArray(j) ? j : j?.data || [];
    const first = new Map(); // earliest broadcast per quarter end
    for (const x of arr) { const t = parseNseTime(x.broadCastDate || x.filingDate); const q = x.toDate || x.period; if (!t || !q) continue; const key = q; const prev = first.get(key); if (!prev || t.date < prev.date || (t.date === prev.date && (t.mins ?? 0) < (prev.mins ?? 0))) first.set(key, t); }
    const list = [];
    for (const t of first.values()) {
      const ri = reactionIndex(days, t); if (ri < 1 || ri + 1 >= days.length) continue;
      const d0 = days[ri - 1], d1 = days[ri]; if (!p[d0] || !p[d1]) continue;
      list.push({ sym: s, ri, date: d1, react: (p[d1].c / p[d0].c - 1) - (bench[d1].c / bench[d0].c - 1) });
    }
    if (!list.length) noEv.push(s); evs[s] = list; nEv += list.length;
    if (n < 3) LOG.push(`${s}: prices ${Object.keys(p).length}, nse rows ${arr.length}, events ${list.length}`);
    if (n % 25 === 0) console.log(`${n + 1}/${all.length} ${s}: ${list.length} events (total ${nEv})`);
    await sleep(900);
  }
  const bees = beesRaw ? days.map((d, i) => beesRaw[d]?.c) : null; if (bees) for (let i = 1; i < bees.length; i++) if (!bees[i]) bees[i] = bees[i - 1];
  const benchEq = bees && bees[0] ? bees : days.map((d) => bench[d].c);
  const out = { generated: new Date().toISOString(), note: 'Current index members only (hindsight bias). Costs 0.15%/side. Benchmark: NIFTYBEES (Nifty 50 ETF incl. dividends) or Nifty 50 price index if unavailable.',
    benchmark: { name: bees && bees[0] ? 'NIFTYBEES' : 'Nifty 50 (price)', full: stats(days, benchEq), periods: PERIODS.map(([a, b]) => stats(days, benchEq, a, b)) }, missingPrices: noPx, noEvents: noEv, universes: {} };
  for (const [k, syms] of Object.entries(uni)) {
    const events = syms.flatMap((s) => evs[s] || []); const rows = [];
    for (const thr of GRID.thr) for (const hold of GRID.hold) for (const slots of GRID.slots) {
      const { eq, trades } = simulate(days, px, events, { thr, hold, slots });
      const per = PERIODS.map(([a, b]) => stats(days, eq, a, b));
      rows.push({ thr, hold, slots, full: stats(days, eq), periods: per, trades: trades.length, winRate: trades.length ? +(trades.filter((t) => t > 0).length / trades.length * 100).toFixed(0) : null,
        beatAll: per.every((p, i) => p && out.benchmark.periods[i] && p.cagr > out.benchmark.periods[i].cagr) });
    }
    rows.sort((a, b) => b.full.cagr - a.full.cagr);
    out.universes[k] = { members: syms.length, withPrices: syms.filter((s) => px[s]).length, events: events.length, beatBenchFull: rows.filter((r) => r.full.cagr > out.benchmark.full.cagr).length, beatAllPeriods: rows.filter((r) => r.beatAll).length, combos: rows.length,
      reference: rows.find((r) => r.thr === 5 && r.hold === 60 && r.slots === 10), rows };
    console.log(k, 'events', events.length, 'ref', JSON.stringify(out.universes[k].reference?.full), 'bench', JSON.stringify(out.benchmark.full));
  }
  mkdirSync('data', { recursive: true }); writeFileSync('data/india_drift.json', JSON.stringify(out, null, 1));
}
if ((process.argv[1] || '').split('/').pop() === 'india-drift.mjs') main().catch((e) => { console.error(e); mkdirSync('data', { recursive: true }); writeFileSync('data/india_drift_error.json', JSON.stringify({ at: new Date().toISOString(), error: String(e?.stack || e), log: LOG }, null, 1)); process.exit(1); });
