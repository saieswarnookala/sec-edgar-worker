// "Dip + smart exit + Clear Leader parking" PAPER trader ($10k). PAPER ONLY: endpoint is hard-coded.
// Runs ~3:15-3:49 pm ET on weekdays and places MARKET-ON-CLOSE orders (fills at the 4:00 pm close).
// Rule (from dip_fast_robust backtest, main settings):
//   Entry: S&P 500 stock above its 200-day average that fell >= 10% more than SPY over the last 5 trading days.
//          Biggest dips first, up to 10 positions, 10% of equity each.
//          NEW (Nov 10 backtest): skip dips that came on heavy volume: average daily volume over the 5-day drop
//          (today estimated from SIP bars up to 16 min ago) > 2x the stock's normal volume (50 days before the drop).
//   Exit (smart exit): sell at the close once the stock closes above its 5-day average, or after 5 trading days.
//   Waiting money: Clear Leader v2.0 ETF (no crash filter), but CASH when SPY is below its 100-day average.
// Signals use live prices ~10-40 min before the close as a stand-in for the close. Long only. Not financial advice.
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { parseSp500Html } from './build-quality-dips.mjs';
import { run as clRun, POOL } from './clear-leader.mjs';
import { monthRows } from './clear-leader-alert.mjs';
export const PAPER = 'https://paper-api.alpaca.markets', DATA = 'https://data.alpaca.markets';
export const DIP = 0.10, LOOKBACK = 5, TREND = 200, EXIT_MA = 5, MAX_HOLD = 5, SLOTS = 10, WEIGHT = 0.10, CRASH_MA = 100, BUFFER = 0.02, MIN_PX = 5, VOL_MAX = 2.0;
const avg = (a) => a.reduce((x, y) => x + y, 0) / a.length;

