// Wash-sale guard between a regular (taxable) account and a Roth IRA account run by a second copy of this bot.
// Off unless a bot runs with ACCOUNT_TYPE=roth. The regular-account bot only writes down its loss sales (a tiny shared file);
// the Roth bot skips buying any stock the regular account sold at a loss in the last 31 days (IRS 30-day window + 1).
// (A Roth buy followed by a loss sale in the regular account within 30 days is not covered: the regular bot never waits to sell.)
import { existsSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { homedir } from 'node:os';
export const LOSS_FILE = process.env.LOSS_SALES_FILE || join(homedir(), '.sentinel-shared', 'loss-sales.json');
const DAY = 86400e3, daysBetween = (a, b) => Math.round((Date.parse(b + 'T12:00:00Z') - Date.parse(a + 'T12:00:00Z')) / DAY);
export const loadLosses = (f = LOSS_FILE) => { try { return existsSync(f) ? JSON.parse(readFileSync(f, 'utf8')) : []; } catch { return []; } };
const save = (rows, f) => { mkdirSync(dirname(f), { recursive: true, mode: 0o700 }); writeFileSync(f, JSON.stringify(rows, null, 1), { mode: 0o600 }); };
/** rows: [{ symbol, date, pl, est }]; est = estimated at order time (price below average cost), replaced by the real result at 'verify' */
export function recordLosses(rows, today, f = LOSS_FILE) {
  if (!rows.length) return;
  const cur = loadLosses(f).filter((x) => daysBetween(x.date, today) <= 120);
  for (const r of rows) {
    const i = cur.findIndex((x) => x.symbol === r.symbol && x.date === r.date);
    if (r.pl != null && r.pl >= 0 && !r.est) { if (i >= 0) cur.splice(i, 1); continue; }   // real result was a gain: drop the estimate
    if (r.pl != null && r.pl >= 0) continue;
    if (i >= 0) cur[i] = { ...cur[i], ...r }; else cur.push(r);
  }
  save(cur, f);
}
export function washBlocked(today, f = LOSS_FILE, window = 31) {
  return new Map(loadLosses(f).filter((x) => { const d = daysBetween(x.date, today); return d >= 0 && d <= window; }).map((x) => [x.symbol, x.date]));
}
