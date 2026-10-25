// Long monthly history (dividend-adjusted) for the momentum ETFs from Alpha Vantage's free
// TIME_SERIES_MONTHLY_ADJUSTED endpoint. 11 calls, ~1.5 s apart (free plan: 25/day, 1/sec).
// Writes data/etf_monthly_long.csv: date + adjusted month-end close per ETF, months where all 11 exist.
// Usage: ALPHAVANTAGE_KEY=... node scripts/build-history.mjs [outDir=data]
import { writeFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';

export const SYMS = ['SPY', 'QQQ', 'IWM', 'EFA', 'EEM', 'VNQ', 'TLT', 'IEF', 'GLD', 'DBC', 'BIL'];

export function parseMonthly(csv) {
  const lines = csv.trim().split(/\r?\n/);
  const h = lines[0].split(',');
  const di = h.indexOf('timestamp'), ai = h.indexOf('adjusted close');
  if (di < 0 || ai < 0) throw new Error('Unexpected Alpha Vantage response: ' + csv.slice(0, 200));
  return lines.slice(1).map((l) => l.split(',')).map((c) => ({ d: c[di], c: Number(c[ai]) })).filter((r) => r.d && r.c > 0);
}

export function combine(series, today = new Date().toISOString().slice(0, 10)) {
  const cur = today.slice(0, 7);
  const maps = Object.fromEntries(Object.entries(series).map(([s, rows]) => [s, new Map(rows.filter((r) => r.d.slice(0, 7) < cur).map((r) => [r.d.slice(0, 7), r]))]));
  const months = [...maps[SYMS[0]].keys()].filter((m) => SYMS.every((s) => maps[s].has(m))).sort();
  return ['date,' + SYMS.join(','), ...months.map((m) => maps.SPY.get(m).d + ',' + SYMS.map((s) => maps[s].get(m).c).join(','))].join('\n') + '\n';
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const key = process.env.ALPHAVANTAGE_KEY;
  const outDir = process.argv[2] || 'data';
  mkdirSync(outDir, { recursive: true });
  try {
    if (!key) throw new Error('ALPHAVANTAGE_KEY is not set');
    const series = {};
    for (const s of SYMS) {
      const r = await fetch(`https://www.alphavantage.co/query?function=TIME_SERIES_MONTHLY_ADJUSTED&symbol=${s}&datatype=csv&apikey=${key}`);
      const t = await r.text();
      series[s] = parseMonthly(t);
      console.log(s, series[s].length, 'months, from', series[s].at(-1)?.d);
      await new Promise((res) => setTimeout(res, 1600));
    }
    const csv = combine(series);
    writeFileSync(join(outDir, 'etf_monthly_long.csv'), csv);
    console.log('rows', csv.trim().split('\n').length - 1);
  } catch (e) {
    writeFileSync(join(outDir, 'history_error.txt'), new Date().toISOString() + '\n' + String(e.message || e).replace(key || '#', '***') + '\n');
    console.error(e.message); process.exit(1);
  }
}
