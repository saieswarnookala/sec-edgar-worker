// Bot 12 "Dip bot v3.2" (VIRTUAL paper bot, no broker orders, from Nov 20 2026). Research only, not financial advice.
// v3.0 (Robinhood rules + ETF dips + IEF parking when SPY is below its 100-day average) plus checking during the day:
//   * every ~15 min from 10:00 ET: buy a stock/ETF the moment it meets the normal dip rules (free slots only, 10% each)
//   * every ~15 min: sell a position held >= 1 day as soon as it is +5% above its buy price
//   * ~3:45 pm (15 min before the close, 12:45 on 1 pm half-days, from Alpaca's calendar): the normal v3.0 rules
//     (sell above the 5-day average or after max hold, buy the 3:45 dips, park the rest)
// Backtest (scripts/intraday_exits.py, data/intraday_final.json, 2016-2026, 5-minute bars, fair volume filter, idle money valued by
// time of day): v3.0 27.2%/yr -> v3.2 30.5%, worst -15.8% -> -16.8%, better in 9 of 11 years (worse in calm 2023-2024).
// The backtest checked the target every 5 min; this bot checks every ~15 min (GitHub schedules), so it may sell a bit later.
// A twin (plain v3.0, decided at the same 3:45 run with the same prices) runs alongside for a fair comparison.
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { PAPER, gatherSignals, virtualStep, bondParkSymbol, BOND, BUFFER, SLOTS, WEIGHT, VBOT_START } from './paper-dip.mjs';
import { POOL } from './clear-leader.mjs';
export const V32 = { target: 0.05, firstCheck: 600, finalBefore: 15, minSlot: 0.02 };
const r2 = (x) => +x.toFixed(2);

