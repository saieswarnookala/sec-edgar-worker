// End-of-day fill report for the phone: sells (bought at / sold at / profit), buys (price / amount / +5% target), parking moves.
// Sent as a table image (PNG, rendered with @resvg/resvg-js + DejaVu fonts when installed) plus a short text; text-only if the image fails.
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';

const num = (x) => (x == null || x === '' ? null : +x);
const money = (v, sign = false) => (v == null ? 'n/a' : (sign ? (v >= 0 ? '+' : '-') : v < 0 ? '-' : '') + '$' + Math.abs(v).toFixed(2));
const pct = (v) => (v == null ? 'n/a' : (v >= 0 ? '+' : '') + v.toFixed(1) + '%');
const t = (o) => new Date(o.created_at || 0).getTime();

/** orders: everything Robinhood returned (any day); todayFills: today's filled orders; isParking(symbol, side) -> bool */
export function fillReport({ today, orders, todayFills, isParking, equity, prevEquity, vsClosePct, target = 0.05 }) {
  const sells = [], buys = [], park = {};
  for (const o of [...todayFills].sort((a, b) => t(a) - t(b))) {
    const px = num(o.avg_price), qty = num(o.filled_qty) ?? num(o.quantity);
    if (!(px > 0) || !(qty > 0)) continue;
    if (isParking(o.symbol, o.side)) { const p = (park[o.symbol] ||= { in: 0, out: 0 }); p[o.side === 'buy' ? 'in' : 'out'] += px * qty; continue; }
    if (o.side === 'sell') {
      const b = orders.filter((x) => x.symbol === o.symbol && x.side === 'buy' && /fill/.test(x.state) && num(x.avg_price) > 0 && t(x) < t(o)).sort((a, b2) => t(b2) - t(a))[0];
      const bp = b ? num(b.avg_price) : null;
      sells.push({ symbol: o.symbol, buy: bp, sell: px, qty, pl: bp ? (px - bp) * qty : null, plPct: bp ? (px / bp - 1) * 100 : null });
    } else buys.push({ symbol: o.symbol, price: px, amount: px * qty, target: px * (1 + target) });
  }
  const realized = sells.some((s) => s.pl != null) ? sells.reduce((a, s) => a + (s.pl || 0), 0) : null;
  return { today, sells, buys, park, realized, equity: num(equity), dayChange: equity != null && prevEquity != null ? equity - prevEquity : null, vsClosePct };
}

