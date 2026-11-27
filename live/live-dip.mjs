#!/usr/bin/env node
// LIVE dip strategy on Robinhood's official agentic-trading MCP. Runs on the Oracle VM from systemd timers.
// The strategy code (scripts/paper-dip.mjs: gatherSignals + decide) picks every order, exactly like the backtest and the
// Alpaca paper bot. This file only checks limits, places that exact list through Robinhood's MCP tools, and verifies it.
// No AI picks stocks or sizes orders. Not financial advice.
//
// Commands:  login | doctor | health | trade | preview (today's plan, nothing placed or saved) | intraday | preview-intraday | verify | status | halt | resume
// Config (env, from ~/.sentinel-live/config.env):
//   LIVE_MODE=dry|live (default dry)   RH_ACCOUNT=<agentic account number>   APCA_API_KEY_ID / APCA_API_SECRET_KEY (market data)
//   NTFY_TOPIC=<topic> [NTFY_URL=https://ntfy.sh]   HC_PING_URL=<healthchecks.io ping url, optional>
//   MAX_ORDER_USD (default 20% of account)   MAX_DRAWDOWN=0.35   EQUITY_CAP=<only trade this much of the account, optional>
//   LIVE_STRATEGY=v1|v3|v32 (default v1). v3 = paper bot 10 rules: + ETF dips in free slots + IEF bonds instead of cash when SPY is weak.
//     v32 = v3 at 3:47 pm + the 'intraday' command every 15 min (10:00 ET to 20 min before the close): sell at +5% if held >= 1 day, buy new dips.
//   EXECUTOR=direct|claude (default direct). claude = every Robinhood call goes through official Claude Code + Robinhood MCP
//     (CLAUDE_BIN, CLAUDE_MCP_SERVER=robinhood); our code still decides the orders and checks each call Claude makes.
import { readFileSync, writeFileSync, existsSync, mkdirSync, openSync, closeSync, unlinkSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { gatherSignals, decide, PAPER, DATA, SLOTS, BOND, bondParkSymbol, ETF_DIP_LIST, WEIGHT, BUFFER } from '../scripts/paper-dip.mjs';
import { V32 } from '../scripts/paper-v32.mjs';
import { POOL } from '../scripts/clear-leader.mjs';
import { HOME, connect, call, login, ensureFresh, tokenSecondsLeft, AuthRequired } from './rh-client.mjs';
import { readPositions, readOrders, readMoney, readAvgPrices, buildOrderArgs, planToOrders, checkLimits, fitBuys, formatTradeAlert } from './orders.mjs';
import { claudeClient, UnexpectedAction } from './claude-exec.mjs';
import { fillReport, reportText, reportTitle, reportSvg, reportPng } from './report.mjs';
import { gatherSignalsRH, compareSignals, shadowAlert } from './rh-data.mjs';

// Read ~/.sentinel-live/config.env ourselves. systemd's EnvironmentFile keeps inline "# comments" as part of the value
// (e.g. MAX_DRAWDOWN="0.35   # ..." would silently disable the breaker), so the file always wins, comments stripped.
export function parseConfig(text) {
  const out = {};
  for (const raw of String(text).split('\n')) {
    const line = raw.trim(); if (!line || line.startsWith('#')) continue;
    const m = line.match(/^([A-Z_][A-Z0-9_]*)=(.*)$/); if (!m) continue;
    let v = m[2].trim();
    if (/^["']/.test(v)) { const q = v[0], end = v.indexOf(q, 1); v = end > 0 ? v.slice(1, end) : v.slice(1); } else v = v.replace(/(^|\s+)#.*$/, '').trim();
    out[m[1]] = v;
  }
  return out;
}
const CFG = join(HOME, 'config.env');
if (existsSync(CFG)) Object.assign(process.env, parseConfig(readFileSync(CFG, 'utf8')));
const E = process.env; let MODE = E.LIVE_MODE === 'live' ? 'live' : 'dry'; const STRAT = ['v3', 'v32'].includes(E.LIVE_STRATEGY) ? E.LIVE_STRATEGY : 'v1';
const STATE = join(HOME, 'dip-state.json'), HALT = join(HOME, 'HALT'), TOOLS = join(HOME, 'tools.json'), LOCK = join(HOME, 'run.lock');
mkdirSync(HOME, { recursive: true, mode: 0o700 });
const loadState = () => (existsSync(STATE) ? JSON.parse(readFileSync(STATE, 'utf8')) : { positions: [], history: [] });
const saveState = (s) => writeFileSync(STATE, JSON.stringify(s, null, 1));
const ny = (d = new Date()) => { const p = Object.fromEntries(new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }).formatToParts(d).map((x) => [x.type, x.value])); return { date: `${p.year}-${p.month}-${p.day}`, min: +p.hour * 60 + +p.minute + +p.second / 60, hm: `${p.hour}:${p.minute}` }; };

// ---- alerts ----
export async function notify(title, body, { priority = 3, tags = '' } = {}) {
  console.log(`[alert p${priority}] ${title}\n${body}`);
  if (!E.NTFY_TOPIC) { console.error('ntfy skipped: NTFY_TOPIC is empty in config.env'); return; }
  // headers must be plain ASCII (a stray symbol in the title makes fetch throw); a non-200 reply used to be ignored silently
  const headers = { Title: String(title).replace(/[^\x20-\x7E]/g, '-'), Priority: String(priority), Tags: tags };
  for (let i = 1; i <= 3; i++) {
    try {
      const r = await fetch(`${E.NTFY_URL || 'https://ntfy.sh'}/${E.NTFY_TOPIC}`, { method: 'POST', body: String(body).slice(0, 3800), headers, signal: AbortSignal.timeout(15000) });
      if (r.ok) return;
      console.error(`ntfy failed (try ${i}): HTTP ${r.status} ${(await r.text()).slice(0, 200)}`);
    } catch (e) { console.error(`ntfy failed (try ${i}):`, e.message); }
    if (i < 3) await new Promise((res) => setTimeout(res, 5000 * i));
  }
}
// Image attachment (PUT + Filename); the one-line message goes in a header, so ASCII only. Falls back to a text alert.
export const sampleReport = () => fillReport({ today: '2026-11-27', isParking: (sym) => sym === 'IEF', equity: 102.65, prevEquity: 101.69, vsClosePct: -0.027,
  orders: [{ symbol: 'AMD', side: 'buy', state: 'filled', avg_price: 398.2, filled_qty: 0.025, created_at: '2026-11-20T20:47:00Z' }, { symbol: 'CRWD', side: 'buy', state: 'filled', avg_price: 204.39, filled_qty: 0.049562, created_at: '2026-11-25T15:00:00Z' }],
  todayFills: [{ symbol: 'CRWD', side: 'sell', state: 'filled', avg_price: 214.6, filled_qty: 0.049562, created_at: '2026-11-27T16:00:00Z' }, { symbol: 'CRWD', side: 'buy', state: 'filled', avg_price: 215.29, filled_qty: 0.047611, created_at: '2026-11-27T16:15:00Z' },
    { symbol: 'ANET', side: 'buy', state: 'filled', avg_price: 170.4, filled_qty: 0.0598, created_at: '2026-11-27T15:30:00Z' }, { symbol: 'AMD', side: 'sell', state: 'filled', avg_price: 415.7, filled_qty: 0.025, created_at: '2026-11-27T17:47:00Z' },
    { symbol: 'IEF', side: 'buy', state: 'filled', avg_price: 91.71, filled_qty: 0.0937, created_at: '2026-11-27T16:01:00Z' }, { symbol: 'IEF', side: 'sell', state: 'filled', avg_price: 91.69, filled_qty: 0.08956, created_at: '2026-11-27T16:14:00Z' }] });
export async function notifyImage(title, png, line, fallbackBody, { priority = 3, tags = '' } = {}) {
  if (!png || !E.NTFY_TOPIC) return notify(title, fallbackBody, { priority, tags });
  const headers = { Title: String(title).replace(/[^\x20-\x7E]/g, '-'), Message: String(line).replace(/[^\x20-\x7E]/g, '-').slice(0, 900), Filename: 'trades.png', Priority: String(priority), Tags: tags };
  for (let i = 1; i <= 3; i++) {
    try {
      const r = await fetch(`${E.NTFY_URL || 'https://ntfy.sh'}/${E.NTFY_TOPIC}`, { method: 'PUT', body: png, headers, signal: AbortSignal.timeout(20000) });
      if (r.ok) { console.log(`[alert p${priority}] ${title} (table image)\n${fallbackBody}`); return; }
      console.error(`ntfy image failed (try ${i}): HTTP ${r.status} ${(await r.text()).slice(0, 200)}`);
    } catch (e) { console.error(`ntfy image failed (try ${i}):`, e.message); }
    if (i < 3) await new Promise((res) => setTimeout(res, 5000 * i));
  }
  return notify(title, fallbackBody, { priority, tags });
}
const ping = async (suffix = '') => { if (E.HC_PING_URL) try { await fetch(E.HC_PING_URL + suffix, { method: 'POST' }); } catch {} };

// ---- one run at a time (a slow run must never overlap the backup run and double-trade) ----
function lock() {
  try { if (existsSync(LOCK) && Date.now() - statSync(LOCK).mtimeMs > 30 * 60e3) unlinkSync(LOCK); } catch {}
  try { closeSync(openSync(LOCK, 'wx')); return true; } catch { return false; }
}
const unlock = () => { try { unlinkSync(LOCK); } catch {} };

// ---- Alpaca (market data + market calendar only; no Alpaca orders here) ----
const H = { 'APCA-API-KEY-ID': E.APCA_API_KEY_ID, 'APCA-API-SECRET-KEY': E.APCA_API_SECRET_KEY };
const api = async (base, path) => { const r = await fetch(base + path, { headers: H }); const t = await r.text(); if (!r.ok) throw new Error(`${r.status} ${path.split('?')[0]}: ${t.slice(0, 200)}`); return t ? JSON.parse(t) : null; };
// Market calendar; also remembers each day's real closing time (half days close at 13:00 ET).
const closeMins = {};
const tradingDays = async (today) => (await api(PAPER, `/v2/calendar?start=${new Date(Date.now() - 400 * 86400e3).toISOString().slice(0, 10)}&end=${today}`)).map((c) => { const [hh, mm] = String(c.close || '16:00').split(':'); closeMins[c.date] = +hh * 60 + +mm; return c.date; });
// Trade window relative to the day's close: start 13 min before, last order 1.25 min before (3:47-3:58:45 on a normal day).
export const tradeWindow = (closeMin = 960) => ({ start: closeMin - 13, end: closeMin - 2, cutoff: closeMin - 1.25 });
const fmtMin = (m) => `${Math.floor(m / 60)}:${String(Math.floor(m % 60)).padStart(2, '0')}`;

// ---- Robinhood helpers (argument names come from the tools' own schemas) ----
let toolMap = {};
const EXECUTOR = E.EXECUTOR === 'claude' ? 'claude' : 'direct';
const reloginHint = () => (EXECUTOR === 'claude' ? 'On the VM run: claude, then /mcp, select robinhood, re-authenticate' : 'On the VM run: node live-dip.mjs login');
async function rh() {
  if (!/^\w{5,20}$/.test(E.RH_ACCOUNT || '')) throw new Error('RH_ACCOUNT is missing or invalid in ~/.sentinel-live/config.env (the MCP account number)');
  let client, fresh;
  if (EXECUTOR === 'claude') { client = claudeClient({ toolsFile: TOOLS }); fresh = { executor: 'claude' }; }
  else { fresh = await ensureFresh(); ({ client } = await connect()); }
  const { tools } = await client.listTools();
  toolMap = Object.fromEntries(tools.map((t) => [t.name, t]));
  for (const need of ['get_portfolio', 'get_equity_positions', 'get_equity_orders', 'place_equity_order']) if (!toolMap[need]) throw new Error(`Robinhood tool ${need} not available (tools changed?)`);
  return { client, fresh };
}
const acctArgs = (name, extra = {}) => { const p = toolMap[name]?.inputSchema?.properties || {}; const k = Object.keys(p).find((x) => /account/i.test(x)); return { ...(k && E.RH_ACCOUNT ? { [k]: E.RH_ACCOUNT } : {}), ...extra }; };
const rhRead = async (client) => {
  const [pf, pos, ord] = await Promise.all([call(client, 'get_portfolio', acctArgs('get_portfolio')), call(client, 'get_equity_positions', acctArgs('get_equity_positions')), call(client, 'get_equity_orders', acctArgs('get_equity_orders'))]);
  return { money: readMoney(pf), held: readPositions(pos), orders: readOrders(ord), raw: { pf, pos, ord } };
};
// Robinhood's own answer on fractional shares: true / false when it says so, undefined when unclear or the check failed
// (an order Robinhood can't take is simply rejected, so "unknown" is tried as fractional rather than silently dropped).
export function readFractional(reply) {
  // Only the regular-hours field counts: "extended_hours_fractional_tradability" is about after-hours orders, and the bot
  // trades at ~3:47 pm (Robinhood: fractional / dollar orders place only in regular hours anyway).
  let ans;
  const walk = (x) => {
    if (ans !== undefined || x == null || typeof x !== 'object') return;
    if (Array.isArray(x)) return x.forEach(walk);
    for (const [k, v] of Object.entries(x)) {
      const key = k.toLowerCase();
      if (key === 'fractional_tradability' && typeof v === 'string') { ans = v.toLowerCase() === 'tradable'; return; }
      if (/^(is_)?fractional(ly)?_(tradable|tradability|enabled)$/.test(key) && typeof v === 'boolean') { ans = v; return; }
    }
    for (const v of Object.values(x)) walk(v);
  };
  walk(typeof reply === 'string' ? (() => { try { return JSON.parse(reply); } catch { return null; } })() : reply);
  return ans;
}
async function tradabilityRaw(client, s) {
  const p = toolMap.get_equity_tradability.inputSchema?.properties || {}, k = Object.keys(p).find((x) => /symbol/i.test(x)) || 'symbols';
  return call(client, 'get_equity_tradability', acctArgs('get_equity_tradability', { [k]: p[k]?.type === 'array' ? [s] : s }));
}
const FRAC_RAW = {};
async function fractionalMap(client, syms) {
  const out = {};
  if (!toolMap.get_equity_tradability) return out;
  for (const s of syms) {
    try { const r = await tradabilityRaw(client, s); FRAC_RAW[s] = JSON.stringify(r).slice(0, 600); out[s] = readFractional(r); }
    catch (e) { FRAC_RAW[s] = 'check failed: ' + String(e?.message || e).slice(0, 200); out[s] = undefined; }
  }
  return out;
}
async function cmdTradable() {
  const syms = process.argv.slice(3).map((x) => x.toUpperCase());
  if (!syms.length) return console.log('usage: node live-dip.mjs tradable MRNA GPN');
  const { client } = await rh();
  for (const s of syms) {
    try { const r = await tradabilityRaw(client, s); console.log(s, '-> fractional:', readFractional(r), '\n', JSON.stringify(r, null, 1).slice(0, 1500)); }
    catch (e) { console.log(s, '-> check failed:', e?.message || e); }
  }
}

// ---- commands ----
async function cmdDoctor() {
  if (EXECUTOR === 'claude' && existsSync(TOOLS)) unlinkSync(TOOLS);
  const { client, fresh } = await rh();
  const tools = Object.values(toolMap).map((t) => ({ name: t.name, description: t.description?.slice(0, 200), inputSchema: t.inputSchema }));
  writeFileSync(TOOLS, JSON.stringify(tools, null, 1));
  const accts = await call(client, 'get_accounts', {});
  const r = await rhRead(client);
  const test = buildOrderArgs(toolMap.place_equity_order, { symbol: 'SPY', side: 'buy', dollars: 5 }, E.RH_ACCOUNT);
  const test2 = buildOrderArgs(toolMap.place_equity_order, { symbol: 'SPY', side: 'sell', shares: 0.01 }, E.RH_ACCOUNT);
  const mask = (o) => JSON.parse(JSON.stringify(o).replace(/\d{6,}/g, (m) => '…' + m.slice(-4)));
  console.log(JSON.stringify({ mode: MODE, executor: EXECUTOR, token: fresh, tools: tools.length, saved_schemas: TOOLS, place_equity_order_schema: toolMap.place_equity_order.inputSchema, dollar_order_mapping: mask(test), share_order_mapping: mask(test2),
    accounts: JSON.stringify(accts).replace(/\d{6,}/g, (m) => '…' + m.slice(-4)).slice(0, 1500), money: r.money, positions: r.held, open_or_recent_orders: r.orders.slice(0, 5) }, null, 1));
  console.log('\nSend Claude the "place_equity_order_schema" and both "mapping" lines above (no balances needed).');
}

async function cmdHealth() {
  const problems = [];
  try {
    const { client, fresh } = await rh(); const r = await rhRead(client);
    if (!(r.money.equity > 0)) problems.push('could not read account value');
    const hrs = Math.round((tokenSecondsLeft() || 0) / 3600);
    if (existsSync(HALT)) problems.push('bot is HALTED: ' + readFileSync(HALT, 'utf8').slice(0, 200));
    if (problems.length) { await notify('Dip bot: needs attention', problems.join('\n'), { priority: 4, tags: 'warning' }); await ping('/fail'); }
    else { await ping(); console.log(JSON.stringify({ ok: true, mode: MODE, equity: r.money.equity, buying_power: r.money.buying_power, token_hours_left: hrs, refreshed: fresh.refreshed })); }
  } catch (e) {
    const auth = e instanceof AuthRequired || /401|unauthor|authenticat|sign.?in again|re-?auth|expired token/i.test(String(e.message));
    await notify(auth ? 'Dip bot: Robinhood login expired' : 'Dip bot: health check failed', auth ? reloginHint() + ' (takes 1 minute). No trades until then.' : String(e.message).slice(0, 500), { priority: 5, tags: 'rotating_light' });
    await ping('/fail'); process.exitCode = 1;
  }
}

export async function cmdTrade({ force = E.FORCE === '1', gather = gatherSignals, getDays = tradingDays, preview = false } = {}) {
  if (preview) { MODE = 'dry'; force = true; }   // preview: today's plan on real data, nothing placed, nothing saved, never halts
  const now = ny(), today = now.date, state = loadState();
  const log = { run: new Date().toISOString(), today, ny_time: now.hm, mode: MODE };
  if (existsSync(HALT)) { await notify('Dip bot halted: no trades today', readFileSync(HALT, 'utf8'), { priority: 4, tags: 'stop_sign' }); return; }
  const days = await getDays(today);
  if (days.at(-1) !== today && !force) return console.log('market closed today', today);
  const win = tradeWindow(closeMins[today] ?? 960); log.close_et = fmtMin(win.start + 13);
  if (!force && (now.min < win.start - 0.5 || now.min >= win.end)) return console.log(`outside ${fmtMin(win.start)}-${fmtMin(win.end)} ET window (close ${log.close_et})`, now.hm);
  if (!force && state.history.some((h) => h.today === today && h.mode === 'live' && h.placed?.length)) return console.log('already traded today', today);
  if (!lock()) return console.log('another run is in progress');
  try {
    const { client } = await rh();
    const before = await rhRead(client);
    const accountValue = before.money.equity; if (!(accountValue > 0)) throw new Error('could not read Robinhood account value');
    const equity = E.EQUITY_CAP ? Math.min(accountValue, +E.EQUITY_CAP) : accountValue;
    // drawdown breaker: well beyond the backtest's worst drop (-28%) means something is broken
    state.peak_equity = Math.max(state.peak_equity || 0, accountValue); state.start_equity ??= accountValue;
    const maxDd = +(E.MAX_DRAWDOWN || 0.35);
    if (accountValue < state.peak_equity * (1 - maxDd)) { if (preview) throw new Error('drawdown breaker would trip'); writeFileSync(HALT, `Account fell ${((1 - accountValue / state.peak_equity) * 100).toFixed(0)}% from its peak on ${today}. Check it, then run: node live-dip.mjs resume`); throw new Error('drawdown breaker tripped'); }
    // sync with what Robinhood really holds
    const held = before.held, etfs = [...POOL, 'BIL'];
    state.positions = state.positions.filter((p) => held[p.symbol] > 0).map((p) => ({ ...p, qty: held[p.symbol] }));
    const g = await gather({ api, today, days });
    const parkHeld = Object.fromEntries(Object.entries(held).filter(([s]) => etfs.includes(s) && !state.positions.some((p) => p.symbol === s)));
    // v3 (LIVE_STRATEGY=v3): bonds instead of cash when SPY is weak + ETF dips in free slots, exactly like paper bot 10.
    // One holding can't be both parking and an ETF-dip position, so ETF dips skip today's parking ETF and any ETF held as parking.
    const V3 = STRAT === 'v3' || STRAT === 'v32';
    const park = V3 ? bondParkSymbol({ park: g.park, bondCloses: g.closes?.[BOND], bondPx: g.prices?.[BOND] }) : g.park;
    const etfScores = V3 ? Object.fromEntries(Object.entries(g.etfScores || {}).filter(([s]) => s !== park && !(parkHeld[s] > 0))) : {};
    const plan = decide({ today, days, state, held, equity, prices: g.prices, closes: g.closes, scores: g.scores, park, parkHeld, fractional: true, etfScores });
    const frac = await fractionalMap(client, [...new Set([...plan.buys.map((b) => b.symbol), ...plan.parkTrades.map((t) => t.symbol)])]);
    let orders = planToOrders(plan, g.prices, (s) => frac[s] !== false);
    log.fractional = { answer: frac, raw: FRAC_RAW };
    // idempotency: never re-place an order Robinhood already has for today
    const dayIds = new Set((state.intraday || []).filter((x) => x.today === today).flatMap((x) => (x.placed || []).flatMap((p) => [p.id, ...(p.ids || [])])).filter(Boolean).map(String));
    const todays = before.orders.filter((o) => o.created_at && ny(new Date(o.created_at)).date === today && !/cancel|reject|fail/.test(o.state) && !dayIds.has(String(o.id)) && !(STRAT === 'v32' && ny(new Date(o.created_at)).min < win.start - 1));   // v32: today's intraday orders are not duplicates
    const dupes = orders.filter((o) => todays.some((t) => t.symbol === o.symbol && t.side === o.side));
    if (dupes.length) { log.skipped_already_placed = dupes.map((o) => o.symbol + ' ' + o.side); orders = orders.filter((o) => !dupes.includes(o)); }
    const allowed = new Set([...g.members, ...etfs, ...(V3 ? ETF_DIP_LIST : []), ...Object.keys(held)]);
    const maxOrderUsd = +(E.MAX_ORDER_USD || Math.max(5, equity * 0.2));
    const problems = checkLimits(orders, { equity, held, prices: g.prices, allowed, maxOrderUsd });
    Object.assign(log, { account_value: accountValue, equity_used: equity, buying_power: before.money.buying_power, park: park || 'CASH', strategy: STRAT, etf_signals: Object.keys(etfScores), signals: Object.keys(g.scores).length, signal_list: Object.entries(g.scores).sort((a, b) => a[1] - b[1]).map(([k, v]) => `${k} ${(v * 100).toFixed(1)}%`), skipped_heavy_volume: g.skipped_heavy_volume, plan: orders });
    if (problems.length) { if (preview) throw new Error('safety check would fail: ' + problems.join('; ')); writeFileSync(HALT, `Safety check failed on ${today}: ${problems.join('; ')}`); throw new Error('safety check failed: ' + problems.join('; ')); }
    const placed = [], failed = [];
    const place = async (o) => {
      if (!force && ny().min >= win.cutoff) { failed.push({ ...o, error: 'too close to the close, skipped' }); return; }
      o.refKey = `${E.RH_ACCOUNT}|${today}|${o.symbol}|${o.side}`;
      const b = buildOrderArgs(toolMap.place_equity_order, o, E.RH_ACCOUNT);
      if (!b.ok) { failed.push({ ...o, error: b.error }); return; }
      if (toolMap.review_equity_order) { try { o.review = await call(client, 'review_equity_order', buildOrderArgs(toolMap.review_equity_order, o, E.RH_ACCOUNT).args || b.args); } catch (e) { failed.push({ ...o, error: 'review: ' + e.message }); return; } }
      if (MODE !== 'live') { placed.push({ ...o, dry: true, args: b.args }); return; }
      try { const r = await call(client, 'place_equity_order', b.args); const id = r?.id ?? r?.order_id ?? r?.order?.id; placed.push({ ...o, id, ids: [...uuidsIn(r)], state: r?.state ?? r?.status ?? r?.order?.state }); }
      catch (e) {
        failed.push({ ...o, error: e.message });
        if (e instanceof UnexpectedAction) { writeFileSync(HALT, `Claude Code did something other than the exact order on ${today}: ${e.message}. Check Robinhood, then: node live-dip.mjs resume`); throw e; }
      }
    };
    for (const o of orders.filter((x) => x.side === 'sell')) await place(o);
    // sells fill instantly during market hours; with a limited-margin account the proceeds are spendable right away
    let bp = before.money.buying_power;
    if (MODE === 'live' && placed.some((p) => p.side === 'sell')) { await new Promise((r) => setTimeout(r, 4000)); bp = readMoney(await call(client, 'get_portfolio', acctArgs('get_portfolio'))).buying_power ?? bp; }
    else bp = (bp ?? 0) + orders.filter((o) => o.side === 'sell').reduce((a, o) => a + o.shares * (g.prices[o.symbol] || 0), 0);
    for (const o of fitBuys(orders.filter((x) => x.side === 'buy'), bp ?? equity, g.prices)) await place(o);
    // record entries: share counts get corrected from real holdings on the next run / verify
    // record strategy entries (stock dips and, in v3, ETF dips); parking buys are not positions
    for (const p of placed.filter((x) => x.side === 'buy' && plan.buys.some((b) => b.symbol === x.symbol))) {
      const b = plan.buys.find((x) => x.symbol === p.symbol);
      state.positions.push({ symbol: p.symbol, entry_date: today, qty: p.shares ?? +(p.dollars / g.prices[p.symbol]).toFixed(6), dollars: p.dollars, why: p.why, entry_px: g.prices[p.symbol], ...(b.kind ? { kind: b.kind } : {}) });
    }
    if (MODE === 'live') state.positions = state.positions.filter((p) => !placed.some((x) => x.side === 'sell' && x.symbol === p.symbol));
    Object.assign(log, { placed, failed, prices_at_order: Object.fromEntries(placed.map((p) => [p.symbol, g.prices[p.symbol]])) });
    const r5 = (s) => { const c = g.closes?.[s] || [], p = g.prices?.[s]; return c.length >= 5 && p > 0 ? p / c.at(-5) - 1 : null; };   // same 5-day window as dipScore
    const a = formatTradeAlert({ mode: MODE, today, time: now.hm, planBuys: plan.buys.map((b) => b.symbol), frac, prices: g.prices, spy5: r5('SPY'), moves: Object.fromEntries(Object.keys(g.scores).map((s) => [s, r5(s)])), signals: Object.entries(g.scores).sort((x, y) => x[1] - y[1]), keep: plan.keep, orders, placed, failed, skipped: log.skipped_already_placed || [], park, account: accountValue, buyingPower: bp, slots: SLOTS, heavyVolume: (g.skipped_heavy_volume || []).map((x) => x.symbol ?? x) });
    await notify((preview ? 'PREVIEW (nothing placed) ' : '') + a.title, a.body, { priority: a.priority, tags: a.tags });
    // SHADOW: the same picks from Robinhood data only (after the orders, so it can never delay or change them). RH_SHADOW=0 turns it off.
    if (!preview && E.RH_SHADOW !== '0' && EXECUTOR !== 'claude') {
      try { const rg = await gatherSignalsRH({ client, call, today, members: g.members, closeMin: closeMins[today] ?? 960 }); log.shadow = compareSignals(g, rg); const sa = shadowAlert(log.shadow); await notify(sa.title, sa.body, { priority: 2, tags: 'mag' }); }
      catch (e) { log.shadow = { error: String(e.message || e).slice(0, 300) }; }
    }
  } catch (e) {
    log.error = String(e.message || e);
    const auth = e instanceof AuthRequired || /401|unauthor|authenticat|sign.?in again|re-?auth|expired token/i.test(log.error);
    await notify(auth ? 'Dip bot: Robinhood login expired, NO trades placed' : 'Dip bot: run failed', auth ? reloginHint() : log.error.slice(0, 600), { priority: 5, tags: 'rotating_light' });
    process.exitCode = 1;
  } finally {
    unlock();
    if (!preview) { state.history = [...state.history, log].slice(-500); state.updated = log.run; saveState(state); }
    console.log(JSON.stringify(log, null, 1).slice(0, 6000));
  }
}

// ---- v3.2 during the day (LIVE_STRATEGY=v32), same rules as paper bot 12 (scripts/paper-v32.mjs v32Intraday) ----
// 1) sell a dip position at +5% over its buy price, only if held >= 1 trading day (never a same-day round trip)
// 2) buy new stock dips (then ETF dips) into free slots, 10% each, biggest dips first; never a symbol already held (incl. the parking ETF)
// 3) fund buys from cash first, then by selling part of the parked ETF; target-sell money with nothing to buy goes back to parking (2% buffer)
export function intradayPlan({ today, days, positions, held, equity, cash, prices, scores = {}, etfScores = {}, park, parkHeld = {} }) {
  const ti = days.indexOf(today), sells = [], keep = [], buys = [], parkSells = [];
  for (const p of positions) {
    if (!(held[p.symbol] > 0)) continue;
    const ei = days.indexOf(p.entry_date), age = ei >= 0 ? ti - ei : 99, px = prices[p.symbol];
    if (age >= 1 && p.entry_px > 0 && px >= p.entry_px * (1 + V32.target)) sells.push({ symbol: p.symbol, qty: held[p.symbol], reason: `target +${V32.target * 100}% (now +${((px / p.entry_px - 1) * 100).toFixed(1)}%)` });
    else keep.push(p);
  }
  const sellUsd = sells.reduce((a, x) => a + x.qty * (prices[x.symbol] || 0), 0);
  const parkVal = Object.entries(parkHeld).reduce((a, [s, q]) => a + q * (prices[s] || 0), 0);
  let avail = Math.max(0, cash) + sellUsd + parkVal, slots = SLOTS - keep.length;
  const taken = new Set([...keep.map((p) => p.symbol), ...Object.keys(held).filter((s) => held[s] > 0)]);
  const cands = [...Object.entries(scores).filter(([s]) => !POOL.includes(s)).sort((a, b) => a[1] - b[1]).map(([s, r]) => [s, r, null]),
    ...Object.entries(etfScores).filter(([s]) => s !== park).sort((a, b) => a[1] - b[1]).map(([s, r]) => [s, r, 'etf'])];
  for (const [s, r, kind] of cands) {
    if (slots <= 0) break;
    if (taken.has(s) || !(prices[s] > 0)) continue;
    const usd = Math.min(WEIGHT * equity, avail);
    if (usd < V32.minSlot * equity) break;
    buys.push({ symbol: s, qty: usd / prices[s], usd, dip_pct: +(r * 100).toFixed(1), ...(kind ? { kind } : {}) }); avail -= usd; taken.add(s); slots--;
  }
  let need = buys.reduce((a, b) => a + b.usd, 0) - Math.max(0, cash) - sellUsd;
  for (const [ps, q] of Object.entries(parkHeld)) {
    if (need <= 0.5) break; const px = prices[ps]; if (!(px > 0) || !(q > 0)) continue;
    const qty = Math.min(q, need / px); parkSells.push({ symbol: ps, qty, reason: 'parking: fund intraday dip buys' }); need -= qty * px;
  }
  const leftover = Math.max(0, cash) + sellUsd - buys.reduce((a, b) => a + b.usd, 0) - BUFFER * equity;
  const parkBuy = !parkSells.length && sells.length && park && prices[park] > 0 && leftover >= 1 ? { symbol: park, qty: leftover / prices[park], reason: 'parking: target-sell money' } : null;
  return { sells, keep, buys, parkSells, parkBuy };
}
export async function cmdIntraday({ gather = gatherSignals, getDays = tradingDays, preview = false, nowMin = null } = {}) {
  if (STRAT !== 'v32') return console.log('intraday checks run only with LIVE_STRATEGY=v32 (now ' + STRAT + ')');
  const now = ny(), today = now.date, state = loadState(), mode = preview || E.INTRADAY_MODE === 'dry' ? 'dry' : MODE;   // INTRADAY_MODE=dry: 3:47 run stays live (v3.0 rules), daytime checks only plan
  const log = { run: new Date().toISOString(), today, ny_time: now.hm, mode, kind: 'intraday' };
  if (existsSync(HALT)) return console.log('halted: no intraday check');
  const days = await getDays(today);
  if (days.at(-1) !== today && !preview) return console.log('market closed today', today);
  const closeMin = closeMins[today] ?? 960, m = nowMin ?? now.min;
  if (!preview && (m < V32.firstCheck || m >= closeMin - 20)) return console.log(`outside the intraday window (10:00 ET to ${fmtMin(closeMin - 20)})`, now.hm);
  if (!lock()) return console.log('another run is in progress');
  const slot = `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(Math.floor((m % 60) / 15) * 15).padStart(2, '0')}`;
  try {
    const { client } = await rh();
    const before = await rhRead(client);
    const accountValue = before.money.equity; if (!(accountValue > 0)) throw new Error('could not read Robinhood account value');
    const equity = E.EQUITY_CAP ? Math.min(accountValue, +E.EQUITY_CAP) : accountValue;
    state.peak_equity = Math.max(state.peak_equity || 0, accountValue);
    if (accountValue < state.peak_equity * (1 - +(E.MAX_DRAWDOWN || 0.35))) { if (!preview) writeFileSync(HALT, `Account fell ${((1 - accountValue / state.peak_equity) * 100).toFixed(0)}% from its peak on ${today} (intraday). Check it, then: node live-dip.mjs resume`); throw new Error('drawdown breaker tripped'); }
    const held = before.held, etfs = [...POOL, 'BIL'];
    const avgPx = readAvgPrices(before.raw.pos);   // positions from before v3.2 have no entry_px: use Robinhood's average buy price
    const positions = state.positions.filter((p) => held[p.symbol] > 0).map((p) => ({ ...p, qty: held[p.symbol], entry_px: p.entry_px ?? avgPx[p.symbol] ?? (p.dollars && p.qty ? p.dollars / p.qty : undefined) }));
    const g = await gather({ api, today, days, closeMin });
    const park = bondParkSymbol({ park: g.park, bondCloses: g.closes?.[BOND], bondPx: g.prices?.[BOND] });
    const parkHeld = Object.fromEntries(Object.entries(held).filter(([s]) => etfs.includes(s) && !positions.some((p) => p.symbol === s)));
    const heldVal = Object.entries(held).reduce((a, [s, q]) => a + q * (g.prices[s] || 0), 0);
    const cash = Math.min(before.money.buying_power ?? accountValue - heldVal, accountValue - heldVal);   // never margin
    const plan = intradayPlan({ today, days, positions, held, equity, cash, prices: g.prices, scores: g.scores, etfScores: g.etfScores || {}, park, parkHeld });
    const frac = await fractionalMap(client, plan.buys.map((b) => b.symbol));
    const fr = (s) => frac[s] !== false;
    const r2 = (x) => Math.floor(x * 100) / 100;
    let orders = [...plan.sells.map((x) => ({ symbol: x.symbol, side: 'sell', shares: x.qty, why: x.reason })),
      ...plan.parkSells.map((x) => ({ symbol: x.symbol, side: 'sell', shares: +x.qty.toFixed(6), why: x.reason })),
      ...plan.buys.map((b) => (fr(b.symbol) ? { symbol: b.symbol, side: 'buy', dollars: r2(b.usd), why: `dip ${b.dip_pct}% (intraday)` } : { symbol: b.symbol, side: 'buy', shares: Math.floor(b.qty), why: `dip ${b.dip_pct}% (intraday)` })),
      ...(plan.parkBuy ? [{ symbol: plan.parkBuy.symbol, side: 'buy', dollars: r2(plan.parkBuy.qty * g.prices[plan.parkBuy.symbol]), why: 'parking' }] : [])].filter((o) => (o.dollars ?? o.shares) > 0);
    // never buy a dip symbol twice in a day, never sell a dip position twice (parking orders may repeat across checks)
    const todays = before.orders.filter((o) => o.created_at && ny(new Date(o.created_at)).date === today && !/cancel|reject|fail/.test(o.state));
    orders = orders.filter((o) => /^parking/.test(o.why) || !todays.some((t) => t.symbol === o.symbol && t.side === o.side));
    const allowed = new Set([...g.members, ...etfs, ...ETF_DIP_LIST, ...Object.keys(held)]);
    const problems = checkLimits(orders, { equity, held, prices: g.prices, allowed, maxOrderUsd: +(E.MAX_ORDER_USD || Math.max(5, equity * 0.2)) });
    log.holding = positions.map((p) => ({ symbol: p.symbol, entry_date: p.entry_date, entry_px: p.entry_px ?? null, now: g.prices[p.symbol] ?? null, pct: p.entry_px && g.prices[p.symbol] ? +((g.prices[p.symbol] / p.entry_px - 1) * 100).toFixed(1) : null }));   // dry day: check every position has an entry price
    Object.assign(log, { slot, account_value: accountValue, park: park || 'CASH', cash, signals: Object.keys(g.scores).length, etf_signals: Object.keys(g.etfScores || {}), orders });
    if (problems.length) { if (!preview) writeFileSync(HALT, `Intraday safety check failed on ${today} ${now.hm}: ${problems.join('; ')}`); throw new Error('safety check failed: ' + problems.join('; ')); }
    const placed = [], failed = [];
    for (const o of [...orders.filter((x) => x.side === 'sell'), ...orders.filter((x) => x.side === 'buy')]) {
      o.refKey = `${E.RH_ACCOUNT}|${today}|${slot}|${o.symbol}|${o.side}`;   // one key per 15-min check: a retry can't double, the next check can
      const b = buildOrderArgs(toolMap.place_equity_order, o, E.RH_ACCOUNT);
      if (!b.ok) { failed.push({ ...o, error: b.error }); continue; }
      if (mode !== 'live') { placed.push({ ...o, dry: true }); continue; }
      try { const r = await call(client, 'place_equity_order', b.args); placed.push({ ...o, id: r?.id ?? r?.order_id ?? r?.order?.id, ids: [...uuidsIn(r)], state: r?.state ?? r?.status ?? r?.order?.state }); }
      catch (e) { failed.push({ ...o, error: e.message }); if (e instanceof UnexpectedAction) { writeFileSync(HALT, `Claude Code did something other than the exact order (intraday ${today}): ${e.message}`); throw e; } }
      if (o.side === 'sell' && mode === 'live') await new Promise((r) => setTimeout(r, 2000));
    }
    Object.assign(log, { placed, failed });
    if (!preview && mode === 'live') {   // dry runs record nothing (holdings don't change), so a dry day shows the same plan each check
      for (const p of placed.filter((x) => x.side === 'buy' && !/^parking/.test(x.why))) {
        const b = plan.buys.find((x) => x.symbol === p.symbol);
        state.positions.push({ symbol: p.symbol, entry_date: today, qty: p.shares ?? +(p.dollars / g.prices[p.symbol]).toFixed(6), dollars: p.dollars, why: p.why, entry_px: g.prices[p.symbol], bought_intraday: true, ...(b?.kind ? { kind: b.kind } : {}) });
      }
      state.positions = state.positions.filter((p) => !placed.some((x) => x.side === 'sell' && x.symbol === p.symbol && !/^parking/.test(x.why)));
    }
    const sig = placed.map((o) => o.side + o.symbol).sort().join(',');   // dry mode: alert only when the plan changes, not every 15 minutes
    const quiet = mode !== 'live' && !preview && (state.intraday || []).some((x) => x.today === today && (x.placed || []).map((o) => o.side + o.symbol).sort().join(',') === sig);
    if ((placed.length || failed.length || preview) && !quiet) await notify(`${preview ? 'PREVIEW (nothing placed) ' : ''}${mode === 'live' ? 'LIVE' : 'DRY'} dip bot v3.2 ${today} ${now.hm} ET: ${placed.length} order(s)${failed.length ? `, ${failed.length} failed` : ''}`,
      [...placed.map((o) => `${o.side.toUpperCase()} ${o.symbol} ${o.dollars != null ? '$' + o.dollars : o.shares + ' sh'} - ${o.why}`), ...failed.map((o) => `FAILED ${o.side} ${o.symbol}: ${o.error}`), `park: ${park || 'CASH'} | dips seen: ${Object.keys(g.scores).length} stocks, ${Object.keys(g.etfScores || {}).length} ETFs`].join('\n') || 'no orders', { priority: failed.length ? 4 : 3, tags: 'chart_with_upwards_trend' });
  } catch (e) {
    log.error = String(e?.message || e).slice(0, 1000);
    const auth = e instanceof AuthRequired || /sign in|login|unauthorized|401/i.test(log.error);
    const errKey = `${today}|${auth ? 'auth' : log.error.slice(0, 60)}`;   // one alert per problem per day, not one every 15 minutes
    if (preview || state.intraday_alerted !== errKey) await notify(auth ? 'Dip bot v3.2: Robinhood login expired, intraday checks skipped' : 'Dip bot v3.2: intraday check failed', (auth ? reloginHint() : log.error.slice(0, 600)) + '\n(further identical errors today stay quiet)', { priority: 4, tags: 'warning' });
    state.intraday_alerted = errKey;
    process.exitCode = 1;
  } finally {
    unlock();
    if (!preview) { state.intraday = [...(state.intraday || []), log].slice(-400); state.updated = log.run; saveState(state); }
    console.log(JSON.stringify(log, null, 1).slice(0, 4000));
  }
}

// Robinhood daily bar close for one symbol on `day` (YYYY-MM-DD) from a get_equity_historicals reply, whatever its nesting.
export function rhCloseOn(reply, day) {
  let best = null;
  const walk = (x) => {
    if (Array.isArray(x)) return x.forEach(walk);
    if (!x || typeof x !== 'object') return;
    const t = x.begins_at ?? x.timestamp ?? x.time ?? x.date ?? x.t, c = x.close_price ?? x.close ?? x.c;
    if (t != null && c != null && String(t).slice(0, 10) === day && Number(c) > 0) best = Number(c);
    Object.values(x).forEach(walk);
  };
  walk(reply); return best;
}
// Today's close per symbol from a get_equity_quotes reply: results[].close when dated today, else the last regular-hours trade
export function rhTodayClose(reply, today) {
  const out = {};
  for (const r of reply?.data?.results || reply?.results || []) {
    const q = r.quote || {}, c = r.close || {}, sym = q.symbol || c.symbol;
    if (!sym) continue;
    if (c.date === today && +c.price > 0) out[sym] = +c.price;
    else if (+q.last_trade_price > 0 && String(q.venue_last_trade_time || '').slice(0, 10) === today) out[sym] = +q.last_trade_price;
  }
  return out;
}
// Every UUID anywhere in a reply (Robinhood places the order under an approval id, so the order id can differ from the first id seen)
export function uuidsIn(x, out = new Set()) {
  if (typeof x === 'string') { for (const m of x.matchAll(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi)) out.add(m[0].toLowerCase()); }
  else if (x && typeof x === 'object') for (const v of Object.values(x)) uuidsIn(v, out);
  return out;
}
// Which of today's account orders are the bot's: by id first; then, for the bot's orders whose id we couldn't see, the same
// side + symbol, at most as many as the bot placed (so an extra order in the same stock still counts as a stranger).
export function matchOurOrders(placed, todays) {
  const ids = new Set(placed.flatMap((p) => [p.id, ...(p.ids || [])]).filter(Boolean).map((x) => String(x).toLowerCase()));
  const left = {}; for (const p of placed) { const k = `${p.side}|${p.symbol}`; left[k] = (left[k] || 0) + 1; }
  const mine = new Set();
  for (const o of todays) if (o.id && ids.has(String(o.id).toLowerCase())) { mine.add(o); left[`${o.side}|${o.symbol}`]--; }
  for (const o of todays) { const k = `${o.side}|${o.symbol}`; if (!mine.has(o) && left[k] > 0) { mine.add(o); left[k]--; } }
  return mine;
}
// After the close: confirm fills from Robinhood's own order history, measure fill vs closing price, catch strangers.
// Runs at 13:35 and 16:35 ET: acts once per day, at least 30 min after that day's real close (13:35 only on 1 pm half days). 'verify force' = run now.
export const verifyGate = ({ nowMin, closeMin, doneToday, force = false }) => force ? 'run' : closeMin == null ? 'skip: market closed today' : nowMin < closeMin + 30 ? 'skip: too early (close ' + fmtMin(closeMin) + ')' : doneToday ? 'skip: already verified today' : 'run';
async function cmdVerify() {
  const now = ny(), today = now.date, state = loadState(), h = [...state.history].reverse().find((x) => x.today === today && x.placed);
  const force = process.argv.includes('force');
  if (!force) {
    let cm = 960;
    try { const days = await tradingDays(today); cm = days.includes(today) ? closeMins[today] ?? 960 : null; } catch (e) { cm = 960; }
    const gate = verifyGate({ nowMin: now.min, closeMin: cm, doneToday: (state.verify || []).some((x) => x.today === today) });
    if (gate !== 'run') return console.log('verify', gate, now.hm);
  }
  try {
    const { client } = await rh(); const r = await rhRead(client);
    state.positions = state.positions.filter((p) => r.held[p.symbol] > 0).map((p) => ({ ...p, qty: r.held[p.symbol] }));
    const todays = r.orders.filter((o) => o.created_at && ny(new Date(o.created_at)).date === today);
    const mine = matchOurOrders([...(h?.placed || []), ...(state.intraday || []).filter((x) => x.today === today).flatMap((x) => x.placed || [])], todays);
    const strangers = MODE === 'live' ? todays.filter((o) => o.id && !mine.has(o) && !/cancel|reject|fail/.test(o.state)) : [];
    const unfilled = todays.filter((o) => mine.has(o) && !/fill/.test(o.state));
    // fill quality vs the official close (the backtest's "ideal" price)
    let closes = {}, log_close_err = null;
    const syms = [...new Set(todays.map((o) => o.symbol))];
    // 1) Alpaca's official SIP close. Free data: SIP only for data older than 15 minutes (an end time in the future is refused) -> end = now - 16 min, IEX as a fallback
    for (const feed of ['sip', 'iex']) {
      if (!syms.length || syms.every((s) => closes[s])) break;
      try { const js = await api(DATA, '/v2/stocks/bars?' + new URLSearchParams({ symbols: syms.join(','), timeframe: '1Day', start: today, end: new Date(Date.now() - 16 * 60e3).toISOString(), feed })); for (const [s, b] of Object.entries(js.bars || {})) if (!closes[s] && b.at(-1)?.c) closes[s] = b.at(-1).c; }
      catch (e) { log_close_err = String(e.message || e).slice(0, 200); }
    }
    // 2) backup: Robinhood quotes. Its daily bars leave out today until it settles, so: the official close if it is already
    //    today's, else the last regular-session trade (within ~0.01% of the official close in the Nov 19 check)
    const miss = syms.filter((x) => !closes[x]);
    if (miss.length && toolMap.get_equity_quotes) {
      try { closes = { ...closes, ...rhTodayClose(await call(client, 'get_equity_quotes', { symbols: miss }), today) }; }
      catch (e) { log_close_err = (log_close_err ? log_close_err + ' | ' : '') + 'robinhood: ' + String(e.message || e).slice(0, 160); }
    }
    const fills = todays.filter((o) => o.avg_price).map((o) => ({ symbol: o.symbol, side: o.side, price: o.avg_price, close: closes[o.symbol] ?? null, vs_close_pct: closes[o.symbol] ? +(((o.avg_price / closes[o.symbol]) - 1) * (o.side === 'buy' ? 100 : -100)).toFixed(3) : null }));
    const v = { today, filled: fills.length, unfilled: unfilled.map((o) => `${o.side} ${o.symbol} (${o.state})`), strangers: strangers.map((o) => `${o.side} ${o.symbol} ${o.id}`), fills, avg_cost_vs_close_pct: fills.filter((f) => f.vs_close_pct != null).length ? +(fills.filter((f) => f.vs_close_pct != null).reduce((a, f) => a + f.vs_close_pct, 0) / fills.filter((f) => f.vs_close_pct != null).length).toFixed(3) : null, equity: r.money.equity, close_lookup_error: log_close_err };
    const prevEq = (state.verify || []).at(-1)?.equity ?? null;
    state.verify = [...(state.verify || []), v].slice(-500); saveState(state);
    const whys = {};
    for (const p of [...(h?.placed || []), ...(state.intraday || []).filter((x) => x.today === today).flatMap((x) => x.placed || [])]) (whys[p.symbol + ':' + p.side] ||= []).push(String(p.why || ''));
    const isParking = (sym, side) => { const w = whys[sym + ':' + side]; return w?.length ? w.every((x) => /parking/i.test(x)) : [BOND, 'BIL', ...POOL].includes(sym); };
    const R = fillReport({ today, orders: r.orders, todayFills: todays.filter((o) => mine.has(o) && /fill/.test(o.state)), isParking, equity: r.money.equity, prevEquity: prevEq, vsClosePct: v.avg_cost_vs_close_pct });
    const line = [R.sells.length ? 'Sold ' + R.sells.map((x) => `${x.symbol} ${x.pl == null ? '' : (x.pl >= 0 ? '+$' : '-$') + Math.abs(x.pl).toFixed(2)}`).join(', ') : '', R.buys.length ? 'Bought ' + R.buys.map((x) => x.symbol).join(', ') : '', `Account $${(R.equity || 0).toFixed(2)}`].filter(Boolean).join(' | ');
    if (strangers.length) { writeFileSync(HALT, `Orders today that the bot did not place: ${v.strangers.join(', ')}. Check Robinhood, then: node live-dip.mjs resume`); await notify('Dip bot HALTED: unknown orders in the account', v.strangers.join('\n'), { priority: 5, tags: 'rotating_light' }); }
    else if (unfilled.length) await notify(`LIVE dip bot ${today}: ${unfilled.length} order(s) NOT filled`, ['Not filled (check Robinhood):', ...v.unfilled, '', reportText(R)].join('\n'), { priority: 4, tags: 'warning' });
    else if ((h?.placed?.length || fills.length) && MODE === 'live') await notifyImage(reportTitle(R), await reportPng(reportSvg(R)), line, reportText(R), { priority: 3, tags: 'white_check_mark' });
    console.log(JSON.stringify(v, null, 1));
  } catch (e) { await notify('Dip bot: verify failed', String(e.message).slice(0, 500), { priority: 4, tags: 'warning' }); process.exitCode = 1; }
}

// Read-only peek at any Robinhood tool: node live-dip.mjs rhcall get_equity_quotes '{"symbols":["AMD"]}'
async function cmdRhCall() {
  const name = process.argv[3] || '', args = JSON.parse(process.argv[4] || '{}');
  if (!/^get_/.test(name)) throw new Error('rhcall only runs read-only get_* tools');
  const { client } = await rh();
  if (!toolMap[name]) throw new Error('no such tool: ' + name);
  console.log(JSON.stringify(await call(client, name, args), null, 1).slice(0, 4000));
}

// Compare Alpaca and Robinhood data right now, no orders: node live-dip.mjs shadow
async function cmdShadow() {
  const today = ny().date, days = await tradingDays(today);
  const { client } = await rh();
  const a = await gatherSignals({ api, today, days });
  const b = await gatherSignalsRH({ client, call, today, members: a.members, closeMin: closeMins[today] ?? 960 });
  const c = compareSignals(a, b), sa = shadowAlert(c);
  console.log(sa.title + '\n' + sa.body + '\n' + JSON.stringify({ ...c, watch: c.watch.slice(0, 15) }, null, 1));
}

function cmdStatus() {
  const s = loadState();
  console.log(JSON.stringify({ mode: MODE, halted: existsSync(HALT) ? readFileSync(HALT, 'utf8') : false, token_hours_left: Math.round((tokenSecondsLeft() || 0) / 3600), positions: s.positions, peak_equity: s.peak_equity, last_runs: s.history.slice(-3).map((h) => ({ today: h.today, mode: h.mode, placed: h.placed?.length, failed: h.failed?.length, error: h.error })), last_verify: s.verify?.at(-1) }, null, 1));
}

const cmd = process.argv[2];
if (import.meta.url === `file://${process.argv[1]}`) {
  const run = { login: async () => { await login(); console.log('Next: node live-dip.mjs doctor'); }, doctor: cmdDoctor, health: cmdHealth, trade: () => cmdTrade(), preview: () => cmdTrade({ preview: true }), intraday: () => cmdIntraday(), 'preview-intraday': () => cmdIntraday({ preview: true }), rhcall: cmdRhCall, shadow: cmdShadow, tradable: cmdTradable, verify: cmdVerify, status: cmdStatus,
    'ntfy-test': () => notify('Dip bot: test alert', 'If you see this on your phone, alerts from the VM work. ' + new Date().toISOString()),
    'report-test': async () => { const R = sampleReport(); await notifyImage('SAMPLE ' + reportTitle(R), await reportPng(reportSvg(R)), 'Sample of the new end-of-day table (made-up AMD buy price)', reportText(R), { priority: 2, tags: 'white_check_mark' }); },
    halt: () => { writeFileSync(HALT, 'Stopped by hand ' + new Date().toISOString()); console.log('halted'); }, resume: () => { try { unlinkSync(HALT); } catch {} console.log('resumed'); } }[cmd];
  if (!run) { console.log('usage: node live-dip.mjs login|doctor|health|trade|preview|intraday|preview-intraday|tradable SYM..|verify|shadow|rhcall get_tool {json}|status|ntfy-test|report-test|halt|resume'); process.exit(2); }
  Promise.resolve(run()).catch(async (e) => { console.error(e); await notify('Dip bot: ' + cmd + ' crashed', String(e?.message || e).slice(0, 500), { priority: 4 }); process.exit(1); });
}
