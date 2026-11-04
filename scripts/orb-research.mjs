// ORB research grid: opening-range breakout on "stocks in play". Research only, no orders.
// Usage: node scripts/orb-research.mjs chunk <sp500|wide> <year> <outDir>   |   node scripts/orb-research.mjs merge <inDir> <outDir>
// Chunk: per trading day, daily filters (prev close>$5, 14d avg vol>=1M, ATR14>$0.50), rel. volume of 9:30 5-min bar vs its
// 14-day avg (>=1x), gap vs prev close. Picks = top 20 by rel vol + top 20 gappers (|gap|>=3%). 1-min bars for picks.
// Every combo below -> daily return (risk 1% equity/trade, max 4x leverage, $0.0035/sh + 1c/sh slippage per side).
// Conservative: stop touched in the entry minute = stopped; stop checked before target in the same minute.
// Bias: current S&P 500 / currently active assets (survivorship).
import { writeFileSync, readFileSync, mkdirSync, readdirSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
export const COMM = 0.0035, SLIP = 0.01, RISK = 0.01, LEV = 4, IS_END = '2024-12-31';
export const ORS = [5, 15, 30], STOPS = [0.1, 0.25, 0.5, 1], TOPS = [5, 20], MKTS = ['off', 'on'], TGTS = ['close', '2R', 'trail1R'], GAPS = ['off', 'on'], SIDES = ['both', 'long'];
export const COMBOS = [];
for (const o of ORS) for (const s of STOPS) for (const t of TOPS) for (const m of MKTS) for (const g of TGTS) for (const p of GAPS) for (const d of SIDES) COMBOS.push({ key: `or${o}|s${s}|t${t}|mkt-${m}|${g}|gap-${p}|${d}`, o, s, t, m, g, p, d });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const fmt = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
export function et(t) { const o = Object.fromEntries(fmt.formatToParts(new Date(t)).map((x) => [x.type, x.value])); return { d: `${o.year}-${o.month}-${o.day}`, m: (+o.hour % 24) * 60 + +o.minute }; }

// bars: 1-min bars after the opening range. Returns {fill, exit} or null.
export function simTrade(dir, lvl, bars, sd, tgt) {
  let fill = null, stop = 0, best = 0, take = 0;
  for (const b of bars) {
    if (fill == null) {
      if (dir > 0 ? b.h < lvl : b.l > lvl) continue;
      fill = dir > 0 ? Math.max(lvl, b.o) : Math.min(lvl, b.o); stop = fill - dir * sd; take = fill + dir * 2 * sd;
      if (dir > 0 ? b.l <= stop : b.h >= stop) return { fill, exit: stop };
      best = dir > 0 ? Math.max(fill, b.c) : Math.min(fill, b.c); if (tgt === 'trail1R') stop = best - dir * sd;
      continue;
    }
    if (dir > 0 ? b.l <= stop : b.h >= stop) return { fill, exit: dir > 0 ? Math.min(stop, b.o) : Math.max(stop, b.o) };
    if (tgt === '2R' && (dir > 0 ? b.h >= take : b.l <= take)) return { fill, exit: dir > 0 ? Math.max(take, b.o) : Math.min(take, b.o) };
    if (tgt === 'trail1R') { best = dir > 0 ? Math.max(best, b.h) : Math.min(best, b.l); stop = best - dir * sd; }
  }
  return fill == null ? null : { fill, exit: bars[bars.length - 1].c };
}
export const tradeRet = (dir, fill, exit, sd, top) => Math.min(RISK / sd, LEV / top / fill) * (dir * (exit - fill) - 2 * (COMM + SLIP));
export const orOf = (ob, k) => { if (ob.length < k) return null; const s = ob.slice(0, k); const dir = Math.sign(s[k - 1].c - s[0].o); return dir ? { dir, hi: Math.max(...s.map((b) => b.h)), lo: Math.min(...s.map((b) => b.l)) } : null; };

// picks: [{s, rv, gap, atr, ob:[5-min bars 9:30..9:55], m:[1-min bars {m,o,h,l,c}]}]; spyOb: SPY 5-min bars.
export function dayResults(picks, spyOb) {
  const byRv = [...picks.keys()].sort((a, b) => picks[b].rv - picks[a].rv);
  const lists = { off: byRv.filter((i) => picks[i].inAll), on: byRv.filter((i) => Math.abs(picks[i].gap) >= 0.03) };
  const cache = new Map(), out = {};
  const sim = (i, o, s, g) => {
    const k = `${i}|${o}|${s}|${g}`; if (cache.has(k)) return cache.get(k);
    const p = picks[i], r = orOf(p.ob, o / 5); let v = null;
    if (r) { const sd = s * p.atr; const t = simTrade(r.dir, r.dir > 0 ? r.hi : r.lo, p.m.filter((b) => b.m >= 570 + o && b.m < 960), sd, g); if (t) v = { dir: r.dir, ...t, sd }; }
    cache.set(k, v); return v;
  };
  for (const c of COMBOS) {
    let ret = 0, n = 0, w = 0, R = 0; const spy = c.m === 'on' ? orOf(spyOb, c.o / 5) : null;
    if (c.m === 'on' && !spy) { out[c.key] = [0, 0, 0, 0]; continue; }
    for (const i of lists[c.p].slice(0, c.t)) {
      const t = sim(i, c.o, c.s, c.g); if (!t) continue;
      if (c.d === 'long' && t.dir < 0) continue; if (spy && spy.dir !== t.dir) continue;
      const r = tradeRet(t.dir, t.fill, t.exit, t.sd, c.t); ret += r; n++; if (r > 0) w++; R += (t.dir * (t.exit - t.fill) - 2 * (COMM + SLIP)) / t.sd;
    }
    out[c.key] = [ret, n, w, R];
  }
  return out;
}

export function stats(rets) { // rets: [[date, r]]
  if (!rets.length) return null; let e = 1, pk = 1, dd = 0; for (const [, r] of rets) { e *= 1 + r; pk = Math.max(pk, e); dd = Math.max(dd, 1 - e / pk); }
  const yrs = Math.max((Date.parse(rets.at(-1)[0]) - Date.parse(rets[0][0])) / 31557600000, 1 / 252);
  const mu = rets.reduce((a, [, r]) => a + r, 0) / rets.length, sdv = Math.sqrt(rets.reduce((a, [, r]) => a + (r - mu) ** 2, 0) / rets.length);
  return { cagr: +((Math.max(e, 1e-9) ** (1 / yrs) - 1) * 100).toFixed(2), total: +((e - 1) * 100).toFixed(1), max_dd: +(dd * 100).toFixed(1), sharpe: sdv ? +(mu / sdv * Math.sqrt(252)).toFixed(2) : 0 };
}
export function makeApi(env = process.env, fetchFn = (...a) => globalThis.fetch(...a)) {
  const H = { 'APCA-API-KEY-ID': env.APCA_API_KEY_ID, 'APCA-API-SECRET-KEY': env.APCA_API_SECRET_KEY }; const api = { reqs: 0 };
  async function get(url) {
    for (let a = 0; ; a++) {
      try { const r = await fetchFn(url, { headers: H }); api.reqs++; if (r.ok) return await r.json(); const t = await r.text(); if (a >= 8 || (r.status < 500 && r.status !== 429)) throw new Error(`${r.status} ${t.slice(0, 200)} ${url.slice(0, 120)}`); }
      catch (e) { if (a >= 8 || /^4\d\d (?!.*429)/.test(e.message) && !/^429/.test(e.message)) throw e; }
      await sleep(Math.min(60000, 2000 * 2 ** a));
    }
  }
  api.bars = async (symbols, tf, start, end, per = 400) => {
    const out = {};
    for (let i = 0; i < symbols.length; i += per) {
      let token = null;
      do { const p = new URLSearchParams({ symbols: symbols.slice(i, i + per).join(','), timeframe: tf, start, end, limit: '10000', adjustment: 'split', feed: 'sip' }); if (token) p.set('page_token', token);
        const j = await get('https://data.alpaca.markets/v2/stocks/bars?' + p); for (const [s, a] of Object.entries(j.bars || {})) (out[s] ||= []).push(...a); token = j.next_page_token; await sleep(+(env.ORB_PAUSE ?? 330)); } while (token);
    }
    return out;
  };
  api.assets = async () => { for (const h of ['https://paper-api.alpaca.markets', 'https://api.alpaca.markets']) { try { return await get(h + '/v2/assets?status=active&asset_class=us_equity'); } catch (e) { console.log('assets', h, e.message); } } throw new Error('assets: no endpoint worked'); };
  return api;
}
export async function universe(kind, api) {
  if (kind === 'sp500') return JSON.parse(readFileSync('data/sp500_tickers.json', 'utf8')).tickers.map((t) => t.symbol);
  const a = await api.assets(); const bad = /\b(ETF|ETN|Fund|Trust|ProShares|Direxion|iShares|SPDR|Invesco|Vanguard|Warrant|Units?|Rights?|Notes?|Preferred|Depositary)\b/i;
  return a.filter((x) => x.tradable && ['NYSE', 'NASDAQ', 'AMEX'].includes(x.exchange) && /^[A-Z]{1,5}$/.test(x.symbol) && !bad.test(x.name || '')).map((x) => x.symbol);
}
export async function runChunk(kind, year, outDir, { api = makeApi(), now = Date.now() - 3600e3, log = console.log } = {}) {
  const syms = await universe(kind, api); log(kind, 'universe', syms.length);
  const start = `${year}-01-01`, endMs = Math.min(Date.parse(`${+year + 1}-01-01T00:00:00Z`), now), iso = (ms) => new Date(ms).toISOString();
  const daily = await api.bars([...syms, 'SPY'], '1Day', iso(Date.parse(start) - 75 * 86400e3), iso(endMs), 400);
  log('daily symbols', Object.keys(daily).length, 'reqs', api.reqs);
  const info = {};
  for (const s of syms) { const a = daily[s]; if (!a) continue;
    for (let i = 15; i < a.length; i++) { let tr = 0, v = 0; for (let k = i - 14; k < i; k++) { tr += Math.max(a[k].h - a[k].l, Math.abs(a[k].h - a[k - 1].c), Math.abs(a[k].l - a[k - 1].c)); v += a[k].v; }
      const pc = a[i - 1].c, atr = tr / 14, vol = v / 14; if (pc > 5 && vol >= 1e6 && atr > 0.5) (info[et(a[i].t).d] ||= {})[s] = { atr, pc }; } }
  const days = (daily.SPY || []).map((b) => ({ d: et(b.t).d, t0: Date.parse(b.t) })).filter((x) => x.t0 >= Date.parse(start) - 35 * 86400e3 && x.t0 + 16 * 3600e3 < endMs);
  const fv = {}, dates = [], res = Object.fromEntries(COMBOS.map((c) => [c.key, { r: [], n: 0, w: 0, R: 0 }])); let elig = 0, td = 0;
  for (const { d, t0 } of days) {
    const o = t0 + 9.5 * 3600e3, el = Object.keys(info[d] || {}); if (!el.length) continue;
    const ob = await api.bars([...el, 'SPY'], '5Min', iso(o), iso(o + 29 * 60e3), 400); const cands = [];
    for (const s of el) { const a = (ob[s] || []).filter((b) => Date.parse(b.t) - o < 30 * 60e3); if (!a.length || Date.parse(a[0].t) !== o) continue;
      const h = (fv[s] ||= []), avg = h.length >= 14 ? h.reduce((x, y) => x + y, 0) / h.length : 0; h.push(a[0].v); if (h.length > 14) h.shift();
      if (d < start || !avg || a[0].o <= 5) continue; const rv = a[0].v / avg; if (rv >= 1) cands.push({ s, rv, gap: a[0].o / info[d][s].pc - 1, atr: info[d][s].atr, ob: a }); }
    if (d < start) continue; td++; elig += el.length;
    cands.sort((x, y) => y.rv - x.rv); cands.slice(0, 20).forEach((c) => (c.inAll = true));
    const picks = [...new Set([...cands.slice(0, 20), ...cands.filter((c) => Math.abs(c.gap) >= 0.03).slice(0, 20)])];
    const m1 = picks.length ? await api.bars(picks.map((p) => p.s), '1Min', iso(o), iso(o + 389 * 60e3), 50) : {};
    for (const p of picks) p.m = (m1[p.s] || []).map((b) => ({ m: et(b.t).m, o: b.o, h: b.h, l: b.l, c: b.c }));
    const spyOb = (ob.SPY || []).filter((b) => Date.parse(b.t) - o < 30 * 60e3 && Date.parse(b.t) >= o);
    const dr = dayResults(picks, spyOb); dates.push(d);
    for (const [k, [r, n, w, R]] of Object.entries(dr)) { const x = res[k]; x.r.push(+r.toFixed(6)); x.n += n; x.w += w; x.R += R; }
    if (td % 20 === 1) log(d, 'eligible', el.length, 'cands', cands.length, 'picks', picks.length, 'reqs', api.reqs);
  }
  const spy = (daily.SPY || []).map((b) => [et(b.t).d, b.c]).filter(([d]) => d >= start);
  mkdirSync(outDir, { recursive: true }); const f = `${outDir}/${kind}_${year}.json`;
  writeFileSync(f, JSON.stringify({ kind, year: +year, universe: syms.length, days: td, avg_eligible: td ? Math.round(elig / td) : 0, reqs: api.reqs, dates, spy, combos: res }));
  log('wrote', f, 'days', td, 'reqs', api.reqs); return f;
}
export function merge(inDir, outDir, log = console.log) {
  const files = readdirSync(inDir).filter((f) => /^(sp500|wide)_\d{4}\.json$/.test(f)).sort(); const by = {};
  for (const f of files) { const j = JSON.parse(readFileSync(`${inDir}/${f}`, 'utf8')); (by[j.kind] ||= []).push(j); }
  const out = { generated: new Date().toISOString(), in_sample: `.. ${IS_END}`, out_of_sample: `after ${IS_END}`, notes: ['Conservative fills; survivorship bias (current lists).', 'Rank by in-sample Sharpe; trust only combos that also beat SPY out-of-sample.'], universes: {} };
  for (const [kind, ch] of Object.entries(by)) {
    ch.sort((a, b) => a.year - b.year); const spyC = ch.flatMap((c) => c.spy); const spyR = spyC.slice(1).map(([d, c], i) => [d, c / spyC[i][1] - 1]);
    const per = (arr, f) => arr.filter(([d]) => f(d)); const isF = (d) => d <= IS_END, osF = (d) => d > IS_END;
    const rows = COMBOS.map((c) => { const r = ch.flatMap((x) => x.dates.map((d, i) => [d, x.combos[c.key].r[i]]));
      const agg = (f) => ch.filter((x) => f(`${x.year}-06-30`)).reduce((a, x) => { const k = x.combos[c.key]; a.n += k.n; a.w += k.w; a.R += k.R; return a; }, { n: 0, w: 0, R: 0 });
      const mk = (f) => { const a = agg(f); return { ...stats(per(r, f)), trades: a.n, win_rate: a.n ? +(100 * a.w / a.n).toFixed(1) : null, avg_R: a.n ? +(a.R / a.n).toFixed(3) : null }; };
      return { key: c.key, is: mk(isF), oos: mk(osF), all: stats(r) }; }).filter((x) => x.is && x.is.cagr != null);
    rows.sort((a, b) => (b.is.sharpe ?? -99) - (a.is.sharpe ?? -99));
    out.universes[kind] = { years: ch.map((c) => c.year), avg_eligible: ch.map((c) => c.avg_eligible), spy: { is: stats(per(spyR, isF)), oos: stats(per(spyR, osF)) }, top10: rows.slice(0, 10), all: rows };
    log(`\n== ${kind} (years ${ch.map((c) => c.year).join(',')})  SPY IS ${JSON.stringify(out.universes[kind].spy.is)} OOS ${JSON.stringify(out.universes[kind].spy.oos)}`);
    for (const x of rows.slice(0, 10)) log(x.key.padEnd(48), 'IS', x.is.cagr, '%', 'sh', x.is.sharpe, 'dd', x.is.max_dd, '| OOS', x.oos.cagr, '%', 'sh', x.oos.sharpe, 'dd', x.oos.max_dd, 'trades', x.is.trades + '/' + x.oos.trades);
  }
  mkdirSync(outDir, { recursive: true }); writeFileSync(`${outDir}/orb_grid_summary.json`, JSON.stringify(out, null, 1)); return out;
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const [cmd, a, b, c] = process.argv.slice(2);
  (cmd === 'chunk' ? runChunk(a, b, c || 'out') : Promise.resolve(merge(a, b || 'data'))).catch((e) => { console.error(e); process.exit(1); });
}
