// Assembles site/public: the dashboard page wrapped with the website runtime, plus the data files.
// Run from the repo root: node site/build.mjs
import { readFileSync, writeFileSync, mkdirSync, copyFileSync, existsSync } from 'node:fs';
const page = readFileSync('site/dashboard/page.html', 'utf8');
const runtime = readFileSync('site/dashboard/runtime.js', 'utf8');
writeFileSync('site/public/runtime.js', runtime);
const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Sentinel</title><link rel="icon" href="/favicon.svg"><link rel="stylesheet" href="/theme.css">
<script src="/vendor/d3.min.js"></script><script src="/runtime.js"></script></head>
<body><div id="sw-bar"></div><main class="sw-main">
${page}
</main><script>dash.__start();</script></body></html>
`;
writeFileSync('site/public/index.html', html);
mkdirSync('site/public/data', { recursive: true });
const files = [
  ['site/static-data/industry_benchmarks_jan2026.csv', 'industry_benchmarks_jan2026.csv'],
  ['site/static-data/strategies_oct10.json', 'strategies_oct10.json'],
  ['data/screen.json', 'screen.json'], ['site/static-data/screener_rules_report.pdf', 'screener_rules_report.pdf'], ['data/universe.json', 'universe.json'],
  ['data/etf_monthly.csv', 'etf_monthly.csv'], ['data/etf_monthly_long.csv', 'etf_monthly_long.csv'], ['data/dip_daily.csv', 'dip_daily.csv'], ['data/india_monthly.csv', 'india_monthly.csv'],
];
for (const [from, to] of files) {
  if (!existsSync(from)) { console.warn('missing', from); continue; }
  copyFileSync(from, 'site/public/data/' + to);
}
// Paper bots summary for the "Paper bots" tab (small: no per-run signal lists)
const readJ = (f) => { try { return JSON.parse(readFileSync(f, 'utf8')); } catch { return null; } };
const byDay = (hist, eq, spy) => { const m = new Map(); for (const h of hist || []) { const e = eq(h), s = spy(h); if (h.today && e > 0) m.set(h.today, { d: h.today, eq: +(+e).toFixed(2), spy: s > 0 ? +(+s).toFixed(2) : null }); } return [...m.values()].sort((a, b) => (a.d < b.d ? -1 : 1)); };
const lastRun = (hist) => { const h = (hist || []).at(-1); if (!h) return null; return { day: h.today, sells: (h.sells || []).map((x) => x.symbol + (x.reason ? ' (' + x.reason + ')' : '')), buys: (h.buys || []).map((x) => x.symbol + (x.dip_pct != null ? ' (dip ' + x.dip_pct + '%)' : x.reaction_pct != null ? ' (+' + x.reaction_pct + '%)' : '')), orders: h.orders || [], dry: !!h.dry, park: typeof h.park === 'string' ? h.park : null }; };
const dipS = readJ('data/paper_dip_state.json'), volS = readJ('data/paper_dip_vol_state.json'), drS = readJ('data/paper_drift_state.json');
const etfS = readJ('data/paper_dip_etf_state.json');
const tunS = readJ('data/paper_dip_tuned_state.json');
const mixS = readJ('data/paper_mix_state.json');
const shS = readJ('data/paper_short_state.json');
const bdS = readJ('data/paper_bond_state.json');
const v3S = readJ('data/paper_v3_state.json');
const v31S = readJ('data/paper_v31_state.json');
const v32S = readJ('data/paper_v32_state.json');
const imS = readJ('data/paper_india_mom_state.json');
const im2S = readJ('data/paper_india_mom200_state.json');
const status = { built: new Date().toISOString(), bots: {
  dip: dipS && { start: 10000, curve: byDay(dipS.history, (h) => h.equity, (h) => h.spy), positions: dipS.positions || [], last: lastRun(dipS.history), updated: dipS.updated },
  vol: volS && { start: 10000, curve: byDay(volS.history, (h) => h.equity, (h) => h.spy), positions: (volS.vs || {}).positions || [], cash: (volS.vs || {}).cash, park: (volS.vs || {}).park || {}, trades: ((volS.vs || {}).trades || []).slice(-15), last: (() => { const h = (volS.history || []).at(-1); return h && { day: h.today, orders: h.orders || [], scale: h.scale, vol_rank: h.vol_rank, spy_vol_pct: h.spy_vol_pct, park: h.park }; })(), updated: volS.updated },
  etf: etfS && { start: 10000, curve: byDay(etfS.history, (h) => h.equity, (h) => h.spy), twin: byDay(etfS.history, (h) => h.twin_equity, (h) => h.spy), positions: (etfS.vs || {}).positions || [], trades: ((etfS.vs || {}).trades || []).slice(-15), twin_trades: ((etfS.twin || {}).trades || []).length, last: (() => { const h = (etfS.history || []).at(-1); return h && { day: h.today, orders: h.orders || [], park: h.park, etf_signals: Object.keys(h.etf_signals || {}) }; })(), updated: etfS.updated },
  tuned: tunS && { start: 10000, curve: byDay(tunS.history, (h) => h.equity, (h) => h.spy), positions: (tunS.vs || {}).positions || [], trades: ((tunS.vs || {}).trades || []).slice(-15), last: (() => { const h = (tunS.history || []).at(-1); return h && { day: h.today, orders: h.orders || [], park: h.park, etf_signals: h.etf_signals || [], stock_signals: h.stock_signals }; })(), updated: tunS.updated },
  mix: mixS && { start: 10000, curve: byDay(mixS.history, (h) => h.equity, (h) => h.spy), positions: (mixS.vs || {}).positions || [], trades: ((mixS.vs || {}).trades || []).slice(-15), last: (() => { const h = (mixS.history || []).at(-1); return h && { day: h.today, orders: h.orders || [], park: h.park, dip_signals: h.dip_signals, drift_signals: h.drift_signals || [], drift_found: h.drift_signals_found }; })(), updated: mixS.updated },
  short: shS && { start: 10000, curve: byDay(shS.history, (h) => h.equity, (h) => h.spy), twin: byDay(shS.history, (h) => h.twin_equity, (h) => h.spy), positions: (shS.vs || {}).positions || [], trades: ((shS.vs || {}).trades || []).slice(-15), last: (() => { const h = (shS.history || []).at(-1); return h && { day: h.today, orders: h.orders || [], park: h.park, si_date: h.si_date, si_error: h.si_error, skipped: h.skipped || {}, dip_signals: h.dip_signals }; })(), updated: shS.updated },
  bond: bdS && { start: 10000, curve: byDay(bdS.history, (h) => h.equity, (h) => h.spy), twin: byDay(bdS.history, (h) => h.twin_equity, (h) => h.spy), positions: (bdS.vs || {}).positions || [], trades: ((bdS.vs || {}).trades || []).slice(-15), last: (() => { const h = (bdS.history || []).at(-1); return h && { day: h.today, orders: h.orders || [], park: h.park, twin_park: h.twin_park, ief: h.ief, ief_ma100: h.ief_ma100, dip_signals: h.dip_signals }; })(), updated: bdS.updated },
  v3: v3S && { start: 10000, curve: byDay(v3S.history, (h) => h.equity, (h) => h.spy), positions: (v3S.vs || {}).positions || [], trades: ((v3S.vs || {}).trades || []).slice(-15), last: (() => { const h = (v3S.history || []).at(-1); return h && { day: h.today, orders: h.orders || [], park: h.park, etf_signals: h.etf_signals || [], stock_signals: h.stock_signals }; })(), updated: v3S.updated },
  v31: v31S && { start: 10000, curve: byDay(v31S.history, (h) => h.equity, (h) => h.spy), positions: [...((v31S.vs || {}).positions || []), ...((v31S.vs || {}).drift || [])], trades: ((v31S.vs || {}).trades || []).slice(-15), last: (() => { const h = (v31S.history || []).at(-1); return h && { day: h.today, orders: h.orders || [], park: h.park, etf_signals: h.etf_signals || [], stock_signals: h.stock_signals, drift_signals: h.drift_signals || [], drift_signals_found: h.drift_signals_found }; })(), updated: v31S.updated },
  v32: v32S && { start: 10000, curve: byDay(v32S.history, (h) => h.equity, (h) => h.spy), twin: byDay(v32S.history, (h) => h.twin_equity, (h) => h.spy), positions: (v32S.vs || {}).positions || [], trades: ((v32S.vs || {}).trades || []).slice(-15), last: (() => { const h = (v32S.history || []).at(-1); return h && { day: h.today, orders: h.orders || [], park: h.park, intraday_checks: h.intraday_checks, intraday_orders: (h.intraday_orders || []).slice(-10), twin_equity: h.twin_equity }; })(), updated: v32S.updated },
  inmom: imS && { start: 1000000, curve: (imS.history || []).map((h) => ({ d: h.day, eq: +(+h.equity).toFixed(0), spy: h.nifty })), holdings: Object.entries(imS.holdings || {}).map(([s, v]) => ({ s, v: Math.round(v) })).sort((a, b) => b.v - a.v), cash: Math.round(imS.cash || 0), inside: imS.inside, hide: imS.hide, universe_asof: imS.universe_asof, twin: im2S ? (im2S.history || []).map((h) => ({ d: h.day, eq: +(+h.equity).toFixed(0) })) : [], twin_inside: im2S ? im2S.inside : null, rebalances: (imS.rebalances || []).slice(-6).map((r) => ({ day: r.day, inside: r.inside, hide: r.hide, sells: r.sells, buys: r.buys, turnover_pct: r.turnover_pct })), latest: (imS.rebalances || []).at(-1) || null, updated: imS.updated },
  drift: drS && { start: 100000, curve: byDay(drS.history, (h) => h.equity, (h) => h.park && h.park.spy_price), positions: drS.positions || [], last: lastRun(drS.history), updated: drS.updated },
} };
writeFileSync('site/public/data/paper_status.json', JSON.stringify(status));
console.log('built site/public (' + html.length + ' bytes index.html)');
