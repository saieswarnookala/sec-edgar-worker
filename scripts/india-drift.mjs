// India earnings drift backtest (Nifty 100, CURRENT members -> hindsight bias).
// Events: NSE quarterly results broadcast times. Reaction = stock minus Nifty on the first session after the news.
// Buy next open, hold N sessions, equal slots, long only. Costs 0.15%/side (STT, stamp, charges, slippage).
import { writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { taxGrid } from './tax-sim.mjs';
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const COST = 0.0015, START = '2016-01-01';
const GRID = { thr: [3, 5, 8], hold: [20, 40, 60], slots: [5, 10] };
const FORMER = ['HDFC', 'MINDTREE', 'LTI', 'IBULHSGFIN', 'DHFL', 'ZEEL', 'IDEA', 'YESBANK', 'CADILAHC', 'MCDOWELL-N', 'GRUH', 'BHARTIINFRA', 'PEL', 'AUROPHARMA', 'GLENMARK', 'RCOM', 'RELINFRA', 'RPOWER', 'JETAIRWAYS', 'SRTRANSFIN', 'L&TFH', 'NIACL', 'GICRE', 'BANKBARODA', 'IDBI', 'PNB', 'CANBK', 'MOTHERSUMI', 'AMARAJABAT', 'TATAMTRDVR', 'ADANITRANS', 'ADANIGAS', 'INFRATEL', 'HDFCAMC', 'VEDL', 'NMDC', 'SAIL', 'BHEL', 'OFSS', 'MRF', 'PAGEIND', 'BOSCHLTD', 'CONCOR', 'PETRONET', 'IGL', 'GAIL', 'ACC', 'AMBUJACEM', 'LUPIN', 'BIOCON', 'COLPAL', 'MARICO', 'DABUR', 'GODREJCP', 'HAVELLS', 'BERGEPAINT', 'PIDILITIND', 'SIEMENS', 'ABB', 'INDIGO', 'NAUKRI', 'UBL', 'TORNTPHARM', 'ICICIPRULI', 'ICICIGI', 'BANDHANBNK', 'PGHH', 'DLF', 'MUTHOOTFIN', 'COFORGE', 'PERSISTENT', 'TATAPOWER', 'TATACHEM', 'CHOLAFIN', 'APOLLOHOSP'];
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
        res.timestamp.forEach((t, k) => { const c = q.close[k], o = q.open[k], ac = adj[k]; if (c > 0 && o > 0 && ac > 0) { const d = new Date((t + 19800) * 1000).toISOString().slice(0, 10); out[d] = { o: o * ac / c, c: ac, tv: (q.volume[k] || 0) * c }; } }); return cleanSeries(splitAdjust(out)); }
      if (r.status === 404) return null;
    } catch {}
    await sleep(1500 * (a + 1));
  }
  return null;
}

