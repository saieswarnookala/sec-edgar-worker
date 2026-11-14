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
const status = { built: new Date().toISOString(), bots: {
  dip: dipS && { start: 10000, curve: byDay(dipS.history, (h) => h.equity, (h) => h.spy), positions: dipS.positions || [], last: lastRun(dipS.history), updated: dipS.updated },
  vol: volS && { start: 10000, curve: byDay(volS.history, (h) => h.equity, (h) => h.spy), positions: (volS.vs || {}).positions || [], cash: (volS.vs || {}).cash, park: (volS.vs || {}).park || {}, trades: ((volS.vs || {}).trades || []).slice(-15), last: (() => { const h = (volS.history || []).at(-1); return h && { day: h.today, orders: h.orders || [], scale: h.scale, vol_rank: h.vol_rank, spy_vol_pct: h.spy_vol_pct, park: h.park }; })(), updated: volS.updated },
  drift: drS && { start: 100000, curve: byDay(drS.history, (h) => h.equity, (h) => h.park && h.park.spy_price), positions: drS.positions || [], last: lastRun(drS.history), updated: drS.updated },
} };
writeFileSync('site/public/data/paper_status.json', JSON.stringify(status));
console.log('built site/public (' + html.length + ' bytes index.html)');
