// Earnings drift, point-in-time S&P 500 (fixes survivorship bias). Research only, no orders.
// Membership rebuilt from Wikipedia "Selected changes" table, walking back from today's list.
// Universes: A current_only (old test), B current_pit (current names, only while members),
// C full_pit (B + companies removed since 2016 that we can find: SEC CIK by name + Alpaca prices).
import { writeFileSync, readFileSync, mkdirSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { stats } from './orb-research.mjs';
import { taxGrid, simTax } from './tax-sim.mjs';
import { COMBOS, PER, THRS, reactionIndex, simulate, getJson, daily, events8k } from './earnings-drift.mjs';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const MON = { january: 1, february: 2, march: 3, april: 4, may: 5, june: 6, july: 7, august: 8, september: 9, october: 10, november: 11, december: 12 };
export function parseDate(s) { const m = /([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})/.exec(s || ''); if (!m || !MON[m[1].toLowerCase()]) return null; return `${m[3]}-${String(MON[m[1].toLowerCase()]).padStart(2, '0')}-${m[2].padStart(2, '0')}`; }
const clean = (h) => h.replace(/<sup[\s\S]*?<\/sup>/g, '').replace(/<[^>]+>/g, '').replace(/&amp;/g, '&').replace(/&#160;|&nbsp;/g, ' ').replace(/&#39;/g, "'").replace(/\s+/g, ' ').trim();
// Generic wikitable parser with rowspan/colspan. Returns rows of cell strings (header rows included).
export function parseTable(html, id) {
  let st = html.indexOf(`id="${id}"`);
  if (st < 0 && id === 'changes') { const h = html.search(/id="Selected_changes|Selected changes/i); if (h >= 0) st = html.indexOf('<table', h); }
  if (st < 0 && id === 'changes') { const all = [...html.matchAll(/<table[^>]*wikitable/g)]; if (all[1]) st = all[1].index; }
  if (st < 0 && id === 'constituents') { const all = [...html.matchAll(/<table[^>]*wikitable/g)]; if (all[0]) st = all[0].index; }
  if (st < 0) throw new Error(`table ${id} not found; ids: ${[...html.matchAll(/<table[^>]*id="([^"]+)"/g)].map((m) => m[1]).join(',')}; len ${html.length}`);
  const body = html.slice(st, html.indexOf('</table>', st)), rows = [], carry = [];
  for (const tr of body.split(/<tr[^>]*>/).slice(1)) {
    const cells = [...tr.matchAll(/<(td|th)(\s[^>]*)?>([\s\S]*?)(?=<\/t[dh]>|<t[dh][\s>]|$)/g)].map((m) => ({ txt: clean(m[3]), rs: +(/rowspan="?(\d+)/.exec(m[2] || '')?.[1] || 1), cs: +(/colspan="?(\d+)/.exec(m[2] || '')?.[1] || 1), th: m[1] === 'th' }));
    const row = []; let ci = 0, col = 0;
    const fill = () => { while (carry[col] && carry[col].n > 0) { row[col] = carry[col].txt; carry[col].n--; col++; } };
    fill();
    while (ci < cells.length) { const c = cells[ci++]; for (let k = 0; k < c.cs; k++) { row[col] = c.txt; if (c.rs > 1) carry[col] = { txt: c.txt, n: c.rs - 1 }; col++; } fill(); }
    if (row.length) rows.push(row);
  }
  return rows;
}
export function parseChanges(rows) {
  const out = [];
  for (const r of rows) { const date = parseDate(r[0]); if (!date || r.length < 5) continue;
    out.push({ date, addT: (r[1] || '').toUpperCase(), addN: r[2] || '', remT: (r[3] || '').toUpperCase(), remN: r[4] || '' }); }
  return out.sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0));
}
// current: [{symbol, name, cik}] -> members: [{id, symbol, name, cik, start, end, removed}]
export function membership(current, changes, since = '2016-01-01') {
  const active = new Map(), done = [];
  for (const c of current) active.set(c.symbol, { ...c, end: '9999-12-31', removed: false });
  for (const ch of changes) {
    if (ch.date < since) break;
    if (ch.addT && active.has(ch.addT)) { const m = active.get(ch.addT); done.push({ ...m, start: ch.date }); active.delete(ch.addT); }
    if (ch.remT) active.set(ch.remT, { symbol: ch.remT, name: ch.remN, cik: null, end: ch.date, removed: true });
  }
  for (const m of active.values()) done.push({ ...m, start: '0000-01-01' });
  return done.map((m, i) => ({ id: m.removed ? `${m.symbol}#r${i}` : m.symbol, ...m }));
}
const SUF = new Set(['INC', 'INCORPORATED', 'CORP', 'CORPORATION', 'CO', 'COMPANY', 'COMPANIES', 'LTD', 'LIMITED', 'PLC', 'LLC', 'LP', 'HOLDINGS', 'HOLDING', 'GROUP', 'THE', 'NV', 'SA', 'AG', 'SE', 'TRUST', 'BANCORP', 'CLASS', 'A', 'B', 'C', 'DE', 'NEW', 'INTERNATIONAL', 'INTL']);
export const norm = (s) => (s || '').toUpperCase().replace(/&/g, ' AND ').replace(/\(.*?\)/g, ' ').replace(/[^A-Z0-9 ]/g, ' ').split(/\s+/).filter((w) => w && !SUF.has(w)).join(' ');

// signals for a set of members; ev: cik -> events; R/Hh/L raw arrays keyed by member id; C forward-filled closes.
export function buildSignals(members, ev, dates, R, Hh, L, C, pit) {
  const signals = []; let n = 0;
  for (const m of members) {
    const e = ev[m.cik]; if (!e || !R[m.id]) continue; const seen = new Set();
    for (const x of e) {
      const k = reactionIndex(dates, x.day, x.min); if (k < 1 || k + 1 >= dates.length || seen.has(k)) continue; seen.add(k);
      if (pit && !(dates[k] >= m.start && dates[k] < m.end)) continue;
      const c0 = R[m.id][k], c1 = R[m.id][k - 1]; if (!c0 || !c1 || c0 < 5) continue;
      const r = c0 / c1 - 1 - (C.SPY[k] / C.SPY[k - 1] - 1); if (r < THRS[0]) continue; n++;
      const h = Hh[m.id][k], l = L[m.id][k]; (signals[k + 1] ||= []).push({ s: m.id, r, strong: h > l ? (c0 - l) / (h - l) >= 0.5 : false });
    }
  }
  for (const x of signals) if (x) x.sort((a, b) => b.r - a.r);
  return { signals, n };
}
export function evaluate(dates, O, C, signals, t0, REF) {
  const toR = (cv) => cv.slice(1).map(([d, e], i) => [d, e / cv[i][1] - 1]), P = Object.keys(PER);
  const spyR = toR(dates.slice(t0).map((d, i) => [d, C.SPY[t0 + i]]));
  const spy = Object.fromEntries(Object.entries(PER).map(([k, f]) => [k, stats(spyR.filter(([d]) => f(d)))])); spy.all = stats(spyR);
  let refLog = null;
  const rows = COMBOS.map((c) => {
    const log = c.key === REF ? [] : null, r = simulate(dates, O, C, signals, c, t0, log), rr = toR(r.curve); if (log) refLog = log;
    const row = { key: c.key, trades: r.trades, win_rate: +(100 * r.wins / Math.max(r.trades, 1)).toFixed(1), avg_trade_pct: +(100 * r.sumR / Math.max(r.trades, 1)).toFixed(2), all: stats(rr) };
    for (const [k, f] of Object.entries(PER)) row[k] = stats(rr.filter(([d]) => f(d)));
    row.beats = P.filter((k) => row[k] && row[k].cagr > spy[k].cagr); return row;
  });
  const pct = Object.fromEntries(P.map((k) => [k, +(100 * rows.filter((x) => x.beats.includes(k)).length / rows.length).toFixed(1)]));
  pct.every_period = +(100 * rows.filter((x) => x.beats.length === P.length).length / rows.length).toFixed(1);
  pct.full_period = +(100 * rows.filter((x) => x.all && x.all.cagr > spy.all.cagr).length / rows.length).toFixed(1);
  const best = [...rows].sort((a, b) => b.all.cagr - a.all.cagr).slice(0, 8);
  let conc = null;
  if (refLog?.length) { const tot = refLog.reduce((a, x) => a + x.pnl, 0), top = [...refLog].sort((a, b) => b.pnl - a.pnl);
    conc = { trades: refLog.length, top10_share_of_profit_pct: +(100 * top.slice(0, 10).reduce((a, x) => a + x.pnl, 0) / tot).toFixed(1), top10: top.slice(0, 10).map(({ s, d, ret }) => ({ s, d, ret })) }; }
  return { spy, pct_beating_spy: pct, ref: rows.find((x) => x.key === REF), best, concentration: conc, all: rows };
}

async function main(out = 'data') {
  const ua = process.env.SEC_USER_AGENT; if (!ua) throw new Error('SEC_USER_AGENT missing');
  const IDX = process.env.INDEX || 'sp500', TITLE = IDX === 'sp400' ? 'List_of_S%26P_400_companies' : 'List_of_S%26P_500_companies';
  const REF = process.env.REF || (IDX === 'sp400' ? 'thr5|hold60|n10|any' : 'thr8|hold60|n10|any'), H = { 'User-Agent': ua };
  const WUA = { 'User-Agent': `sec-edgar-worker earnings-drift/1.0 (${ua})` }, W = 'https://en.wikipedia.org';
  const page = async (q) => { const r = await fetch(`${W}/w/index.php?title=${TITLE}${q}`, { headers: WUA }); return r.text(); };
  const curHtml = await page('');
  const tryChanges = (h) => { try { const c = parseChanges(parseTable(h, 'changes')); return c.length >= 100 ? c : null; } catch { return null; } };
  let changes = tryChanges(curHtml), revDate = 'current';
  if (!changes) {
    const rv = await (await fetch(`${W}/w/api.php?action=query&prop=revisions&titles=${TITLE}&rvprop=ids|timestamp&rvlimit=500&format=json`, { headers: WUA })).json();
    const revs = Object.values(rv.query.pages)[0].revisions;
    for (const back of [20, 45, 90, 150, 240, 365, 540, 730]) {
      const cut = new Date(Date.now() - back * 86400e3).toISOString(), r = revs.find((x) => x.timestamp <= cut); if (!r) break;
      changes = tryChanges(await page(`&oldid=${r.revid}`)); if (changes) { revDate = r.timestamp.slice(0, 10); break; } await sleep(500);
    }
  }
  if (!changes) throw new Error('no changes table in current page or older revisions; headings: ' + [...curHtml.matchAll(/<h2[^>]*id="([^"]+)"/g)].map((m) => m[1]).join(','));
  // gap fill: current members added after the revision, from "Date added" in today's constituents table
  let gap = 0;
  if (revDate !== 'current') try {
    const rows = parseTable(curHtml, 'constituents'), hdr = rows[0].map((x) => x.toLowerCase()), iS = hdr.findIndex((x) => x.startsWith('symbol')), iD = hdr.findIndex((x) => x.includes('date added'));
    const have = new Set(changes.map((c) => c.addT));
    for (const r of rows.slice(1)) { const d = /^\d{4}-\d{2}-\d{2}/.exec(r[iD] || '')?.[0] || parseDate(r[iD]); if (d && d > revDate && !have.has((r[iS] || '').toUpperCase())) { changes.push({ date: d, addT: r[iS].toUpperCase(), addN: '', remT: '', remN: '' }); gap++; } }
    changes.sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0));
  } catch (e) { console.log('gap fill skipped', e.message); }
  console.log('changes', changes.length, 'from', revDate, 'gap-filled additions', gap);
  let current;
  if (IDX === 'sp500') current = JSON.parse(readFileSync('data/sp500_tickers.json', 'utf8')).tickers;
  else {
    const tk0 = await getJson('https://www.sec.gov/files/company_tickers.json', H), ck = {};
    for (const v of Object.values(tk0 || {})) ck[v.ticker.replace('-', '.')] = v.cik_str;
    const rows = parseTable(curHtml, 'constituents'), hdr = rows[0].map((x) => x.toLowerCase());
    const iS = hdr.findIndex((x) => /^(symbol|ticker)/.test(x)), iN = hdr.findIndex((x) => /^(security|company)/.test(x));
    current = rows.slice(1).map((r) => ({ symbol: (r[iS] || '').toUpperCase(), name: r[iN] || '', cik: ck[(r[iS] || '').toUpperCase()] || null })).filter((t) => /^[A-Z.]{1,6}$/.test(t.symbol));
    console.log(IDX, 'constituents', current.length, 'with cik', current.filter((t) => t.cik).length);
    if (current.length < 300) throw new Error(`only ${current.length} ${IDX} constituents parsed`);
    current = current.filter((t) => t.cik);
  }
  const members = membership(current, changes);
  const removed = members.filter((m) => m.removed);
  console.log('changes', changes.length, 'since 2016', changes.filter((c) => c.date >= '2016-01-01').length, 'removed members', removed.length);
  // CIKs for removed: SEC name list + ticker list
  const want = new Map(removed.map((m) => [norm(m.name), []]));
  const lk = await (await fetch('https://www.sec.gov/Archives/edgar/cik-lookup-data.txt', { headers: H })).text();
  for (const line of lk.split('\n')) { const i = line.lastIndexOf(':', line.length - 2); if (i < 0) continue; const k = norm(line.slice(0, i)); if (want.has(k)) { const c = +line.slice(i + 1).replace(/:/g, ''); const a = want.get(k); if (c && !a.includes(c) && a.length < 6) a.push(c); } }
  const tk = await getJson('https://www.sec.gov/files/company_tickers.json', H);
  const byT = {}; for (const v of Object.values(tk || {})) byT[v.ticker.replace('-', '.')] = { cik: v.cik_str, name: v.title };
  const evCache = {};
  const evOf = async (cik) => { if (!(cik in evCache)) { try { evCache[cik] = await events8k(cik, ua); } catch { evCache[cik] = []; } await sleep(120); } return evCache[cik]; };
  const cov = { removed: removed.length, cik: 0, events: 0, prices: 0, used: 0, missing: [] };
  for (const m of removed) {
    const cands = [...(want.get(norm(m.name)) || [])]; const t = byT[m.symbol];
    if (t && norm(t.name).split(' ')[0] === norm(m.name).split(' ')[0] && !cands.includes(t.cik)) cands.push(t.cik);
    let best = null, bn = 0;
    for (const c of cands.slice(0, 6)) { const e = await evOf(c), n = e.filter((x) => x.day >= m.start && x.day < m.end).length; if (n > bn) { bn = n; best = c; } }
    if (cands.length) cov.cik++; if (best && bn >= 2) { m.cik = best; cov.events++; } else cov.missing.push(`${m.symbol} ${m.name} (${cands.length ? 'no earnings 8-Ks' : 'no CIK'})`);
  }
  for (const m of members.filter((x) => !x.removed)) await evOf(m.cik);
  // prices
  const bars = await daily([...new Set([...current.map((t) => t.symbol), 'SPY'])], '2016-01-01T00:00:00Z', new Date(Date.now() - 3600e3).toISOString());
  const rbars = await daily([...new Set(removed.filter((m) => m.cik).map((m) => m.symbol))], '2016-01-01T00:00:00Z', new Date(Date.now() - 3600e3).toISOString());
  const dates = bars.SPY.map((b) => b.t.slice(0, 10)), idx = Object.fromEntries(dates.map((d, i) => [d, i])), N = dates.length;
  const O = {}, C = {}, R = {}, Hh = {}, L = {};
  const load = (id, a, lo = '0000', hi = '9999') => { if (!a) return 0; const o = Array(N).fill(null), c = Array(N).fill(null), h = Array(N).fill(null), l = Array(N).fill(null); let k = 0;
    for (const b of a) { const d = b.t.slice(0, 10), i = idx[d]; if (i == null || d < lo || d > hi) continue; o[i] = b.o; c[i] = b.c; h[i] = b.h; l[i] = b.l; k++; }
    R[id] = [...c]; for (let i = 1; i < N; i++) if (c[i] == null) c[i] = c[i - 1]; O[id] = o; C[id] = c; Hh[id] = h; L[id] = l; return k; };
  for (const s of Object.keys(bars)) load(s, bars[s]);
  const curSet = new Set(current.map((t) => t.symbol));
  for (const m of removed.filter((x) => x.cik)) {
    if (curSet.has(m.symbol)) { cov.missing.push(`${m.symbol} ${m.name} (ticker now used by a current member)`); m.cik = null; continue; }
    const lo = new Date(Date.parse(m.start === '0000-01-01' ? '2016-01-01' : m.start) - 30 * 86400e3).toISOString().slice(0, 10), hi = new Date(Date.parse(m.end) + 120 * 86400e3).toISOString().slice(0, 10);
    const k = load(m.id, rbars[m.symbol], lo, hi), need = dates.filter((d) => d >= (m.start === '0000-01-01' ? '2016-01-04' : m.start) && d < m.end).length;
    if (k >= 0.8 * need && need > 0) cov.prices++; else { cov.missing.push(`${m.symbol} ${m.name} (prices ${k}/${need})`); m.cik = null; delete R[m.id]; }
  }
  const t0 = dates.findIndex((d) => d >= '2016-07-01'), curM = members.filter((m) => !m.removed);
  const A = buildSignals(curM, evCache, dates, R, Hh, L, C, false), B = buildSignals(curM, evCache, dates, R, Hh, L, C, true), Cc = buildSignals(members, evCache, dates, R, Hh, L, C, true);
  cov.used = removed.filter((m) => m.cik && R[m.id]).length;
  const res = { generated: new Date().toISOString(), index: IDX, ref: REF, changes_source: revDate, gap_filled_additions: gap, coverage: cov, signals: { current_only: A.n, current_pit: B.n, full_pit: Cc.n }, universes: {} };
  for (const [k, S] of [['current_only', A], ['current_pit', B], ['full_pit', Cc]]) res.universes[k] = evaluate(dates, O, C, S.signals, t0, REF);
  // After-tax + idle cash (rule: 5% jump, hold 60, 10 slots). Short-term rates tested; SPY buy-and-hold taxed 15% long-term once at the end.
  res.after_tax = { rule: 'thr5|hold60|n10|any', universe: 'full_pit', benchmark: 'SPY buy and hold, 15% long-term tax on the gain at the end', note: 'Federal only (Texas has no state income tax). Gains netted yearly, losses carried forward. Dividend taxes ignored for both.',
    rows: taxGrid({ dates, O, C, B: C.SPY, signals: Cc.signals, th: 0.05, h: 60, n: 10, t0 }, [0, 0.12, 0.22, 0.24, 0.32], 0.15) };
  for (const r of res.after_tax.rows) console.log('after-tax', JSON.stringify(r));
  // Robustness: neighbours of the chosen rule. Success = all (or nearly all) beat SPY in every period.
  const toR2 = (cv) => cv.slice(1).map(([d, e], i) => [d, e / cv[i][1] - 1]);
  const spyR2 = toR2(dates.slice(t0).map((d, i) => [d, C.SPY[t0 + i]]));
  const spyP = Object.fromEntries(Object.entries(PER).map(([k, f]) => [k, stats(spyR2.filter(([d]) => f(d))).cagr])); spyP.all = stats(spyR2).cagr;
  const rob = [];
  for (const th of [0.04, 0.05, 0.06]) for (const h of [50, 60, 70]) {
    const sim = simulate(dates, O, C, Cc.signals, { key: `thr${th * 100}|hold${h}|n10|any`, th, h, n: 10, cl: 'any' }, t0), rr = toR2(sim.curve);
    const row = { thr: th * 100, hold: h, all: stats(rr).cagr, maxDD: stats(rr).max_dd, trades: sim.trades };
    for (const [k, f] of Object.entries(PER)) row[k] = stats(rr.filter(([d]) => f(d))).cagr;
    row.beatsEveryPeriod = Object.keys(PER).every((k) => row[k] > spyP[k]);
    const at = simTax({ dates, O, C, B: C.SPY, signals: Cc.signals, th, h, n: 10, t0, rate: 0.24, park: true, ltRate: 0.15 });
    row.afterTax24Park = at.cagr; row.spyAfterTax = at.benchCagr; row.beatsAfterTax = at.cagr > at.benchCagr;
    rob.push(row); console.log('robust', JSON.stringify(row));
  }
  res.robustness = { spy: spyP, universe: 'full_pit', rows: rob, beatEveryPeriod: rob.filter((r) => r.beatsEveryPeriod).length, beatAfterTax: rob.filter((r) => r.beatsAfterTax).length, of: rob.length };
  mkdirSync(out, { recursive: true }); writeFileSync(`${out}/earnings_drift_pit${IDX === 'sp500' ? '' : '_' + IDX}.json`, JSON.stringify(res, null, 1));
  console.log('coverage', JSON.stringify({ ...cov, missing: cov.missing.length }), 'signals', JSON.stringify(res.signals));
  for (const [k, u] of Object.entries(res.universes)) { const r = u.ref; console.log(`\n== ${k} SPY ${u.spy.all.cagr}%  REF all ${r.all.cagr}% dd ${r.all.max_dd} | ${Object.keys(PER).map((p) => `${p} ${r[p].cagr}`).join(' | ')} | %beat ${JSON.stringify(u.pct_beating_spy)} | top10 share ${u.concentration?.top10_share_of_profit_pct}`); }
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main(process.argv[2] || 'data').catch((e) => { console.error(e); try { mkdirSync(process.argv[2] || 'data', { recursive: true }); writeFileSync(`${process.argv[2] || 'data'}/earnings_drift_pit_error.txt`, String(e.stack || e)); } catch {} process.exit(1); });
