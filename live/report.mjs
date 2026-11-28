// End-of-day fill report for the phone: sells (bought at / sold at / profit), buys (price / amount / +5% target), parking moves.
// Sent as a table image (PNG, rendered with @resvg/resvg-js + DejaVu fonts when installed) plus a short text; text-only if the image fails.
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';

const num = (x) => (x == null || x === '' ? null : +x);
const money = (v, sign = false) => (v == null ? 'n/a' : (sign ? (v >= 0 ? '+' : '-') : v < 0 ? '-' : '') + '$' + Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
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
// Sentinel dark theme
const C = { bg: '#0b1220', card: '#111a2e', card2: '#0f1729', line: '#1f2a44', ink: '#e6edf7', muted: '#8a97b1', dim: '#5b6785', green: '#22c55e', red: '#f43f5e', amber: '#f59e0b', blue: '#38bdf8', violet: '#a78bfa', brand: '#38bdf8' };
const tone = (c) => (c == null ? C.muted : c >= 0 ? C.green : C.red);
const PILL = (label) => /target/i.test(label) ? C.green : /bounce/i.test(label) ? C.blue : /time limit/i.test(label) ? C.amber : /parking/i.test(label) ? C.dim : /dip/i.test(label) ? C.violet : C.muted;
const arrow = (v) => (v == null ? '' : v >= 0 ? '▲ ' : '▼ ');
function sheet(W = 960) {
  const P = 32, RH = 46, out = []; let y = P;
  const text = (x, yy, s, { size = 20, weight = 400, fill = C.ink, anchor = 'start', mono = false, ls = 0 } = {}) =>
    out.push(`<text x="${x}" y="${yy}" font-family="${mono ? 'DejaVu Sans Mono' : 'DejaVu Sans'}" font-size="${size}" font-weight="${weight}" fill="${fill}" text-anchor="${anchor}"${ls ? ` letter-spacing="${ls}"` : ''}>${esc(s)}</text>`);
  const rect = (x, yy, w, h, fill, r = 10, stroke) => out.push(`<rect x="${x}" y="${yy}" width="${w}" height="${h}" rx="${r}" fill="${fill}"${stroke ? ` stroke="${stroke}" stroke-width="1"` : ''}/>`);
  const tw = (s, size) => String(s).length * size * 0.68;
  return {
    brand(sub, right) {
      // logo: shield with a pulse line
      out.push(`<g transform="translate(${P},${y})"><path d="M22 2 L40 9 V22 C40 33 32 40 22 44 C12 40 4 33 4 22 V9 Z" fill="${C.card}" stroke="${C.brand}" stroke-width="2.5"/><polyline points="10,25 17,25 20,17 24,31 27,22 34,22" fill="none" stroke="${C.brand}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/></g>`);
      text(P + 56, y + 22, 'SENTINEL', { size: 22, weight: 700, ls: 4 }); text(P + 56, y + 44, sub, { size: 16, fill: C.muted });
      if (right) text(W - P, y + 30, right, { size: 16, fill: C.muted, anchor: 'end' });
      y += 66;
    },
    kpis(items) {
      const g = 14, w = (W - 2 * P - g * (items.length - 1)) / items.length;
      items.forEach((k, i) => { const x = P + i * (w + g); rect(x, y, w, 108, C.card, 12, C.line); text(x + 18, y + 30, k.label.toUpperCase(), { size: 13, weight: 700, fill: C.muted, ls: 1 }); text(x + 18, y + 66, k.value, { size: 26, weight: 700, fill: k.color || C.ink }); if (k.sub) text(x + 18, y + 92, k.sub, { size: 15, fill: k.subColor || C.muted }); });
      y += 108 + 26;
    },
    section(title, right) { text(P, y + 20, title.toUpperCase(), { size: 15, weight: 700, fill: C.muted, ls: 2 }); if (right) text(W - P, y + 20, right.v, { size: 17, weight: 700, fill: right.c || C.ink, anchor: 'end' }); y += 34; },
    table(cols, rows) {
      const w = W - 2 * P, sum = cols.reduce((a, c) => a + c.w, 0), xs = [], ws = []; let x = P + 16;
      cols.forEach((c, i) => { const cw = (c.w / sum) * (w - 32); ws.push(cw); xs.push(c.a === 'start' ? x + (i ? 10 : 0) : x + cw - (i < cols.length - 1 ? 10 : 0)); x += cw; });
      rect(P, y, w, RH * (rows.length + 1), C.card, 12, C.line);
      cols.forEach((c, i) => text(xs[i], y + 29, c.h.toUpperCase(), { size: 12, weight: 700, fill: C.dim, anchor: c.a || 'end', ls: 1 }));
      y += RH;
      rows.forEach((r, ri) => {
        if (ri % 2 === 0 && ri < rows.length - 1) out.push(`<rect x="${P + 1}" y="${y}" width="${w - 2}" height="${RH}" fill="${C.card2}"/>`);
        out.push(`<line x1="${P + 1}" x2="${P + w - 1}" y1="${y}" y2="${y}" stroke="${C.line}" stroke-width="1"/>`);
        cols.forEach((c, i) => {
          const cell = r[i] || {};
          if (cell.pill) { const pw = tw(cell.v, 15) + 22, px = xs[i]; out.push(`<rect x="${px}" y="${y + 11}" width="${pw}" height="25" rx="12.5" fill="${cell.pill}" fill-opacity="0.16" stroke="${cell.pill}" stroke-opacity="0.45"/>`); text(px + 11, y + 29, cell.v, { size: 15, weight: 700, fill: cell.pill }); return; }
          if (cell.bar) { const n = cell.bar.n ?? 0, of = cell.bar.of, sw = 14, gap = 4, x0 = xs[i] - of * (sw + gap) + gap; for (let k = 0; k < of; k++) out.push(`<rect x="${x0 + k * (sw + gap)}" y="${y + 16}" width="${sw}" height="14" rx="3" fill="${k < n ? (n >= of - 1 ? C.amber : C.brand) : C.line}"/>`); return; }
          text(xs[i], y + 30, cell.v ?? '', { size: i === 0 ? 20 : 19, weight: i === 0 || cell.b ? 700 : 400, fill: cell.c || C.ink, anchor: c.a || 'end', mono: i > 0 && !c.text });
        });
        y += RH;
      });
      y += 24;
    },
    note(s, c = C.muted, size = 15) { text(P, y + 18, s, { size, fill: c }); y += 28; },
    svg(foot) {
      y += 6; out.push(`<line x1="${P}" x2="${W - P}" y1="${y}" y2="${y}" stroke="${C.line}" stroke-width="1"/>`);
      text(P, y + 28, foot || 'Sentinel · automated report', { size: 13, fill: C.dim }); text(W - P, y + 28, 'Not financial advice', { size: 13, fill: C.dim, anchor: 'end' });
      const H = y + 46; return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}"><rect width="${W}" height="${H}" fill="${C.bg}"/>${out.join('')}</svg>`;
    },
  };
}
export function reportSvg(R) {
  const S = sheet();
  S.brand('Dip bot · End-of-day report', dateLabel(R.today));
  const wins = R.sells.filter((x) => x.pl > 0).length;
  S.kpis([{ label: 'Account', value: money(R.equity) },
    { label: 'Since last report', value: (R.dayChange == null ? 'n/a' : arrow(R.dayChange) + money(Math.abs(R.dayChange))), color: tone(R.dayChange), sub: R.dayChange != null && R.equity ? pct((R.dayChange / (R.equity - R.dayChange)) * 100) : '', subColor: tone(R.dayChange) },
    { label: 'Realized today', value: R.realized == null ? '$0.00' : money(R.realized, true), color: tone(R.realized), sub: R.sells.length ? `${wins}/${R.sells.length} wins` : '' },
    { label: 'Positions', value: `${R.holding?.length ?? 0} / 10`, sub: 'dip slots' }]);
  if (R.sells.length) { S.section('Sold', { v: 'Total ' + money(R.realized, true), c: tone(R.realized) });
    S.table([{ h: 'Stock', w: 11, a: 'start' }, { h: 'Reason', w: 29, a: 'start' }, { h: 'Bought', w: 14 }, { h: 'Sold', w: 14 }, { h: 'Profit', w: 14 }, { h: 'Return', w: 12 }],
      R.sells.map((x) => [{ v: x.symbol }, { v: x.reason, pill: PILL(x.reason) }, { v: money(x.buy) }, { v: money(x.sell) }, { v: money(x.pl, true), c: tone(x.pl), b: true }, { v: arrow(x.plPct) + pct(x.plPct).replace(/^[+-]/, ''), c: tone(x.pl) }])); }
  if (R.buys.length) { S.section('Bought');
    S.table([{ h: 'Stock', w: 11, a: 'start' }, { h: 'Reason', w: 31, a: 'start' }, { h: 'Price', w: 15 }, { h: 'Amount', w: 14 }, { h: 'Target +5%', w: 16 }],
      R.buys.map((x) => [{ v: x.symbol }, { v: x.reason, pill: PILL(x.reason) }, { v: money(x.price) }, { v: money(x.amount) }, { v: money(x.target), c: C.green }])); }
  if (R.holding?.length) { S.section('Holding now');
    S.table([{ h: 'Stock', w: 11, a: 'start' }, { h: 'Bought', w: 14 }, { h: 'Now', w: 14 }, { h: 'Gain', w: 13 }, { h: 'Target +5%', w: 15 }, { h: 'Days held (max 5)', w: 21 }],
      R.holding.map((h) => [{ v: h.symbol }, { v: money(h.buy) }, { v: money(h.now) }, { v: arrow(h.pct) + pct(h.pct).replace(/^[+-]/, ''), c: tone(h.pct) }, { v: money(h.buy ? h.buy * 1.05 : null) }, { bar: { n: h.day ?? 0, of: 5 } }])); }
  if (!R.sells.length && !R.buys.length) S.note('No stock trades today.', C.muted, 17);
  const pk = Object.entries(R.park);
  if (pk.length) S.note('Spare cash (parking): ' + pk.map(([sy, p]) => `${sy}  in ${money(p.in)} · out ${money(p.out)}`).join('   '));
  if (R.vsClosePct != null) S.note(`Fill quality: ${R.vsClosePct >= 0 ? '+' : ''}${R.vsClosePct}% vs the closing price (negative = better than the close)`);
  return S.svg('Sentinel · dip strategy v3.2 · fills from Robinhood');
}
/** order alert (3:47 pm step or a 15-minute check). D = { title, when, account, free, picked, orders, result, slotsUsed, slots } */
export function ordersSvg(D) {
  const S = sheet();
  const when = /^\d{4}-\d\d-\d\d$/.test(D.when) ? dateLabel(D.when) : D.when;
  S.brand(D.title, when);
  const placed = D.orders.filter((o) => o.ok).length, bad = D.orders.filter((o) => o.ok === false).length;
  S.kpis([{ label: 'Account', value: D.account != null ? money(D.account) : 'n/a' }, { label: 'Free to buy', value: D.free != null ? money(D.free) : 'n/a' },
    { label: 'Orders', value: `${placed} / ${D.orders.length}`, color: bad ? C.red : C.ink, sub: bad ? `${bad} failed` : 'placed', subColor: bad ? C.red : C.muted },
    { label: 'Dip slots', value: D.slotsUsed != null ? `${D.slotsUsed} / ${D.slots || 10}` : '—', sub: 'in use' }]);
  if (D.picked) {
    S.section('Stocks picked', { v: 'down 10%+ vs SPY in 5 days', c: C.dim });
    if (D.picked.length) S.table([{ h: 'Stock', w: 16, a: 'start' }, { h: 'vs SPY (5d)', w: 18 }, { h: 'Decision', w: 50, a: 'start', text: true }],
      D.picked.map((p) => [{ v: p.symbol }, { v: p.move ? arrow(-1) + p.move.replace(/^-/, '') : '', c: C.red }, /^BUY/.test(p.decision) ? { v: 'BUY', pill: C.green } : { v: p.decision, c: C.muted }]));
    else S.note('None today, so no new buys.', C.muted, 17);
  }
  S.section('Orders');
  if (D.orders.length) S.table([{ h: 'Action', w: 12, a: 'start' }, { h: 'Stock', w: 12, a: 'start' }, { h: 'Amount', w: 15 }, { h: 'Reason', w: 33, a: 'start' }, { h: 'Status', w: 16, a: 'start', text: true }],
    D.orders.map((o) => [{ v: o.side.toUpperCase(), pill: o.side === 'sell' ? C.red : C.green }, { v: o.symbol, b: true }, { v: o.amount }, { v: o.reason, pill: PILL(o.reason) }, { v: (o.ok ? '● ' : o.ok === false ? '✕ ' : '○ ') + o.status, c: o.ok ? C.green : o.ok === false ? C.red : C.muted }]));
  else S.note('No orders.', C.muted, 17);
  for (const l of D.result || []) S.note(l);
  return S.svg('Sentinel · dip strategy v3.2 · fill report with profits comes after the close');
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

// ---------- weekly / monthly / watch list (same Sentinel sheet)
const shortDate = (d) => new Date(d + 'T12:00:00Z').toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
const monthLabel = (m) => new Date(m + '-15T12:00:00Z').toLocaleDateString('en-US', { month: 'short', year: 'numeric', timeZone: 'UTC' });
const chg = (a, b) => (a > 0 && b != null ? (b / a - 1) * 100 : null);
/** W = { from, to, startEq, endEq, spyPct, sells: [ledger rows], buys: n, holding: [...] } */
export function weeklySvg(W) {
  const S = sheet();
  S.brand('Dip bot · Weekly summary', `${shortDate(W.from)} – ${shortDate(W.to)}`);
  const wk = chg(W.startEq, W.endEq), realized = W.sells.reduce((a, x) => a + (x.pl || 0), 0), wins = W.sells.filter((x) => x.pl > 0).length;
  S.kpis([{ label: 'Account', value: money(W.endEq) },
    { label: 'This week', value: wk == null ? 'n/a' : arrow(wk) + Math.abs(wk).toFixed(1) + '%', color: tone(wk), sub: W.startEq != null && W.endEq != null ? money(W.endEq - W.startEq, true) : '', subColor: tone(wk) },
    { label: 'Realized', value: money(realized, true), color: tone(realized), sub: W.sells.length ? `${wins}/${W.sells.length} wins` : 'no sells' },
    { label: W.spyPct == null ? 'vs SPY' : `vs SPY (${pct(W.spyPct)})`, value: wk == null || W.spyPct == null ? 'n/a' : (wk - W.spyPct >= 0 ? '+' : '') + (wk - W.spyPct).toFixed(1), color: wk == null || W.spyPct == null ? C.muted : tone(wk - W.spyPct), sub: wk == null || W.spyPct == null ? '' : 'pts' }]);
  if (W.sells.length) {
    S.section('Trades closed this week', { v: 'Total ' + money(realized, true), c: tone(realized) });
    S.table([{ h: 'Day', w: 8, a: 'start', text: true }, { h: 'Stock', w: 10, a: 'start' }, { h: 'Reason', w: 33, a: 'start' }, { h: 'Bought', w: 13 }, { h: 'Sold', w: 13 }, { h: 'Profit', w: 12 }, { h: 'Return', w: 11 }],
      W.sells.map((x) => [{ v: new Date(x.date + 'T12:00:00Z').toLocaleDateString('en-US', { weekday: 'short', timeZone: 'UTC' }), c: C.muted }, { v: x.symbol, b: true }, { v: x.reason, pill: PILL(x.reason) }, { v: money(x.buy) }, { v: money(x.sell) }, { v: money(x.pl, true), c: tone(x.pl), b: true }, { v: arrow(x.plPct) + pct(x.plPct).replace(/^[+-]/, ''), c: tone(x.pl) }]));
    const best = [...W.sells].sort((a, b) => (b.plPct ?? -1e9) - (a.plPct ?? -1e9))[0], worst = [...W.sells].sort((a, b) => (a.plPct ?? 1e9) - (b.plPct ?? 1e9))[0];
    if (W.sells.length > 1) S.note(`Best: ${best.symbol} ${pct(best.plPct)}   ·   Worst: ${worst.symbol} ${pct(worst.plPct)}   ·   New buys this week: ${W.buys}`);
  } else S.note(`No trades closed this week · new buys: ${W.buys}`, C.muted, 17);
  if (W.holding?.length) { S.section('Holding into next week');
    S.table([{ h: 'Stock', w: 12, a: 'start' }, { h: 'Bought', w: 15 }, { h: 'Now', w: 15 }, { h: 'Gain', w: 14 }, { h: 'Days held (max 5)', w: 22 }],
      W.holding.map((h) => [{ v: h.symbol }, { v: money(h.buy) }, { v: money(h.now) }, { v: arrow(h.pct) + pct(h.pct).replace(/^[+-]/, ''), c: tone(h.pct) }, { bar: { n: h.day ?? 0, of: 5 } }])); }
  return S.svg('Sentinel · weekly summary · account change includes any deposits or withdrawals');
}
/** M = { month: 'YYYY-MM', rows: [{ month, startEq, endEq, spyPct, realized, trades, wins }] } newest last */
export function monthlySvg(M) {
  const S = sheet();
  const cur = M.rows.at(-1) || {}, mc = chg(cur.startEq, cur.endEq);
  S.brand('Dip bot · Monthly report card', monthLabel(M.month));
  S.kpis([{ label: 'Account', value: money(cur.endEq) },
    { label: 'This month', value: mc == null ? 'n/a' : arrow(mc) + Math.abs(mc).toFixed(1) + '%', color: tone(mc), sub: cur.startEq != null ? money(cur.endEq - cur.startEq, true) : '', subColor: tone(mc) },
    { label: 'Realized', value: money(cur.realized || 0, true), color: tone(cur.realized), sub: cur.trades ? `${cur.trades} trades` : 'no trades' },
    { label: 'Win rate', value: cur.trades ? Math.round((cur.wins / cur.trades) * 100) + '%' : 'n/a', sub: cur.trades ? `${cur.wins} of ${cur.trades}` : '' }]);
  S.section('Month by month');
  S.table([{ h: 'Month', w: 14, a: 'start', text: true }, { h: 'Start', w: 13 }, { h: 'End', w: 13 }, { h: 'Return', w: 12 }, { h: 'SPY', w: 11 }, { h: 'Realized', w: 13 }, { h: 'Trades', w: 9 }, { h: 'Wins', w: 9 }],
    M.rows.map((m) => { const c = chg(m.startEq, m.endEq); return [{ v: monthLabel(m.month), b: m.month === M.month }, { v: money(m.startEq) }, { v: money(m.endEq) }, { v: c == null ? 'n/a' : arrow(c) + pct(c).replace(/^[+-]/, ''), c: tone(c) }, { v: pct(m.spyPct), c: C.muted }, { v: money(m.realized || 0, true), c: m.realized ? tone(m.realized) : C.muted }, { v: String(m.trades || 0) }, { v: m.trades ? Math.round((m.wins / m.trades) * 100) + '%' : '–' }]; }));
  const all = M.rows.filter((m) => m.startEq != null && m.endEq != null), first = all[0], last = all.at(-1);
  if (first && last) { const tot = chg(first.startEq, last.endEq), spy = all.reduce((a, m) => a * (1 + (m.spyPct ?? 0) / 100), 1); S.note(`Since ${monthLabel(first.month)}: bot ${pct(tot)} vs SPY ${pct((spy - 1) * 100)} · realized ${money(all.reduce((a, m) => a + (m.realized || 0), 0), true)}`, C.ink, 16); }
  return S.svg('Sentinel · monthly report card · returns include any deposits or withdrawals');
}
/** D = { today, time, spy5, signals: [symbols], rows: [{ s, px, r5, ex, buyAt, own }], etfs: [{ s, px, r5, buyAt }], free, slotsUsed } */
export function watchSvg(D) {
  const S = sheet();
  S.brand('Dip bot · Morning watch list', `${dateLabel(D.today)} · ${D.time} ET`);
  const close = D.rows.filter((x) => !x.own && x.ex > -0.10);
  S.kpis([{ label: 'SPY 5 days', value: pct(D.spy5 * 100), color: tone(D.spy5) },
    { label: 'Buy signals', value: String(D.signals.length), color: D.signals.length ? C.green : C.ink, sub: D.signals.slice(0, 3).join(', ') },
    { label: 'Closest', value: close[0] ? close[0].s : '–', sub: close[0] ? `needs ${pct((close[0].buyAt / close[0].px - 1) * 100)}` : '' },
    { label: 'Dip slots', value: `${D.slotsUsed ?? 0} / 10`, sub: 'in use' }]);
  S.section('Closest to a buy', { v: 'buys at 10%+ below SPY over 5 days', c: C.dim });
  S.table([{ h: 'Stock', w: 12, a: 'start' }, { h: 'Price', w: 14 }, { h: '5-day', w: 12 }, { h: 'vs SPY', w: 12 }, { h: 'Needs to fall', w: 16 }, { h: 'Buys below', w: 15 }, { h: 'Status', w: 15, a: 'start' }],
    D.rows.map((x) => { const q = x.ex <= -0.10; return [{ v: x.s }, { v: money(x.px) }, { v: pct(x.r5 * 100), c: tone(x.r5) }, { v: pct(x.ex * 100), c: C.red }, { v: q ? '—' : pct((x.buyAt / x.px - 1) * 100), c: C.muted }, { v: money(x.buyAt) }, x.own ? { v: 'Own it', pill: C.blue } : q ? { v: 'Buy signal', pill: C.green } : { v: 'Watching', pill: C.dim }]; }));
  if (D.etfs?.length) S.note('ETFs closest (buy at -5% in 5 days): ' + D.etfs.map((x) => `${x.s} ${pct(x.r5 * 100)}`).join('   '));
  S.note('Checked again every 15 minutes until 20 min before the close; buys happen automatically.');
  return S.svg('Sentinel · watch list · "buys below" assumes SPY stays where it is');
}
/** private paper bots, monthly card. D = { month: 'YYYY-MM', data_through, rows: [{ name, value, month_pct, total_pct, since }] } (names and numbers only) */
export function paperSvg(D) {
  const S = sheet(), rows = [...D.rows].sort((a, b) => (a.name === 'SPY') - (b.name === 'SPY') || b.total_pct - a.total_pct);
  const spy = D.rows.find((r) => r.name === 'SPY'), best = rows.filter((r) => r.name !== 'SPY')[0];
  S.brand('Paper bots (private) · Monthly card', `${monthLabel(D.month)} · data to ${shortDate(D.data_through)}`);
  S.kpis([{ label: 'Bots tracked', value: String(rows.length - (spy ? 1 : 0)), sub: '$10,000 each' }, { label: `Best ${monthLabel(D.month).split(' ')[0]}`, value: best ? pct([...rows].filter((r) => r.name !== 'SPY').sort((a, b) => b.month_pct - a.month_pct)[0].month_pct) : 'n/a', color: C.green, sub: best ? [...rows].filter((r) => r.name !== 'SPY').sort((a, b) => b.month_pct - a.month_pct)[0].name.replace('Mix ', '') : '' },
    { label: 'Leader overall', value: best ? pct(best.total_pct) : 'n/a', color: best ? tone(best.total_pct) : C.muted, sub: best ? best.name.replace('Mix ', '') : '' }, { label: 'SPY', value: spy ? pct(spy.total_pct) : 'n/a', color: spy ? tone(spy.total_pct) : C.muted, sub: spy ? `month ${pct(spy.month_pct)}` : '' }]);
  S.section('All paper bots');
  S.table([{ h: 'Bot', w: 26, a: 'start' }, { h: 'Value', w: 14 }, { h: monthLabel(D.month).split(' ')[0], w: 12 }, { h: 'vs SPY', w: 12 }, { h: 'Since start', w: 14 }, { h: 'Started', w: 12, a: 'start', text: true }],
    rows.map((r) => [{ v: r.name, c: r.name === 'SPY' ? C.muted : C.ink }, { v: money(r.value) }, { v: arrow(r.month_pct) + pct(r.month_pct).replace(/^[+-]/, ''), c: tone(r.month_pct) },
      { v: r.name === 'SPY' || !spy ? '—' : (r.month_pct - spy.month_pct >= 0 ? '+' : '') + (r.month_pct - spy.month_pct).toFixed(1), c: r.name === 'SPY' || !spy ? C.dim : tone(r.month_pct - spy.month_pct) }, { v: pct(r.total_pct), c: tone(r.total_pct), b: true }, { v: shortDate(r.since), c: C.muted }]));
  S.note('Virtual money only. One month says little: Frontrunner changes stock a few times a year.');
  return S.svg('Sentinel · private paper bots · names and numbers only');
}
