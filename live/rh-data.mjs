// Robinhood-only market data for the live dip bot (Nov 19 2026): the same inputs gatherSignals() gets from Alpaca, read through
// Robinhood's MCP instead (get_equity_historicals + get_equity_quotes), so the VM can run with Robinhood as its only data source.
// Runs in SHADOW mode first: the live bot still trades on Alpaca data; this computes the same picks from Robinhood data and
// logs every difference (compareSignals). Switch over only after the two agree for several days.
// Differences to expect: Robinhood daily bars are split-adjusted only (Alpaca: splits + dividends), so averages can differ by a
// few hundredths of a percent; Clear Leader's 12-month returns leave out dividends.
import { dipScore, etfDipScore, parkSymbol, volumeRatio, volFraction, sessionMinute, TUNED, VOL_MAX, ETF_DIP_LIST } from '../scripts/paper-dip.mjs';
import { run as clRun, POOL } from '../scripts/clear-leader.mjs';
import { monthRows } from '../scripts/clear-leader-alert.mjs';

const chunks = (a, n) => Array.from({ length: Math.ceil(a.length / n) }, (_, i) => a.slice(i * n, i * n + n));
const results = (r) => r?.data?.results || r?.results || [];
const nyMinute = (d = new Date()) => { const f = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hour: 'numeric', minute: 'numeric', hourCycle: 'h23' }).formatToParts(d); return +f.find((x) => x.type === 'hour').value * 60 + +f.find((x) => x.type === 'minute').value; };

// Daily bars per symbol from get_equity_historicals replies: [{d:'YYYY-MM-DD', c, v}] ascending
export function parseBars(reply) {
  const out = {};
  for (const r of results(reply)) {
    if (!r?.symbol) continue;
    out[r.symbol] = (r.bars || []).filter((b) => !b.interpolated && +b.close_price > 0)
      .map((b) => ({ d: String(b.begins_at).slice(0, 10), c: +b.close_price, v: +b.volume || 0 })).sort((a, b) => a.d.localeCompare(b.d));
  }
  return out;
}
// Current price per symbol from get_equity_quotes: the newer of the regular and extended-hours last trade
export function parseQuotes(reply) {
  const out = {};
  for (const r of results(reply)) {
    const q = r.quote || r; if (!q?.symbol) continue;
    const a = [[+q.last_trade_price, q.venue_last_trade_time], [+q.last_non_reg_trade_price, q.venue_last_non_reg_trade_time]].filter(([p]) => p > 0);
    a.sort((x, y) => String(y[1] || '').localeCompare(String(x[1] || '')));
    if (a.length) out[q.symbol] = a[0][0];
  }
  return out;
}

