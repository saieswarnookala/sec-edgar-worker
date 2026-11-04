// Monthly (dividend/split-adjusted) closes for individual stocks, for the Clear leader v2.0 test.
// Source: Alpha Vantage TIME_SERIES_MONTHLY_ADJUSTED, one call per symbol, ~1.5 s apart.
// Writes data/stocks_monthly.csv: date + adjusted month-end close per symbol, oldest first,
// current (incomplete) month skipped. Symbols with no data for a month get an empty cell;
// symbols whose fetch fails are logged and left out of the file.
// Usage: ALPHAVANTAGE_KEY=... node scripts/build-stocks.mjs [outDir=data]
import { writeFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { parseMonthly } from './build-history.mjs';

export const STOCK_SYMS = ['XOM', 'GE', 'MSFT', 'T', 'PG', 'CVX', 'JNJ', 'WMT', 'BAC', 'GOOGL', 'SPY', 'BIL'];

export function combineStocks(series, today = new Date().toISOString().slice(0, 10)) {
  const cur = today.slice(0, 7);
  const syms = Object.keys(series);
  const maps = Object.fromEntries(syms.map((s) => [s, new Map(series[s].filter((r) => r.d.slice(0, 7) < cur).map((r) => [r.d.slice(0, 7), r]))]));
  const months = [...new Set(syms.flatMap((s) => [...maps[s].keys()]))].sort();
  const rows = months.map((m) => {
    // Month-end date: the latest trading date any symbol reports for that month.
    const d = syms.map((s) => maps[s].get(m)?.d).filter(Boolean).sort().at(-1);
    return d + ',' + syms.map((s) => maps[s].get(m)?.c ?? '').join(',');
  });
  return ['date,' + syms.join(','), ...rows].join('\n') + '\n';
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const key = process.env.ALPHAVANTAGE_KEY;
  const outDir = process.argv[2] || 'data';
  const mask = (s) => String(s).split(key || '\u0000').join('***');
  if (!key) { console.error('ALPHAVANTAGE_KEY is not set'); process.exit(1); }
  mkdirSync(outDir, { recursive: true });
  const series = {};
  const failed = [];
  for (const [i, s] of STOCK_SYMS.entries()) {
    if (i > 0) await new Promise((res) => setTimeout(res, 1500));
    try {
      const r = await fetch(`https://www.alphavantage.co/query?function=TIME_SERIES_MONTHLY_ADJUSTED&symbol=${s}&datatype=csv&apikey=${key}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const rows = parseMonthly(await r.text());
      if (!rows.length) throw new Error('no rows');
      series[s] = rows;
      console.log(s, rows.length, 'months, from', rows.at(-1)?.d);
    } catch (e) {
      failed.push(s);
      console.error(`FAILED ${s}: ${mask(e.message || e)}`);
    }
  }
  if (!Object.keys(series).length) { console.error('All symbols failed; nothing written.'); process.exit(1); }
  const csv = combineStocks(series);
  writeFileSync(join(outDir, 'stocks_monthly.csv'), csv);
  console.log('rows', csv.trim().split('\n').length - 1, 'symbols', Object.keys(series).length);
  if (failed.length) console.error('Failed symbols:', failed.join(', '));
}
