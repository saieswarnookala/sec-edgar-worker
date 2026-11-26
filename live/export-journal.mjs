// Shadow-journal hand-off (Nov 26 2026). Runs on the VM from its OWN timer (dip-journal.timer, 4:50 pm ET), after the trade (3:47) and
// verify (4:35) runs. It only READS ~/.sentinel-live/dip-state.json and sends today's decisions (signals, orders, fills) to the dashboard
// worker; the GitHub shadow journal picks them up. It never imports live-dip.mjs, never talks to Robinhood, never writes the state file.
// Nothing about account size is sent (no equity, cash or buying power).
//   node export-journal.mjs            send today's record
//   node export-journal.mjs --dry      print what would be sent, send nothing
//   node export-journal.mjs --date 2026-11-25
// Config (~/.sentinel-live/config.env): JOURNAL_TOKEN=<same value as the GitHub secret>, optional JOURNAL_URL.
import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { homedir } from 'node:os';
const HOME = process.env.SENTINEL_HOME || join(homedir(), '.sentinel-live');
const cfg = {};
if (existsSync(join(HOME, 'config.env'))) for (const raw of readFileSync(join(HOME, 'config.env'), 'utf8').split('\n')) {
  const m = raw.trim().match(/^([A-Z_][A-Z0-9_]*)=(.*)$/); if (!m) continue;
  let v = m[2].trim(); if (/^["']/.test(v)) { const q = v[0], e = v.indexOf(q, 1); v = e > 0 ? v.slice(1, e) : v.slice(1); } else v = v.replace(/(^|\s+)#.*$/, '').trim();
  cfg[m[1]] = v;
}
const arg = (k) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : null; };
const nyDate = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());

export function buildRecord(state, date) {
  const runs = (state.history || []).filter((h) => h.today === date);
  const intra = (state.intraday || []).filter((x) => x.today === date);
  const sig = new Map();   // symbol -> { first_seen 'HH:MM' ET, dip }
  for (const x of intra) for (const o of x.placed || []) if (o.side === 'buy' && !/^parking/.test(o.why || '')) if (!sig.has(o.symbol)) sig.set(o.symbol, { first_seen: x.ny_time, dip: o.why || null });
  for (const h of runs) for (const s of h.signal_list || []) { const [sym, pct] = String(s).split(' '); if (!sig.has(sym)) sig.set(sym, { first_seen: h.ny_time, dip: pct || null }); }
  const orders = [];
  for (const x of intra) for (const o of x.placed || []) orders.push({ time: x.ny_time, run: 'intraday', symbol: o.symbol, side: o.side, why: o.why || '', mode: x.mode });
  for (const h of runs) for (const o of h.placed || []) orders.push({ time: h.ny_time, run: 'close', symbol: o.symbol, side: o.side, why: o.why || '', mode: h.mode });
  const v = (state.verify || []).filter((x) => x.today === date).at(-1);
  return {
    date, sent: new Date().toISOString(), strategy: runs.at(-1)?.strategy || null, park: runs.at(-1)?.park || null,
    signals: [...sig].map(([symbol, x]) => ({ symbol, ...x })),
    orders, failed: runs.flatMap((h) => (h.failed || []).map((o) => ({ symbol: o.symbol, side: o.side, error: String(o.error || '').slice(0, 120) }))),
    fills: (v?.fills || []).map((f) => ({ symbol: f.symbol, side: f.side, price: f.price, vs_close_pct: f.vs_close_pct })),
    errors: [...runs, ...intra].filter((x) => x.error).map((x) => String(x.error).slice(0, 120)),
  };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const date = arg('--date') || nyDate();
  const state = JSON.parse(readFileSync(join(HOME, 'dip-state.json'), 'utf8'));
  const rec = buildRecord(state, date);
  if (process.argv.includes('--dry')) { console.log(JSON.stringify(rec, null, 1)); process.exit(0); }
  if (!cfg.JOURNAL_TOKEN) { console.error('JOURNAL_TOKEN missing in config.env: nothing sent'); process.exit(0); }
  const url = cfg.JOURNAL_URL || 'https://sentinel-web.saiesh-dev.workers.dev/api/live-journal';
  for (let i = 1; i <= 3; i++) {
    try {
      const r = await fetch(url, { method: 'POST', headers: { authorization: 'Bearer ' + cfg.JOURNAL_TOKEN, 'content-type': 'application/json' }, body: JSON.stringify(rec), signal: AbortSignal.timeout(20000) });
      if (r.ok) { console.log(`sent ${date}: ${rec.signals.length} signals, ${rec.orders.length} orders, ${rec.fills.length} fills`); process.exit(0); }
      console.error(`try ${i}: HTTP ${r.status} ${(await r.text()).slice(0, 200)}`);
    } catch (e) { console.error(`try ${i}:`, e.message); }
    await new Promise((res) => setTimeout(res, 5000 * i));
  }
  process.exit(0);   // journal only: never fail loudly
}