export async function gatherSignalsRH({ client, call, today, members, closeMin = 960, now = new Date() }) {
  const t0 = Date.now(), calls = { historicals: 0, quotes: 0 }, errors = [];
  const hist = async (args) => { calls.historicals++; return call(client, 'get_equity_historicals', args); };
  const etfs = [...POOL, 'BIL'];
  const syms = [...new Set([...members, ...etfs, ...ETF_DIP_LIST])];
  const start = new Date(Date.parse(today + 'T12:00:00Z') - 450 * 864e5).toISOString().slice(0, 10);
  // prior daily closes and volumes (today's bar excluded, like the Alpaca path)
  const closes = {}, vols = {};
  for (const c of chunks(syms, 10)) {
    try {
      const bars = parseBars(await hist({ symbols: c, start_time: start, interval: 'day', bounds: 'regular', adjustment_type: 'split' }));
      for (const s of c) { const b = (bars[s] || []).filter((x) => x.d < today).slice(-300); closes[s] = b.map((x) => x.c); vols[s] = b.map((x) => x.v); }
    } catch (e) { errors.push(`bars ${c[0]}..: ${String(e.message || e).slice(0, 120)}`); }
  }
  // live prices
  const prices = {};
  for (const c of chunks(syms, 50)) {
    try { calls.quotes++; Object.assign(prices, parseQuotes(await call(client, 'get_equity_quotes', { symbols: c }))); }
    catch (e) { errors.push(`quotes ${c[0]}..: ${String(e.message || e).slice(0, 120)}`); }
  }
  // Clear Leader from completed months (monthly bars since 2016, split-adjusted)
  let clPos = 'SPY', clWhy = null;
  try {
    const etfBars = {}, mb = {};
    for (const c of chunks(etfs, 10)) Object.assign(mb, parseBars(await hist({ symbols: c, start_time: '2016-01-01', interval: 'month', bounds: 'regular', adjustment_type: 'split' })));
    for (const s of etfs) etfBars[s] = (mb[s] || []).map((b) => ({ d: b.d, c: b.c }));
    const rows = monthRows(etfBars, today).filter((r) => r.date.slice(0, 7) < today.slice(0, 7));
    const cl = clRun(rows, {}); clPos = cl?.now?.pos || 'SPY'; clWhy = cl?.now?.why;
  } catch (e) { errors.push('clear leader: ' + String(e.message || e).slice(0, 120)); }
  const park = parkSymbol({ clPos, spyCloses: closes.SPY || [], spyPx: prices.SPY });
  // dip signals
  const scores = {}, scoresTuned = {};
  for (const s of members) {
    if (etfs.includes(s)) continue;
    const sc = dipScore(closes[s] || [], prices[s], closes.SPY || [], prices.SPY); if (sc != null) scores[s] = sc;
    const st = dipScore(closes[s] || [], prices[s], closes.SPY || [], prices.SPY, TUNED); if (st != null) scoresTuned[s] = st;
  }
  // volume filter: today's regular-session volume so far (Robinhood intraday bars, no 15-minute delay), scaled to a full day
  const cands0 = [...new Set([...Object.keys(scores), ...Object.keys(scoresTuned)])], partial = {}, volInfo = {}, out = {};
  const nowMin = nyMinute(now);
  if (cands0.length && nowMin > 600) {
    for (const c of chunks(cands0, 10)) {
      try { const b = parseBars(await hist({ symbols: c, start_time: today, interval: '30minute', bounds: 'regular', adjustment_type: 'none' })); for (const s of c) partial[s] = (b[s] || []).filter((x) => x.d === today).reduce((a, x) => a + x.v, 0); }
      catch (e) { errors.push('volume: ' + String(e.message || e).slice(0, 120)); }
    }
  }
  const frac = volFraction(sessionMinute(nowMin, closeMin));
  for (const s of cands0) {
    const est = partial[s] && frac > 0.2 ? partial[s] / frac : null, r = volumeRatio(vols[s] || [], est);
    volInfo[s] = { ratio: r == null ? null : +r.toFixed(2), today_est: est ? Math.round(est) : null };
    if (r != null && r > VOL_MAX) { if (s in scores) out.skipped_heavy_volume = [...(out.skipped_heavy_volume || []), `${s} (${r.toFixed(1)}x)`]; delete scores[s]; delete scoresTuned[s]; }
  }
  const etfScores = {};
  for (const s of ETF_DIP_LIST) { const sc = etfDipScore(closes[s] || [], prices[s]); if (sc != null) etfScores[s] = sc; }
  return { ...out, members, etfs, closes, prices, scores, scoresTuned, etfScores, park, clPos, clWhy, volInfo, source: 'robinhood', calls, errors, secs: Math.round((Date.now() - t0) / 1000) };
}