// closes: array of prior daily closes (ascending, excludes today); px: today's live price.
export function dipScore(closes, px, spyCloses, spyPx) {
  if (!(px >= MIN_PX) || closes.length < TREND || spyCloses.length < LOOKBACK) return null;
  const ma200 = avg([...closes.slice(-(TREND - 1)), px]);
  if (!(px > ma200)) return null;
  const ex = px / closes.at(-LOOKBACK) - 1 - (spyPx / spyCloses.at(-LOOKBACK) - 1);
  return ex <= -DIP ? ex : null;
}
// Typical share of a day's volume traded by a given time (ET minutes since midnight), U-shaped curve incl. closing auction.
const VOL_CURVE = [[570, 0], [600, 0.12], [660, 0.25], [720, 0.35], [780, 0.43], [840, 0.52], [900, 0.64], [930, 0.74], [960, 1]];
export function volFraction(min) {
  if (min <= 570) return 0; if (min >= 960) return 1;
  for (let i = 1; i < VOL_CURVE.length; i++) { const [m1, f1] = VOL_CURVE[i], [m0, f0] = VOL_CURVE[i - 1]; if (min <= m1) return f0 + (f1 - f0) * (min - m0) / (m1 - m0); }
  return 1;
}
// vols: prior full-day volumes (ascending, excludes today); todayEst: estimated full-day volume today (or null).
// Ratio = average volume over the 5-day drop window / average over the 50 days before it (same as the backtest).
export function volumeRatio(vols, todayEst) {
  if (vols.length < 54) return null;
  const recent = todayEst > 0 ? [...vols.slice(-4), todayEst] : vols.slice(-5), base = vols.slice(-54, -4);
  const b = avg(base); return b > 0 ? avg(recent) / b : null;
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
// fractional: size in fractions of a share (live Robinhood account with ~$100 slots); default whole shares (Alpaca paper).
export const roundQty = (q, fractional) => fractional ? Math.floor(q * 1e6) / 1e6 : Math.floor(q);
export function decide({ today, days, state, held, equity, prices, closes, scores, park, parkHeld, fractional = false, minOrderUsd = 1 }) {
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
  for (const [s, ex] of cands) { const qty = roundQty((w * equity) / prices[s], fractional); if (qty > 0 && qty * prices[s] >= (fractional ? minOrderUsd : 0)) buys.push({ symbol: s, qty, dip_pct: +(ex * 100).toFixed(1) }); }
  const stockVal = keptVal + buys.reduce((a, b) => a + b.qty * prices[b.symbol], 0);
  // parking: sell any ETF that isn't today's park target; size the target to the leftover
  const parkTrades = [];
  for (const [s, q] of Object.entries(parkHeld)) if (q > 0 && s !== park) parkTrades.push({ symbol: s, qty: q, side: 'sell', reason: 'switch parking' });
  if (park && prices[park]) {
    const target = Math.max(0, roundQty((equity * (1 - BUFFER) - stockVal) / prices[park], fractional)), cur = parkHeld[park] || 0, delta = roundQty(Math.abs(target - cur), fractional) * Math.sign(target - cur);
    if (Math.abs(delta) * prices[park] > Math.max(equity * 0.005, fractional ? minOrderUsd : 0)) parkTrades.push({ symbol: park, qty: Math.abs(delta), side: delta > 0 ? 'buy' : 'sell', reason: 'resize parking' });
  }
  return { sells, buys, keep, parkTrades, stockVal };
}

// Market data + signals (shared by the Alpaca paper bot and the live Robinhood runner in live/).
// api(base, path) must be an authenticated Alpaca fetcher (data only is used here).
export async function gatherSignals({ api, today, days }) {
  const out = {};
  // universe
  const wiki = await (await fetch('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies', { headers: { 'User-Agent': 'sec-edgar-worker paper-dip/1.0' } })).text();
  const members = [...new Set(parseSp500Html(wiki).map((m) => m.symbol))];
  const etfs = [...POOL, 'BIL'];
  const syms = [...new Set([...members, ...etfs])];
  // prior daily closes (exclude today)
  const prevDay = days.at(-1) === today ? days.at(-2) : days.at(-1);
  const closes = Object.fromEntries(syms.map((s) => [s, []])), vols = Object.fromEntries(syms.map((s) => [s, []])), etfBars = Object.fromEntries(etfs.map((s) => [s, []]));
  for (let i = 0; i < syms.length; i += 100) {
    const p = new URLSearchParams({ symbols: syms.slice(i, i + 100).join(','), timeframe: '1Day', start: days.at(-260), end: prevDay + 'T23:59:00Z', adjustment: 'all', feed: 'sip', limit: '10000' });
    for (;;) { const js = await api(DATA, '/v2/stocks/bars?' + p); for (const [s, bl] of Object.entries(js.bars || {})) for (const b of bl) { closes[s].push(b.c); vols[s].push(b.v); } if (!js.next_page_token) break; p.set('page_token', js.next_page_token); }
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
  // volume filter: today's SIP volume so far (free plan allows SIP data older than 15 min), scaled to a full day
  const cut = new Date(Date.now() - 16 * 60e3), cutMin = (() => { const f = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hour: 'numeric', minute: 'numeric', hourCycle: 'h23' }).formatToParts(cut); return +f.find((x) => x.type === 'hour').value * 60 + +f.find((x) => x.type === 'minute').value; })();
  const cands0 = Object.keys(scores), partial = {}, volInfo = {};
  if (cands0.length && cutMin > 600) {
    try {
      const vp = new URLSearchParams({ symbols: cands0.join(','), timeframe: '30Min', start: today + 'T13:00:00Z', end: cut.toISOString(), feed: 'sip', limit: '10000' });
      for (;;) { const js = await api(DATA, '/v2/stocks/bars?' + vp); for (const [s, bl] of Object.entries(js.bars || {})) for (const b of bl) { const m = new Date(b.t); const hm = +new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hour: 'numeric', hourCycle: 'h23' }).format(m) * 60 + m.getUTCMinutes(); if (hm >= 570) partial[s] = (partial[s] || 0) + b.v; } if (!js.next_page_token) break; vp.set('page_token', js.next_page_token); }
    } catch (e) { out.volume_error = String(e.message || e).slice(0, 200); }
  }
  const frac = volFraction(cutMin);
  for (const s of cands0) {
    const est = partial[s] && frac > 0.2 ? partial[s] / frac : null, r = volumeRatio(vols[s] || [], est);
    volInfo[s] = { ratio: r == null ? null : +r.toFixed(2), today_est: est ? Math.round(est) : null };
    if (r != null && r > VOL_MAX) { out.skipped_heavy_volume = [...(out.skipped_heavy_volume || []), `${s} (${r.toFixed(1)}x)`]; delete scores[s]; }
  }
  return { ...out, members, etfs, closes, prices, scores, park, clPos, clWhy: cl?.now?.why, volInfo };
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
  if (!force && (nyMin < 15 * 60 || nyMin >= 15 * 60 + 58)) { console.log('outside 3:00-3:57 pm ET window', log.ny_time); return; }
  if (!force && !dry && (state.history || []).some((h) => h.today === today && !h.dry)) { console.log('already traded today', today); return; }
  const g = await gatherSignals({ api, today, days });
  const { etfs, closes, prices, scores, park, clPos } = g;
  if (g.volume_error) log.volume_error = g.volume_error;
  if (g.skipped_heavy_volume) log.skipped_heavy_volume = g.skipped_heavy_volume;
  log.volume_check = g.volInfo;
  const posList = await api(PAPER, '/v2/positions'), held = Object.fromEntries(posList.map((x) => [x.symbol, +x.qty]));
  // sync with the broker: drop positions that never filled / were sold, use real share counts
  if (own) { const before = state.positions.map((p) => p.symbol); state.positions = state.positions.filter((p) => held[p.symbol] > 0).map((p) => ({ ...p, qty: Math.min(p.qty, held[p.symbol]) })); const gone = before.filter((s) => !state.positions.some((p) => p.symbol === s)); if (gone.length) log.synced_out = gone; }
  const parkHeld = Object.fromEntries(Object.entries(held).filter(([s]) => etfs.includes(s) && !state.positions.some((p) => p.symbol === s)));
  const d = decide({ today, days, state: own ? state : { positions: [] }, held: own ? held : {}, equity: own ? equity : 10000, prices, closes, scores, park, parkHeld: own ? parkHeld : {} });
  Object.assign(log, { clear_leader: clPos, clear_leader_why: g.clWhy, spy: prices.SPY, park: park || 'CASH (SPY below 100-day average)', signals: scores, sells: d.sells, buys: d.buys, park_trades: d.parkTrades });
  const done = [];
  if (!dry) {
    const order = (symbol, qty, side) => api(PAPER, '/v2/orders', { method: 'POST', body: JSON.stringify({ symbol, qty: String(qty), side, type: 'market', time_in_force: 'day' }) });
    for (const t of d.parkTrades.filter((x) => x.side === 'sell')) { try { await order(t.symbol, t.qty, 'sell'); done.push(`SELL ${t.qty} ${t.symbol} (${t.reason})`); } catch (e) { done.push(`SELL ${t.symbol} failed: ${e.message}`); } }
    for (const s of d.sells) { try { await order(s.symbol, s.qty, 'sell'); done.push(`SELL ${s.qty} ${s.symbol} (${s.reason})`); } catch (e) { done.push(`SELL ${s.symbol} failed: ${e.message}`); d.keep.push(state.positions.find((x) => x.symbol === s.symbol)); } }
    for (const b of d.buys) { try { await order(b.symbol, b.qty, 'buy'); done.push(`BUY ${b.qty} ${b.symbol} (dip ${b.dip_pct}%)`); d.keep.push({ symbol: b.symbol, entry_date: today, qty: b.qty, dip_pct: b.dip_pct }); } catch (e) { done.push(`BUY ${b.symbol} failed: ${e.message}`); } }
    for (const t of d.parkTrades.filter((x) => x.side === 'buy')) { try { await order(t.symbol, t.qty, 'buy'); done.push(`BUY ${t.qty} ${t.symbol} (parking)`); } catch (e) { done.push(`BUY ${t.symbol} failed: ${e.message}`); } }
    state.positions = d.keep.filter(Boolean);
  }
  log.orders = done; delete state.last_error; state.history = [...(state.history || []), log].slice(-400); state.updated = log.run;
  mkdirSync('data', { recursive: true }); writeFileSync(file, JSON.stringify(state, null, 1));
  console.log(JSON.stringify({ ...log, signals: Object.keys(scores).length + ' stocks' }, null, 1));
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main().catch((e) => {
  console.error(e);
  try { const f = 'data/paper_dip_state.json', st = existsSync(f) ? JSON.parse(readFileSync(f, 'utf8')) : { positions: [], history: [] };
    st.last_error = { at: new Date().toISOString(), message: String(e?.stack || e).slice(0, 1500) }; mkdirSync('data', { recursive: true }); writeFileSync(f, JSON.stringify(st, null, 1)); } catch {}
  process.exit(1);
});
