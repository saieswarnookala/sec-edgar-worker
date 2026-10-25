// Clear leader v2.0 engine — identical to the dashboard's Clear leader v2.0 tab.
// Clear leader v2.0: 10 ETFs, monthly. Rank by 12-month return; buy #1 when it leads #2 by >= 15 pts,
// has been #1 for 3 month-ends in a row and beats T-bills; sell when it is no longer #1 or its lead
// drops below 7.5 pts; otherwise hold SPY (optional crash filter: IEF when SPY < its 10-month average).
const CL = (() => {
  const POOL = ['SPY', 'QQQ', 'IWM', 'EFA', 'EEM', 'VNQ', 'TLT', 'IEF', 'GLD', 'DBC'];
  const ENTRY = 0.15, EXIT = 0.075, STREAK = 3, COST = 0.0005;
  const run = (rowsIn, opts = {}) => {
    const crash = !!opts.crash;
    const rows = [...rowsIn].map((r) => { const x = { date: String(r.date).slice(0, 10) }; for (const s of [...POOL, 'BIL']) x[s] = Number(r[s]); return x; })
      .filter((r) => [...POOL, 'BIL'].every((s) => r[s] > 0)).sort((a, b) => (a.date < b.date ? -1 : 1));
    if (rows.length < 26) return null;
    const ret = (s, i) => rows[i][s] / rows[i - 12][s] - 1;
    const sma = (i) => { let t = 0; for (let k = i - 9; k <= i; k++) t += rows[k].SPY; return t / 10; };
    let lead = null, prevTop = null, streak = 0, hold = null, eq = 1, spy = 1, trades = 0;
    const pts = [{ d: rows[12].date, eq: 1, spy: 1 }], months = [], episodes = [];
    let ep = null;
    const decide = (i) => {
      const rk = [...POOL].sort((a, b) => ret(b, i) - ret(a, i));
      const top = rk[0], gap = ret(rk[0], i) - ret(rk[1], i);
      streak = top === prevTop ? streak + 1 : 1; prevTop = top;
      const trig = gap >= ENTRY && streak >= STREAK && ret(top, i) > ret('BIL', i);
      const stay = lead && top === lead && gap >= EXIT;
      const was = lead;
      lead = stay ? lead : trig ? top : null;
      const spyAvg = sma(i), down = rows[i].SPY < spyAvg;
      const pos = lead || (crash && down ? 'IEF' : 'SPY');
      let why;
      if (lead && was === lead) why = `${lead} still leads #2 by ${(gap * 100).toFixed(0)} pts (needs 7.5+ to stay)`;
      else if (lead) why = `${lead} is a clear leader: ${(gap * 100).toFixed(0)} pts ahead of #2, #1 for ${streak} month-ends`;
      else if (was) why = `${was} ${top !== was ? 'is no longer #1' : 'lead shrank to ' + (gap * 100).toFixed(0) + ' pts'} — back to ${pos}`;
      else why = `No clear leader (#1 ${top} leads by ${(gap * 100).toFixed(0)} pts${streak < STREAK ? ', #1 for ' + streak + ' month' + (streak > 1 ? 's' : '') : ''})` + (pos === 'IEF' ? ' and SPY is below its 10-month average' : '');
      return { pos, top, gap, streak, rank: rk.map((s) => ({ symbol: s, ret12: ret(s, i) })), spy: rows[i].SPY, spyAvg, why };
    };
    for (let i = 12; i < rows.length - 1; i++) {
      const d = decide(i);
      if (d.pos !== hold) {
        trades++;
        if (ep) { ep.end = rows[i].date; episodes.push(ep); ep = null; }
        if (d.pos !== 'SPY' && d.pos !== 'IEF') ep = { symbol: d.pos, start: rows[i].date, eq0: eq, spy0: spy };
      }
      const cost = d.pos !== hold ? (hold ? 2 : 1) * COST : 0;
      const r = rows[i + 1][d.pos] / rows[i][d.pos] - 1 - cost;
      eq *= 1 + r; spy *= rows[i + 1].SPY / rows[i].SPY; hold = d.pos;
      months.push({ d: rows[i + 1].date, r, s: rows[i + 1].SPY / rows[i].SPY - 1, pos: d.pos });
      pts.push({ d: rows[i + 1].date, eq, spy });
      if (ep) { ep.eq1 = eq; ep.spy1 = spy; }
    }
    if (ep) { ep.end = null; episodes.push(ep); }
    const now = decide(rows.length - 1);
    const st = (key, a = '0', b = '9') => {
      const m = months.filter((x) => x.d >= a && x.d < b); let e = 1, pk = 1, dd = 0;
      for (const x of m) { e *= 1 + x[key]; pk = Math.max(pk, e); dd = Math.max(dd, 1 - e / pk); }
      return { total: e - 1, cagr: m.length ? e ** (12 / m.length) - 1 : null, dd };
    };
    const yr = {};
    for (const x of months) { const y = x.d.slice(0, 4); yr[y] = yr[y] || { r: 1, s: 1, held: {} }; yr[y].r *= 1 + x.r; yr[y].s *= 1 + x.s; yr[y].held[x.pos] = (yr[y].held[x.pos] || 0) + 1; }
    const lastM = months[months.length - 1].d, firstM = months[0].d;
    const years = Object.entries(yr).map(([y, v]) => ({ year: +y, ret: v.r - 1, spy: v.s - 1, partial: (y === firstM.slice(0, 4) && firstM.slice(5, 7) !== '01') || (y === lastM.slice(0, 4) && lastM.slice(5, 7) !== '12'),
      held: Object.entries(v.held).sort((a, b) => b[1] - a[1]).map(([s]) => s) }));
    const periods = [['2008–2016', '0', '2017'], ['2017–2021', '2017', '2022'], ['2022–' + lastM.slice(0, 4), '2022', '9'], ['All years', '0', '9']]
      .map(([label, a, b]) => ({ label, strat: st('r', a, b), spy: st('s', a, b) }));
    return {
      start: rows[12].date, end: lastM, asOf: rows[rows.length - 1].date, crash,
      summary: { ...st('r'), spy: st('s'), trades, beatYears: years.filter((y) => !y.partial && y.ret > y.spy).length, fullYears: years.filter((y) => !y.partial).length },
      periods, years, now,
      episodes: episodes.map((e) => ({ symbol: e.symbol, start: e.start, end: e.end, ret: e.eq1 / e.eq0 - 1, spy: e.spy1 / e.spy0 - 1 })).reverse(),
      curve: pts.map((p) => ({ date: p.d, equity: 10000 * p.eq, spy: 10000 * p.spy })),
    };
  };
  return { run, POOL };
})();

export const run = CL.run, POOL = CL.POOL;
