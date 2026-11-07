// After-tax + idle-cash simulator shared by US and India earnings-drift tests. Research only.
// Arrays aligned to dates: O[s][t], C[s][t] (null if missing). B[t] = benchmark ETF close (SPY / NIFTYBEES).
// signals[t] = [{s, r}] (sorted desc) entering at the open of day t.
// Taxes: realized gains netted per calendar year, tax paid at year end at `rate` (short-term); net losses carry forward.
// Idle cash ("park"): uninvested cash sits in the benchmark ETF, sold as needed to fund trades (gains taxed at `rate` too, conservative).
// At the end everything is sold and remaining gains taxed. Benchmark: buy and hold, gain taxed once at the end at `ltRate`.
export function simTax({ dates, O, C, B, signals, th, h, n, t0 = 0, cost = 0.0005, rate = 0, park = false, ltRate = 0 }) {
  let cash = 1, pos = [], pk = 0, pkBasis = 0, yrGain = 0, carry = 0, taxPaid = 0, trades = 0, peak = 0, dd = 0;
  const bAt = (t) => B[t] ?? null;
  const sellPark = (amt, t) => { const px = bAt(t); if (!pk || !px) return 0; const sh = Math.min(pk, amt / px), frac = sh / pk, proceeds = sh * px; yrGain += proceeds - pkBasis * frac; pkBasis -= pkBasis * frac; pk -= sh; cash += proceeds; return proceeds; };
  const payTax = (t) => { const g = yrGain - carry; if (g > 0) { const tax = g * rate; if (cash < tax) sellPark(tax - cash + 1e-12, t); cash -= tax; taxPaid += tax; carry = 0; } else carry = -g; yrGain = 0; };
  for (let t = t0; t < dates.length; t++) {
    if (t > t0 && dates[t].slice(0, 4) !== dates[t - 1].slice(0, 4)) payTax(t - 1);
    const val = (p) => p.sh * (C[p.s]?.[t] ?? p.last);
    const eq = cash + pk * (bAt(t) ?? 0) + pos.reduce((a, p) => a + p.last * p.sh, 0);
    for (const x of signals[t] || []) {
      if (x.r < th) continue; if (pos.length >= n) break; if (pos.some((p) => p.s === x.s)) continue;
      const o = O[x.s]?.[t]; if (!o) continue;
      const want = eq / n; if (cash < want && park) sellPark(want - cash, t);
      const alloc = Math.min(want, cash); if (alloc <= 1e-9) break;
      cash -= alloc; pos.push({ s: x.s, sh: (alloc * (1 - cost)) / o, basis: alloc, exitT: t + h - 1, last: o });
    }
    for (const p of pos) { const c = C[p.s]?.[t]; if (c) p.last = c; }
    pos = pos.filter((p) => { if (t < p.exitT && t < dates.length - 1) return true; const v = p.sh * p.last * (1 - cost); cash += v; yrGain += v - p.basis; trades++; return false; });
    if (park && cash > 1e-9 && bAt(t)) { pk += cash / bAt(t); pkBasis += cash; cash = 0; }
    const tot = cash + pk * (bAt(t) ?? 0) + pos.reduce((a, p) => a + p.sh * p.last, 0); peak = Math.max(peak, tot); dd = Math.min(dd, tot / peak - 1);
  }
  const T = dates.length - 1; for (const p of pos) { const v = p.sh * p.last * (1 - cost); cash += v; yrGain += v - p.basis; } pos = [];
  if (pk) sellPark(pk * bAt(T), T); payTax(T);
  const yrs = (Date.parse(dates[T]) - Date.parse(dates[t0])) / 31557600000, cagr = (v) => +((Math.pow(v, 1 / yrs) - 1) * 100).toFixed(1);
  const bench = 1 + (B[T] / B[t0] - 1) * (1 - ltRate);
  return { cagr: cagr(cash), final: +cash.toFixed(3), maxDD: +(dd * 100).toFixed(1), taxPaid: +taxPaid.toFixed(3), trades, benchCagr: cagr(bench), benchPreTaxCagr: cagr(B[T] / B[t0]) };
}
export function taxGrid(base, rates, ltRate) {
  const rows = [];
  for (const rate of rates) for (const park of [false, true]) rows.push({ rate, park, ...simTax({ ...base, rate, park, ltRate }) });
  return rows;
}
