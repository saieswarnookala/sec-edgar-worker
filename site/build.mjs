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
  ['data/screen.json', 'screen.json'], ['data/universe.json', 'universe.json'],
  ['data/etf_monthly.csv', 'etf_monthly.csv'], ['data/etf_monthly_long.csv', 'etf_monthly_long.csv'], ['data/dip_daily.csv', 'dip_daily.csv'],
];
for (const [from, to] of files) {
  if (!existsSync(from)) { console.warn('missing', from); continue; }
  copyFileSync(from, 'site/public/data/' + to);
}
console.log('built site/public (' + html.length + ' bytes index.html)');
