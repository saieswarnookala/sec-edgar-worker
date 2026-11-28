// Weekly / monthly summaries for the live dip bot: a small trade ledger kept in the state file + the daily account values from 'verify'.
import { fillReport } from './report.mjs';

export const mondayOf = (d) => { const t = new Date(d + 'T12:00:00Z'), k = (t.getUTCDay() + 6) % 7; t.setUTCDate(t.getUTCDate() - k); return t.toISOString().slice(0, 10); };
export const weekKey = (d) => mondayOf(d);
export const monthKey = (d) => d.slice(0, 7);

/** add one day's sells/buys (from fillReport) to the ledger; idempotent */
export function addToLedger(ledger, date, R) {
  const key = (x) => `${x.date}:${x.side}:${x.symbol}:${(+x.price).toFixed(4)}`, have = new Set(ledger.map(key));
  const rows = [...R.sells.map((s) => ({ date, side: 'sell', symbol: s.symbol, reason: s.reason, buy: s.buy, sell: s.sell, price: s.sell, qty: s.qty, pl: s.pl, plPct: s.plPct })),
    ...R.buys.map((b) => ({ date, side: 'buy', symbol: b.symbol, reason: b.reason, price: b.price, amount: b.amount }))];
  for (const r of rows) if (!have.has(key(r))) { ledger.push(r); have.add(key(r)); }
  return ledger.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
}

/** rebuild past days from Robinhood's order list (first run only). dateOf(order) -> 'YYYY-MM-DD' (New York). */
export function backfillLedger({ orders, before, dateOf, whysFor, isParkingFor, etfs = [] }) {
  const byDay = {};
  for (const o of orders) { if (!/fill/.test(o.state) || !(+o.avg_price > 0)) continue; const d = dateOf(o); if (d && d < before) (byDay[d] ||= []).push(o); }
  const ledger = [];
  for (const d of Object.keys(byDay).sort()) {
    const whys = whysFor(d), whyOf = (s, side) => { const w = whys[s + ':' + side] || []; return w.find((x) => !/parking/i.test(x)) ?? w[0] ?? ''; };
    addToLedger(ledger, d, fillReport({ today: d, orders, todayFills: byDay[d], isParking: isParkingFor(whys), whyOf, etfs }));
  }
  return ledger;
}

const eqBefore = (verify, d) => [...verify].filter((v) => v.today < d && v.equity > 0).at(-1)?.equity ?? null;
const eqFirstFrom = (verify, d) => verify.find((v) => v.today >= d && v.equity > 0)?.equity ?? null;
const dayFirstFrom = (verify, d) => verify.find((v) => v.today >= d && v.equity > 0)?.today ?? d;
/** SPY start: the close before the period, or (if the bot started mid-period) the close of the bot's first day */
const spyStart = (spy, verify, d) => (eqBefore(verify, d) != null ? closeBefore(spy, d) : closeUpTo(spy, dayFirstFrom(verify, d)));
const eqLastUpTo = (verify, d) => [...verify].filter((v) => v.today <= d && v.equity > 0).at(-1)?.equity ?? null;
const closeUpTo = (spy, d) => { const k = Object.keys(spy).filter((x) => x <= d).sort().at(-1); return k ? spy[k] : null; };
const closeBefore = (spy, d) => { const k = Object.keys(spy).filter((x) => x < d).sort().at(-1); return k ? spy[k] : null; };

export function weeklyData({ ledger, verify, today, holding = [], spy = {} }) {
  const from = mondayOf(today), sells = ledger.filter((x) => x.side === 'sell' && x.date >= from && x.date <= today);
  const s0 = spyStart(spy, verify, from), s1 = closeUpTo(spy, today);
  return { from, to: today, startEq: eqBefore(verify, from) ?? eqFirstFrom(verify, from), endEq: eqLastUpTo(verify, today), spyPct: s0 && s1 ? (s1 / s0 - 1) * 100 : null,
    sells, buys: ledger.filter((x) => x.side === 'buy' && x.date >= from && x.date <= today).length, holding };
}

export function monthlyData({ ledger, verify, today, spy = {} }) {
  const months = [...new Set([...verify.filter((v) => v.equity > 0).map((v) => monthKey(v.today)), ...ledger.map((x) => monthKey(x.date))])].filter((m) => m <= monthKey(today)).sort();
  const rows = months.map((m) => {
    const first = m + '-01', last = m + '-31', sells = ledger.filter((x) => x.side === 'sell' && monthKey(x.date) === m);
    const s0 = spyStart(spy, verify, first), s1 = closeUpTo(spy, last);
    return { month: m, startEq: eqBefore(verify, first) ?? eqFirstFrom(verify, first), endEq: eqLastUpTo(verify, last), spyPct: s0 && s1 ? (s1 / s0 - 1) * 100 : null,
      realized: sells.reduce((a, x) => a + (x.pl || 0), 0), trades: sells.length, wins: sells.filter((x) => x.pl > 0).length };
  });
  return { month: monthKey(today), rows };
}
