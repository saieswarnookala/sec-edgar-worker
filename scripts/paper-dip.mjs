// "Dip + smart exit + Clear Leader parking" PAPER trader ($10k). PAPER ONLY: endpoint is hard-coded.
// Runs ~3:25-3:40 pm ET on weekdays (12:25-12:40 pm on 1 pm half days) and places MARKET-ON-CLOSE orders (fills at the 4:00 pm close).
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
export function dipScore(closes, px, spyCloses, spyPx, { dip = DIP, trend = TREND } = {}) {
  if (!(px >= MIN_PX) || closes.length < trend || spyCloses.length < LOOKBACK) return null;
  const ma = avg([...closes.slice(-(trend - 1)), px]);
  if (!(px > ma)) return null;
  const ex = px / closes.at(-LOOKBACK) - 1 - (spyPx / spyCloses.at(-LOOKBACK) - 1);
  return ex <= -dip ? ex : null;
}
// Bot 6 "tuned dip" (Nov 15 combination test, 1999-2026 S&P 500 point-in-time + ETF dips: 20.9%/yr, worst -19%,
// better than today's rules in both 1999-2012 and 2013-2026; virtual only): 8% dips, 150-day trend, hold up to 7 days.
export const TUNED = { dip: 0.08, trend: 150, maxHold: 7 };
// Typical share of a day's volume traded by a given time (ET minutes since midnight), U-shaped curve incl. closing auction.
const VOL_CURVE = [[570, 0], [600, 0.12], [660, 0.25], [720, 0.35], [780, 0.43], [840, 0.52], [900, 0.64], [930, 0.74], [960, 1]];
// Half days (1 pm close): squeeze the same curve into the shorter session.
export function sessionMinute(min, closeMin = 960) { return closeMin >= 960 ? min : 570 + (min - 570) * 390 / (closeMin - 570); }
// Trade window: the hour before the close, last run 2 min before it (regular day = 3:00-3:57 pm ET).
export function inWindow(nyMin, closeMin = 960) { return nyMin >= closeMin - 60 && nyMin < closeMin - 2; }
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
export function shouldExit({ age, closes, px, maxHold = MAX_HOLD }) {
  if (age >= maxHold) return `held ${age} days (max ${maxHold})`;
  if (age >= 1 && px > avg([...closes.slice(-(EXIT_MA - 1)), px])) return `bounced above ${EXIT_MA}-day average`;
  return null;
}
export function parkSymbol({ clPos, spyCloses, spyPx }) {
  const ma = avg([...spyCloses.slice(-(CRASH_MA - 1)), spyPx]);
  return spyPx > ma ? clPos : null; // null = cash
}
// ---- ETF dip sleeve (Nov 14 combined backtest 1999-2026: 17.1%/yr, worst -22% vs 14.9%, -27% for stocks only) ----
// When slots are still free after the stock dips, buy ETFs down 5%+ over 5 days that are above their 200-day average.
// Same sell rule (close back above the 5-day average), held at most 10 days. Virtual bot only for now.
export const ETF_DIP_LIST = ['SPY', 'QQQ', 'IWM', 'DIA', 'MDY', 'XLB', 'XLE', 'XLF', 'XLI', 'XLK', 'XLP', 'XLU', 'XLV', 'XLY', 'XLRE', 'XLC',
  'EFA', 'EEM', 'EWJ', 'EWG', 'EWU', 'EWC', 'EWA', 'EWZ', 'EWH', 'EWT', 'EWY', 'INDA', 'FXI'];
