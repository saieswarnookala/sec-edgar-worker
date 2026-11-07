// Earnings-drift PAPER trader. Runs before the US open on weekdays. PAPER ONLY: endpoint is hard-coded.
// Idle cash parked in SPY (added 2026-11-06).
// Rule (from earnings_drift_pit backtest, thr5|hold60|n10|any): S&P 500 stock whose earnings reaction day
// (SEC 8-K Item 2.02) was the last trading day and that beat SPY by >= 5% that day -> buy at today's open,
// equal 1/10 of equity, max 10 positions, sell at the open after 60 trading days. Long only. Not financial advice.
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { parseSp500Html } from './build-quality-dips.mjs';
import { parse8k, reactionIndex } from './earnings-drift.mjs';
export const PAPER = 'https://paper-api.alpaca.markets', DATA = 'https://data.alpaca.markets';
export const THR = 0.05, HOLD = 60, SLOTS = 10, PARK = 'SPY', PARK_BUFFER = 0.02;
// Idle cash is parked in SPY (backtest: ~+1 pt/yr). Target SPY value = equity*(1-buffer) - value of stock positions after today's trades.
// Returns a share delta (negative = sell). Small changes (< 0.5% of equity) are skipped to avoid churn.
export function parkOrder({ equity, stockValue, spyPx, spyHeld = 0, buffer = PARK_BUFFER }) {
  if (!(spyPx > 0) || !(equity > 0)) return 0;
  const target = Math.max(0, Math.floor((equity * (1 - buffer) - stockValue) / spyPx));
  const delta = target - spyHeld;
  return Math.abs(delta) * spyPx <= equity * 0.005 ? 0 : delta;
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Pure decision logic. state.positions: [{symbol, entry_date, qty}]; days: trading dates ascending ending with today.
export function decide({ today, days, state, held, signals, equity, prices }) {
  const ti = days.indexOf(today), sells = [], keep = [];
  for (const p of state.positions) {
    if (!held[p.symbol]) continue;                                   // gone (e.g. sold manually) -> drop
    const ei = days.indexOf(p.entry_date), age = ei >= 0 ? ti - ei : HOLD;
    if (age >= HOLD) sells.push({ symbol: p.symbol, qty: held[p.symbol], reason: `held ${age} trading days` }); else keep.push(p);
  }
  let free = SLOTS - keep.length; const buys = [];
  for (const s of [...signals].sort((a, b) => b.r - a.r)) {
    if (free <= 0) break; if (held[s.symbol] || keep.some((p) => p.symbol === s.symbol)) continue;
    const px = prices[s.symbol]; if (!px) continue; const qty = Math.floor(equity / SLOTS / px); if (qty < 1) continue;
    buys.push({ symbol: s.symbol, qty, r: s.r }); free--;
  }
  return { sells, buys, keep };
}

async function main() {
  const H = { 'APCA-API-KEY-ID': process.env.APCA_API_KEY_ID, 'APCA-API-SECRET-KEY': process.env.APCA_API_SECRET_KEY, 'Content-Type': 'application/json' };
  const ua = process.env.SEC_USER_AGENT, dry = process.env.DRY_RUN === '1';
  const api = async (base, path, opt = {}) => { const r = await fetch(base + path, { ...opt, headers: H }); const t = await r.text(); if (!r.ok) throw new Error(`${r.status} ${path}: ${t.slice(0, 300)}`); return t ? JSON.parse(t) : null; };
  const acct = await api(PAPER, '/v2/account');                    // fails if keys are not paper keys -> nothing happens
  const nowNY = new Date().toLocaleString('en-CA', { timeZone: 'America/New_York' }).slice(0, 10);
  const cal = await api(PAPER, `/v2/calendar?start=${new Date(Date.now() - 200 * 86400e3).toISOString().slice(0, 10)}&end=${nowNY}`);
  const days = cal.map((c) => c.date); const log = { run: new Date().toISOString(), today: nowNY, equity: +acct.equity, dry };
  if (days.at(-1) !== nowNY) { console.log('market closed today', nowNY); return; }
  const today = nowNY, prev = days.at(-2);
  const wiki = await (await fetch('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies', { headers: { 'User-Agent': `sec-edgar-worker paper-drift/1.0 (${ua})` } })).text();
  const members = parseSp500Html(wiki).filter((t) => t.cik);
  // events whose reaction day is the previous trading day
  const cands = [];
  for (const m of members) {
    try { const r = await fetch(`https://data.sec.gov/submissions/CIK${String(m.cik).padStart(10, '0')}.json`, { headers: { 'User-Agent': ua } });
      if (r.ok) { const j = await r.json(); const ev = parse8k([j.filings.recent]).filter((e) => e.day >= days.at(-6));
        if (ev.some((e) => days[reactionIndex(days, e.day, e.min)] === prev)) cands.push(m.symbol); } } catch {}
    await sleep(110);
  }
  // reaction vs SPY on prev day
  const syms = [...new Set([...cands, 'SPY'])], p = new URLSearchParams({ symbols: syms.join(','), timeframe: '1Day', start: days.at(-3), end: prev + 'T23:59:00Z', adjustment: 'all', feed: 'sip', limit: '10000' });
  const bars = (await api(DATA, '/v2/stocks/bars?' + p)).bars || {};
  const ret = (s) => { const a = (bars[s] || []).filter((b) => b.t.slice(0, 10) <= prev); return a.length >= 2 && a.at(-1).t.slice(0, 10) === prev ? a.at(-1).c / a.at(-2).c - 1 : null; };
  const spy = ret('SPY'), signals = [], prices = {};
  for (const s of cands.filter((x) => x !== PARK)) { const r = ret(s); const c = (bars[s] || []).at(-1)?.c; if (r != null && spy != null && c >= 5 && r - spy >= THR) { signals.push({ symbol: s, r: r - spy }); prices[s] = c; } }
  const posList = await api(PAPER, '/v2/positions'), held = Object.fromEntries(posList.map((x) => [x.symbol, +x.qty]));
  const file = 'data/paper_drift_state.json', state = existsSync(file) ? JSON.parse(readFileSync(file, 'utf8')) : { positions: [], history: [] };
  const d = decide({ today, days, state, held, signals, equity: +acct.equity, prices });
  log.earnings_reactions_checked = cands.length; log.signals = signals; log.sells = d.sells; log.buys = d.buys;
  const order = (symbol, qty, side) => api(PAPER, '/v2/orders', { method: 'POST', body: JSON.stringify({ symbol, qty: String(qty), side, type: 'market', time_in_force: 'opg' }) });
  const done = [];
  // SPY parking: value of stocks after today = kept positions (market value) + new buys at last close
  const mv = Object.fromEntries(posList.map((x) => [x.symbol, +x.market_value]));
  const stockValue = d.keep.reduce((a, k) => a + (mv[k.symbol] || 0), 0) + d.buys.reduce((a, b) => a + b.qty * prices[b.symbol], 0);
  const spyPx = (bars.SPY || []).at(-1)?.c, spyHeld = held[PARK] || 0;
  const park = parkOrder({ equity: +acct.equity, stockValue, spyPx, spyHeld });
  log.park = { spy_held: spyHeld, spy_delta: park, spy_price: spyPx, stock_value: Math.round(stockValue) };
  if (!dry) {
    if (park < 0) { try { await order(PARK, -park, 'sell'); done.push(`SELL ${-park} ${PARK} (park)`); } catch (e) { done.push(`SELL ${PARK} failed: ${e.message}`); } }
    for (const s of d.sells) { try { await order(s.symbol, s.qty, 'sell'); done.push(`SELL ${s.qty} ${s.symbol}`); } catch (e) { done.push(`SELL ${s.symbol} failed: ${e.message}`); d.keep.push(state.positions.find((x) => x.symbol === s.symbol)); } }
    for (const b of d.buys) { try { await order(b.symbol, b.qty, 'buy'); done.push(`BUY ${b.qty} ${b.symbol}`); d.keep.push({ symbol: b.symbol, entry_date: today, qty: b.qty, reaction_pct: +(b.r * 100).toFixed(1) }); } catch (e) { done.push(`BUY ${b.symbol} failed: ${e.message}`); } }
    if (park > 0) { try { await order(PARK, park, 'buy'); done.push(`BUY ${park} ${PARK} (park)`); } catch (e) { done.push(`BUY ${PARK} failed: ${e.message}`); } }
  }
  log.orders = done; state.positions = d.keep.filter(Boolean); state.history = [...(state.history || []), log].slice(-400); state.updated = log.run;
  mkdirSync('data', { recursive: true }); writeFileSync(file, JSON.stringify(state, null, 1));
  console.log(JSON.stringify(log, null, 1));
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main().catch((e) => { console.error(e); process.exit(1); });
