// End-of-day fill report for the phone: sells (bought at / sold at / profit), buys (price / amount / +5% target), parking moves.
// Sent as a table image (PNG, rendered with @resvg/resvg-js + DejaVu fonts when installed) plus a short text; text-only if the image fails.
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';

const num = (x) => (x == null || x === '' ? null : +x);
const money = (v, sign = false) => (v == null ? 'n/a' : (sign ? (v >= 0 ? '+' : '-') : v < 0 ? '-' : '') + '$' + Math.abs(v).toFixed(2));
const pct = (v) => (v == null ? 'n/a' : (v >= 0 ? '+' : '') + v.toFixed(1) + '%');
const t = (o) => new Date(o.created_at || 0).getTime();

/** short reason label from the bot's own order note ('why') */
export function category(why = '', side = 'buy', symbol = '', etfs = []) {
  const w = String(why || '');
  if (/parking/i.test(w)) return /fund/i.test(w) ? 'Parking: cash for dips' : /switch/i.test(w) ? 'Parking: switch fund' : /resize/i.test(w) ? 'Parking: resize' : side === 'buy' ? 'Parking: spare cash' : 'Parking: free cash';
  if (side === 'sell') return /target/i.test(w) ? 'Profit target +5%' : /bounced/i.test(w) ? 'Bounced above 5-day avg' : /held/i.test(w) ? 'Time limit (5 days)' : w ? w.slice(0, 28) : 'Sell';
  const m = w.match(/dip\s*(-?[\d.]+)%/), d = m ? ` ${(+m[1] > 0 ? -m[1] : +m[1]).toFixed(1)}%` : '';
  return (etfs.includes(symbol) ? 'ETF dip' : /intraday|during the day/i.test(w) ? 'Intraday dip' : 'Dip at close') + d;
}

/** orders: everything Robinhood returned (any day); todayFills: today's filled orders; isParking(symbol, side) -> bool */
export function fillReport({ today, orders, todayFills, isParking, equity, prevEquity, vsClosePct, target = 0.05, whyOf = () => '', etfs = [], holding = [] }) {
  const sells = [], buys = [], park = {};
  for (const o of [...todayFills].sort((a, b) => t(a) - t(b))) {
    const px = num(o.avg_price), qty = num(o.filled_qty) ?? num(o.quantity);
    if (!(px > 0) || !(qty > 0)) continue;
    if (isParking(o.symbol, o.side)) { const p = (park[o.symbol] ||= { in: 0, out: 0 }); p[o.side === 'buy' ? 'in' : 'out'] += px * qty; continue; }
    if (o.side === 'sell') {
      const b = orders.filter((x) => x.symbol === o.symbol && x.side === 'buy' && /fill/.test(x.state) && num(x.avg_price) > 0 && t(x) < t(o)).sort((a, b2) => t(b2) - t(a))[0];
      const bp = b ? num(b.avg_price) : null;
      sells.push({ symbol: o.symbol, reason: category(whyOf(o.symbol, 'sell'), 'sell', o.symbol, etfs), buy: bp, sell: px, qty, pl: bp ? (px - bp) * qty : null, plPct: bp ? (px / bp - 1) * 100 : null });
    } else buys.push({ symbol: o.symbol, reason: category(whyOf(o.symbol, 'buy'), 'buy', o.symbol, etfs), price: px, amount: px * qty, target: px * (1 + target) });
  }
  const realized = sells.some((s) => s.pl != null) ? sells.reduce((a, s) => a + (s.pl || 0), 0) : null;
  return { today, sells, buys, park, realized, holding, equity: num(equity), dayChange: equity != null && prevEquity != null ? equity - prevEquity : null, vsClosePct };
}

