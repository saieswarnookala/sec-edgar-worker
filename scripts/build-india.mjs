// India data for Clear leader v2.0: monthly adjusted closes for candidate NSE/BSE ETFs (Alpha Vantage, *.BSE),
// with unadjusted splits fixed (e.g. GOLDBEES 1:100 in Dec 2019). Writes:
//   data/india_monthly_raw.json  raw adjusted closes per symbol (for auditing)
//   data/india_monthly.csv       cleaned month-end closes, one column per ETF that has data
//   data/india_report.json       per-symbol: found?, first month, rows, split fixes, dividends seen
// Usage: ALPHAVANTAGE_KEY=... node scripts/build-india.mjs [outDir=data]
import { writeFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { parseMonthly } from './build-history.mjs';

export const CANDIDATES = ['NIFTYBEES', 'JUNIORBEES', 'BANKBEES', 'GOLDBEES', 'MON100', 'LIQUIDBEES', 'SETF10GILT', 'CPSEETF', 'INFRABEES', 'PSUBNKBEES'];
const NICE = [2, 3, 4, 5, 10, 20, 25, 50, 100, 1000];

// Rescale earlier prices when a month-to-month move is an unadjusted split (or reverse split).
export function fixSplits(rowsAsc) {
  const out = rowsAsc.map((r) => ({ ...r })), fixes = [];
  for (let i = out.length - 1; i > 0; i--) {
    const r = out[i].c / out[i - 1].c;
    let f = null;
    if (r < 0.2) f = NICE.find((n) => Math.abs(1 / r / n - 1) < 0.35);
    else if (r > 5) f = 1 / NICE.find((n) => Math.abs(r / n - 1) < 0.35);
    if (f) { for (let k = 0; k < i; k++) out[k].c /= f; fixes.push({ month: out[i].d.slice(0, 7), ratio: +(f >= 1 ? f : -1 / f).toFixed(2) }); }
  }
  return { rows: out, fixes };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const key = process.env.ALPHAVANTAGE_KEY, outDir = process.argv[2] || 'data';
  mkdirSync(outDir, { recursive: true });
  const raw = {}, report = {}, clean = {};
  for (const s of CANDIDATES) {
    try {
      const t = await (await fetch(`https://www.alphavantage.co/query?function=TIME_SERIES_MONTHLY_ADJUSTED&symbol=${s}.BSE&datatype=csv&apikey=${key}`)).text();
      if (!t.startsWith('timestamp')) { report[s] = { found: false, note: t.replace(key || '#', '***').slice(0, 160) }; }
      else {
        const L = t.trim().split(/\r?\n/), h = L[0].split(','), di = h.indexOf('dividend amount');
        const divs = L.slice(1).filter((l) => Number(l.split(',')[di]) > 0).length;
        const rows = parseMonthly(t).sort((a, b) => (a.d < b.d ? -1 : 1));
        raw[s] = rows;
        const { rows: fixed, fixes } = fixSplits(rows);
        clean[s] = fixed;
        report[s] = { found: true, first: rows[0]?.d, last: rows[rows.length - 1]?.d, months: rows.length, split_fixes: fixes, dividend_months: divs,
          last_12m_return: rows.length > 13 ? +(fixed[fixed.length - 1].c / fixed[fixed.length - 13].c - 1).toFixed(4) : null };
      }
    } catch (e) { report[s] = { found: false, note: String(e.message).slice(0, 160) }; }
    await new Promise((r) => setTimeout(r, 1600));
  }
  const cur = new Date().toISOString().slice(0, 7);
  const have = Object.keys(clean);
  const months = [...new Set(have.flatMap((s) => clean[s].map((r) => r.d.slice(0, 7))))].filter((m) => m < cur).sort();
  const by = Object.fromEntries(have.map((s) => [s, new Map(clean[s].map((r) => [r.d.slice(0, 7), r]))]));
  const lines = ['month,' + have.join(','), ...months.map((m) => m + ',' + have.map((s) => (by[s].get(m) ? +by[s].get(m).c.toFixed(4) : '')).join(','))];
  writeFileSync(join(outDir, 'india_monthly.csv'), lines.join('\n') + '\n');
  writeFileSync(join(outDir, 'india_monthly_raw.json'), JSON.stringify(raw));
  writeFileSync(join(outDir, 'india_report.json'), JSON.stringify(report, null, 1));
  console.log(JSON.stringify(report, null, 1));
}
