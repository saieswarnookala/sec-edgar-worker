// Dip watch list (read-only, no orders, saves nothing): S&P 500 stocks and ETFs closest to the dip bot's buy rules right now.
// Stock rule: above its 200-day average AND 5-day return at least 10 pts worse than SPY's. ETF rule: above 200-day average AND 5-day return <= -5%.
// Output: job log + GitHub step summary. Usage: APCA_API_KEY_ID=.. APCA_API_SECRET_KEY=.. node scripts/dip-watch.mjs
import { appendFileSync } from 'node:fs';
import { gatherSignals, PAPER, DIP, LOOKBACK, TREND, ETF_DIP_LIST, ETF_DIP, ETF_LOOKBACK } from './paper-dip.mjs';

const avg = (a) => a.reduce((x, y) => x + y, 0) / a.length;
export function watchRows({ members, closes, prices, n = 15 }) {
  const spyR = prices.SPY / closes.SPY.at(-LOOKBACK) - 1, rows = [];
  for (const s of members) {
    const c = closes[s] || [], px = prices[s];
    if (!(px > 0) || c.length < TREND || c.length < LOOKBACK) continue;
    const ma = avg([...c.slice(-(TREND - 1)), px]), r5 = px / c.at(-LOOKBACK) - 1, ex = r5 - spyR;
    rows.push({ s, px, ex, r5, trend: px > ma, ma, buyAt: c.at(-LOOKBACK) * (1 + spyR - DIP) });
  }
  return rows.filter((x) => x.trend).sort((a, b) => a.ex - b.ex).slice(0, n);
}
export function etfRows({ closes, prices, n = 8 }) {
  const rows = [];
  for (const s of ETF_DIP_LIST) {
    const c = closes[s] || [], px = prices[s];
    if (!(px > 0) || c.length < TREND) continue;
    const ma = avg([...c.slice(-(TREND - 1)), px]), r5 = px / c.at(-ETF_LOOKBACK) - 1;
    if (px > ma) rows.push({ s, px, r5, buyAt: c.at(-ETF_LOOKBACK) * (1 - ETF_DIP) });
  }
  return rows.sort((a, b) => a.r5 - b.r5).slice(0, n);
}
const pct = (x) => (x >= 0 ? '+' : '') + (x * 100).toFixed(1) + '%';

async function main() {
  const H = { 'APCA-API-KEY-ID': process.env.APCA_API_KEY_ID, 'APCA-API-SECRET-KEY': process.env.APCA_API_SECRET_KEY };
  const api = async (base, path) => { const r = await fetch(base + path, { headers: H }); const t = await r.text(); if (!r.ok) throw new Error(`${r.status} ${path.split('?')[0]}: ${t.slice(0, 200)}`); return JSON.parse(t); };
  const ny = Object.fromEntries(new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).formatToParts(new Date()).map((x) => [x.type, x.value]));
  const today = `${ny.year}-${ny.month}-${ny.day}`;
  const cal = await api(PAPER, `/v2/calendar?start=${new Date(Date.now() - 470 * 86400e3).toISOString().slice(0, 10)}&end=${today}`);
  const days = cal.map((c) => c.date);
  const g = await gatherSignals({ api, today, days });
  const spyR = g.prices.SPY / g.closes.SPY.at(-LOOKBACK) - 1;
  const st = watchRows(g), et = etfRows(g);
  const L = [`## Dip watch list ${today} ${ny.hour}:${ny.minute} ET`, '', `SPY 5-day: ${pct(spyR)}. A stock qualifies at <= ${pct(-DIP)} vs SPY (and above its 200-day average). Buy signals right now: ${Object.keys(g.scores).join(', ') || 'none'}${g.skipped_heavy_volume ? ' | skipped (heavy volume): ' + g.skipped_heavy_volume.join(', ') : ''}`, '',
    '| Stock | Price | 5-day | vs SPY | Needs to fall | Qualifies below |', '|---|---|---|---|---|---|',
    ...st.map((x) => `| ${x.s} | $${x.px.toFixed(2)} | ${pct(x.r5)} | ${pct(x.ex)} | ${x.ex <= -DIP ? 'QUALIFIES' : pct(x.buyAt / x.px - 1)} | $${x.buyAt.toFixed(2)} |`), '',
    '| ETF | Price | 5-day | Needs to fall | Qualifies below |', '|---|---|---|---|---|',
    ...et.map((x) => `| ${x.s} | $${x.px.toFixed(2)} | ${pct(x.r5)} | ${x.r5 <= -ETF_DIP ? 'QUALIFIES' : pct(x.buyAt / x.px - 1)} | $${x.buyAt.toFixed(2)} |`),
    '', '"Qualifies below" assumes SPY stays where it is. Read-only: no orders, nothing saved.'];
  console.log(L.join('\n'));
  if (process.env.GITHUB_STEP_SUMMARY) appendFileSync(process.env.GITHUB_STEP_SUMMARY, L.join('\n') + '\n');
}
if (import.meta.url === `file://${process.argv[1]}`) main().catch((e) => { console.error(e); process.exit(1); });