const dateLabel = (d) => new Date(d + 'T12:00:00Z').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC' });
export function reportTitle(R) {
  return `Dip bot ${dateLabel(R.today)}: ${R.sells.length} sold, ${R.buys.length} bought` + (R.realized != null ? `, profit ${money(R.realized, true)}` : '');
}
export function reportText(R) {
  const L = [];
  if (R.sells.length) { L.push('SOLD (bought -> sold, profit)'); for (const s of R.sells) L.push(`${s.symbol}: ${money(s.buy)} -> ${money(s.sell)}  ${money(s.pl, true)} (${pct(s.plPct)})  [${s.reason}]`); L.push(`Total: ${money(R.realized, true)}`, ''); }
  if (R.buys.length) { L.push('BOUGHT (price, amount, sells at +5%)'); for (const b of R.buys) L.push(`${b.symbol}: ${money(b.price)}  ${money(b.amount)}  target ${money(b.target)}  [${b.reason}]`); L.push(''); }
  if (R.holding?.length) { L.push('HOLDING NOW (bought, now, day of 5)'); for (const h of R.holding) L.push(`${h.symbol}: ${money(h.buy)} -> ${money(h.now)} ${pct(h.pct)}  day ${h.day ?? '?'} of 5`); L.push(''); }
  const pk = Object.entries(R.park);
  if (pk.length) L.push('Parking: ' + pk.map(([s, p]) => `${s} in ${money(p.in)} / out ${money(p.out)}`).join(', '));
  L.push(`Account ${money(R.equity)}` + (R.dayChange != null ? ` (${money(R.dayChange, true)} since last report)` : ''));
  return L.join('\n');
}

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;');
const GREEN = '#15803d', RED = '#b91c1c', INK = '#111827', MUTED = '#6b7280', LINE = '#e5e7eb', HEAD = '#f3f4f6', AMBER = '#b45309';
const tone = (c) => (c == null ? MUTED : c >= 0 ? GREEN : RED);
/** tiny layout helper: title row, sections with tables (cols: {h, w, a}), notes; returns an SVG string */
function sheet(W = 940) {
  const P = 28, RH = 40, out = []; let y = P;
  const text = (x, yy, s, { size = 20, weight = 400, fill = INK, anchor = 'start', mono = false } = {}) =>
    out.push(`<text x="${x}" y="${yy}" font-family="${mono ? 'DejaVu Sans Mono' : 'DejaVu Sans'}" font-size="${size}" font-weight="${weight}" fill="${fill}" text-anchor="${anchor}">${esc(s)}</text>`);
  return {
    header(left, right, sub, subColor = MUTED) {
      text(P, y + 28, left, { size: 28, weight: 700 }); if (right) text(W - P, y + 28, right, { size: 24, weight: 700, anchor: 'end' }); y += 40;
      if (sub) text(W - P, y + 16, sub, { size: 17, fill: subColor, anchor: 'end' }); y += 30;
    },
    table(title, cols, rows, total) {
      if (title) { text(P, y + 26, title, { size: 22, weight: 700 }); y += 40; }
      const w = W - 2 * P, sum = cols.reduce((a, c) => a + c.w, 0), xs = []; let x = P + 12;
      cols.forEach((c, i) => { const cw = (c.w / sum) * (w - 24); xs.push(c.a === 'start' ? x + (i ? 18 : 0) : x + cw - (i < cols.length - 1 ? 18 : 0)); x += cw; });
      out.push(`<rect x="${P}" y="${y}" width="${w}" height="${RH}" rx="6" fill="${HEAD}"/>`);
      cols.forEach((c, i) => text(xs[i], y + 26, c.h, { size: 16, weight: 700, fill: MUTED, anchor: c.a || 'end' })); y += RH;
      for (const r of rows) {
        cols.forEach((c, i) => { const cell = r[i] || {}; text(xs[i], y + 27, cell.v ?? '', { size: c.small ? 17 : 20, weight: i === 0 ? 700 : 400, fill: cell.c || (c.small ? MUTED : INK), anchor: c.a || 'end', mono: !c.small && i > 0 }); });
        y += RH; out.push(`<line x1="${P}" x2="${P + w}" y1="${y}" y2="${y}" stroke="${LINE}" stroke-width="1"/>`);
      }
      if (total) { text(P + w - 12, y + 28, total.v, { size: 20, weight: 700, fill: total.c, anchor: 'end' }); text(P + 12, y + 28, total.label, { size: 18, weight: 700, fill: MUTED }); y += RH; }
      y += 18;
    },
    note(s, c = MUTED, size = 17) { text(P, y + 22, s, { size, fill: c }); y += 32; },
    svg() { const H = y + P - 6; return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}"><rect width="${W}" height="${H}" rx="16" fill="#ffffff"/>${out.join('')}</svg>`; },
  };
}
export function reportSvg(R) {
  const S = sheet();
  S.header(`Dip bot · ${dateLabel(R.today)}`, `Account ${money(R.equity)}`, R.dayChange != null ? `${money(R.dayChange, true)} since last report` : '', tone(R.dayChange));
  if (R.sells.length) S.table('Sold', [{ h: 'Stock', w: 13, a: 'start' }, { h: 'Reason', w: 30, a: 'start', small: true }, { h: 'Bought at', w: 15 }, { h: 'Sold at', w: 15 }, { h: 'Profit', w: 14 }, { h: '%', w: 11 }],
    R.sells.map((s) => [{ v: s.symbol }, { v: s.reason }, { v: money(s.buy) }, { v: money(s.sell) }, { v: money(s.pl, true), c: tone(s.pl) }, { v: pct(s.plPct), c: tone(s.pl) }]),
    { label: 'Total profit', v: money(R.realized, true), c: tone(R.realized) });
  if (R.buys.length) S.table('Bought', [{ h: 'Stock', w: 13, a: 'start' }, { h: 'Reason', w: 30, a: 'start', small: true }, { h: 'Price', w: 17 }, { h: 'Amount', w: 15 }, { h: 'Sells at +5%', w: 20 }],
    R.buys.map((b) => [{ v: b.symbol }, { v: b.reason }, { v: money(b.price) }, { v: money(b.amount) }, { v: money(b.target) }]));
  if (R.holding?.length) S.table('Holding now', [{ h: 'Stock', w: 13, a: 'start' }, { h: 'Bought at', w: 17 }, { h: 'Now', w: 17 }, { h: 'Gain', w: 13 }, { h: 'Sells at +5%', w: 20 }, { h: 'Days held', w: 15 }],
    R.holding.map((h) => [{ v: h.symbol }, { v: money(h.buy) }, { v: money(h.now) }, { v: pct(h.pct), c: tone(h.pct) }, { v: money(h.buy ? h.buy * 1.05 : null) }, { v: h.day != null ? `${h.day} of 5` : '?', c: h.day >= 4 ? AMBER : INK }]));
  const pk = Object.entries(R.park);
  if (pk.length) S.note('Spare cash (parking): ' + pk.map(([s, p]) => `${s} +${money(p.in)} in / -${money(p.out)} out`).join(', '));
  if (R.vsClosePct != null) S.note(`Fill prices vs the close: ${R.vsClosePct >= 0 ? '+' : ''}${R.vsClosePct}% (negative = better than the close)`);
  if (!R.sells.length && !R.buys.length) S.note('No stock trades today.', MUTED, 20);
  return S.svg();
}
/** order alert (3:47 pm step or a 15-minute check) as a table image. D = { title, when, account, free, picked: [{symbol, move, decision}], orders: [{side, symbol, amount, reason, status, ok}], result: [lines], dips } */
export function ordersSvg(D) {
  const S = sheet();
  S.header(D.title, D.account != null ? `Account ${money(D.account)}` : '', (/^\d{4}-\d\d-\d\d$/.test(D.when) ? dateLabel(D.when) : D.when) + (D.free != null ? ` · ${money(D.free)} free to buy` : ''));
  if (D.picked) {
    if (D.picked.length) S.table('1 · Stocks picked (down 10%+ vs SPY in 5 days)', [{ h: 'Stock', w: 16, a: 'start' }, { h: 'vs SPY 5d', w: 18 }, { h: 'Decision', w: 50, a: 'start', small: true }],
      D.picked.map((p) => [{ v: p.symbol }, { v: p.move, c: RED }, { v: p.decision, c: /^BUY/.test(p.decision) ? GREEN : MUTED }]));
    else S.note('1 · Stocks picked: none today, so no new buys', MUTED, 19);
  }
  if (D.orders.length) S.table(D.picked ? '2 · Orders' : 'Orders', [{ h: 'Action', w: 12, a: 'start' }, { h: 'Stock', w: 13, a: 'start' }, { h: 'Amount', w: 16 }, { h: 'Reason', w: 32, a: 'start', small: true }, { h: 'Status', w: 18, a: 'start', small: true }],
    D.orders.map((o) => [{ v: o.side.toUpperCase(), c: o.side === 'sell' ? RED : GREEN }, { v: o.symbol }, { v: o.amount }, { v: o.reason }, { v: o.status, c: o.ok ? GREEN : o.ok === false ? RED : MUTED }]));
  else S.note((D.picked ? '2 · ' : '') + 'Orders: none', MUTED, 19);
  for (const l of D.result || []) S.note(l);
  return S.svg();
}
/** PNG bytes, or null when the optional renderer / fonts are not installed */
export async function reportPng(svg) {
  try {
    const { Resvg } = await import('@resvg/resvg-js');
    const req = createRequire(import.meta.url);
    const dir = join(dirname(req.resolve('dejavu-fonts-ttf/package.json')), 'ttf');
    const r = new Resvg(svg, { fitTo: { mode: 'zoom', value: 2 }, font: { loadSystemFonts: false, fontFiles: ['DejaVuSans.ttf', 'DejaVuSans-Bold.ttf', 'DejaVuSansMono.ttf', 'DejaVuSansMono-Bold.ttf'].map((f) => join(dir, f)), defaultFontFamily: 'DejaVu Sans' } });
    return Buffer.from(r.render().asPng());
  } catch (e) { console.error('report image skipped:', e.message); return null; }
}
