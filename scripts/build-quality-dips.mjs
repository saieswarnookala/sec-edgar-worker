// "Quality dips" backtest: buy short-term dips (RSI(2) < 10 above the 200-day SMA) in S&P 500 stocks,
// once restricted to point-in-time "quality" companies (SEC 10-K data) and once on the whole index.
// No orders, ever — research only.
//
// Data:
//   - Universe: current S&P 500 constituents scraped from Wikipedia -> data/sp500_tickers.json
//     (survivorship bias: today's members are tested back to 2016).
//   - Prices: Alpaca daily bars 2016-01-01 -> now-1h, adjustment=all, SIP feed (IEX if SIP is refused).
//   - Fundamentals: SEC XBRL companyfacts, only 10-K values filed before Jan 1 of each test year.
// Output: data/quality_dips.json (+ data/quality_dips_error.txt on failure).
// Usage: APCA_API_KEY_ID=.. APCA_API_SECRET_KEY=.. SEC_USER_AGENT="Name email" node scripts/build-quality-dips.mjs [outDir=data]
//
// Note: the Alpaca fetcher in build-strategies.mjs is not exported (and rejects a whole request if any
// symbol has < 300 days), so a batched version lives here; the stats helpers are reused from there.

import { writeFileSync, mkdirSync, readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { curveStats, yearly, START } from './build-strategies.mjs';

export const COST = 0.0002;   // 0.02% per side
export const MAX_POS = 5;
export const WEIGHT = 0.2;
export const MAX_HOLD = 10;   // trading days
export const ROE_TOP = 0.4;   // top 40% by ROE
const DAY = 86400000;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const pct = (x) => (x == null || !Number.isFinite(x) ? null : Math.round(x * 10000) / 100);

// ---------------- universe (Wikipedia) ----------------
const decode = (s) => s.replace(/&amp;/g, '&').replace(/&#39;|&#039;/g, "'").replace(/&quot;/g, '"').replace(/&nbsp;|&#160;/g, ' ').replace(/&lt;/g, '<').replace(/&gt;/g, '>');
const cellText = (h) => decode(h.replace(/<sup[\s\S]*?<\/sup>/gi, '').replace(/<[^>]+>/g, '')).replace(/\s+/g, ' ').trim();

// Parses the id="constituents" table into [{symbol, name, sector, cik}].
export function parseSp500Html(html) {
  const at = html.search(/<table[^>]*id="constituents"/i);
  if (at < 0) throw new Error('Wikipedia: constituents table not found');
  const table = html.slice(at, html.indexOf('</table>', at));
  const rows = table.split(/<tr[\s>]/i).slice(1).map((r) => [...r.matchAll(/<(t[hd])[^>]*>([\s\S]*?)(?=<t[hd][\s>]|<\/tr>|$)/gi)].map((m) => ({ tag: m[1].toLowerCase(), text: cellText(m[2]) })));
  const head = rows.find((r) => r.length && r.every((c) => c.tag === 'th'));
  if (!head) throw new Error('Wikipedia: header row not found');
  const col = (re) => head.findIndex((c) => re.test(c.text));
  const iSym = col(/^symbol|^ticker/i), iName = col(/^security|^company/i), iSec = col(/gics sector/i), iCik = col(/^cik/i);
  if (iSym < 0) throw new Error('Wikipedia: Symbol column not found');
  const out = [];
  for (const r of rows) {
    if (r === head || r.length <= iSym || r[iSym].tag === 'th') continue;
    const symbol = r[iSym].text.toUpperCase();
    if (!/^[A-Z][A-Z0-9.\-]{0,9}$/.test(symbol)) continue;
    out.push({ symbol, name: r[iName]?.text || '', sector: r[iSec]?.text || '', cik: iCik >= 0 && /^\d+$/.test(r[iCik]?.text || '') ? Number(r[iCik].text) : null });
  }
  if (out.length < 400) throw new Error(`Wikipedia: only ${out.length} tickers parsed`);
  return [...new Map(out.map((t) => [t.symbol, t])).values()];
}

// ---------------- prices (Alpaca) ----------------
// Returns { bars: {SYM: [{d, o, c}]}, feed, failed: [{symbol, error}] }. A failing batch is retried
// symbol by symbol; symbols that still fail are skipped and listed. Multi-symbol requests, paginated, ~170 req/min max.
export async function alpacaDaily(symbols, { env = process.env, fetchFn = fetch, start = START, endTs, batch = 100, pauseMs = 350, log = console.log } = {}) {
  endTs = endTs || new Date(Date.now() - 3600e3).toISOString();
  const headers = { 'APCA-API-KEY-ID': env.APCA_API_KEY_ID, 'APCA-API-SECRET-KEY': env.APCA_API_SECRET_KEY };
  let feed = env.APCA_FEED || 'sip';
  const bars = Object.fromEntries(symbols.map((s) => [s, []]));
  const get = async (p) => {
    for (let a = 0; ; a++) {
      const r = await fetchFn('https://data.alpaca.markets/v2/stocks/bars?' + p, { headers });
      if (r.ok) return r.json();
      const body = (await r.text()).slice(0, 300);
      if (r.status === 403 && feed === 'sip' && /sip|subscription/i.test(body)) { const e = new Error(body); e.sipRefused = true; throw e; }
      if ((r.status === 429 || r.status >= 500) && a < 6) { await sleep((Number(r.headers?.get?.('retry-after')) || 2 ** a * 2) * 1000); continue; }
      throw new Error(`Alpaca HTTP ${r.status}: ${body}`);
    }
  };
  const fetchChunk = async (chunk) => {
    const p = new URLSearchParams({ symbols: chunk.join(','), timeframe: '1Day', start, end: endTs, limit: '10000', adjustment: 'all', feed });
    const got = Object.fromEntries(chunk.map((s) => [s, []]));
    for (;;) {
      const js = await get(p);
      for (const [s, bl] of Object.entries(js.bars || {})) for (const b of bl) (got[s] ||= []).push({ d: b.t.slice(0, 10), o: b.o, c: b.c });
      await sleep(pauseMs);
      if (!js.next_page_token) break;
      p.set('page_token', js.next_page_token);
    }
    for (const s of chunk) bars[s] = got[s].sort((a, b) => (a.d < b.d ? -1 : 1));
  };
  let failed = [];
  for (let i = 0; i < symbols.length; i += batch) {
    const chunk = symbols.slice(i, i + batch);
    try { await fetchChunk(chunk); }
    catch (e) {
      if (e.sipRefused) {
        log(`Alpaca refused SIP (${e.message.slice(0, 120)}); switching to feed=iex`);
        feed = 'iex'; failed = [];
        for (const s of symbols) bars[s] = [];
        i = -batch; // restart from the first batch with the IEX feed
        continue;
      }
      log(`bars batch ${i}-${i + chunk.length} failed (${String(e.message).slice(0, 120)}); retrying one by one`);
      for (const s of chunk) {
        try { await fetchChunk([s]); }
        catch (e2) { if (e2.sipRefused) throw e2; bars[s] = []; failed.push({ symbol: s, error: String(e2.message).slice(0, 200) }); log(`bars SKIP ${s}: ${String(e2.message).slice(0, 120)}`); }
      }
    }
    log(`bars ${Math.min(i + batch, symbols.length)}/${symbols.length} (feed=${feed})`);
  }
  return { bars, feed, failed };
}

// ---------------- fundamentals (SEC companyfacts) ----------------
const TAGS = {
  ni: ['NetIncomeLoss', 'ProfitLoss'],
  eq: ['StockholdersEquity', 'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest'],
  ltd: ['LongTermDebt'],
  ltdNon: ['LongTermDebtNoncurrent'],
  ltdc: ['LongTermDebtCurrent'],
};
// Keeps only annual 10-K USD facts for the tags above: {key: [[tagRank, start|null, end, val, filed]]}.
export function extractFacts(companyfacts) {
  const g = companyfacts?.facts?.['us-gaap'] || {};
  const out = {};
  for (const [key, tags] of Object.entries(TAGS)) {
    out[key] = [];
    tags.forEach((tag, rank) => {
      for (const f of g[tag]?.units?.USD || []) {
        if (!/^10-K/.test(f.form || '') || f.fp !== 'FY' || !f.end || !f.filed || !Number.isFinite(f.val)) continue;
        out[key].push([rank, f.start || null, f.end, f.val, f.filed]);
      }
    });
  }
  return out;
}

// value per period end known before `cutoff` (latest filing wins, preferred tag wins)
function asOf(rows, cutoff, annual) {
  const m = new Map();
  for (const [rank, start, end, val, filed] of rows) {
    if (filed >= cutoff) continue;
    if (annual) { if (!start) continue; const dur = (Date.parse(end) - Date.parse(start)) / DAY; if (dur < 340 || dur > 380) continue; }
    const cur = m.get(end);
    if (!cur || rank < cur.rank || (rank === cur.rank && filed > cur.filed)) m.set(end, { rank, val, filed });
  }
  return m;
}
const near = (m, end, days = 7) => {
  if (m.has(end)) return m.get(end).val;
  const t = Date.parse(end);
  for (const [e, v] of m) if (Math.abs(Date.parse(e) - t) <= days * DAY) return v.val;
  return null;
};

// Point-in-time inputs for test year `year` (only 10-Ks filed before Jan 1 of that year).
export function qualityInputs(facts, year) {
  const cutoff = `${year}-01-01`;
  const ni = asOf(facts.ni, cutoff, true);
  const fy = [];
  for (const end of [...ni.keys()].sort().reverse()) if (!fy.length || Date.parse(fy.at(-1)) - Date.parse(end) > 300 * DAY) fy.push(end);
  if (!fy.length) return { reason: 'no annual net income' };
  const last = fy[0];
  if (Date.parse(cutoff) - Date.parse(last) > 550 * DAY) return { reason: 'stale 10-K', fy_end: last };
  const nis = fy.slice(0, 3).map((e) => ni.get(e).val);
  const eq = near(asOf(facts.eq, cutoff, false), last);
  const ltd = near(asOf(facts.ltd, cutoff, false), last) ?? near(asOf(facts.ltdNon, cutoff, false), last);
  const ltdc = near(asOf(facts.ltdc, cutoff, false), last);
  const debt = (ltd ?? 0) + (ltdc ?? 0);
  return {
    fy_end: last, ni: nis[0], eq,
    pos3: nis.length === 3 && nis.every((v) => v > 0),
    roe: eq ? nis[0] / eq : null,
    de: eq ? debt / eq : null,
    debt_missing: ltd == null && ltdc == null,
  };
}

// inputs: {SYM: qualityInputs(...)}; sectors: {SYM: 'Financials', ...}. Returns the year's quality set + stats.
export function rankQuality(inputs, sectors = {}) {
  const elig = Object.entries(inputs).filter(([, q]) => q.pos3 && q.eq > 0 && Number.isFinite(q.roe) && Number.isFinite(q.de));
  const byRoe = [...elig].sort((a, b) => b[1].roe - a[1].roe);
  const nTop = Math.ceil(ROE_TOP * elig.length);
  const top = new Set(byRoe.slice(0, nTop).map(([s]) => s));
  const des = elig.map(([, q]) => q.de).sort((a, b) => a - b);
  const median = des.length ? (des.length % 2 ? des[(des.length - 1) / 2] : (des[des.length / 2 - 1] + des[des.length / 2]) / 2) : null;
  const quality = elig.filter(([s, q]) => top.has(s) && q.de < median).map(([s]) => s).sort();
  const fin = (list) => list.filter((s) => /financ/i.test(sectors[s] || '')).length;
  return {
    quality,
    stats: {
      with_data: Object.values(inputs).filter((q) => q.fy_end && !q.reason).length,
      eligible: elig.length, quality: quality.length,
      roe_cutoff: nTop ? pct(byRoe[nTop - 1][1].roe) : null, de_median: median == null ? null : Math.round(median * 1000) / 1000,
      financials_eligible: fin(elig.map(([s]) => s)), financials_quality: fin(quality),
      debt_tag_missing_in_quality: quality.filter((s) => inputs[s].debt_missing).length,
    },
  };
}

// ---------------- indicators ----------------
export function indicators(rows) {
  const C = rows.map((r) => r.c), n = C.length;
  const sma = (k) => { const out = new Array(n).fill(null); let s = 0; for (let i = 0; i < n; i++) { s += C[i]; if (i >= k) s -= C[i - k]; if (i >= k - 1) out[i] = s / k; } return out; };
  // RSI(2): same 2-day average gain/loss formula as build-strategies.mjs
  const rsi = new Array(n).fill(null);
  for (let i = 2; i < n; i++) {
    let g = 0, l = 0;
    for (const k of [i - 1, i]) { const ch = C[k] - C[k - 1]; g += Math.max(ch, 0); l += Math.max(-ch, 0); }
    rsi[i] = l === 0 ? 100 : 100 - 100 / (1 + g / l);
  }
  return { sma200: sma(200), sma5: sma(5), rsi };
}

// ---------------- backtest ----------------
// bars: {SYM: [{d,o,c}]} ascending; cal: trading dates (SPY); bil: [{d,c}] for cash; allowed(sym, date) gate.
// Signals at the close of day t, orders fill at the open of the next day the symbol trades.
export function backtest({ bars, cal, bil, allowed = () => true, cost = COST, maxPos = MAX_POS, weight = WEIGHT, maxHold = MAX_HOLD }) {
  const syms = Object.keys(bars).filter((s) => bars[s]?.length);
  const S = {};
  for (const s of syms) S[s] = { rows: bars[s], idx: new Map(bars[s].map((r, i) => [r.d, i])), ...indicators(bars[s]) };
  const bilC = new Map((bil || []).map((r) => [r.d, r.c]));
  let cash = 1, prevBil = null, invSum = 0, daysIn = 0;
  const pos = [];       // {sym, shares, entryPx, entryD, entryI, last, exit}
  let orders = [];      // {sym, alloc}
  const trades = [], pts = [];
  for (const d of cal) {
    // 1) fills at the open: exits first, then entries
    for (let k = pos.length - 1; k >= 0; k--) {
      const p = pos[k]; if (!p.exit) continue;
      const i = S[p.sym].idx.get(d); if (i == null) continue;
      const px = S[p.sym].rows[i].o;
      cash += p.shares * px * (1 - cost);
      trades.push({ sym: p.sym, entry_d: p.entryD, exit_d: d, hold: i - p.entryI, ret: (px * (1 - cost)) / (p.entryPx * (1 + cost)) - 1 });
      pos.splice(k, 1);
    }
    for (const o of orders) {
      const i = S[o.sym].idx.get(d); if (i == null) continue;
      const amt = Math.min(o.alloc, cash); if (amt <= 0) continue;
      const px = S[o.sym].rows[i].o;
      pos.push({ sym: o.sym, shares: amt / (px * (1 + cost)), entryPx: px, entryD: d, entryI: i, last: px, exit: false });
      cash -= amt;
    }
    orders = [];
    // 2) idle cash earns BIL
    const b = bilC.get(d);
    if (b != null) { if (prevBil != null) cash *= b / prevBil; prevBil = b; }
    // 3) mark to market at the close
    let inv = 0;
    for (const p of pos) { const i = S[p.sym].idx.get(d); if (i != null) p.last = S[p.sym].rows[i].c; inv += p.shares * p.last; }
    const eq = cash + inv;
    pts.push({ d, eq });
    invSum += eq > 0 ? inv / eq : 0; if (pos.length) daysIn++;
    // 4) signals at the close
    for (const p of pos) {
      if (p.exit) continue;
      const s = S[p.sym], i = s.idx.get(d); if (i == null) continue;
      if ((s.sma5[i] != null && s.rows[i].c > s.sma5[i]) || i - p.entryI + 1 >= maxHold) p.exit = true;
    }
    const slots = maxPos - pos.filter((p) => !p.exit).length;
    if (slots > 0) {
      const held = new Set(pos.map((p) => p.sym));
      const cands = [];
      for (const sym of syms) {
        if (held.has(sym)) continue;
        const s = S[sym], i = s.idx.get(d);
        if (i == null || s.sma200[i] == null || s.rsi[i] == null) continue;
        if (s.rows[i].c > s.sma200[i] && s.rsi[i] < 10 && allowed(sym, d)) cands.push({ sym, rsi: s.rsi[i] });
      }
      cands.sort((a, b) => a.rsi - b.rsi || (a.sym < b.sym ? -1 : 1));
      orders = cands.slice(0, slots).map((c) => ({ sym: c.sym, alloc: weight * eq }));
    }
  }
  return { pts, trades, open: pos.map((p) => ({ sym: p.sym, entry_d: p.entryD })), exposure: invSum / cal.length, days_in: daysIn / cal.length };
}

// ---------------- reporting ----------------
const tradeStats = (tr) => ({
  trades: tr.length,
  win_rate: tr.length ? pct(tr.filter((t) => t.ret > 0).length / tr.length) : null,
  avg_hold_days: tr.length ? Math.round((tr.reduce((s, t) => s + t.hold, 0) / tr.length) * 100) / 100 : null,
  avg_trade_ret: tr.length ? pct(tr.reduce((s, t) => s + t.ret, 0) / tr.length) : null,
});
// Sub-period curve [from, to] chained from the last mark before `from`.
function slice(pts, from, to) {
  const before = pts.filter((p) => p.d < from).at(-1);
  const inside = pts.filter((p) => p.d >= from && p.d <= to);
  return before ? [before, ...inside] : inside;
}
export const PERIODS = [['2016-2020', '2016-01-01', '2020-12-31'], ['2021-2026', '2021-01-01', '2026-12-31']];

export function report(name, run, spyPts) {
  const s = curveStats(run.pts);
  const yb = new Map(yearly(spyPts).map((y) => [y.year, y.ret]));
  const periods = {};
  for (const [k, from, to] of PERIODS) {
    const a = slice(run.pts, from, to), b = slice(spyPts, from, to);
    if (a.length < 2) continue;
    const sa = curveStats(a), sb = curveStats(b);
    periods[k] = { start: a[0].d, end: a.at(-1).d, cagr: pct(sa.cagr), total: pct(sa.total), max_dd: pct(sa.max_dd), spy_cagr: pct(sb.cagr), spy_total: pct(sb.total), spy_max_dd: pct(sb.max_dd), ...tradeStats(run.trades.filter((t) => t.entry_d >= from && t.entry_d <= to)) };
  }
  return {
    name, start: run.pts[0].d, end: run.pts.at(-1).d,
    cagr: pct(s.cagr), total: pct(s.total), max_dd: pct(s.max_dd),
    ...tradeStats(run.trades),
    exposure_pct: pct(run.exposure), days_invested_pct: pct(run.days_in), open_positions: run.open,
    yearly: yearly(run.pts).map((y) => ({ year: y.year, ret: pct(y.ret), spy: pct(yb.get(y.year)), partial: y.partial })),
    periods,
  };
}

export function spyRun(spyRows, cal) {
  const c = new Map(spyRows.map((r) => [r.d, r.c]));
  const c0 = c.get(cal[0]);
  let last = c0;
  return { pts: cal.map((d) => ({ d, eq: (last = c.get(d) ?? last) / c0 })), trades: [], open: [], exposure: 1, days_in: 1 };
}

export function summaryTable(out) {
  const f = (x, w = 8) => String(x ?? '-').padStart(w);
  const lines = [`${'version'.padEnd(16)}${f('CAGR%')}${f('total%')}${f('maxDD%')}${f('trades')}${f('win%')}${f('hold')}${f('avgTr%')}${f('expo%')}`];
  for (const v of Object.values(out.versions)) {
    lines.push(`${v.name.padEnd(16)}${f(v.cagr)}${f(v.total)}${f(v.max_dd)}${f(v.trades)}${f(v.win_rate)}${f(v.avg_hold_days)}${f(v.avg_trade_ret)}${f(v.exposure_pct)}`);
    for (const [k, p] of Object.entries(v.periods)) lines.push(`  ${k.padEnd(14)}${f(p.cagr)}${f(p.total)}${f(p.max_dd)}${f(p.trades)}${f(p.win_rate)}   | SPY ${p.spy_cagr}%/yr DD ${p.spy_max_dd}%`);
  }
  return lines.join('\n');
}

// ---------------- main ----------------
// Wikipedia first; if that fails, the last saved data/sp500_tickers.json; otherwise a clear error.
export async function loadUniverse(outDir, env = process.env, notes = [], fetchFn = fetch) {
  const file = join(outDir, 'sp500_tickers.json');
  try {
    const r = await fetchFn('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies', { headers: { 'User-Agent': `sec-edgar-worker quality-dips/1.0 (${env.SEC_USER_AGENT || 'research script'})` } });
    if (!r.ok) throw new Error(`Wikipedia HTTP ${r.status}`);
    const tickers = parseSp500Html(await r.text());
    writeFileSync(file, JSON.stringify({ fetched: new Date().toISOString(), source: 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies', count: tickers.length, tickers }, null, 1));
    return tickers;
  } catch (e) {
    if (!existsSync(file)) throw new Error(`Could not get the S&P 500 list: Wikipedia failed (${e.message}) and ${file} does not exist yet.`);
    const saved = JSON.parse(readFileSync(file, 'utf8'));
    if (!Array.isArray(saved.tickers) || saved.tickers.length < 400) throw new Error(`Wikipedia failed (${e.message}) and ${file} is unusable.`);
    const msg = `Wikipedia failed (${e.message}); using saved ${file} from ${saved.fetched}.`;
    console.log(msg); notes.push(msg);
    return saved.tickers;
  }
}

async function main(outDir) {
  const env = process.env;
  if (!env.APCA_API_KEY_ID || !env.APCA_API_SECRET_KEY) throw new Error('APCA_API_KEY_ID / APCA_API_SECRET_KEY are not set');
  if (!env.SEC_USER_AGENT) throw new Error('SEC_USER_AGENT is not set (SEC requires "Name email")');
  const notes = [
    'Universe is the CURRENT S&P 500 tested back to 2016: survivorship bias flatters both stock versions vs SPY.',
    'RSI(2) uses the same 2-day average gain/loss formula as build-strategies.mjs.',
    'Signals at the close, fills at the next open; exits before entries on the same open; 20% of equity per new position, capped by available cash.',
    'Quality uses only 10-K facts filed before Jan 1 of the signal year. Debt = LongTermDebt (or LongTermDebtNoncurrent) + LongTermDebtCurrent; missing tags count as 0.',
  ];

  // 1) universe
  const universe = await loadUniverse(outDir, env, notes);
  console.log('S&P 500 tickers:', universe.length);
  const sectors = Object.fromEntries(universe.map((t) => [t.symbol, t.sector]));

  // 2) prices
  const syms = universe.map((t) => t.symbol);
  const { bars, feed, failed: barsFailed } = await alpacaDaily([...new Set([...syms, 'SPY', 'BIL'])], { env });
  if (bars.SPY.length < 400 || bars.BIL.length < 400) throw new Error(`Alpaca: SPY ${bars.SPY.length} / BIL ${bars.BIL.length} days`);
  if (bars.SPY[0].d > '2016-02-01') notes.push(`Alpaca ${feed} history starts ${bars.SPY[0].d}, not 2016-01.`);
  if (feed === 'iex') notes.push('SIP was refused, so prices are from the IEX feed (IEX-only trades; opens/closes can differ from the consolidated tape).');
  const noBars = syms.filter((s) => bars[s].length < 201);

  // 3) fundamentals
  const ua = { 'User-Agent': env.SEC_USER_AGENT, Accept: 'application/json' };
  const secGet = async (url) => {
    for (let a = 0; a < 5; a++) {
      const r = await fetch(url, { headers: ua });
      if (r.ok) return r.json();
      if (r.status === 404) return null;
      await sleep(1000 * 2 ** a);
    }
    throw new Error('SEC request failed: ' + url);
  };
  const cikMap = new Map(Object.values(await secGet('https://www.sec.gov/files/company_tickers.json')).map((x) => [String(x.ticker).toUpperCase(), x.cik_str]));
  let nextSlot = 0;
  const throttle = async () => { const now = Date.now(); const at = Math.max(now, nextSlot); nextSlot = at + 125; if (at > now) await sleep(at - now); }; // ~8 req/s
  const facts = {}, noCik = [], noFacts = [], secFailed = [];
  const queue = universe.slice();
  let done = 0;
  await Promise.all(Array.from({ length: 4 }, async () => {
    for (let t; (t = queue.shift()); ) {
      const cik = cikMap.get(t.symbol.replace('.', '-')) ?? cikMap.get(t.symbol) ?? t.cik;
      if (!cik) { noCik.push(t.symbol); continue; }
      try {
        await throttle();
        const js = await secGet(`https://data.sec.gov/api/xbrl/companyfacts/CIK${String(cik).padStart(10, '0')}.json`);
        if (!js) noFacts.push(t.symbol);
        else facts[t.symbol] = extractFacts(js);
      } catch (e) { secFailed.push({ symbol: t.symbol, error: String(e.message).slice(0, 200) }); console.log(`SEC SKIP ${t.symbol}: ${String(e.message).slice(0, 120)}`); }
      if (++done % 50 === 0) console.log(`SEC ${done}/${universe.length}`);
    }
  }));
  console.log(`SEC ${universe.length}/${universe.length}: facts for ${Object.keys(facts).length}, no CIK ${noCik.length}, no companyfacts ${noFacts.length}, failed ${secFailed.length}`);

  // 4) quality per year
  const cal = bars.SPY.slice(200).map((r) => r.d); // first date with a 200-day SMA on SPY
  const years = [...new Set(cal.map((d) => +d.slice(0, 4)))];
  const qSets = {}, quality_by_year = {};
  for (const y of years) {
    const inputs = Object.fromEntries(Object.entries(facts).map(([s, f]) => [s, qualityInputs(f, y)]));
    const r = rankQuality(inputs, sectors);
    qSets[y] = new Set(r.quality);
    quality_by_year[y] = { ...r.stats, tickers: r.quality };
    console.log(`quality ${y}: ${r.stats.quality} of ${r.stats.eligible} eligible (financials ${r.stats.financials_quality}/${r.stats.financials_eligible}), ROE cut ${r.stats.roe_cutoff}%, D/E median ${r.stats.de_median}`);
  }

  // 5) backtests
  const stockBars = Object.fromEntries(syms.filter((s) => bars[s].length).map((s) => [s, bars[s]]));
  const spyPts = spyRun(bars.SPY, cal).pts;
  const runQ = backtest({ bars: stockBars, cal, bil: bars.BIL, allowed: (s, d) => qSets[+d.slice(0, 4)]?.has(s) });
  const runA = backtest({ bars: stockBars, cal, bil: bars.BIL });
  const out = {
    generated: new Date().toISOString(),
    source: { prices: `Alpaca daily bars, adjustment=all, feed=${feed}`, fundamentals: 'SEC XBRL companyfacts (10-K, filed before Jan 1 of each year)', universe: 'Wikipedia S&P 500 constituents (current)' },
    rules: { entry: 'close > SMA200 and RSI(2) < 10', exit: 'close > SMA5 or 10 trading days held', fills: 'next open', max_positions: MAX_POS, position_size: WEIGHT, cost_per_side: COST, cash: 'BIL', quality: 'net income > 0 in each of the last 3 fiscal years, equity > 0, ROE in top 40%, D/E below median (of eligible)' },
    notes,
    universe: { count: syms.length, bars_failed: barsFailed, without_price_history: noBars, without_cik: noCik, without_companyfacts: noFacts, sec_failed: secFailed },
    versions: { quality: report('quality only', runQ, spyPts), all: report('all S&P 500', runA, spyPts), spy: report('SPY buy & hold', spyRun(bars.SPY, cal), spyPts) },
    quality_by_year,
    trades: { quality: runQ.trades.map((t) => ({ ...t, ret: pct(t.ret) })) },
  };
  writeFileSync(join(outDir, 'quality_dips.json'), JSON.stringify(out, null, 1));
  console.log('\n' + summaryTable(out));
  for (const n of notes) console.log('note:', n);
  const skipped = [...barsFailed.map((f) => f.symbol), ...noBars, ...noCik, ...noFacts, ...secFailed.map((f) => f.symbol)];
  if (skipped.length) console.log(`skipped/partial tickers (${new Set(skipped).size}): bars failed [${barsFailed.map((f) => f.symbol).join(' ')}], <201 days [${noBars.join(' ')}], no CIK [${noCik.join(' ')}], no companyfacts [${noFacts.join(' ')}], SEC failed [${secFailed.map((f) => f.symbol).join(' ')}]`);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const outDir = process.argv[2] || 'data';
  mkdirSync(outDir, { recursive: true });
  try { await main(outDir); }
  catch (e) {
    const msg = String(e.stack || e.message || e).split(process.env.APCA_API_SECRET_KEY || '\u0000').join('***');
    writeFileSync(join(outDir, 'quality_dips_error.txt'), new Date().toISOString() + '\n' + msg + '\n');
    console.error(msg); process.exit(1);
  }
}