// One intraday check: +5% target sells, then dip buys into free slots, funded from cash then the parked ETF(s).
export function v32Intraday({ vs, today, days, prices, scores = {}, etfScores = {}, park, mult = null }) {   // mult: per-stock size multipliers (bot 19 v3.3); null = v3.2
  vs = { cash: VBOT_START, positions: [], park: {}, trades: [], ...vs };
  const px = (s, fb) => prices[s] || fb || 0, ti = days.indexOf(today), done = [];
  const parkVal = () => Object.entries(vs.park).reduce((a, [s, q]) => a + q * px(s), 0);
  const equity = vs.cash + vs.positions.reduce((a, p) => a + p.qty * px(p.symbol, p.entry_px), 0) + parkVal();
  // 1) profit target
  const keep = [];
  for (const p of vs.positions) {
    const ei = days.indexOf(p.entry_date), age = ei >= 0 ? ti - ei : 99;
    if (age >= 1 && prices[p.symbol] && prices[p.symbol] >= p.entry_px * (1 + V32.target)) {
      vs.cash += p.qty * prices[p.symbol];
      vs.trades.push({ symbol: p.symbol, kind: p.kind || 'stock', entry_date: p.entry_date, exit_date: today, ret_pct: r2((prices[p.symbol] / p.entry_px - 1) * 100), reason: `target +${V32.target * 100}% during the day`, ...(p.mult ? { mult: p.mult } : {}) });
      done.push(`SELL ${p.symbol} (+${r2((prices[p.symbol] / p.entry_px - 1) * 100)}%, target)`);
    } else keep.push(p);
  }
  vs.positions = keep;
  // 2) dip buys (stocks first, biggest dips first, then ETFs)
  const held = new Set(vs.positions.map((p) => p.symbol));
  const cands = [...Object.entries(scores).filter(([s]) => !POOL.includes(s)).sort((a, b) => a[1] - b[1]).map(([s, r]) => [s, r, null]),
    ...Object.entries(etfScores).sort((a, b) => a[1] - b[1]).map(([s, r]) => [s, r, 'etf'])];
  for (const [s, r, kind] of cands) {
    if (vs.positions.length >= SLOTS) break;
    if (held.has(s) || !(prices[s] > 0)) continue;
    const m = mult && !kind ? (mult[s] ?? 1) : 1, usd = Math.min(WEIGHT * m * equity, vs.cash + parkVal());
    if (usd < V32.minSlot * equity) break;
    let need = usd - vs.cash;                                       // sell parked ETF shares to fund the rest
    for (const [ps, q] of Object.entries(vs.park)) {
      if (need <= 0) break;
      const sell = Math.min(q, need / px(ps)); vs.park[ps] = +(q - sell).toFixed(6); vs.cash += sell * px(ps); need -= sell * px(ps);
      if (vs.park[ps] <= 1e-6) delete vs.park[ps];
    }
    const qty = Math.floor((Math.min(usd, vs.cash) / prices[s]) * 1e6) / 1e6;
    vs.cash -= qty * prices[s]; held.add(s);
    vs.positions.push({ symbol: s, ...(kind ? { kind } : {}), entry_date: today, qty, entry_px: prices[s], dip_pct: r2(r * 100), size_pct: r2(100 * qty * prices[s] / equity), bought_intraday: true, ...(mult && !kind ? { mult: m } : {}) });
    done.push(`BUY $${(qty * prices[s]).toFixed(0)} ${s}${kind ? ' ETF' : ''} (dip ${r2(r * 100)}%, during the day${mult && !kind ? `, ${m}x` : ''})`);
  }
  // 3) money from target sells goes back to the parked ETF (keep a 2% cash buffer), like the backtest
  if (park && prices[park]) { const usd = vs.cash - BUFFER * equity; if (usd >= 1) { const q = Math.floor((usd / prices[park]) * 1e6) / 1e6; vs.park[park] = +((vs.park[park] || 0) + q).toFixed(6); vs.cash -= q * prices[park]; } }
  vs.trades = vs.trades.slice(-300);
  const eqAfter = vs.cash + vs.positions.reduce((a, p) => a + p.qty * px(p.symbol, p.entry_px), 0) + parkVal();
  return { vs, equity: r2(eqAfter), done };
}
export function phase(nyMin, closeMin) {
  if (nyMin < V32.firstCheck || nyMin >= closeMin - 2) return 'closed';
  return nyMin >= closeMin - V32.finalBefore - 5 ? 'final' : 'intraday';   // final window: 3:40-3:57 pm (12:40-12:57 on half-days)
}