// What differs between the Alpaca and the Robinhood inputs (a = Alpaca gather, b = Robinhood gather)
export function compareSignals(a, b) {
  const top = (sc) => Object.entries(sc || {}).sort((x, y) => x[1] - y[1]).slice(0, 10).map(([s]) => s);
  const ka = Object.keys(a.scores || {}), kb = Object.keys(b.scores || {});
  const ea = Object.keys(a.etfScores || {}), eb = Object.keys(b.etfScores || {});
  const diffs = [];
  for (const s of new Set([...a.members || [], 'SPY'])) { const x = a.prices?.[s], y = b.prices?.[s]; if (x > 0 && y > 0) diffs.push(Math.abs(y / x - 1) * 100); }
  diffs.sort((x, y) => x - y);
  const watch = [...new Set([...ka, ...kb])].map((s) => ({ s, alpaca_px: a.prices?.[s] ?? null, rh_px: b.prices?.[s] ?? null, alpaca_gap: a.scores?.[s] != null ? +(a.scores[s] * 100).toFixed(2) : null, rh_gap: b.scores?.[s] != null ? +(b.scores[s] * 100).toFixed(2) : null }));
  const sameBuys = JSON.stringify(top(a.scores)) === JSON.stringify(top(b.scores));
  return {
    same_picks: sameBuys && JSON.stringify(ea.sort()) === JSON.stringify(eb.sort()) && a.park === b.park,
    stock_dips: { alpaca: ka.length, robinhood: kb.length, only_alpaca: ka.filter((s) => !kb.includes(s)), only_robinhood: kb.filter((s) => !ka.includes(s)), same_top10_order: sameBuys },
    etf_dips: { only_alpaca: ea.filter((s) => !eb.includes(s)), only_robinhood: eb.filter((s) => !ea.includes(s)) },
    park: { alpaca: a.park ?? null, robinhood: b.park ?? null }, clear_leader: { alpaca: a.clPos ?? null, robinhood: b.clPos ?? null },
    heavy_volume: { alpaca: a.skipped_heavy_volume || [], robinhood: b.skipped_heavy_volume || [] },
    price_gap_pct: { median: diffs.length ? +diffs[Math.floor(diffs.length / 2)].toFixed(3) : null, p95: diffs.length ? +diffs[Math.floor(diffs.length * 0.95)].toFixed(3) : null, max: diffs.length ? +diffs.at(-1).toFixed(3) : null, compared: diffs.length },
    history_days: { alpaca_spy: a.closes?.SPY?.length ?? null, robinhood_spy: b.closes?.SPY?.length ?? null, robinhood_missing: (a.members || []).filter((s) => !(b.closes?.[s]?.length >= 200)).length },
    watch, robinhood_calls: b.calls, robinhood_errors: b.errors, robinhood_secs: b.secs,
  };
}
export function shadowAlert(c) {
  const lines = [c.same_picks ? 'SAME picks from Robinhood data as from Alpaca' : 'DIFFERENT picks (live orders still use Alpaca):'];
  if (c.stock_dips.only_alpaca.length) lines.push('  dips only in Alpaca: ' + c.stock_dips.only_alpaca.join(', '));
  if (c.stock_dips.only_robinhood.length) lines.push('  dips only in Robinhood: ' + c.stock_dips.only_robinhood.join(', '));
  if (!c.stock_dips.same_top10_order && !c.stock_dips.only_alpaca.length && !c.stock_dips.only_robinhood.length) lines.push('  same dips, different order');
  if (c.etf_dips.only_alpaca.length || c.etf_dips.only_robinhood.length) lines.push(`  ETF dips: Alpaca-only ${c.etf_dips.only_alpaca.join(',') || '-'} | Robinhood-only ${c.etf_dips.only_robinhood.join(',') || '-'}`);
  if (c.park.alpaca !== c.park.robinhood) lines.push(`  parking: Alpaca ${c.park.alpaca || 'cash'} vs Robinhood ${c.park.robinhood || 'cash'}`);
  lines.push(`Prices: median gap ${c.price_gap_pct.median}%, max ${c.price_gap_pct.max}% over ${c.price_gap_pct.compared} stocks`);
  lines.push(`Robinhood: ${c.robinhood_calls?.historicals ?? 0} history + ${c.robinhood_calls?.quotes ?? 0} quote calls, ${c.robinhood_secs}s${c.robinhood_errors?.length ? `, ${c.robinhood_errors.length} errors: ${c.robinhood_errors[0]}` : ''}`);
  return { title: `Robinhood data check: ${c.same_picks ? 'match' : 'DIFFERENT'}`, body: lines.join('\n') };
}