export const ETF_DIP = 0.05, ETF_LOOKBACK = 5, ETF_MAX_HOLD = 10;
export function etfDipScore(closes, px) {
  if (!(px > 0) || closes.length < TREND) return null;
  if (!(px > avg([...closes.slice(-(TREND - 1)), px]))) return null;
  const r = px / closes.at(-ETF_LOOKBACK) - 1;
  return r <= -ETF_DIP ? r : null;
}
// ---- Volatility-sized variant (Nov 14 backtest: 16.1%/yr vs 14.9%, same worst drop) ----
// Slot size = 10% x scale, scale = 0.5 (calmest day of the past year) .. 1.5 (jumpiest), from SPY's 20-day volatility rank.
export const VOL_WIN = 20, VOL_RANK = 252, VOL_LO = 0.5, VOL_HI = 1.5, VBOT_START = 10000;
export function volScale(spyCloses, spyPx) {
  const c = spyPx ? [...spyCloses, spyPx] : [...spyCloses], r = [];
  for (let i = 1; i < c.length; i++) r.push(c[i] / c[i - 1] - 1);
  const sd = (a) => { const m = avg(a); return Math.sqrt(a.reduce((x, y) => x + (y - m) ** 2, 0) / (a.length - 1)); };
  const v = []; for (let i = VOL_WIN; i <= r.length; i++) v.push(sd(r.slice(i - VOL_WIN, i)));
  if (v.length < 60) return { scale: 1, rank: null, vol_pct: null };
  const w = v.slice(-VOL_RANK), now = v.at(-1), less = w.filter((x) => x < now).length, eq = w.filter((x) => x === now).length;
  const rank = (less + (eq + 1) / 2) / w.length;            // same as pandas rank(pct=True)
  return { scale: +(VOL_LO + (VOL_HI - VOL_LO) * rank).toFixed(3), rank: +rank.toFixed(3), vol_pct: +(now * Math.sqrt(252) * 100).toFixed(1) };
}
// Virtual paper portfolio (no broker): same signals and exits as the dip bot, fills at the ~3:45 pm price, fractional shares.
export function virtualStep({ vs, today, days, prices, closes, scores, park, scale, etfScores = {}, stockMaxHold = MAX_HOLD }) {
  vs = { cash: VBOT_START, positions: [], park: {}, trades: [], ...vs };
  const px = (s, fb) => prices[s] || fb || 0;
  const held = Object.fromEntries(vs.positions.map((p) => [p.symbol, p.qty]));
  const posVal = vs.positions.reduce((a, p) => a + p.qty * px(p.symbol, p.entry_px), 0);
  const parkVal = Object.entries(vs.park).reduce((a, [s, q]) => a + q * px(s), 0);
  const equity = vs.cash + posVal + parkVal;
  const d = decide({ today, days, state: { positions: vs.positions }, held, equity, prices, closes, scores, park, parkHeld: { ...vs.park }, fractional: true, minOrderUsd: 1, weight: WEIGHT * scale, etfScores, stockMaxHold });
  const done = [];
  for (const t of d.parkTrades.filter((x) => x.side === 'sell')) { vs.cash += t.qty * px(t.symbol); vs.park[t.symbol] = +((vs.park[t.symbol] || 0) - t.qty).toFixed(6); if (vs.park[t.symbol] <= 1e-6) delete vs.park[t.symbol]; done.push(`SELL ${t.symbol} (${t.reason})`); }
  for (const s of d.sells) {
    const p = vs.positions.find((x) => x.symbol === s.symbol); vs.cash += s.qty * px(s.symbol);
    vs.trades.push({ symbol: s.symbol, kind: p.kind || 'stock', entry_date: p.entry_date, exit_date: today, ret_pct: +((px(s.symbol) / p.entry_px - 1) * 100).toFixed(2), reason: s.reason });
    done.push(`SELL ${s.symbol} (${s.reason})`);
  }
  vs.positions = vs.positions.filter((p) => !d.sells.some((s) => s.symbol === p.symbol));
  for (const b of d.buys) { vs.cash -= b.qty * px(b.symbol); vs.positions.push({ symbol: b.symbol, ...(b.kind ? { kind: b.kind } : {}), entry_date: today, qty: b.qty, entry_px: px(b.symbol), dip_pct: b.dip_pct, size_pct: +(100 * b.qty * px(b.symbol) / equity).toFixed(1) }); done.push(`BUY $${(b.qty * px(b.symbol)).toFixed(0)} ${b.symbol}${b.kind === 'etf' ? ' ETF' : ''} (dip ${b.dip_pct}%)`); }
  for (const t of d.parkTrades.filter((x) => x.side === 'buy')) { vs.cash -= t.qty * px(t.symbol); vs.park[t.symbol] = +((vs.park[t.symbol] || 0) + t.qty).toFixed(6); done.push(`BUY ${t.symbol} (parking)`); }
  vs.trades = vs.trades.slice(-300);
  return { vs, equity: +equity.toFixed(2), done };
}
// ---- Bot 7 "dip + drift 6+4" (virtual, from Nov 16; backtest 2004-2026: 15.8%/yr, worst -24%) ----
// One $10k account: up to 6 dip slots (today's dip rules) + up to 4 earnings-drift slots (stock beat SPY by >= 5% on its
// earnings reaction day -> buy, hold 60 trading days), 10% each. Drift signals come from the morning drift run
// (data/paper_drift_signals.json); this afternoon run fills them at the ~3:45 pm price (backtest bought at the open).
// Idle money parks like the dip bot (Clear Leader ETF, cash when SPY < 100-day avg). Fractional shares, no broker.
export const MIX = { dipSlots: 6, driftSlots: 4, weight: 0.10, driftHold: 60, start: 10000 };
export function mixStep({ vs, today, days, prices, closes, scores, park, driftSignals = [] }) {
  vs = { cash: MIX.start, positions: [], park: {}, trades: [], ...vs };
  const px = (s, fb) => prices[s] || fb || 0, ti = days.indexOf(today), done = [];
  const equity = vs.cash + vs.positions.reduce((a, p) => a + p.qty * px(p.symbol, p.entry_px), 0) + Object.entries(vs.park).reduce((a, [s, q]) => a + q * px(s), 0);
  // 1) exits
  const keep = [];
  for (const p of vs.positions) {
    const ei = days.indexOf(p.entry_date), age = ei >= 0 ? ti - ei : 999;
    const why = !prices[p.symbol] ? null : p.kind === 'drift' ? (age >= MIX.driftHold ? `held ${age} days (drift max ${MIX.driftHold})` : null)
      : shouldExit({ age, closes: closes[p.symbol] || [], px: prices[p.symbol] });
    if (why) { vs.cash += p.qty * px(p.symbol); vs.trades.push({ symbol: p.symbol, kind: p.kind, entry_date: p.entry_date, exit_date: today, ret_pct: +((px(p.symbol) / p.entry_px - 1) * 100).toFixed(2), reason: why }); done.push(`SELL ${p.symbol} ${p.kind} (${why})`); }
    else keep.push(p);
  }
  vs.positions = keep;
  // 2) empty the parking, re-size it at the end
  for (const [s, q] of Object.entries(vs.park)) { if (!px(s)) continue; vs.cash += q * px(s); delete vs.park[s]; }
  const heldSyms = new Set(vs.positions.map((p) => p.symbol)), size = MIX.weight * equity, buys = [];
  const nDrift = vs.positions.filter((p) => p.kind === 'drift').length, nDip = vs.positions.length - nDrift;
  for (const s of [...driftSignals].sort((a, b) => b.r - a.r).filter((x) => prices[x.symbol] && !heldSyms.has(x.symbol)).slice(0, Math.max(0, MIX.driftSlots - nDrift))) { buys.push({ symbol: s.symbol, kind: 'drift', info: `reaction +${(s.r * 100).toFixed(1)}% vs SPY` }); heldSyms.add(s.symbol); }
  for (const [s, ex] of Object.entries(scores).filter(([s]) => prices[s] && !heldSyms.has(s) && !POOL.includes(s)).sort((a, b) => a[1] - b[1]).slice(0, Math.max(0, MIX.dipSlots - nDip))) { buys.push({ symbol: s, kind: 'dip', info: `dip ${(ex * 100).toFixed(1)}%` }); heldSyms.add(s); }
  for (const b of buys) {
    const usd = Math.min(size, vs.cash); if (usd < 1) break;
    const qty = Math.floor((usd / px(b.symbol)) * 1e6) / 1e6; vs.cash -= qty * px(b.symbol);
    vs.positions.push({ symbol: b.symbol, kind: b.kind, entry_date: today, qty, entry_px: px(b.symbol), info: b.info }); done.push(`BUY $${(qty * px(b.symbol)).toFixed(0)} ${b.symbol} ${b.kind} (${b.info})`);
  }
  // 3) park the rest (keep a 2% cash buffer)
  if (park && px(park)) { const usd = Math.max(0, vs.cash - BUFFER * equity); if (usd >= 1) { const q = Math.floor((usd / px(park)) * 1e6) / 1e6; vs.park[park] = q; vs.cash -= q * px(park); } }
  vs.trades = vs.trades.slice(-300);
  return { vs, equity: +equity.toFixed(2), done };
}
// Decide trades. state.positions: [{symbol, entry_date, qty}]; days: trading dates ending with today.
// fractional: size in fractions of a share (live Robinhood account with ~$100 slots); default whole shares (Alpaca paper).
export const roundQty = (q, fractional) => fractional ? Math.floor(q * 1e6) / 1e6 : Math.floor(q);
export function decide({ today, days, state, held, equity, prices, closes, scores, park, parkHeld, fractional = false, minOrderUsd = 1, weight = WEIGHT, etfScores = {}, stockMaxHold = MAX_HOLD }) {
  const ti = days.indexOf(today), sells = [], keep = [];
  for (const p of state.positions) {
    if (!held[p.symbol]) continue;
    const ei = days.indexOf(p.entry_date), age = ei >= 0 ? ti - ei : MAX_HOLD;
    const why = prices[p.symbol] ? shouldExit({ age, closes: closes[p.symbol] || [], px: prices[p.symbol], maxHold: p.kind === 'etf' ? ETF_MAX_HOLD : stockMaxHold }) : null;
    if (why) sells.push({ symbol: p.symbol, qty: held[p.symbol], reason: why }); else keep.push(p);
  }
  const keptVal = keep.reduce((a, p) => a + held[p.symbol] * (prices[p.symbol] || 0), 0);
  const freeFrac = Math.max(0, 1 - keptVal / equity);
  const cands = Object.entries(scores).filter(([s]) => !POOL.includes(s) && !keep.some((p) => p.symbol === s))
    .sort((a, b) => a[1] - b[1]).slice(0, Math.max(0, SLOTS - keep.length));
  // ETF dips fill whatever slots the stock dips left (stocks always come first)
  const etfC = Object.entries(etfScores).filter(([s]) => prices[s] && !keep.some((p) => p.symbol === s) && !cands.some(([c]) => c === s))
    .sort((a, b) => a[1] - b[1]).slice(0, Math.max(0, SLOTS - keep.length - cands.length)).map(([s, r]) => [s, r, 'etf']);
  cands.push(...etfC);
  const w = cands.length ? Math.min(weight, freeFrac / cands.length) : 0, buys = [];
  for (const [s, ex, kind] of cands) { const qty = roundQty((w * equity) / prices[s], fractional); if (qty > 0 && qty * prices[s] >= (fractional ? minOrderUsd : 0)) buys.push({ symbol: s, qty, dip_pct: +(ex * 100).toFixed(1), ...(kind ? { kind } : {}) }); }
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
export async function gatherSignals({ api, today, days, closeMin = 960 }) {
  const out = {};
  // universe
  const wiki = await (await fetch('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies', { headers: { 'User-Agent': 'sec-edgar-worker paper-dip/1.0' } })).text();
  const members = [...new Set(parseSp500Html(wiki).map((m) => m.symbol))];
  const etfs = [...POOL, 'BIL'];
  const syms = [...new Set([...members, ...etfs, ...ETF_DIP_LIST])];
  // prior daily closes (exclude today)
  const prevDay = days.at(-1) === today ? days.at(-2) : days.at(-1);
  const closes = Object.fromEntries(syms.map((s) => [s, []])), vols = Object.fromEntries(syms.map((s) => [s, []])), etfBars = Object.fromEntries(etfs.map((s) => [s, []]));
  for (let i = 0; i < syms.length; i += 100) {
    const p = new URLSearchParams({ symbols: syms.slice(i, i + 100).join(','), timeframe: '1Day', start: days.at(-300) ?? days[0], end: prevDay + 'T23:59:00Z', adjustment: 'all', feed: 'sip', limit: '10000' });
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
  const scores = {}, scoresTuned = {};
  for (const s of members) {
    if (etfs.includes(s)) continue;
    const sc = dipScore(closes[s] || [], prices[s], closes.SPY, prices.SPY); if (sc != null) scores[s] = sc;
    const st = dipScore(closes[s] || [], prices[s], closes.SPY, prices.SPY, TUNED); if (st != null) scoresTuned[s] = st;
  }
  // volume filter: today's SIP volume so far (free plan allows SIP data older than 15 min), scaled to a full day
  const cut = new Date(Date.now() - 16 * 60e3), cutMin = (() => { const f = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hour: 'numeric', minute: 'numeric', hourCycle: 'h23' }).formatToParts(cut); return +f.find((x) => x.type === 'hour').value * 60 + +f.find((x) => x.type === 'minute').value; })();
  const cands0 = [...new Set([...Object.keys(scores), ...Object.keys(scoresTuned)])], partial = {}, volInfo = {};
  if (cands0.length && cutMin > 600) {
    try {
      const vp = new URLSearchParams({ symbols: cands0.join(','), timeframe: '30Min', start: today + 'T13:00:00Z', end: cut.toISOString(), feed: 'sip', limit: '10000' });
      for (;;) { const js = await api(DATA, '/v2/stocks/bars?' + vp); for (const [s, bl] of Object.entries(js.bars || {})) for (const b of bl) { const m = new Date(b.t); const hm = +new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hour: 'numeric', hourCycle: 'h23' }).format(m) * 60 + m.getUTCMinutes(); if (hm >= 570) partial[s] = (partial[s] || 0) + b.v; } if (!js.next_page_token) break; vp.set('page_token', js.next_page_token); }
    } catch (e) { out.volume_error = String(e.message || e).slice(0, 200); }
  }
  const frac = volFraction(sessionMinute(cutMin, closeMin));
  for (const s of cands0) {
    const est = partial[s] && frac > 0.2 ? partial[s] / frac : null, r = volumeRatio(vols[s] || [], est);
    volInfo[s] = { ratio: r == null ? null : +r.toFixed(2), today_est: est ? Math.round(est) : null };
    if (r != null && r > VOL_MAX) { if (s in scores) out.skipped_heavy_volume = [...(out.skipped_heavy_volume || []), `${s} (${r.toFixed(1)}x)`]; delete scores[s]; delete scoresTuned[s]; }
  }
  const etfScores = {};
  for (const s of ETF_DIP_LIST) { const sc = etfDipScore(closes[s] || [], prices[s]); if (sc != null) etfScores[s] = sc; }
  return { ...out, members, etfs, closes, prices, scores, scoresTuned, etfScores, park, clPos, clWhy: cl?.now?.why, volInfo };
}