async function main() {
  const H = { 'APCA-API-KEY-ID': process.env.APCA_API_KEY_ID, 'APCA-API-SECRET-KEY': process.env.APCA_API_SECRET_KEY };
  const api = async (base, path) => { const r = await fetch(base + path, { headers: H }); const t = await r.text(); if (!r.ok) throw new Error(`${r.status} ${path.split('?')[0]}: ${t.slice(0, 300)}`); return t ? JSON.parse(t) : null; };
  const ny = Object.fromEntries(new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).formatToParts(new Date()).map((x) => [x.type, x.value]));
  let today = `${ny.year}-${ny.month}-${ny.day}`;
  const nyMin = +ny.hour * 60 + +ny.minute, dry = process.env.DRY_RUN === '1';
  const cal = await api(PAPER, `/v2/calendar?start=${new Date(Date.now() - 470 * 86400e3).toISOString().slice(0, 10)}&end=${today}`);
  const days = cal.map((c) => c.date);
  let tc = cal.find((c) => c.date === today);
  if (!tc && dry && process.env.PHASE) { today = days.at(-1); tc = cal.at(-1); console.log('DRY_RUN test on a closed day: replaying', today, 'with the latest prices'); }
  if (!tc) { console.log('market closed today', today); return; }
  const closeMin = +tc.close.slice(0, 2) * 60 + +tc.close.slice(3, 5);
  const file = 'data/paper_v32_state.json', st = existsSync(file) ? JSON.parse(readFileSync(file, 'utf8')) : { history: [], checks: [] };
  const f33 = 'data/paper_v33_state.json', st33 = existsSync(f33) ? JSON.parse(readFileSync(f33, 'utf8')) : { history: [], checks: [] };
  const ph = process.env.PHASE || phase(nyMin, closeMin);
  if (ph === 'closed') { console.log('outside 10:00 ET - close', `${ny.hour}:${ny.minute}`, 'close', tc.close); return; }
  const done32 = !dry && (st.history || []).some((h) => h.today === today), done33 = !dry && (st33.history || []).some((h) => h.today === today);
  if (done32 && done33) { console.log('3:45 step already done today'); return; }
  const g = await gatherSignals({ api, today, days, closeMin });
  const { prices, closes, scores } = g, etfScores = g.etfScores || {};
  const bpark = bondParkSymbol({ park: g.park, bondCloses: closes[BOND], bondPx: prices[BOND] });
  if (!done32) {
    const check = { at: new Date().toISOString(), ny_time: `${ny.hour}:${ny.minute}`, phase: ph, stock_signals: Object.keys(scores), etf_signals: Object.keys(etfScores), park: bpark || 'CASH' };
    if (ph === 'intraday') {
      const r = v32Intraday({ vs: st.vs, today, days, prices, scores, etfScores, park: bpark });
      st.vs = r.vs; Object.assign(check, { equity: r.equity, orders: r.done });
    } else {
      const r = virtualStep({ vs: st.vs, today, days, prices, closes, scores, park: bpark, scale: 1, etfScores });
      const tw = virtualStep({ vs: st.twin, today, days, prices, closes, scores, park: bpark, scale: 1, etfScores });
      st.vs = r.vs; st.twin = tw.vs; Object.assign(check, { equity: r.equity, twin_equity: tw.equity, orders: r.done });
      const todays = (st.checks || []).filter((c) => c.at.slice(0, 10) === check.at.slice(0, 10) && c.phase === 'intraday');
      const prev = days[days.indexOf(today) - 1];
      st.history = [...(st.history || []), { today, equity: r.equity, twin_equity: tw.equity, spy: prices.SPY, park: bpark || 'CASH', stock_signals: Object.keys(scores).length, etf_signals: Object.keys(etfScores),
        intraday_checks: todays.length, intraday_orders: todays.flatMap((c) => (c.orders || []).map((o) => `${c.ny_time} ${o}`)), orders: r.done, twin_orders: tw.done,
        ...(prev && (st.history || []).length && st.history.at(-1).today !== prev ? { missed_previous_345: true } : {}) }].slice(-400);
    }
    st.checks = [...(st.checks || []), check].slice(-200); st.updated = check.at;
    console.log('v3.2', JSON.stringify({ ...check, stock_signals: check.stock_signals.length }, null, 1));
    if (!dry) { mkdirSync('data', { recursive: true }); writeFileSync(file, JSON.stringify(st, null, 1)); }
  }
  // ---- bot 19: v3.3 (same prices, same moment); a failure here never touches bot 12 ----
  if (!done33) {
    try {
      const { runV33 } = await import('./paper-v33.mjs');   // loaded here only, so the live bot (imports V32 from this file) never loads v3.3 code
      const out = await runV33({ st: st33, g, today, days, ph, park: bpark, ny, dry, v32Intraday, virtualStep });
      console.log('v3.3', JSON.stringify(out, null, 1));
      if (!dry) writeFileSync(f33, JSON.stringify(st33, null, 1));
    } catch (e) {
      console.error('v3.3 failed:', e);
      st33.errors = [...(st33.errors || []), { at: new Date().toISOString(), error: String(e.message || e).slice(0, 300) }].slice(-20);
      if (!dry) writeFileSync(f33, JSON.stringify(st33, null, 1));
    }
  }
  if (dry) console.log('DRY_RUN: state not saved');
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main().catch((e) => { console.error(e); process.exit(1); });