const dateLabel = (d) => new Date(d + 'T12:00:00Z').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC' });
export function reportTitle(R) {
  return `Dip bot ${dateLabel(R.today)}: ${R.sells.length} sold, ${R.buys.length} bought` + (R.realized != null ? `, profit ${money(R.realized, true)}` : '');
}
export function reportText(R) {
  const L = [];
  if (R.sells.length) { L.push('SOLD (bought -> sold, profit)'); for (const s of R.sells) L.push(`${s.symbol}: ${money(s.buy)} -> ${money(s.sell)}  ${money(s.pl, true)} (${pct(s.plPct)})`); L.push(`Total: ${money(R.realized, true)}`, ''); }
  if (R.buys.length) { L.push('BOUGHT (price, amount, sells at +5%)'); for (const b of R.buys) L.push(`${b.symbol}: ${money(b.price)}  ${money(b.amount)}  target ${money(b.target)}`); L.push(''); }
  const pk = Object.entries(R.park);
  if (pk.length) L.push('Parking: ' + pk.map(([s, p]) => `${s} in ${money(p.in)} / out ${money(p.out)}`).join(', '));
  L.push(`Account ${money(R.equity)}` + (R.dayChange != null ? ` (${money(R.dayChange, true)} since last report)` : ''));
  return L.join('\n');
}

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;');
export function reportSvg(R) {
  const W = 760, P = 28, RH = 40, F = 'DejaVu Sans';
  const GREEN = '#15803d', RED = '#b91c1c', INK = '#111827', MUTED = '#6b7280', LINE = '#e5e7eb', HEAD = '#f3f4f6';
  let y = P, out = [];
  const text = (x, yy, s, { size = 20, weight = 400, fill = INK, anchor = 'start', mono = false } = {}) =>
    out.push(`<text x="${x}" y="${yy}" font-family="${mono ? 'DejaVu Sans Mono' : F}" font-size="${size}" font-weight="${weight}" fill="${fill}" text-anchor="${anchor}">${esc(s)}</text>`);
  const table = (title, cols, rows, total) => {
    text(P, y + 26, title, { size: 22, weight: 700 }); y += 40;
    const x0 = P, w = W - 2 * P;
    out.push(`<rect x="${x0}" y="${y}" width="${w}" height="${RH}" rx="6" fill="${HEAD}"/>`);
    cols.forEach((c) => text(c.x, y + 26, c.h, { size: 17, weight: 700, fill: MUTED, anchor: c.a || 'end' })); y += RH;
    for (const r of rows) {
      cols.forEach((c, i) => text(c.x, y + 27, r[i].v, { size: 20, weight: i === 0 ? 700 : 400, fill: r[i].c || INK, anchor: c.a || 'end', mono: i > 0 }));
      y += RH; out.push(`<line x1="${x0}" x2="${x0 + w}" y1="${y}" y2="${y}" stroke="${LINE}" stroke-width="1"/>`);
    }
    if (total) { text(x0 + w - 8, y + 28, total.v, { size: 20, weight: 700, fill: total.c, anchor: 'end' }); text(x0 + 8, y + 28, total.label, { size: 18, weight: 700, fill: MUTED }); y += RH; }
    y += 18;
  };
  text(P, y + 28, `Dip bot · ${dateLabel(R.today)}`, { size: 28, weight: 700 });
  text(W - P, y + 28, `Account ${money(R.equity)}`, { size: 24, weight: 700, anchor: 'end' }); y += 40;
  if (R.dayChange != null) { text(W - P, y + 16, `${money(R.dayChange, true)} since last report`, { size: 17, fill: R.dayChange >= 0 ? GREEN : RED, anchor: 'end' }); }
  y += 30;
  const col = (c) => (c == null ? MUTED : c >= 0 ? GREEN : RED);
  if (R.sells.length) table('Sold', [{ h: 'Stock', x: P + 12, a: 'start' }, { h: 'Bought at', x: 300 }, { h: 'Sold at', x: 440 }, { h: 'Profit', x: 590 }, { h: '%', x: W - P - 12 }],
    R.sells.map((s) => [{ v: s.symbol }, { v: money(s.buy) }, { v: money(s.sell) }, { v: money(s.pl, true), c: col(s.pl) }, { v: pct(s.plPct), c: col(s.pl) }]),
    { label: 'Total profit', v: money(R.realized, true), c: col(R.realized) });
  if (R.buys.length) table('Bought', [{ h: 'Stock', x: P + 12, a: 'start' }, { h: 'Price', x: 330 }, { h: 'Amount', x: 510 }, { h: 'Sells at (+5%)', x: W - P - 12 }],
    R.buys.map((b) => [{ v: b.symbol }, { v: money(b.price) }, { v: money(b.amount) }, { v: money(b.target) }]));
  const pk = Object.entries(R.park);
  if (pk.length) { text(P, y + 22, 'Spare cash (parking): ' + pk.map(([s, p]) => `${s} +${money(p.in)} in / -${money(p.out)} out`).join(', '), { size: 17, fill: MUTED }); y += 34; }
  if (R.vsClosePct != null) { text(P, y + 22, `Fill prices vs the close: ${R.vsClosePct >= 0 ? '+' : ''}${R.vsClosePct}% (negative = better than the close)`, { size: 17, fill: MUTED }); y += 34; }
  if (!R.sells.length && !R.buys.length) { text(P, y + 26, 'No stock trades today.', { size: 20, fill: MUTED }); y += 40; }
  const H = y + P - 10;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}"><rect width="${W}" height="${H}" rx="16" fill="#ffffff"/>${out.join('')}</svg>`;
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