async function main() {
  const own = !!process.env.DIP_KEY_ID;
  const H = { 'APCA-API-KEY-ID': process.env.DIP_KEY_ID || process.env.APCA_API_KEY_ID, 'APCA-API-SECRET-KEY': process.env.DIP_SECRET_KEY || process.env.APCA_API_SECRET_KEY, 'Content-Type': 'application/json' };
  const dry = process.env.DRY_RUN === '1' || !own;   // never trade the earnings-drift account: without its own keys this is a dry run
  const api = async (base, path, opt = {}) => { const r = await fetch(base + path, { ...opt, headers: H }); const t = await r.text(); if (!r.ok) throw new Error(`${r.status} ${path.split('?')[0]}: ${t.slice(0, 300)}`); return t ? JSON.parse(t) : null; };
  const nyParts = Object.fromEntries(new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).formatToParts(new Date()).map((x) => [x.type, x.value]));
  const today = `${nyParts.year}-${nyParts.month}-${nyParts.day}`, nyMin = +nyParts.hour * 60 + +nyParts.minute;
  const acct = await api(PAPER, '/v2/account'), equity = +acct.equity;
  const cal = await api(PAPER, `/v2/calendar?start=${new Date(Date.now() - 470 * 86400e3).toISOString().slice(0, 10)}&end=${today}`);
  const days = cal.map((c) => c.date);
  const todayCal = cal.find((c) => c.date === today), closeMin = todayCal ? +todayCal.close.slice(0, 2) * 60 + +todayCal.close.slice(3, 5) : 960;
  const file = 'data/paper_dip_state.json', state = existsSync(file) ? JSON.parse(readFileSync(file, 'utf8')) : { positions: [], history: [] };
  const log = { run: new Date().toISOString(), today, ny_time: `${nyParts.hour}:${nyParts.minute}`, equity, dry, own_account: own };
  const force = process.env.FORCE === '1';
  if (days.at(-1) !== today && !force) { console.log('market closed today', today); return; }
  if (closeMin < 960) log.half_day_close = todayCal.close;
  if (!force && !inWindow(nyMin, closeMin)) { console.log(`outside trade window (close ${todayCal?.close || '16:00'} ET)`, log.ny_time); return; }
  if (!force && !dry && (state.history || []).some((h) => h.today === today && !h.dry)) { console.log('already traded today', today); return; }
  const g = await gatherSignals({ api, today, days, closeMin });
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
  // volatility-sized virtual bot (runs once a day on the real schedule; never places orders)
  if (!force) {
    const vfile = 'data/paper_dip_vol_state.json', vst = existsSync(vfile) ? JSON.parse(readFileSync(vfile, 'utf8')) : { history: [] };
    if (!(vst.history || []).some((h) => h.today === today)) {
      const vol = volScale(closes.SPY, prices.SPY);
      const { vs, equity: veq, done: vdone } = virtualStep({ vs: vst.vs, today, days, prices, closes, scores, park, scale: vol.scale });
      vst.vs = vs; vst.history = [...(vst.history || []), { today, equity: veq, spy: prices.SPY, scale: vol.scale, vol_rank: vol.rank, spy_vol_pct: vol.vol_pct, park: park || 'CASH', orders: vdone }].slice(-400);
      vst.updated = log.run; writeFileSync(vfile, JSON.stringify(vst, null, 1));
      log.vol_bot = { scale: vol.scale, equity: veq, orders: vdone.length };
    }
    // ETF-dip virtual bot + an identical virtual twin WITHOUT ETFs (same prices and fills, so the comparison is fair)
    const efile = 'data/paper_dip_etf_state.json', est = existsSync(efile) ? JSON.parse(readFileSync(efile, 'utf8')) : { history: [] };
    if (!(est.history || []).some((h) => h.today === today)) {
      const e = virtualStep({ vs: est.vs, today, days, prices, closes, scores, park, scale: 1, etfScores: g.etfScores || {} });
      const tw = virtualStep({ vs: est.twin, today, days, prices, closes, scores, park, scale: 1 });
      est.vs = e.vs; est.twin = tw.vs;
      est.history = [...(est.history || []), { today, equity: e.equity, twin_equity: tw.equity, spy: prices.SPY, park: park || 'CASH', etf_signals: g.etfScores || {}, orders: e.done }].slice(-400);
      est.updated = log.run; writeFileSync(efile, JSON.stringify(est, null, 1));
      log.etf_bot = { equity: e.equity, twin_equity: tw.equity, etf_signals: Object.keys(g.etfScores || {}).length, orders: e.done.length };
    }
    // Bot 7 "dip + drift 6+4" (virtual): drift signals from this morning's drift run
    const mfile = 'data/paper_mix_state.json', mst = existsSync(mfile) ? JSON.parse(readFileSync(mfile, 'utf8')) : { history: [] };
    if (!(mst.history || []).some((h) => h.today === today)) {
      const dsf = 'data/paper_drift_signals.json', ds = existsSync(dsf) ? JSON.parse(readFileSync(dsf, 'utf8')) : {};
      const driftSignals = ds.date === today ? (ds.signals || []) : [];
      const m = mixStep({ vs: mst.vs, today, days, prices, closes, scores, park, driftSignals });
      mst.vs = m.vs;
      mst.history = [...(mst.history || []), { today, equity: m.equity, spy: prices.SPY, park: park || 'CASH', dip_signals: Object.keys(scores).length, drift_signals: driftSignals.map((x) => x.symbol), drift_signals_found: ds.date === today, orders: m.done }].slice(-400);
      mst.updated = log.run; writeFileSync(mfile, JSON.stringify(mst, null, 1));
      log.mix_bot = { equity: m.equity, drift_signals: driftSignals.length, orders: m.done.length };
    }
    // Bot 6 "tuned dip": 8% dips, 150-day trend, hold up to 7 days, + ETF dips (virtual, no broker)
    const tfile = 'data/paper_dip_tuned_state.json', tst = existsSync(tfile) ? JSON.parse(readFileSync(tfile, 'utf8')) : { history: [] };
    if (!(tst.history || []).some((h) => h.today === today)) {
      const tr = virtualStep({ vs: tst.vs, today, days, prices, closes, scores: g.scoresTuned || {}, park, scale: 1, etfScores: g.etfScores || {}, stockMaxHold: TUNED.maxHold });
      tst.vs = tr.vs;
      tst.history = [...(tst.history || []), { today, equity: tr.equity, spy: prices.SPY, park: park || 'CASH', stock_signals: Object.keys(g.scoresTuned || {}).length, etf_signals: Object.keys(g.etfScores || {}), orders: tr.done }].slice(-400);
      tst.updated = log.run; writeFileSync(tfile, JSON.stringify(tst, null, 1));
      log.tuned_bot = { equity: tr.equity, signals: Object.keys(g.scoresTuned || {}).length, orders: tr.done.length };
    }
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
