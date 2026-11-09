// "Dip + smart exit + Clear Leader parking" PAPER trader ($10k). PAPER ONLY: endpoint is hard-coded.
// Runs ~3:15-3:49 pm ET on weekdays and places MARKET-ON-CLOSE orders (fills at the 4:00 pm close).
// Rule (from dip_fast_robust backtest, main settings):
//   Entry: S&P 500 stock above its 200-day average that fell >= 10% more than SPY over the last 5 trading days.
//          Biggest dips first, up to 10 positions, 10% of equity each.
//   Exit (smart exit): sell at the close once the stock closes above its 5-day average, or after 5 trading days.
//   Waiting money: Clear Leader v2.0 ETF (no crash filter), but CASH when SPY is below its 100-day average.
// Signals use live prices ~10-40 min before the close as a stand-in for the close. Long only. Not financial advice.
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { parseSp500Html } from './build-quality-dips.mjs';
import { run as clRun, POOL } from './clear-leader.mjs';
import { monthRows } from './clear-leader-alert.mjs';
export const PAPER = 'https://paper-api.alpaca.markets', DATA = 'https://data.alpaca.markets';
export const DIP = 0.10, LOOKBACK = 5, TREND = 200, EXIT_MA = 5, MAX_HOLD = 5, SLOTS = 10, WEIGHT = 0.10, CRASH_MA = 100, BUFFER = 0.02, MIN_PX = 5;
const avg = (a) => a.reduce((x, y) => x + y, 0) / a.length;

// closes: array of prior daily closes (ascending, excludes today); px: today's live price.
export function dipScore(closes, px, spyCloses, spyPx) {
  if (!(px >= MIN_PX) || closes.length < TREND || spyCloses.length < LOOKBACK) return null;
  const ma200 = avg([...closes.slice(-(TREND - 1)), px]);
  if (!(px > ma200)) return null;
  const ex = px / closes.at(-LOOKBACK) - 1 - (spyPx / spyCloses.at(-LOOKBACK) - 1);
  return ex <= -DIP ? ex : null;
}
export function shouldExit({ age, closes, px }) {
  if (age >= MAX_HOLD) return `held ${age} days (max ${MAX_HOLD})`;
  if (age >= 1 && px > avg([...closes.slice(-(EXIT_MA - 1)), px])) return `bounced above ${EXIT_MA}-day average`;
  return null;
}
export function parkSymbol({ clPos, spyCloses, spyPx }) {
  const ma = avg([...spyCloses.slice(-(CRASH_MA - 1)), spyPx]);
  return spyPx > ma ? clPos : null; // null = cash
}
// Decide trades. state.positions: [{symbol, entry_date, qty}]; days: trading dates ending with today.
export function decide({ today, days, state, held, equity, prices, closes, scores, park, parkHeld }) {
  const ti = days.indexOf(today), sells = [], keep = [];
  for (const p of state.positions) {
    if (!held[p.symbol]) continue;
    const ei = days.indexOf(p.entry_date), age = ei >= 0 ? ti - ei : MAX_HOLD;
    const why = prices[p.symbol] ? shouldExit({ age, closes: closes[p.symbol] || [], px: prices[p.symbol] }) : null;
    if (why) sells.push({ symbol: p.symbol, qty: held[p.symbol], reason: why }); else keep.push(p);
  }
  const keptVal = keep.reduce((a, p) => a + held[p.symbol] * (prices[p.symbol] || 0), 0);
  const freeFrac = Math.max(0, 1 - keptVal / equity);
  const cands = Object.entries(scores).filter(([s]) => !POOL.includes(s) && !keep.some((p) => p.symbol === s))
    .sort((a, b) => a[1] - b[1]).slice(0, Math.max(0, SLOTS - keep.length));
  const w = cands.length ? Math.min(WEIGHT, freeFrac / cands.length) : 0, buys = [];
  for (const [s, ex] of cands) { const qty = Math.floor((w * equity) / prices[s]); if (qty >= 1) buys.push({ symbol: s, qty, dip_pct: +(ex * 100).toFixed(1) }); }
  const stockVal = keptVal + buys.reduce((a, b) => a + b.qty * prices[b.symbol], 0);
  // parking: sell any ETF that isn't today's park target; size the target to the leftover
  const parkTrades = [];
  for (const [s, q] of Object.entries(parkHeld)) if (q > 0 && s !== park) parkTrades.push({ symbol: s, qty: q, side: 'sell', reason: 'switch parking' });
  if (park && prices[park]) {
    const target = Math.max(0, Math.floor((equity * (1 - BUFFER) - stockVal) / prices[park])), cur = parkHeld[park] || 0, delta = target - cur;
    if (Math.abs(delta) * prices[park] > equity * 0.005) parkTrades.push({ symbol: park, qty: Math.abs(delta), side: delta > 0 ? 'buy' : 'sell', reason: 'resize parking' });
  }
  return { sells, buys, keep, parkTrades, stockVal };
}

