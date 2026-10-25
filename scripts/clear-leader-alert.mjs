// Slack alerts for Clear leader v2.0. Run by .github/workflows/clear-leader-alert.yml around month-end.
//   phase "preview": ~3 pm ET on the last trading day, using live (15-min delayed) prices -> heads-up if a switch is likely
//   phase "final":   after the close on the last trading day -> the official decision with price ranges
// Sends nothing on other days. Remembers what it sent in data/clear_leader_state.json so nothing is sent twice.
// Usage: node scripts/clear-leader-alert.mjs [auto|test] [--dry-run]
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { run, POOL } from './clear-leader.mjs';

const SYMS = [...POOL, 'BIL'];
const NAMES = { SPY: 'S&P 500', QQQ: 'Nasdaq 100', IWM: 'US small caps', EFA: 'Developed intl stocks', EEM: 'Emerging-market stocks', VNQ: 'US real estate', TLT: 'Long US bonds', IEF: '7–10y US bonds', GLD: 'Gold', DBC: 'Commodities' };
const STATE_FILE = 'data/clear_leader_state.json';
const SITE = process.env.SITE_URL || 'https://sentinel-web.saiesh-dev.workers.dev/#trading-clv2';
const pct = (x) => (x >= 0 ? '+' : '') + (x * 100).toFixed(1) + '%';
const usd = (x) => '$' + x.toFixed(2);

export function nyNow(d = new Date()) {
  const p = Object.fromEntries(new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).formatToParts(d).map((x) => [x.type, x.value]));
  return { date: `${p.year}-${p.month}-${p.day}`, minutes: Number(p.hour) * 60 + Number(p.minute), hhmm: `${p.hour}:${p.minute}` };
}
export function phaseFor(minutes) {
  if (minutes >= 14 * 60 + 45 && minutes < 15 * 60 + 55) return 'preview';
  if (minutes >= 16 * 60 + 20 && minutes < 20 * 60) return 'final';
  return null;
}

async function alpaca(path, env, base = 'https://data.alpaca.markets') {
  const r = await fetch(base + path, { headers: { 'APCA-API-KEY-ID': env.APCA_API_KEY_ID, 'APCA-API-SECRET-KEY': env.APCA_API_SECRET_KEY } });
  if (!r.ok) throw new Error(`Alpaca ${path.split('?')[0]} HTTP ${r.status}: ${(await r.text()).slice(0, 160)}`);
  return r.json();
}
// Is `date` (YYYY-MM-DD, New York) the last trading day of its month? Uses Alpaca's market calendar; falls back to "last weekday".
export async function isLastTradingDay(date, env, fetchCal = null) {
  const [y, m] = date.split('-').map(Number);
  const end = new Date(Date.UTC(y, m, 10)).toISOString().slice(0, 10);
  try {
    const cal = fetchCal ? await fetchCal(date, end) : await alpaca(`/v2/calendar?start=${date}&end=${end}`, env, 'https://paper-api.alpaca.markets');
    const days = cal.map((c) => c.date).filter((d) => d >= date).sort();
    if (days[0] !== date) return false;              // market closed today
    return !days[1] || days[1].slice(0, 7) !== date.slice(0, 7);
  } catch {
    const d = new Date(date + 'T12:00:00Z'), wd = d.getUTCDay();
    if (wd === 0 || wd === 6) return false;
    const n = new Date(d); do n.setUTCDate(n.getUTCDate() + 1); while (n.getUTCDay() === 0 || n.getUTCDay() === 6);
    return n.getUTCMonth() !== d.getUTCMonth();
  }
}

// Daily bars (split + dividend adjusted) since 2016 for all 11 ETFs.
async function dailyBars(env) {
  const out = Object.fromEntries(SYMS.map((s) => [s, []]));
  const end = new Date(Date.now() - 16 * 60e3).toISOString(); // free plan: no SIP data from the last 15 minutes
  const p = new URLSearchParams({ symbols: SYMS.join(','), timeframe: '1Day', start: '2016-01-01', end, limit: '10000', adjustment: 'all', feed: 'sip' });
  for (;;) {
    const js = await alpaca('/v2/stocks/bars?' + p, env);
    for (const [s, bl] of Object.entries(js.bars || {})) for (const b of bl) out[s].push({ d: b.t.slice(0, 10), h: b.h, l: b.l, c: b.c });
    if (!js.next_page_token) break;
    p.set('page_token', js.next_page_token);
  }
  for (const s of SYMS) out[s].sort((a, b) => (a.d < b.d ? -1 : 1));
  return out;
}

// Month-end rows (last day of each month where all 11 traded); the last row is `today` (live price in preview).
export function monthRows(bars, today) {
  const by = Object.fromEntries(SYMS.map((s) => [s, new Map(bars[s].map((b) => [b.d, b.c]))]));
  const dates = [...by.SPY.keys()].filter((d) => d <= today && SYMS.every((s) => by[s].has(d))).sort();
  const me = new Map(); for (const d of dates) me.set(d.slice(0, 7), d);
  return [...me.values()].map((d) => ({ date: d, ...Object.fromEntries(SYMS.map((s) => [s, by[s].get(d)])) }));
}
export function atr14(bars) {
  const b = bars.slice(-15); let t = 0;
  for (let i = 1; i < b.length; i++) t += Math.max(b[i].h - b[i].l, Math.abs(b[i].h - b[i - 1].c), Math.abs(b[i].l - b[i - 1].c));
  return t / (b.length - 1);
}

