// Builds data/strategies.json + data/strategy_series.csv: yearly returns and a monthly growth curve
// for the 3 strategies from the Oct 10 backtests, each next to SPY buy & hold over the same dates.
// Rules are copied 1:1 from trend_follow.py and spy_dip.py. No orders, ever.
//
// Data: Alpaca daily bars (dividend-adjusted) when APCA_API_KEY_ID + APCA_API_SECRET_KEY are set,
//       otherwise Yahoo Finance daily (adjusted close, no key).
// Usage: node scripts/build-strategies.mjs [outDir=data]

import { writeFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';

export const ETFS = ['SPY', 'QQQ', 'IWM', 'EFA', 'EEM', 'VNQ', 'TLT', 'IEF', 'GLD', 'DBC'];
export const CASH = 'BIL';
export const DIP_SYMS = ['SPY', 'QQQ'];
export const START = '2016-01-01';
const TREND_COST = 0.0005; // 0.05% per side on turnover
const DIP_COST = 0.0002;   // 0.02% per side

const mean = (a) => a.reduce((s, x) => s + x, 0) / a.length;
const iso = (d) => d.toISOString().slice(0, 10);
const ym = (d) => d.slice(0, 7);

// ---------------- data ----------------
// Returns { SYM: [{d:'YYYY-MM-DD', o, c}] } with dividend/split-adjusted open and close, sorted by date.
export async function loadBars(symbols, { fetchFn = fetch, env = process.env, end, sources } = {}) {
  end = end || iso(new Date(Date.now() - 86400000));
  const chain = sources || [
    ...(env.APCA_API_KEY_ID && env.APCA_API_SECRET_KEY ? [['Alpaca', () => alpacaBars(symbols, end, fetchFn, env)]] : []),
    ['Yahoo', () => yahooBars(symbols, end, fetchFn)],
    ['Nasdaq', () => nasdaqBars(symbols, end, fetchFn)],
  ];
  const notes = [];
  for (const [name, fn] of chain) {
    try {
      const bars = await fn();
      for (const s of symbols) if (!bars[s] || bars[s].length < 300) throw new Error(`${s}: only ${bars[s]?.length || 0} days`);
      bars._notes = notes;
      return bars;
    } catch (e) { notes.push(`${name} failed: ${String(e.message || e).slice(0, 300)}`); }
  }
  throw new Error('All price sources failed:\n' + notes.join('\n'));
}

// Nasdaq: unadjusted daily prices + dividend history -> total-return adjusted open/close.
const NQ_HEADERS = {
  'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36',
  Accept: 'application/json, text/plain, */*', Origin: 'https://www.nasdaq.com', Referer: 'https://www.nasdaq.com/',
};
const nqNum = (v) => { const n = Number(String(v ?? '').replace(/[$,\s]/g, '')); return Number.isFinite(n) ? n : null; };
const nqDate = (v) => { const m = String(v || '').match(/^(\d{2})\/(\d{2})\/(\d{4})$/); return m ? `${m[3]}-${m[1]}-${m[2]}` : null; };
async function nqGet(url, fetchFn) {
  for (let i = 0; i < 4; i++) {
    const r = await fetchFn(url, { headers: NQ_HEADERS });
    if (r.ok) return r.json();
    await new Promise((res) => setTimeout(res, 2000 * (i + 1)));
  }
  throw new Error('Nasdaq request failed: ' + url);
}
export function applyDividends(rows, divs) {
  // rows ascending {d, o, c} unadjusted; divs [{d: exDate, amt}]. Back-adjust like an "adjusted close".
  const out = rows.map((r) => ({ ...r }));
  const ex = [...divs].filter((x) => x.amt > 0).sort((a, b) => (a.d < b.d ? 1 : -1)); // newest first
  let f = 1, j = 0;
  for (let i = out.length - 1; i >= 0; i--) {
    out[i].o *= f; out[i].c *= f;
    while (j < ex.length && i > 0 && ex[j].d > out[i - 1].d && ex[j].d <= out[i].d) {
      const prev = rows[i - 1].c;
      if (prev > 0) f *= 1 - ex[j].amt / prev;
      j++;
    }
  }
  return out;
}
async function nasdaqBars(symbols, end, fetchFn) {
  const out = {};
  for (const s of symbols) {
    const h = await nqGet(`https://api.nasdaq.com/api/quote/${s}/historical?assetclass=etf&fromdate=${START}&todate=${end}&limit=9999`, fetchFn);
    const rows = (h?.data?.tradesTable?.rows || []).map((r) => ({ d: nqDate(r.date), o: nqNum(r.open), c: nqNum(r.close) }))
      .filter((r) => r.d && r.o > 0 && r.c > 0).sort((a, b) => (a.d < b.d ? -1 : 1));
    for (let i = 1; i < rows.length; i++) {
      const jump = rows[i].c / rows[i - 1].c;
      if (jump > 1.6 || jump < 0.6) throw new Error(`${s}: ${rows[i].d} price jump ${jump.toFixed(2)}x looks like an unadjusted split`);
    }
    let dj = null, drows = [];
    for (const cls of ['etf', 'stocks']) {
      dj = await nqGet(`https://api.nasdaq.com/api/quote/${s}/dividends?assetclass=${cls}`, fetchFn);
      drows = dj?.data?.dividends?.rows || dj?.data?.dividendHistoryTable?.rows || dj?.data?.rows || [];
      if (drows.length) break;
    }
    const pick = (r, ...ks) => { for (const k of ks) if (r[k] != null && r[k] !== '' && r[k] !== 'N/A') return r[k]; return null; };
    const divs = drows.map((r) => ({ d: nqDate(pick(r, 'exOrEffDate', 'exDate', 'exDividendDate')), amt: nqNum(pick(r, 'amount', 'cashAmount', 'dividend')) }))
      .filter((x) => x.d && x.amt && x.d >= START);
    out._debug = out._debug || {};
    out._debug[s] = { first_day: rows[0]?.d, days: rows.length, dividends: divs.length, first_div: divs.at(-1)?.d, last_div: divs[0]?.d,
      data_keys: Object.keys(dj?.data || {}).slice(0, 8), row_keys: drows[0] ? Object.keys(drows[0]).slice(0, 10) : [], status: dj?.status?.rCode };
    if (!divs.length) throw new Error(`${s}: no dividends found in Nasdaq response ${JSON.stringify(out._debug[s])}`);
    out[s] = applyDividends(rows, divs);
    await new Promise((r) => setTimeout(r, 500));
  }
  out._source = 'Nasdaq daily prices with dividends added back (adjusted close)';
  return out;
}

async function alpacaBars(symbols, end, fetchFn, env) {
  const out = Object.fromEntries(symbols.map((s) => [s, []]));
  const p = new URLSearchParams({ symbols: symbols.join(','), timeframe: '1Day', start: START, end, limit: '10000', adjustment: 'all', feed: env.APCA_FEED || 'sip' });
  for (;;) {
    const r = await fetchFn('https://data.alpaca.markets/v2/stocks/bars?' + p, {
      headers: { 'APCA-API-KEY-ID': env.APCA_API_KEY_ID, 'APCA-API-SECRET-KEY': env.APCA_API_SECRET_KEY },
    });
    if (!r.ok) throw new Error(`Alpaca HTTP ${r.status}: ${(await r.text()).slice(0, 200)}`);
    const js = await r.json();
    for (const [s, bl] of Object.entries(js.bars || {})) for (const b of bl) out[s].push({ d: b.t.slice(0, 10), o: b.o, c: b.c });
    if (!js.next_page_token) break;
    p.set('page_token', js.next_page_token);
  }
  for (const s of symbols) out[s].sort((a, b) => (a.d < b.d ? -1 : 1));
  out._source = 'Alpaca daily bars (split + dividend adjusted)';
  return out;
}

async function yahooBars(symbols, end, fetchFn) {
  const out = {};
  const p1 = Math.floor(Date.parse(START) / 1000), p2 = Math.floor(Date.parse(end) / 1000) + 86400;
  for (const s of symbols) {
    const url = `https://query1.finance.yahoo.com/v8/finance/chart/${s}?period1=${p1}&period2=${p2}&interval=1d&events=div%2Csplit`;
    let js;
    for (let i = 0; i < 4; i++) {
      const r = await fetchFn(url, { headers: { 'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36', Accept: 'application/json' } });
      if (r.ok) { js = await r.json(); break; }
      await new Promise((res) => setTimeout(res, 2000 * (i + 1)));
    }
    const res = js?.chart?.result?.[0];
    if (!res) throw new Error(`Yahoo returned no data for ${s}`);
    const ts = res.timestamp || [], q = res.indicators.quote[0], adj = res.indicators.adjclose?.[0]?.adjclose || q.close;
    out[s] = [];
    ts.forEach((t, i) => {
      const c = q.close[i], o = q.open[i], a = adj[i];
      if (c == null || o == null || a == null || c <= 0) return;
      const d = iso(new Date((t + (res.meta?.gmtoffset || 0)) * 1000));
      if (d <= end) out[s].push({ d, o: (o * a) / c, c: a }); // adjust the open by the same factor as the close
    });
    await new Promise((r) => setTimeout(r, 400));
  }
  out._source = 'Yahoo Finance daily (adjusted close, dividends reinvested)';
  return out;
}

// ---------------- shared stats ----------------
// points: [{d, eq}] equity marks in date order. Returns CAGR, total, max drawdown (all as fractions).
export function curveStats(points) {
  let peak = points[0].eq, mdd = 0;
  for (const p of points) { peak = Math.max(peak, p.eq); mdd = Math.max(mdd, 1 - p.eq / peak); }
  const first = points[0], last = points[points.length - 1];
  const yrs = (Date.parse(last.d) - Date.parse(first.d)) / (365.25 * 86400000);
  const total = last.eq / first.eq - 1;
  return { total, cagr: yrs > 0 ? (1 + total) ** (1 / yrs) - 1 : 0, max_dd: mdd, years: yrs };
}

// Calendar-year returns from equity marks (first mark = start). Partial first/last years are flagged.
export function yearly(points) {
  const out = [];
  let prevEq = points[0].eq, prevYear = points[0].d.slice(0, 4), lastEq = prevEq;
  const startPartial = points[0].d.slice(5) > '01-10';
  for (const p of points.slice(1)) {
    const y = p.d.slice(0, 4);
    if (y !== prevYear) {
      out.push({ year: +prevYear, ret: lastEq / prevEq - 1, partial: out.length === 0 && startPartial });
      prevEq = lastEq; prevYear = y;
    }
    lastEq = p.eq;
  }
  const lastD = points[points.length - 1].d;
  out.push({ year: +prevYear, ret: lastEq / prevEq - 1, partial: lastD.slice(5) < '12-20' || (out.length === 0 && startPartial) });
  return out;
}

// Month-end marks of a daily equity series (last mark in each month).
const monthEnds = (pts) => {
  const m = new Map();
  for (const p of pts) m.set(ym(p.d), p);
  return [...m.values()];
};

// ---------------- trend strategies (trend_follow.py) ----------------
export function trendRun(bars) {
  const px = {};
  for (const s of [...ETFS, CASH]) px[s] = new Map(bars[s].map((b) => [b.d, b.c]));
  const common = [...px[CASH].keys()].filter((d) => ETFS.every((s) => px[s].has(d))).sort();
  const me = new Map();
  for (const d of common) me.set(ym(d), d);
  const ends = [...me.values()].slice(0, -1); // drop the unfinished month
  const sma10 = {};
  ends.forEach((d, i) => { if (i >= 9) sma10[d] = mean(ends.slice(i - 9, i + 1).map((e) => px.SPY.get(e))); });
  const ret12 = (s, i) => px[s].get(ends[i]) / px[s].get(ends[i - 12]) - 1;
  const merge = (pairs) => pairs.reduce((w, [s, x]) => ((w[s] = (w[s] || 0) + x), w), {});
  const W = {
    momentum: (i) => merge([...ETFS].sort((a, b) => ret12(b, i) - ret12(a, i)).slice(0, 3).map((s) => [ret12(s, i) > ret12(CASH, i) ? s : CASH, 1 / 3])),
    spy10: (i) => (px.SPY.get(ends[i]) > sma10[ends[i]] ? { SPY: 1 } : { [CASH]: 1 }),
    trend10: (i) => merge(ETFS.map((s) => [ret12(s, i) > ret12(CASH, i) ? s : CASH, 0.1])),
    spy: () => ({ SPY: 1 }),
  };
  const simulate = (fn) => {
    let prev = {}, eq = 1, switches = 0, upMonths = 0, invested = 0;
    const pts = [{ d: ends[12], eq: 1 }];
    for (let i = 12; i < ends.length - 1; i++) {
      const w = fn(i), d0 = ends[i], d1 = ends[i + 1];
      const keys = new Set([...Object.keys(w), ...Object.keys(prev)]);
      const turnover = [...keys].reduce((t, s) => t + Math.abs((w[s] || 0) - (prev[s] || 0)), 0);
      if ([...keys].some((s) => s !== CASH && (w[s] || 0) > 0 !== (prev[s] || 0) > 0)) switches++;
      const r = Object.entries(w).reduce((t, [s, x]) => t + x * (px[s].get(d1) / px[s].get(d0) - 1), 0) - turnover * TREND_COST;
      eq *= 1 + r; if (r > 0) upMonths++; invested += 1 - (w[CASH] || 0);
      pts.push({ d: d1, eq });
      prev = r > -1 ? Object.fromEntries(Object.entries(w).map(([s, x]) => [s, (x * px[s].get(d1)) / px[s].get(d0) / (1 + r)])) : {};
    }
    const months = pts.length - 1;
    return { pts, switches, up_months: upMonths / months, invested: invested / months, months };
  };
  return { ends, sim: Object.fromEntries(Object.entries(W).map(([k, fn]) => [k, simulate(fn)])) };
}

// ---------------- dip strategy (spy_dip.py, RSI(2) < 10) ----------------
const rsi2 = (C, i) => {
  let g = 0, l = 0;
  for (const k of [i - 1, i]) { const ch = C[k] - C[k - 1]; g += Math.max(ch, 0); l += Math.max(-ch, 0); }
  return l === 0 ? 100 : 100 - 100 / (1 + g / l);
};

export function dipTrades(rows) {
  const D = rows.map((r) => r.d), O = rows.map((r) => r.o), C = rows.map((r) => r.c);
  const out = [];
  let i = 200;
  while (i < rows.length - 1) {
    const sma200 = mean(C.slice(i - 199, i + 1));
    if (C[i] > sma200 && rsi2(C, i) < 10) {
      const e = i + 1, entry = O[e];
      let k = e;
      while (k < rows.length - 1 && k < e + 9 && !(C[k] > mean(C.slice(k - 4, k + 1)))) k++;
      out.push({ sig: D[i], entry_d: D[e], exit_d: D[k], entry, ei: e, xi: k, pct: C[k] / entry - 1 - 2 * DIP_COST });
      i = k + 1;
      continue;
    }
    i++;
  }
  return out;
}

export function dipRun(bars) {
  const per = Object.fromEntries(DIP_SYMS.map((s) => [s, bars[s]]));
  const all = DIP_SYMS.flatMap((s) => dipTrades(per[s]).map((t) => ({ ...t, sym: s })));
  // one position at a time, earliest entry first (ties: list order, as in the Python sort)
  const taken = [];
  let busy = null;
  for (const t of [...all].sort((a, b) => (a.entry_d < b.entry_d ? -1 : a.entry_d > b.entry_d ? 1 : 0))) {
    if (busy && t.entry_d <= busy) continue;
    taken.push(t); busy = t.exit_d;
  }
  // trade-to-trade equity (matches the original 18% drawdown method)
  let eq = 1, peak = 1, mddTrades = 0;
  for (const t of taken) { eq *= 1 + t.pct; peak = Math.max(peak, eq); mddTrades = Math.max(mddTrades, 1 - eq / peak); }
  // daily mark-to-market equity on the SPY calendar
  const spy = per.SPY, start = spy[200].d;
  const closeOn = Object.fromEntries(DIP_SYMS.map((s) => [s, new Map(per[s].map((r) => [r.d, r.c]))]));
  const daily = [];
  let base = 1, ti = 0;
  for (const r of spy) {
    if (r.d < start) continue;
    while (ti < taken.length && taken[ti].exit_d < r.d) { base *= 1 + taken[ti].pct; ti++; }
    const t = taken[ti];
    let v = base;
    if (t && t.entry_d <= r.d && r.d <= t.exit_d) {
      const c = closeOn[t.sym].get(r.d);
      v = r.d === t.exit_d ? base * (1 + t.pct) : c != null ? base * (c / (t.entry * (1 + DIP_COST))) : base;
    }
    daily.push({ d: r.d, eq: v });
  }
  const spyDaily = spy.filter((r) => r.d >= start).map((r) => ({ d: r.d, eq: r.c / spy[200].c }));
  return { all, taken, mddTrades, daily, spyDaily };
}

// ---------------- assemble ----------------
const r1 = (x) => (x == null ? null : Math.round(x * 10000) / 100); // fraction -> % with 2 decimals
const money = (x) => Math.round(x * 10000);

function pack(id, name, pts, spyPts, extra) {
  const s = curveStats(pts), b = curveStats(spyPts);
  const ys = yearly(pts), yb = new Map(yearly(spyPts).map((y) => [y.year, y.ret]));
  const spyByDate = new Map(spyPts.map((p) => [p.d, p.eq / spyPts[0].eq]));
  const spyMe = new Map(monthEnds(spyPts).map((p) => [ym(p.d), p.eq / spyPts[0].eq]));
  const marks = [pts[0], ...monthEnds(pts).filter((p) => p.d !== pts[0].d)];
  return {
    id, name, start: pts[0].d, end: pts[pts.length - 1].d,
    cagr: r1(s.cagr), total: r1(s.total), max_dd: r1(s.max_dd),
    spy_cagr: r1(b.cagr), spy_total: r1(b.total), spy_max_dd: r1(b.max_dd),
    ...extra,
    yearly: ys.map((y) => ({ year: y.year, ret: r1(y.ret), spy: r1(yb.get(y.year)), partial: y.partial })),
    curve: marks.map((p) => ({ date: p.d, equity: money(p.eq / pts[0].eq), spy: money(spyByDate.get(p.d) ?? spyMe.get(ym(p.d)) ?? NaN) })),
  };
}

export function assemble(bars, now = new Date()) {
  const T = trendRun(bars), D = dipRun(bars);
  const spyM = T.sim.spy.pts;
  const strategies = [
    pack('momentum', 'Top-3 momentum', T.sim.momentum.pts, spyM, { freq: 'monthly', months: T.sim.momentum.months, switch_months: T.sim.momentum.switches, up_months: r1(T.sim.momentum.up_months), invested: r1(T.sim.momentum.invested), dd_basis: 'month-end closes' }),
    pack('spy10', 'SPY above 10-month average', T.sim.spy10.pts, spyM, { freq: 'monthly', months: T.sim.spy10.months, switch_months: T.sim.spy10.switches, up_months: r1(T.sim.spy10.up_months), invested: r1(T.sim.spy10.invested), dd_basis: 'month-end closes' }),
    pack('dip', 'RSI(2) dip on SPY/QQQ', D.daily, D.spyDaily, {
      freq: 'daily', trades_all: D.all.length, win_rate: r1(D.all.filter((t) => t.pct > 0).length / D.all.length),
      trades_taken: D.taken.length, win_rate_taken: r1(D.taken.filter((t) => t.pct > 0).length / D.taken.length),
      max_dd_trades: r1(D.mddTrades), dd_basis: 'daily mark-to-market (max_dd_trades = trade-to-trade, the original method)',
      invested: r1(D.taken.reduce((n, t) => n + (t.xi - t.ei + 1), 0) / D.daily.length),
    }),
    pack('trend10', 'Trend on 10 ETFs', T.sim.trend10.pts, spyM, { freq: 'monthly', months: T.sim.trend10.months, up_months: r1(T.sim.trend10.up_months), invested: r1(T.sim.trend10.invested), dd_basis: 'month-end closes' }),
  ];
  return { generated: now.toISOString(), source: bars._source, source_notes: bars._notes || [], source_debug: bars._debug || null, strategies };
}

// Month-end adjusted closes for the momentum pool (dates where all 11 ETFs traded), for tuning in the dashboard.
export function monthlyCsv(bars) {
  const syms = [...ETFS, CASH];
  const px = Object.fromEntries(syms.map((s) => [s, new Map(bars[s].map((b) => [b.d, b.c]))]));
  const common = [...px[CASH].keys()].filter((d) => syms.every((s) => px[s].has(d))).sort();
  const me = new Map(); for (const d of common) me.set(ym(d), d);
  const ends = [...me.values()].slice(0, -1);
  return ['date,' + syms.join(','), ...ends.map((d) => d + ',' + syms.map((s) => +px[s].get(d).toFixed(4)).join(','))].join('\n') + '\n';
}
// Daily adjusted open/close for the dip ETFs.
export function dailyCsv(bars, syms) {
  const lines = ['symbol,date,open,close'];
  for (const s of syms) for (const b of bars[s]) lines.push([s, b.d, +b.o.toFixed(4), +b.c.toFixed(4)].join(','));
  return lines.join('\n') + '\n';
}

export function toCsv(result) {
  const lines = ['strategy,kind,period,value,spy,partial'];
  for (const s of result.strategies) {
    for (const y of s.yearly) lines.push([s.id, 'year', y.year, y.ret, y.spy ?? '', y.partial ? 1 : 0].join(','));
    for (const c of s.curve) lines.push([s.id, 'month', c.date, c.equity, Number.isFinite(c.spy) ? c.spy : '', 0].join(','));
  }
  return lines.join('\n') + '\n';
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const outDir = process.argv[2] || 'data';
  mkdirSync(outDir, { recursive: true });
  let bars;
  try { bars = await loadBars([...new Set([...ETFS, CASH, ...DIP_SYMS])]); }
  catch (e) { writeFileSync(join(outDir, 'strategies_error.txt'), new Date().toISOString() + '\n' + String(e.message || e) + '\n'); console.error(e.message); process.exit(1); }
  const res = assemble(bars);
  mkdirSync(outDir, { recursive: true });
  writeFileSync(join(outDir, 'strategies.json'), JSON.stringify(res, null, 1));
  writeFileSync(join(outDir, 'strategy_series.csv'), toCsv(res));
  writeFileSync(join(outDir, 'etf_monthly.csv'), monthlyCsv(bars));
  writeFileSync(join(outDir, 'dip_daily.csv'), dailyCsv(bars, DIP_SYMS));
  console.log(`Source: ${res.source}`);
  for (const s of res.strategies)
    console.log(`${s.name.padEnd(28)} ${s.start} -> ${s.end}  CAGR ${s.cagr}%  total ${s.total}%  maxDD ${s.max_dd}%  | SPY ${s.spy_cagr}%/yr, DD ${s.spy_max_dd}%`);
}
