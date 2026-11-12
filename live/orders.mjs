// Pure helpers for the live runner: turn the strategy's plan into Robinhood MCP calls, enforce hard limits,
// and read Robinhood replies whose exact field names are not documented (tolerant, fail closed).
// Exact tool parameter names come from the server's own tool schemas (saved by `node live-dip.mjs doctor`).

// ---- tolerant readers ----
const isObj = (x) => x && typeof x === 'object';
export function deepFind(o, re, depth = 0) {
  if (!isObj(o) || depth > 6) return undefined;
  for (const [k, v] of Object.entries(o)) if (re.test(k) && (typeof v === 'number' || (typeof v === 'string' && v.trim() !== '' && !isNaN(+v)))) return +v;
  for (const [k, v] of Object.entries(o)) if (re.test(k) && isObj(v)) { const r = deepFind(v, /^(amount|value)$/i, depth + 1); if (r !== undefined) return r; }
  for (const v of Object.values(o)) { const r = deepFind(v, re, depth + 1); if (r !== undefined) return r; }
  return undefined;
}
export function arraysIn(o, depth = 0, out = []) {
  if (Array.isArray(o)) { out.push(o); o.forEach((x) => arraysIn(x, depth + 1, out)); }
  else if (isObj(o) && depth < 6) Object.values(o).forEach((v) => arraysIn(v, depth + 1, out));
  return out;
}
const symOf = (x) => x.symbol ?? x.ticker ?? x.instrument_symbol ?? x.instrument?.symbol;
// positions -> { SYMBOL: quantity }
export function readPositions(data) {
  const held = {};
  for (const arr of arraysIn(data)) for (const x of arr) {
    if (!isObj(x)) continue;
    const s = symOf(x), q = deepFind(x, /^(quantity|qty|shares)$/i);
    if (typeof s === 'string' && q > 0) held[s.toUpperCase()] = (held[s.toUpperCase()] || 0) + q;
  }
  return held;
}
// orders -> [{ id, symbol, side, state, created_at, filled_qty, avg_price, notional, quantity }]
export function readOrders(data) {
  const out = [];
  for (const arr of arraysIn(data)) for (const x of arr) {
    if (!isObj(x) || typeof symOf(x) !== 'string' || !(x.side || x.direction)) continue;
    out.push({ id: x.id ?? x.order_id, symbol: symOf(x).toUpperCase(), side: String(x.side || x.direction).toLowerCase(), state: String(x.state ?? x.status ?? '').toLowerCase(),
      created_at: x.created_at ?? x.submitted_at ?? x.created, filled_qty: deepFind(x, /^(cumulative_quantity|filled_quantity|filled_qty)$/i) ?? null,
      avg_price: deepFind(x, /^(average_price|avg_price|average_fill_price|filled_avg_price)$/i) ?? null, quantity: deepFind(x, /^(quantity|qty)$/i) ?? null,
      notional: deepFind(x, /^(dollar_amount|notional|amount)$/i) ?? null });
  }
  const seen = new Set(); return out.filter((o) => (o.id ? !seen.has(o.id) && seen.add(o.id) : true));
}
export function readMoney(data) {
  return { equity: deepFind(data, /^(total_value|equity|portfolio_value|total_equity|account_value)$/i), buying_power: deepFind(data, /buying_power/i) };
}

// ---- schema-driven argument building ----
import { createHash } from 'node:crypto';
// Robinhood takes amounts as strings ("100.00"); keep numbers if a schema ever asks for numbers.
const fmt = (prop, v, dp) => { const f = Math.floor(v * 10 ** dp + 1e-9) / 10 ** dp; return prop?.type === 'string' ? f.toFixed(dp).replace(dp > 2 ? /\.?0+$/ : /$^/, '') : f; };
// Same order on the same day -> same idempotency key, so a retry or the backup run can't place it twice.
export const refId = (key) => { const h = createHash('sha256').update(String(key)).digest('hex'); return `${h.slice(0, 8)}-${h.slice(8, 12)}-4${h.slice(13, 16)}-${'89ab'[parseInt(h[16], 16) % 4]}${h.slice(17, 20)}-${h.slice(20, 32)}`; };
const props = (schema) => schema?.inputSchema?.properties || schema?.properties || {};
const required = (schema) => schema?.inputSchema?.required || schema?.required || [];
const pick = (p, res) => { for (const re of res) { const k = Object.keys(p).find((x) => re.test(x)); if (k) return k; } return null; };
const enumVal = (prop, want) => { const e = prop?.enum; if (!e) return want; return e.find((v) => String(v).toLowerCase() === want) ?? e.find((v) => String(v).toLowerCase().includes(want)); };
// order: { symbol, side: 'buy'|'sell', shares?: number, dollars?: number }
export function buildOrderArgs(schema, order, account) {
  const p = props(schema), args = {}, need = new Set(required(schema));
  const kAcct = pick(p, [/^account(_number|_id)?$/i, /account/i]), kSym = pick(p, [/^symbol$/i, /ticker/i, /symbol/i]), kSide = pick(p, [/^side$/i, /side|direction/i]);
  const kType = pick(p, [/^(order_)?type$/i]), kQty = pick(p, [/^quantity$/i, /^(qty|shares)$/i]), kUsd = pick(p, [/dollar/i, /notional/i, /^amount$/i]);
  const kTif = pick(p, [/time_in_force|^tif$/i]);
  const miss = (what) => ({ ok: false, error: `cannot map ${what} onto place_equity_order schema (${Object.keys(p).join(', ')})` });
  if (!kSym) return miss('symbol'); if (!kSide) return miss('side');
  if (kAcct && account) args[kAcct] = account;   // no account field: the MCP only trades the agentic account anyway
  args[kSym] = order.symbol;
  const side = enumVal(p[kSide], order.side); if (!side) return miss('side value ' + order.side); args[kSide] = side;
  if (order.dollars != null) {
    if (kUsd) args[kUsd] = fmt(p[kUsd], order.dollars, 2);
    else return miss('dollar amount');
    if (kType) { const t = enumVal(p[kType], 'market'); if (!t) return miss('market type'); args[kType] = t; }
  } else {
    if (!kQty) return miss('quantity'); args[kQty] = fmt(p[kQty], +order.shares, 6);
    if (kType) { const t = enumVal(p[kType], 'market'); if (!t) return miss('market type'); args[kType] = t; }
  }
  if (kTif) { const t = enumVal(p[kTif], 'gfd') ?? enumVal(p[kTif], 'day'); if (t) args[kTif] = t; }
  const kHours = pick(p, [/^market_hours$/i]); if (kHours) { const h = enumVal(p[kHours], 'regular_hours'); if (h) args[kHours] = h; }
  const kRef = pick(p, [/^ref_id$/i, /idempoten/i]); if (kRef && order.refKey) args[kRef] = refId(order.refKey);
  // optional marker for which variant (some schemas split dollar vs share orders with a flag)
  const kBasis = pick(p, [/^(order_)?basis$|amount_type|size_type|quantity_type/i]);
  if (kBasis) { const want = order.dollars != null ? 'dollar' : 'share'; const v = enumVal(p[kBasis], want) ?? enumVal(p[kBasis], want === 'dollar' ? 'notional' : 'quantity'); if (v) args[kBasis] = v; }
  for (const r of need) if (!(r in args)) return miss('required field ' + r);
  return { ok: true, args };
}