export function decide(rows) {
  const now = run(rows, {});                 // decision using the latest row (today)
  const before = run(rows.slice(0, -1), {}); // decision at the previous month-end = what you hold now
  return { now: now.now, holding: before.now.pos, switch: now.now.pos !== before.now.pos, asOf: now.asOf };
}

export function message({ phase, d, bars, nyTime, test }) {
  const sell = d.holding, buy = d.now.pos;
  const px = (s) => bars[s][bars[s].length - 1].c, atr = (s) => atr14(bars[s]);
  const range = (s) => { const p = px(s), a = atr(s) / 2; return `${usd(p - a)}–${usd(p + a)}`; };
  const n = d.now, top = n.rank.slice(0, 3).map((x) => `${x.symbol} ${pct(x.ret12)}`).join(' · ');
  const lines = [];
  const tag = test ? ' (TEST — example using today’s data)' : '';
  if (d.switch) {
    lines.push(phase === 'preview'
      ? `:rotating_light: *Clear leader v2.0 — switch likely at today’s close*${tag}`
      : `:bell: *Clear leader v2.0 — SWITCH confirmed at the ${d.asOf} close*${tag}`);
    lines.push(`*Sell ${sell}* (${NAMES[sell]}) — last ${usd(px(sell))} · sell range ${range(sell)}`);
    lines.push(`*Buy ${buy}* (${NAMES[buy]}) — last ${usd(px(buy))} · buy range ${range(buy)} · don’t chase above ${usd(px(buy) + atr(buy))}`);
    lines.push(`Why: ${n.why}.`);
    lines.push(phase === 'preview'
      ? `To match the backtest, trade near today’s 4:00 pm close. I’ll confirm with closing prices after 4:20 pm ET.`
      : `Missed the close? Place the trades at tomorrow’s open inside these ranges (ranges = last price ± half a typical day’s move).`);
  } else {
    if (phase === 'preview' && !test) return null; // only bother you before the close when something changes
    lines.push(`:white_check_mark: *Clear leader v2.0 — no change${phase === 'final' ? ' at the ' + d.asOf + ' close' : ' expected today'}*${tag}`);
    lines.push(`*Keep holding ${buy}* (${NAMES[buy]}) — last ${usd(px(buy))}.`);
    lines.push(`Why: ${n.why}.`);
  }
  lines.push(`Top 3 by 12-month return: ${top}`);
  lines.push(`<${SITE}|Open the dashboard> · checked ${nyTime} ET · not financial advice`);
  return lines.join('\n');
}

async function postSlack(text, env) {
  if (!env.SLACK_WEBHOOK_URL) throw new Error('SLACK_WEBHOOK_URL is not set');
  const r = await fetch(env.SLACK_WEBHOOK_URL, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ text }) });
  if (!r.ok) throw new Error(`Slack HTTP ${r.status}: ${(await r.text()).slice(0, 120)}`);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const mode = process.argv[2] || 'auto', dry = process.argv.includes('--dry-run');
  const env = process.env;
  const ny = nyNow();
  const state = existsSync(STATE_FILE) ? JSON.parse(readFileSync(STATE_FILE, 'utf8')) : {};
  let phase = phaseFor(ny.minutes);
  if (mode === 'test') phase = phase || 'final';
  else {
    if (!phase) { console.log(`${ny.date} ${ny.hhmm} ET: outside the alert windows, nothing to do.`); process.exit(0); }
    if (!(await isLastTradingDay(ny.date, env))) { console.log(`${ny.date}: not the last trading day of the month.`); process.exit(0); }
    if (state[`${ny.date}:${phase}`]) { console.log(`${ny.date} ${phase}: already sent.`); process.exit(0); }
  }
  const bars = await dailyBars(env);
  const rows = monthRows(bars, ny.date);
  if (mode !== 'test' && rows[rows.length - 1].date !== ny.date) { console.log(`No ${ny.date} prices yet (latest ${rows[rows.length - 1].date}); will retry next run.`); process.exit(0); }
  const d = decide(rows);
  const text = message({ phase, d, bars, nyTime: `${ny.date} ${ny.hhmm}`, test: mode === 'test' });
  console.log(text || `${phase}: no switch, nothing to send.`);
  if (text && !dry) await postSlack(text, env);
  if (mode !== 'test') {
    state[`${ny.date}:${phase}`] = { sent: !!text, hold: d.holding, signal: d.now.pos, switch: d.switch, at: new Date().toISOString() };
    writeFileSync(STATE_FILE, JSON.stringify(state, null, 1) + '\n');
  }
}