async function main() {
  const own = !!process.env.DIP_KEY_ID;
  const H = { 'APCA-API-KEY-ID': process.env.DIP_KEY_ID || process.env.APCA_API_KEY_ID, 'APCA-API-SECRET-KEY': process.env.DIP_SECRET_KEY || process.env.APCA_API_SECRET_KEY, 'Content-Type': 'application/json' };
  const dry = process.env.DRY_RUN === '1' || !own;   // never trade the earnings-drift account: without its own keys this is a dry run
  const api = async (base, path, opt = {}) => { const r = await fetch(base + path, { ...opt, headers: H }); const t = await r.text(); if (!r.ok) throw new Error(`${r.status} ${path.split('?')[0]}: ${t.slice(0, 300)}`); return t ? JSON.parse(t) : null; };
  const nyParts = Object.fromEntries(new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).formatToParts(new Date()).map((x) => [x.type, x.value]));
  const today = `${nyParts.year}-${nyParts.month}-${nyParts.day}`, nyMin = +nyParts.hour * 60 + +nyParts.minute;
  const acct = await api(PAPER, '/v2/account'), equity = +acct.equity;
  const cal = await api(PAPER, `/v2/calendar?start=${new Date(Date.now() - 400 * 86400e3).toISOString().slice(0, 10)}&end=${today}`);
  const days = cal.map((c) => c.date);
  const file = 'data/paper_dip_state.json', state = existsSync(file) ? JSON.parse(readFileSync(file, 'utf8')) : { positions: [], history: [] };
  const log = { run: new Date().toISOString(), today, ny_time: `${nyParts.hour}:${nyParts.minute}`, equity, dry, own_account: own };
  const force = process.env.FORCE === '1';
  if (days.at(-1) !== today && !force) { console.log('market closed today', today); return; }
  if (!force && (nyMin < 15 * 60 || nyMin >= 15 * 60 + 49)) { console.log('outside 3:00-3:49 pm ET window', log.ny_time); return; }
  if (!force && !dry && (state.history || []).some((h) => h.today === today && !h.dry)) { console.log('already traded today', today); return; }
  // universe
  const wiki = await (await fetch('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies', { headers: { 'User-Agent': 'sec-edgar-worker paper-dip/1.0' } })).text();
  const members = [...new Set(parseSp500Html(wiki).map((m) => m.symbol.replace('.', '/')))];
  const etfs = [...POOL, 'BIL'];
  const syms = [...new Set([...members, ...etfs])];
  // prior daily closes (exclude today)
  const prevDay = days.at(-1) === today ? days.at(-2) : days.at(-1);
  const closes = Object.fromEntries(syms.map((s) => [s, []])), etfBars = Object.fromEntries(etfs.map((s) => [s, []]));
  for (let i = 0; i < syms.length; i += 100) {
    const p = new URLSearchParams({ symbols: syms.slice(i, i + 100).join(','), timeframe: '1Day', start: days.at(-260), end: prevDay + 'T23:59:00Z', adjustment: 'all', feed: 'sip', limit: '10000' });
    for (;;) { const js = await api(DATA, '/v2/stocks/bars?' + p); for (const [s, bl] of Object.entries(js.bars || {})) for (const b of bl) closes[s].push(b.c); if (!js.next_page_token) break; p.set('page_token', js.next_page_token); }
  }
  // live prices (IEX feed is real-time on the free plan)
  const prices = {};
  for (let i = 0; i < syms.length; i += 200) {
    const js = await api(DATA, '/v2/stocks/snapshots?' + new URLSearchParams({ symbols: syms.slice(i, i + 200).join(','), feed: 'iex' }));
    for (const [s, v] of Object.entries(js || {})) { const px = v?.latestTrade?.p || v?.minuteBar?.c || v?.dailyBar?.c; if (px > 0) prices[s] = px; }
  }
  // Clear Leader position from completed month-ends (since 2016)
  const p = new URLSearchParams({ symbols: etfs.join(','), timeframe: '1Day', start: '2016-01-01', end: prevDay + 'T23:59:00Z', adjustment: 'all', feed: 'sip', limit: '10000' });
  for (;;) { const js = await api(DATA, '/v2/stocks/bars?' + p); for (const [s, bl] of Object.entries(js.bars || {})) for (const b of bl) etfBars[s].push({ d: b.t.slice(0, 10), c: b.c }); if (!js.next_page_token) break; p.set('page_token', js.next_page_token); }
  const rows = monthRows(etfBars, prevDay).filter((r) => r.date.slice(0, 7) < today.slice(0, 7));
  const cl = clRun(rows, {}), clPos = cl?.now?.pos || 'SPY';
  const park = parkSymbol({ clPos, spyCloses: closes.SPY, spyPx: prices.SPY });
  // signals
  const scores = {};
  for (const s of members) { if (etfs.includes(s)) continue; const sc = dipScore(closes[s] || [], prices[s], closes.SPY, prices.SPY); if (sc != null) scores[s] = sc; }
  const posList = await api(PAPER, '/v2/positions'), held = Object.fromEntries(posList.map((x) => [x.symbol, +x.qty]));
  const parkHeld = Object.fromEntries(Object.entries(held).filter(([s]) => etfs.includes(s) && !state.positions.some((p) => p.symbol === s)));
  const d = decide({ today, days, state: own ? state : { positions: [] }, held: own ? held : {}, equity: own ? equity : 10000, prices, closes, scores, park, parkHeld: own ? parkHeld : {} });
  Object.assign(log, { clear_leader: clPos, clear_leader_why: cl?.now?.why, spy: prices.SPY, park: park || 'CASH (SPY below 100-day average)', signals: scores, sells: d.sells, buys: d.buys, park_trades: d.parkTrades });
  const done = [];
  if (!dry) {
    const order = (symbol, qty, side) => api(PAPER, '/v2/orders', { method: 'POST', body: JSON.stringify({ symbol, qty: String(qty), side, type: 'market', time_in_force: 'cls' }) });
    for (const t of d.parkTrades.filter((x) => x.side === 'sell')) { try { await order(t.symbol, t.qty, 'sell'); done.push(`SELL ${t.qty} ${t.symbol} (${t.reason})`); } catch (e) { done.push(`SELL ${t.symbol} failed: ${e.message}`); } }
    for (const s of d.sells) { try { await order(s.symbol, s.qty, 'sell'); done.push(`SELL ${s.qty} ${s.symbol} (${s.reason})`); } catch (e) { done.push(`SELL ${s.symbol} failed: ${e.message}`); d.keep.push(state.positions.find((x) => x.symbol === s.symbol)); } }
    for (const b of d.buys) { try { await order(b.symbol, b.qty, 'buy'); done.push(`BUY ${b.qty} ${b.symbol} (dip ${b.dip_pct}%)`); d.keep.push({ symbol: b.symbol, entry_date: today, qty: b.qty, dip_pct: b.dip_pct }); } catch (e) { done.push(`BUY ${b.symbol} failed: ${e.message}`); } }
    for (const t of d.parkTrades.filter((x) => x.side === 'buy')) { try { await order(t.symbol, t.qty, 'buy'); done.push(`BUY ${t.qty} ${t.symbol} (parking)`); } catch (e) { done.push(`BUY ${t.symbol} failed: ${e.message}`); } }
    state.positions = d.keep.filter(Boolean);
  }
  log.orders = done; state.history = [...(state.history || []), log].slice(-400); state.updated = log.run;
  mkdirSync('data', { recursive: true }); writeFileSync(file, JSON.stringify(state, null, 1));
  console.log(JSON.stringify({ ...log, signals: Object.keys(scores).length + ' stocks' }, null, 1));
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main().catch((e) => { console.error(e); process.exit(1); });