// ---- strategy plan -> broker orders (sells first, then buys) ----
// plan = decide() output; prices = live prices; fractionalOk(symbol) -> bool
export function planToOrders(plan, prices, fractionalOk = () => true) {
  const out = [];
  for (const t of plan.parkTrades.filter((x) => x.side === 'sell')) out.push({ symbol: t.symbol, side: 'sell', shares: t.qty, why: t.reason });
  for (const s of plan.sells) out.push({ symbol: s.symbol, side: 'sell', shares: s.qty, why: s.reason });
  for (const b of plan.buys) out.push(fractionalOk(b.symbol) ? { symbol: b.symbol, side: 'buy', dollars: b.qty * prices[b.symbol], why: `dip ${b.dip_pct}%` } : { symbol: b.symbol, side: 'buy', shares: Math.floor(b.qty), why: `dip ${b.dip_pct}% (whole shares)` });
  for (const t of plan.parkTrades.filter((x) => x.side === 'buy')) out.push(fractionalOk(t.symbol) ? { symbol: t.symbol, side: 'buy', dollars: t.qty * prices[t.symbol], why: 'parking' } : { symbol: t.symbol, side: 'buy', shares: Math.floor(t.qty), why: 'parking (whole shares)' });
  return out.filter((o) => (o.dollars ?? o.shares) > 0);
}

// ---- hard limits (fail closed) ----
export function checkLimits(orders, { equity, held, prices, allowed, maxOrderUsd, maxOrders = 25 }) {
  const problems = [];
  if (!(equity > 0)) problems.push('equity unknown');
  if (orders.length > maxOrders) problems.push(`too many orders (${orders.length} > ${maxOrders})`);
  const seen = new Set();
  for (const o of orders) {
    const key = o.symbol + o.side; if (seen.has(key)) problems.push('duplicate order ' + key); seen.add(key);
    if (!/^[A-Z][A-Z.]{0,5}$/.test(o.symbol)) problems.push('bad symbol ' + o.symbol);
    if (!allowed.has(o.symbol)) problems.push('symbol not in strategy universe ' + o.symbol);
    const usd = o.dollars ?? o.shares * (prices[o.symbol] || 0);
    if (!(usd > 0)) problems.push('no price for ' + o.symbol);
    if (o.side === 'buy' && usd > maxOrderUsd) problems.push(`order too big ${o.symbol} $${usd.toFixed(2)} > $${maxOrderUsd}`);
    if (o.side === 'sell' && !(held[o.symbol] >= o.shares - 1e-6)) problems.push(`selling more ${o.symbol} than held (${o.shares} > ${held[o.symbol] || 0})`);
  }
  const buys = orders.filter((o) => o.side === 'buy').reduce((a, o) => a + (o.dollars ?? o.shares * prices[o.symbol]), 0);
  if (buys > equity * 1.01) problems.push(`buys $${buys.toFixed(0)} exceed account value $${equity.toFixed(0)}`);
  return problems;
}

// Scale buys down to what is actually spendable (after sells settle into limited-margin buying power).
export function fitBuys(orders, buyingPower, prices, keep = 0.995) {
  const buys = orders.filter((o) => o.side === 'buy'), tot = buys.reduce((a, o) => a + (o.dollars ?? o.shares * prices[o.symbol]), 0);
  if (!(tot > buyingPower * keep)) return orders;
  const f = (buyingPower * keep) / tot;
  return orders.map((o) => (o.side !== 'buy' ? o : o.dollars != null ? { ...o, dollars: Math.floor(o.dollars * f * 100) / 100, scaled: +f.toFixed(3) } : { ...o, shares: Math.floor(o.shares * f), scaled: +f.toFixed(3) })).filter((o) => (o.dollars ?? o.shares) > 0);
}