// Remove one-day spikes (bad ticks): a jump of >25% that reverses >20% the next day.
// Fix unadjusted splits/bonuses: a one-day move matching a common ratio (2,3,4,5,10 or reverse) that persists -> rescale earlier prices.
export function splitAdjust(p) {
  const ds = Object.keys(p).sort(); let fixes = 0;
  for (let i = 1; i < ds.length; i++) {
    const r = p[ds[i]].c / p[ds[i - 1]].c; if (r > 0.6 && r < 1.7) continue;
    const next = p[ds[Math.min(i + 3, ds.length - 1)]].c / p[ds[i - 1]].c; // must persist a few days
    let f = null;
    for (const k of [2, 3, 4, 5, 10]) { if (Math.abs(r * k - 1) < 0.15 && Math.abs(next * k - 1) < 0.25) f = 1 / k; if (Math.abs(r / k - 1) < 0.15 && Math.abs(next / k - 1) < 0.25) f = k; }
    if (!f) continue; fixes++;
    for (let j = 0; j < i; j++) { const x = p[ds[j]]; x.o *= f; x.c *= f; }
  }
  if (fixes) p.__splitFixes = fixes;
  return p;
}
export function cleanSeries(p) {
  const fx = p.__splitFixes; delete p.__splitFixes;
  const ds = Object.keys(p).sort();
  let prev = ds[0];
  for (let i = 1; i < ds.length - 1; i++) {
    const a = p[prev].c, b = p[ds[i]].c, c = p[ds[i + 1]].c, up = b / a - 1, back = c / b - 1;
    if (Math.abs(up) > 0.25 && Math.abs(back) > 0.2 && Math.sign(up) !== Math.sign(back)) delete p[ds[i]]; else prev = ds[i];
  }
  if (fx) Object.defineProperty(p, 'splitFixes', { value: fx, enumerable: false });
  return p;
}
// Merge event lists, keeping the earliest event in any 20-day window per symbol.
export function dedupeEvents(list) {
  const out = []; for (const e of [...list].sort((a, b) => a.date.localeCompare(b.date) || (a.mins ?? 0) - (b.mins ?? 0)))
    if (!out.some((o) => Math.abs(Date.parse(o.date) - Date.parse(e.date)) < 20 * 864e5)) out.push(e);
  return out;
}
// Point-in-time approximation: on each rebalance date (Jan/Jul), the top N by 120-session median traded value.
export function liquidityUniverse(days, px, syms, n = 100) {
  const map = new Map(); let cur = new Set(), lastKey = '';
  for (let i = 0; i < days.length; i++) {
    const d = days[i], key = d.slice(0, 4) + (d.slice(5, 7) <= '06' ? 'a' : 'b');
    if (key !== lastKey && i >= 120) {
      const sc = [];
      for (const s of syms) { const v = []; for (let k = i - 120; k < i; k++) { const r = px[s]?.[days[k]]; if (r) v.push(r.tv); }
        if (v.length >= 90) { v.sort((a, b) => a - b); sc.push([s, v[Math.floor(v.length / 2)]]); } }
      sc.sort((a, b) => b[1] - a[1]); cur = new Set(sc.slice(0, n).map((x) => x[0])); lastKey = key;
    } else if (key !== lastKey && i < 120) { lastKey = ''; }
    map.set(i, cur);
  }
  return map;
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
  for (const [k, name, csv] of [['nifty100', 'NIFTY 100', 'ind_nifty100list'], ['nifty500', 'NIFTY 500', 'ind_nifty500list']]) {
    const j = await nse(`https://www.nseindia.com/api/equity-stockIndices?index=${encodeURIComponent(name)}`);
    uni[k] = (j?.data || []).map((x) => x.symbol).filter((s) => s && !/^NIFTY/.test(s));
    if (!uni[k].length) { try { const t = await (await fetch(`https://www.niftyindices.com/IndexConstituent/${csv}.csv`, { headers: { 'user-agent': UA } })).text();
      uni[k] = t.split(/\r?\n/).slice(1).map((l) => l.split(',')[2]).filter((x) => x && /^[A-Z0-9&-]+$/.test(x)); LOG.push(k + ' members from csv'); } catch (e) { LOG.push(k + ' csv fail ' + e.message); } }
    LOG.push(`${k}: ${uni[k].length} members`); console.log(k, uni[k].length, 'members'); await sleep(1500);
  }
  if (!uni.nifty100.length || !uni.nifty500.length) throw new Error('could not load index members');
  const all = [...new Set([...uni.nifty100, ...uni.nifty500, ...FORMER])];
  const bench = await yahoo('^NSEI'), beesRaw = await yahoo('NIFTYBEES.NS'); if (!bench) throw new Error('no Nifty data from Yahoo'); LOG.push('nifty days ' + Object.keys(bench).length + ', bees ' + (beesRaw ? Object.keys(beesRaw).length : 0));
  const days = Object.keys(bench).sort().filter((d) => d >= START);
  const px = {}, evs = {}; let nEv = 0, noPx = [], noEv = [], annCount = 0;
  for (const [n, s] of all.entries()) {
    const p = await yahoo(s + '.NS'); if (!p) { noPx.push(s); continue; } px[s] = p;
    const j = await nse(`https://www.nseindia.com/api/corporates-financial-results?index=equities&symbol=${encodeURIComponent(s)}&period=Quarterly`);
    const arr = Array.isArray(j) ? j : j?.data || [];
    const first = new Map(); // earliest broadcast per quarter end
    for (const x of arr) { const t = parseNseTime(x.broadCastDate || x.filingDate); const q = x.toDate || x.period; if (!t || !q) continue; const key = q; const prev = first.get(key); if (!prev || t.date < prev.date || (t.date === prev.date && (t.mins ?? 0) < (prev.mins ?? 0))) first.set(key, t); }
    const extra = [];
    const an = await nse(`https://www.nseindia.com/api/corporate-announcements?index=equities&symbol=${encodeURIComponent(s)}&from_date=01-12-2024&to_date=${new Date().toISOString().slice(0, 10).split('-').reverse().join('-')}`);
    for (const x of (Array.isArray(an) ? an : an?.data || [])) { const txt = `${x.desc || ''} ${x.attchmntText || ''}`; if (!/financial result/i.test(txt) || /intimation|newspaper|publication|trading window|schedule of/i.test(txt)) continue; const t = parseNseTime(x.an_dt); if (t) extra.push(t); }
    annCount += extra.length;
    const evTimes = dedupeEvents([...first.values(), ...extra]);
    const list = [];
    for (const t of evTimes) {
      const ri = reactionIndex(days, t); if (ri < 1 || ri + 1 >= days.length) continue;
      const d0 = days[ri - 1], d1 = days[ri]; if (!p[d0] || !p[d1]) continue;
      list.push({ sym: s, ri, date: d1, react: (p[d1].c / p[d0].c - 1) - (bench[d1].c / bench[d0].c - 1) });
    }
    if (!list.length) noEv.push(s); evs[s] = list; nEv += list.length;
    if (n < 3) LOG.push(`${s}: prices ${Object.keys(p).length}, nse rows ${arr.length}, ann ${extra.length}, events ${list.length}`);
    if (n % 25 === 0) console.log(`${n + 1}/${all.length} ${s}: ${list.length} events (total ${nEv})`);
    await sleep(700);
  }
  const bees = beesRaw ? days.map((d) => beesRaw[d]?.c) : null; if (bees) for (let i = 1; i < bees.length; i++) if (!bees[i]) bees[i] = bees[i - 1];
  let useBees = bees && bees[0] && Object.keys(beesRaw).length > days.length * 0.9;
  if (useBees) { const st = stats(days, bees); LOG.push('niftybees dd ' + st.dd + ' splitFixes ' + (beesRaw.splitFixes || 0)); if (st.dd < -60) { useBees = false; LOG.push('NIFTYBEES still broken -> using Nifty 50 index'); } }
  const benchEq = useBees ? bees : days.map((d) => bench[d].c);
  const bstat = stats(days, benchEq);
  const out = { generated: new Date().toISOString(), note: 'nifty100_current = today\'s members (hindsight bias). nifty100_pit = approx point-in-time: top 100 by 120-session median traded value each half-year, from Nifty 500 + former large caps (merged/delisted names only if Yahoo has prices). Costs 0.15%/side. Events: NSE results feed + results announcements from Dec 2024.',
    benchmark: { name: useBees ? 'NIFTYBEES (cleaned)' : 'Nifty 50 price index', full: bstat, periods: PERIODS.map(([a, b]) => stats(days, benchEq, a, b)) }, announcementsUsed: annCount, missingPrices: noPx, noEvents: noEv, log: LOG, universes: {} };
  const pitMap = liquidityUniverse(days, px, Object.keys(px), 100);
  const yearEvents = {};
  const allEvents = Object.values(evs).flat(); for (const e of allEvents) { const y = e.date.slice(0, 4); yearEvents[y] = (yearEvents[y] || 0) + 1; } out.eventsByYear = yearEvents;
  const formerInPit = new Set(); for (const set of pitMap.values()) for (const s of set) if (!uni.nifty100.includes(s)) formerInPit.add(s); out.pitNotInTodays100 = [...formerInPit].sort();
  const universes = { nifty100_current: allEvents.filter((e) => uni.nifty100.includes(e.sym)), nifty100_pit: allEvents.filter((e) => pitMap.get(e.ri)?.has(e.sym)) };
  for (const [k, events] of Object.entries(universes)) {
    const rows = [];
    for (const thr of GRID.thr) for (const hold of GRID.hold) for (const slots of GRID.slots) {
      const { eq, trades } = simulate(days, px, events, { thr, hold, slots });
      const per = PERIODS.map(([a, b]) => stats(days, eq, a, b));
      const sorted = [...trades].sort((a, b) => b - a), top10 = sorted.slice(0, 10).reduce((x, y) => x + y, 0), totalPos = sorted.filter((t) => t > 0).reduce((x, y) => x + y, 0);
      rows.push({ thr, hold, slots, full: stats(days, eq), periods: per, trades: trades.length, winRate: trades.length ? +(trades.filter((t) => t > 0).length / trades.length * 100).toFixed(0) : null,
        top10ShareOfGains: totalPos ? +(top10 / totalPos * 100).toFixed(0) : null, beatAll: per.every((p, i) => p && out.benchmark.periods[i] && p.cagr > out.benchmark.periods[i].cagr) });
    }
    rows.sort((a, b) => b.full.cagr - a.full.cagr);
    out.universes[k] = { events: events.length, beatBenchFull: rows.filter((r) => r.full.cagr > bstat.cagr).length, beatAllPeriods: rows.filter((r) => r.beatAll).length, combos: rows.length,
      reference: rows.find((r) => r.thr === 5 && r.hold === 60 && r.slots === 10), rows };
    console.log(k, 'events', events.length, 'ref', JSON.stringify(out.universes[k].reference?.full), 'bench', JSON.stringify(bstat));
  }
  // After-tax + idle cash (rule: 5% jump, hold 60, 10 slots). STCG 20% on the strategy; benchmark ETF held, 12.5% LTCG once at the end (exemption ignored).
  const O = {}, Cl = {}; for (const [s, p] of Object.entries(px)) { O[s] = days.map((d) => p[d]?.o ?? null); let last = null; Cl[s] = days.map((d) => (last = p[d]?.c ?? last)); }
  out.afterTax = { rule: 'thr5|hold60|n10', benchmark: out.benchmark.name + ' held, 12.5% LTCG on the gain at the end', note: 'Gains netted yearly, losses carried forward. Dividend tax and the Rs 1.25 lakh LTCG exemption ignored.', universes: {} };
  for (const [k, events] of Object.entries(universes)) {
    const sig = []; for (const e of events) (sig[e.ri + 1] ||= []).push({ s: e.sym, r: e.react }); for (const x of sig) if (x) x.sort((a, b) => b.r - a.r);
    out.afterTax.universes[k] = taxGrid({ dates: days, O, C: Cl, B: benchEq, signals: sig, th: 0.05, h: 60, n: 10, cost: COST }, [0, 0.2], 0.125);
    for (const r of out.afterTax.universes[k]) console.log('after-tax', k, JSON.stringify(r));
  }
  mkdirSync('data', { recursive: true }); writeFileSync('data/india_drift.json', JSON.stringify(out, null, 1));
}
if ((process.argv[1] || '').split('/').pop() === 'india-drift.mjs') main().catch((e) => { console.error(e); mkdirSync('data', { recursive: true }); writeFileSync('data/india_drift_error.json', JSON.stringify({ at: new Date().toISOString(), error: String(e?.stack || e), log: LOG }, null, 1)); process.exit(1); });
