// ORB gappers robustness test. Reference (from orb research grid, wide universe):
//   5-min opening range, stop 1x ATR14, top 5 by relative volume among |gap|>=3%, 2R target, long only.
// Tests: years 2017-2026 (2017-2020 never seen), neighbouring params, worse slippage, gap-up only.
// Research only, no orders. Survivorship bias: currently active stocks only (worse further back).
// Usage: node scripts/orb-gappers.mjs chunk <year> <outDir> | node scripts/orb-gappers.mjs merge <inDir> <outDir>
import { writeFileSync, readFileSync, mkdirSync, readdirSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { orOf, stats, makeApi, universe, et } from './orb-research.mjs';
export const COMM = 0.0035, RISK = 0.01, LEV = 4;
export const ORS = [5, 10, 15], STOPS = [0.5, 0.75, 1, 1.5], TOPS = [3, 5, 10], TGTS = [1.5, 2, 3, 0], GAPS = [2, 3, 4, 5], DIRS = ['abs', 'up'], SLIPS = [0.01, 0.05];
export const REF = 'or5|s1|t5|tgt2|gap3|abs|slip0.01';
export const COMBOS = [];
for (const o of ORS) for (const s of STOPS) for (const t of TOPS) for (const g of TGTS) for (const p of GAPS) for (const d of DIRS) for (const sl of SLIPS)
  COMBOS.push({ key: `or${o}|s${s}|t${t}|tgt${g}|gap${p}|${d}|slip${sl}`, o, s, t, g, p, d, sl });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Long breakout above lvl; tm = target in R (0 = hold to close). Conservative: stop in entry bar = stopped; stop before target.
export function sim(lvl, bars, sd, tm) {
  let fill = null, stop = 0, take = 0;
  for (const b of bars) {
    if (fill == null) {
      if (b.h < lvl) continue;
      fill = Math.max(lvl, b.o); stop = fill - sd; take = fill + tm * sd;
      if (b.l <= stop) return { fill, exit: stop };
      continue;
    }
    if (b.l <= stop) return { fill, exit: Math.min(stop, b.o) };
    if (tm && b.h >= take) return { fill, exit: Math.max(take, b.o) };
  }
  return fill == null ? null : { fill, exit: bars[bars.length - 1].c };
}
export const ret = (fill, exit, sd, top, slip) => Math.min(RISK / sd, LEV / top / fill) * (exit - fill - 2 * (COMM + slip));

export function dayResults(picks, combos = COMBOS) {
  const byRv = [...picks.keys()].sort((a, b) => picks[b].rv - picks[a].rv), lists = {};
  for (const p of GAPS) for (const d of DIRS) lists[`${p}|${d}`] = byRv.filter((i) => { const g = picks[i].gap * 100; return d === 'up' ? g >= p : Math.abs(g) >= p; });
  const cache = new Map(), out = {};
  const run = (i, o, s, g) => {
    const k = `${i}|${o}|${s}|${g}`; if (cache.has(k)) return cache.get(k);
    const p = picks[i], r = orOf(p.ob, o / 5); let v = null;
    if (r && r.dir > 0) { const sd = s * p.atr, t = sim(r.hi, p.m.filter((b) => b.m >= 570 + o && b.m < 960), sd, g); if (t) v = { ...t, sd }; }
    cache.set(k, v); return v;
  };
  for (const c of combos) {
    let tot = 0, n = 0, w = 0, R = 0;
    for (const i of lists[`${c.p}|${c.d}`].slice(0, c.t)) {
      const t = run(i, c.o, c.s, c.g); if (!t) continue;
      const r = ret(t.fill, t.exit, t.sd, c.t, c.sl); tot += r; n++; if (r > 0) w++; R += (t.exit - t.fill - 2 * (COMM + c.sl)) / t.sd;
    }
    out[c.key] = [tot, n, w, R];
  }
  return out;
}
export function pickLists(cands) { // union of top 10 for every gap/direction list
  const byRv = [...cands].sort((a, b) => b.rv - a.rv), set = new Set();
  for (const p of GAPS) for (const d of DIRS) byRv.filter((c) => (d === 'up' ? c.gap * 100 >= p : Math.abs(c.gap) * 100 >= p)).slice(0, 10).forEach((c) => set.add(c));
  return [...set];
}

export async function runChunk(year, outDir, { api = makeApi(), now = Date.now() - 3600e3, log = console.log } = {}) {
  const syms = await universe('wide', api); log('universe', syms.length);
  const start = `${year}-01-01`, endMs = Math.min(Date.parse(`${+year + 1}-01-01T00:00:00Z`), now), iso = (ms) => new Date(ms).toISOString();
  const daily = await api.bars([...syms, 'SPY'], '1Day', iso(Date.parse(start) - 75 * 86400e3), iso(endMs), 400);
  log('daily symbols', Object.keys(daily).length, 'reqs', api.reqs);
  const info = {};
  for (const s of syms) { const a = daily[s]; if (!a) continue;
    for (let i = 15; i < a.length; i++) { let tr = 0, v = 0; for (let k = i - 14; k < i; k++) { tr += Math.max(a[k].h - a[k].l, Math.abs(a[k].h - a[k - 1].c), Math.abs(a[k].l - a[k - 1].c)); v += a[k].v; }
      const pc = a[i - 1].c, atr = tr / 14, vol = v / 14; if (pc > 5 && vol >= 1e6 && atr > 0.5) (info[et(a[i].t).d] ||= {})[s] = { atr, pc }; } }
  const days = (daily.SPY || []).map((b) => ({ d: et(b.t).d, t0: Date.parse(b.t) })).filter((x) => x.t0 >= Date.parse(start) - 35 * 86400e3 && x.t0 + 16 * 3600e3 < endMs);
  const fv = {}, dates = [], res = Object.fromEntries(COMBOS.map((c) => [c.key, { r: [], n: 0, w: 0, R: 0 }])); let td = 0, nc = 0;
  for (const { d, t0 } of days) {
    const o = t0 + 9.5 * 3600e3, el = Object.keys(info[d] || {}); if (!el.length) continue;
    const ob = await api.bars(el, '5Min', iso(o), iso(o + 14 * 60e3), 400); const cands = [];
    for (const s of el) { const a = (ob[s] || []).filter((b) => Date.parse(b.t) - o < 15 * 60e3); if (!a.length || Date.parse(a[0].t) !== o) continue;
      const h = (fv[s] ||= []), avg = h.length >= 14 ? h.reduce((x, y) => x + y, 0) / h.length : 0; h.push(a[0].v); if (h.length > 14) h.shift();
      if (d < start || !avg || a[0].o <= 5) continue; const rv = a[0].v / avg, gap = a[0].o / info[d][s].pc - 1;
      if (rv >= 1 && Math.abs(gap) >= 0.02) cands.push({ s, rv, gap, atr: info[d][s].atr, ob: a }); }
    if (d < start) continue; td++; nc += cands.length;
    const picks = pickLists(cands);
    const m1 = picks.length ? await api.bars(picks.map((p) => p.s), '1Min', iso(o), iso(o + 389 * 60e3), 50) : {};
    for (const p of picks) p.m = (m1[p.s] || []).map((b) => ({ m: et(b.t).m, o: b.o, h: b.h, l: b.l, c: b.c }));
    const dr = dayResults(picks); dates.push(d);
    for (const [k, [r, n, w, R]] of Object.entries(dr)) { const x = res[k]; x.r.push(+r.toFixed(6)); x.n += n; x.w += w; x.R += R; }
    if (td % 20 === 1) log(d, 'eligible', el.length, 'gappers', cands.length, 'picks', picks.length, 'reqs', api.reqs);
  }
  const spy = (daily.SPY || []).map((b) => [et(b.t).d, b.c]).filter(([d]) => d >= start);
  mkdirSync(outDir, { recursive: true }); const f = `${outDir}/gap_${year}.json`;
  writeFileSync(f, JSON.stringify({ year: +year, universe: syms.length, days: td, avg_gappers: td ? Math.round(nc / td) : 0, reqs: api.reqs, dates, spy, combos: res }));
  log('wrote', f, 'days', td, 'reqs', api.reqs); return f;
}
const PER = { pre: (d) => d <= '2020-12-31', is: (d) => d > '2020-12-31' && d <= '2024-12-31', oos: (d) => d > '2024-12-31' };
const median = (a) => { const s = a.filter((x) => x != null).sort((x, y) => x - y); return s.length ? s[Math.floor(s.length / 2)] : null; };
export function merge(inDir, outDir, log = console.log) {
  const ch = readdirSync(inDir).filter((f) => /^gap_\d{4}\.json$/.test(f)).sort().map((f) => JSON.parse(readFileSync(`${inDir}/${f}`, 'utf8'))).sort((a, b) => a.year - b.year);
  const spyC = ch.flatMap((c) => c.spy), spyR = spyC.slice(1).map(([d, c], i) => [d, c / spyC[i][1] - 1]);
  const spy = Object.fromEntries(Object.entries(PER).map(([k, f]) => [k, stats(spyR.filter(([d]) => f(d)))]));
  const yearsOf = (r) => { const y = {}; for (const [d, x] of r) (y[d.slice(0, 4)] ||= []).push(x); return Object.fromEntries(Object.entries(y).map(([k, a]) => [k, +((a.reduce((e, x) => e * (1 + x), 1) - 1) * 100).toFixed(1)])); };
  const rows = COMBOS.map((c) => {
    const r = ch.flatMap((x) => x.dates.map((d, i) => [d, x.combos[c.key].r[i]]));
    const row = { key: c.key, c, all: stats(r) };
    for (const [k, f] of Object.entries(PER)) { const s = stats(r.filter(([d]) => f(d))); const cs = ch.filter((x) => f(`${x.year}-06-30`)); const n = cs.reduce((a, x) => a + x.combos[c.key].n, 0), w = cs.reduce((a, x) => a + x.combos[c.key].w, 0), R = cs.reduce((a, x) => a + x.combos[c.key].R, 0);
      row[k] = s ? { ...s, trades: n, win_rate: n ? +(100 * w / n).toFixed(1) : null, avg_R: n ? +(R / n).toFixed(3) : null } : null; }
    row.beats = Object.keys(PER).filter((k) => row[k] && spy[k] && row[k].cagr > spy[k].cagr);
    if (c.key === REF) row.yearly = yearsOf(r);
    return row;
  });
  const ref = rows.find((x) => x.key === REF), pers = Object.keys(PER).filter((k) => spy[k]);
  const share = Object.fromEntries(pers.map((k) => [k, +(100 * rows.filter((x) => x.beats.includes(k)).length / rows.length).toFixed(1)]));
  share.all_periods = +(100 * rows.filter((x) => pers.every((k) => x.beats.includes(k))).length / rows.length).toFixed(1);
  const dims = { o: ORS, s: STOPS, t: TOPS, g: TGTS, p: GAPS, d: DIRS, sl: SLIPS }, sens = {};
  for (const [dim, vals] of Object.entries(dims)) sens[dim] = vals.map((v) => { const rs = rows.filter((x) => x.c[dim] === v && (dim === 'sl' || x.c.sl === 0.01));
    return { value: v, ...Object.fromEntries(pers.map((k) => [`median_cagr_${k}`, median(rs.map((x) => x[k]?.cagr))])) }; });
  const robust = rows.filter((x) => x.c.sl === 0.01 && pers.every((k) => x[k])).map((x) => ({ x, m: Math.min(...pers.map((k) => x[k].sharpe)) })).sort((a, b) => b.m - a.m).slice(0, 15).map(({ x }) => x);
  const out = { generated: new Date().toISOString(), years: ch.map((c) => c.year), avg_gappers: ch.map((c) => c.avg_gappers), notes: ['pre = 2017-2020 never seen; is = 2021-2024 (where reference was chosen); oos = 2025-2026.', 'Survivorship bias: currently active stocks only.', 'Conservative fills.'], spy, reference: ref, pct_combos_beating_spy: share, sensitivity: sens, robust_top15: robust.map(({ c, ...x }) => x), all: rows.map(({ c, ...x }) => x) };
  log('SPY', JSON.stringify(spy)); log('REF', JSON.stringify({ pre: ref.pre, is: ref.is, oos: ref.oos, yearly: ref.yearly }));
  log('slip 5c version', JSON.stringify(rows.find((x) => x.key === REF.replace('slip0.01', 'slip0.05'))?.pre));
  log('% combos beating SPY', JSON.stringify(share)); log('sensitivity', JSON.stringify(sens));
  for (const x of robust) log(x.key.padEnd(38), pers.map((k) => `${k} ${x[k].cagr}% sh ${x[k].sharpe} dd ${x[k].max_dd}`).join(' | '));
  mkdirSync(outDir, { recursive: true }); writeFileSync(`${outDir}/orb_gappers_summary.json`, JSON.stringify(out)); return out;
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const [cmd, a, b] = process.argv.slice(2);
  (cmd === 'chunk' ? runChunk(a, b || 'out') : Promise.resolve(merge(a, b || 'data'))).catch((e) => { console.error(e); process.exit(1); });
}
