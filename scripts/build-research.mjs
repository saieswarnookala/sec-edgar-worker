// Research data: daily dividend-adjusted closes (Alpaca, 2016+) for the momentum pool plus extra ETFs,
// and long monthly adjusted closes (Alpha Vantage) for the extra ETFs. Writes:
//   data/etf_daily_wide.csv          date + one column per ETF (adjusted close)
//   data/etf_monthly_long_extra.csv  date + extra ETFs (Alpha Vantage monthly adjusted, as far back as each goes)
// Usage: APCA_API_KEY_ID=... APCA_API_SECRET_KEY=... ALPHAVANTAGE_KEY=... node scripts/build-research.mjs [outDir=data]
import { writeFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { loadBars, ETFS, CASH } from './build-strategies.mjs';
import { parseMonthly } from './build-history.mjs';

export const EXTRA = ['XLK', 'XLE', 'XLF', 'XLV', 'XLU', 'XLP', 'XLY', 'XLI', 'XLB', 'TIP', 'LQD', 'HYG', 'SLV', 'UUP'];

export function wide(bars, syms) {
  const maps = Object.fromEntries(syms.map((s) => [s, new Map((bars[s] || []).map((b) => [b.d, b.c]))]));
  const dates = [...maps.SPY.keys()].sort();
  return ['date,' + syms.join(','), ...dates.map((d) => d + ',' + syms.map((s) => (maps[s].has(d) ? +maps[s].get(d).toFixed(4) : '')).join(','))].join('\n') + '\n';
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const outDir = process.argv[2] || 'data';
  mkdirSync(outDir, { recursive: true });
  const notes = [];
  const syms = [...ETFS, CASH, ...EXTRA];
  try {
    const bars = await loadBars(syms);
    writeFileSync(join(outDir, 'etf_daily_wide.csv'), wide(bars, syms));
    notes.push('daily: ' + bars._source);
  } catch (e) { notes.push('daily failed: ' + e.message); }
  const key = process.env.ALPHAVANTAGE_KEY;
  if (key) {
    const series = {};
    for (const s of EXTRA) {
      try {
        const t = await (await fetch(`https://www.alphavantage.co/query?function=TIME_SERIES_MONTHLY_ADJUSTED&symbol=${s}&datatype=csv&apikey=${key}`)).text();
        series[s] = parseMonthly(t);
      } catch (e) { notes.push(`${s} monthly failed: ${String(e.message).replace(key, '***').slice(0, 160)}`); }
      await new Promise((r) => setTimeout(r, 1600));
    }
    const have = Object.keys(series);
    if (have.length) {
      const cur = new Date().toISOString().slice(0, 7);
      const months = [...new Set(have.flatMap((s) => series[s].map((r) => r.d.slice(0, 7))))].filter((m) => m < cur).sort();
      const by = Object.fromEntries(have.map((s) => [s, new Map(series[s].map((r) => [r.d.slice(0, 7), r]))]));
      const lines = ['month,' + have.join(','), ...months.map((m) => m + ',' + have.map((s) => by[s].get(m)?.c ?? '').join(','))];
      writeFileSync(join(outDir, 'etf_monthly_long_extra.csv'), lines.join('\n') + '\n');
      notes.push('monthly extra: ' + have.join(' '));
    }
  }
  writeFileSync(join(outDir, 'research_notes.txt'), new Date().toISOString() + '\n' + notes.join('\n') + '\n');
  console.log(notes.join('\n'));
}
