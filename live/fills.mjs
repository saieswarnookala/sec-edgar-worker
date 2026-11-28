// Fill quality: real Robinhood fills vs the two backtest assumptions (Nov 28).
//   "expected" backtest = filled at the official close, cost 0.08% a side (stocks)
//   "worst case" backtest = buys filled at the NEXT open, cost 0.15% a side
// Input: state.verify (each verify saves fills with price + official close) and next-day opens.
// cost_vs_close_pct: + = worse than the close (paid more on a buy / got less on a sell).
export function fillStats(verify, opens = {}, isParking = () => false) {
  const rows = [];
  for (const v of verify || []) for (const f of v.fills || []) {
    if (!(+f.price > 0)) continue;
    const no = opens[`${f.symbol}:${v.today}`];
    rows.push({ date: v.today, symbol: f.symbol, side: f.side, parking: isParking(f.symbol), price: +f.price, close: f.close ?? null,
      cost_vs_close_pct: f.vs_close_pct ?? null,
      cost_vs_next_open_pct: f.side === 'buy' && no > 0 ? +(((f.price / no) - 1) * 100).toFixed(3) : null });
  }
  const avg = (xs) => { const a = xs.filter((x) => x != null && Number.isFinite(x)); return a.length ? { avg: +(a.reduce((s, x) => s + x, 0) / a.length).toFixed(3), n: a.length } : { avg: null, n: 0 }; };
  const g = (pred) => { const r = rows.filter(pred); return { vs_close: avg(r.map((x) => x.cost_vs_close_pct)), vs_next_open: avg(r.map((x) => x.cost_vs_next_open_pct)) }; };
  return { rows, dip_buys: g((x) => !x.parking && x.side === 'buy'), dip_sells: g((x) => !x.parking && x.side === 'sell'), parking: g((x) => x.parking) };
}
export function fillsText(S) {
  const f = (o) => (o.avg == null ? 'no data yet' : `${o.avg >= 0 ? '+' : ''}${o.avg.toFixed(2)}% (${o.n} fills)`);
  return [
    'Real fills vs backtest (cost, + = worse)',
    `Dip buys vs close: ${f(S.dip_buys.vs_close)}`,
    `Dip buys vs next open: ${f(S.dip_buys.vs_next_open)}`,
    `Dip sells vs close: ${f(S.dip_sells.vs_close)}`,
    `Parking vs close: ${f(S.parking.vs_close)}`,
    '',
    'Backtest assumes: expected = close + 0.08%, worst case = next open + 0.15%.',
    'Near +0.08% or below = the expected column is realistic.',
  ].join('\n');
}
