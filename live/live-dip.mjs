#!/usr/bin/env node
// LIVE dip strategy on Robinhood's official agentic-trading MCP. Runs on the Oracle VM from systemd timers.
// The strategy code (scripts/paper-dip.mjs: gatherSignals + decide) picks every order, exactly like the backtest and the
// Alpaca paper bot. This file only checks limits, places that exact list through Robinhood's MCP tools, and verifies it.
// No AI picks stocks or sizes orders. Not financial advice.
//
// Commands:  login | doctor | health | trade | verify | status | halt | resume
// Config (env, from ~/.sentinel-live/config.env):
//   LIVE_MODE=dry|live (default dry)   RH_ACCOUNT=<agentic account number>   APCA_API_KEY_ID / APCA_API_SECRET_KEY (market data)
//   NTFY_TOPIC=<topic> [NTFY_URL=https://ntfy.sh]   HC_PING_URL=<healthchecks.io ping url, optional>
//   MAX_ORDER_USD (default 20% of account)   MAX_DRAWDOWN=0.35   EQUITY_CAP=<only trade this much of the account, optional>
//   EXECUTOR=direct|claude (default direct). claude = every Robinhood call goes through official Claude Code + Robinhood MCP
//     (CLAUDE_BIN, CLAUDE_MCP_SERVER=robinhood); our code still decides the orders and checks each call Claude makes.
import { readFileSync, writeFileSync, existsSync, mkdirSync, openSync, closeSync, unlinkSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { gatherSignals, decide, PAPER, DATA } from '../scripts/paper-dip.mjs';
import { POOL } from '../scripts/clear-leader.mjs';
import { HOME, connect, call, login, ensureFresh, tokenSecondsLeft, AuthRequired } from './rh-client.mjs';
import { readPositions, readOrders, readMoney, buildOrderArgs, planToOrders, checkLimits, fitBuys } from './orders.mjs';
import { claudeClient, UnexpectedAction } from './claude-exec.mjs';

const E = process.env, MODE = E.LIVE_MODE === 'live' ? 'live' : 'dry';
const STATE = join(HOME, 'dip-state.json'), HALT = join(HOME, 'HALT'), TOOLS = join(HOME, 'tools.json'), LOCK = join(HOME, 'run.lock');
mkdirSync(HOME, { recursive: true, mode: 0o700 });
const loadState = () => (existsSync(STATE) ? JSON.parse(readFileSync(STATE, 'utf8')) : { positions: [], history: [] });
const saveState = (s) => writeFileSync(STATE, JSON.stringify(s, null, 1));
const ny = (d = new Date()) => { const p = Object.fromEntries(new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }).formatToParts(d).map((x) => [x.type, x.value])); return { date: `${p.year}-${p.month}-${p.day}`, min: +p.hour * 60 + +p.minute + +p.second / 60, hm: `${p.hour}:${p.minute}` }; };

// ---- alerts ----
export async function notify(title, body, { priority = 3, tags = '' } = {}) {
  console.log(`[alert p${priority}] ${title}\n${body}`);
  if (!E.NTFY_TOPIC) return;
  try { await fetch(`${E.NTFY_URL || 'https://ntfy.sh'}/${E.NTFY_TOPIC}`, { method: 'POST', body: String(body).slice(0, 3800), headers: { Title: title, Priority: String(priority), Tags: tags } }); } catch (e) { console.error('ntfy failed', e.message); }
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
const tradingDays = async (today) => (await api(PAPER, `/v2/calendar?start=${new Date(Date.now() - 400 * 86400e3).toISOString().slice(0, 10)}&end=${today}`)).map((c) => c.date);

// ---- Robinhood helpers (argument names come from the tools' own schemas) ----
let toolMap = {};
const EXECUTOR = E.EXECUTOR === 'claude' ? 'claude' : 'direct';
const reloginHint = () => (EXECUTOR === 'claude' ? 'On the VM run: claude, then /mcp, select robinhood, re-authenticate' : 'On the VM run: node live-dip.mjs login');
async function rh() {
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
async function fractionalMap(client, syms) {
  const out = {};
  if (!toolMap.get_equity_tradability) return out;
  const p = toolMap.get_equity_tradability.inputSchema?.properties || {}, k = Object.keys(p).find((x) => /symbol/i.test(x)) || 'symbols';
  for (const s of syms) {
    try { const r = await call(client, 'get_equity_tradability', acctArgs('get_equity_tradability', { [k]: p[k]?.type === 'array' ? [s] : s })); const txt = JSON.stringify(r).toLowerCase(); out[s] = /fractional[^,]*(true|"tradable"|"yes")/.test(txt) && !/fractional[^,]*(false|"untradable"|"no")/.test(txt); } catch { out[s] = false; }
  }
  return out;
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
  console.log(JSON.stringify({ executor: EXECUTOR, token: fresh, tools: tools.length, saved_schemas: TOOLS, place_equity_order_schema: toolMap.place_equity_order.inputSchema, dollar_order_mapping: test, share_order_mapping: test2,
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

export async function cmdTrade({ force = E.FORCE === '1', gather = gatherSignals, getDays = tradingDays } = {}) {
  const now = ny(), today = now.date, state = loadState();
  const log = { run: new Date().toISOString(), today, ny_time: now.hm, mode: MODE };
  if (existsSync(HALT)) { await notify('Dip bot halted: no trades today', readFileSync(HALT, 'utf8'), { priority: 4, tags: 'stop_sign' }); return; }
  const days = await getDays(today);
  if (days.at(-1) !== today && !force) return console.log('market closed today', today);
  if (!force && (now.min < 15 * 60 + 45 || now.min >= 15 * 60 + 58)) return console.log('outside 3:45-3:58 pm ET window', now.hm);
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
    if (accountValue < state.peak_equity * (1 - maxDd)) { writeFileSync(HALT, `Account fell ${((1 - accountValue / state.peak_equity) * 100).toFixed(0)}% from its peak on ${today}. Check it, then run: node live-dip.mjs resume`); throw new Error('drawdown breaker tripped'); }
    // sync with what Robinhood really holds
    const held = before.held, etfs = [...POOL, 'BIL'];
    state.positions = state.positions.filter((p) => held[p.symbol] > 0).map((p) => ({ ...p, qty: held[p.symbol] }));
    const g = await gather({ api, today, days });
    const parkHeld = Object.fromEntries(Object.entries(held).filter(([s]) => etfs.includes(s) && !state.positions.some((p) => p.symbol === s)));
    const plan = decide({ today, days, state, held, equity, prices: g.prices, closes: g.closes, scores: g.scores, park: g.park, parkHeld, fractional: true });
    const frac = await fractionalMap(client, [...new Set([...plan.buys.map((b) => b.symbol), ...plan.parkTrades.map((t) => t.symbol)])]);
    let orders = planToOrders(plan, g.prices, (s) => frac[s] !== false);
    // idempotency: never re-place an order Robinhood already has for today
    const todays = before.orders.filter((o) => o.created_at && ny(new Date(o.created_at)).date === today && !/cancel|reject|fail/.test(o.state));
    const dupes = orders.filter((o) => todays.some((t) => t.symbol === o.symbol && t.side === o.side));
    if (dupes.length) { log.skipped_already_placed = dupes.map((o) => o.symbol + ' ' + o.side); orders = orders.filter((o) => !dupes.includes(o)); }
    const allowed = new Set([...g.members, ...etfs, ...Object.keys(held)]);
    const maxOrderUsd = +(E.MAX_ORDER_USD || Math.max(5, equity * 0.2));
    const problems = checkLimits(orders, { equity, held, prices: g.prices, allowed, maxOrderUsd });
    Object.assign(log, { account_value: accountValue, equity_used: equity, buying_power: before.money.buying_power, park: g.park || 'CASH', signals: Object.keys(g.scores).length, skipped_heavy_volume: g.skipped_heavy_volume, plan: orders });
    if (problems.length) { writeFileSync(HALT, `Safety check failed on ${today}: ${problems.join('; ')}`); throw new Error('safety check failed: ' + problems.join('; ')); }
    const placed = [], failed = [];
    const place = async (o) => {
      if (!force && ny().min >= 15 * 60 + 58.75) { failed.push({ ...o, error: 'too close to the close, skipped' }); return; }
      o.refKey = `${E.RH_ACCOUNT}|${today}|${o.symbol}|${o.side}`;
      const b = buildOrderArgs(toolMap.place_equity_order, o, E.RH_ACCOUNT);
      if (!b.ok) { failed.push({ ...o, error: b.error }); return; }
      if (toolMap.review_equity_order) { try { o.review = await call(client, 'review_equity_order', buildOrderArgs(toolMap.review_equity_order, o, E.RH_ACCOUNT).args || b.args); } catch (e) { failed.push({ ...o, error: 'review: ' + e.message }); return; } }
      if (MODE !== 'live') { placed.push({ ...o, dry: true, args: b.args }); return; }
      try { const r = await call(client, 'place_equity_order', b.args); const id = r?.id ?? r?.order_id ?? r?.order?.id; placed.push({ ...o, id, state: r?.state ?? r?.status ?? r?.order?.state }); }
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
    for (const p of placed.filter((x) => x.side === 'buy' && !etfs.includes(x.symbol))) state.positions.push({ symbol: p.symbol, entry_date: today, qty: p.shares ?? +(p.dollars / g.prices[p.symbol]).toFixed(6), dollars: p.dollars, why: p.why });
    if (MODE === 'live') state.positions = state.positions.filter((p) => !placed.some((x) => x.side === 'sell' && x.symbol === p.symbol));
    Object.assign(log, { placed, failed, prices_at_order: Object.fromEntries(placed.map((p) => [p.symbol, g.prices[p.symbol]])) });
    const lines = placed.map((p) => `${p.side.toUpperCase()} ${p.symbol} ${p.dollars != null ? '$' + p.dollars.toFixed(2) : p.shares + ' sh'} (${p.why})`);
    await notify(`Dip bot ${MODE === 'live' ? '' : '(DRY RUN) '}${today}: ${placed.length} orders${failed.length ? `, ${failed.length} FAILED` : ''}`, [...lines, ...failed.map((f) => `FAILED ${f.side} ${f.symbol}: ${f.error}`)].join('\n') || 'No trades today.', { priority: failed.length ? 4 : 2, tags: failed.length ? 'warning' : 'chart_with_upwards_trend' });
  } catch (e) {
    log.error = String(e.message || e);
    const auth = e instanceof AuthRequired || /401|unauthor|authenticat|sign.?in again|re-?auth|expired token/i.test(log.error);
    await notify(auth ? 'Dip bot: Robinhood login expired, NO trades placed' : 'Dip bot: run failed', auth ? reloginHint() : log.error.slice(0, 600), { priority: 5, tags: 'rotating_light' });
    process.exitCode = 1;
  } finally {
    unlock();
    state.history = [...state.history, log].slice(-500); state.updated = log.run; saveState(state);
    console.log(JSON.stringify(log, null, 1).slice(0, 6000));
  }
}

// After the close: confirm fills from Robinhood's own order history, measure fill vs closing price, catch strangers.
async function cmdVerify() {
  const today = ny().date, state = loadState(), h = [...state.history].reverse().find((x) => x.today === today && x.placed);
  try {
    const { client } = await rh(); const r = await rhRead(client);
    state.positions = state.positions.filter((p) => r.held[p.symbol] > 0).map((p) => ({ ...p, qty: r.held[p.symbol] }));
    const todays = r.orders.filter((o) => o.created_at && ny(new Date(o.created_at)).date === today);
    const ours = new Set((h?.placed || []).map((p) => p.id).filter(Boolean));
    const strangers = MODE === 'live' ? todays.filter((o) => o.id && !ours.has(o.id) && !/cancel|reject|fail/.test(o.state)) : [];
    const unfilled = todays.filter((o) => ours.has(o.id) && !/fill/.test(o.state));
    // fill quality vs the official close (the backtest's "ideal" price)
    let closes = {};
    try { const syms = [...new Set(todays.map((o) => o.symbol))]; if (syms.length) { const js = await api(DATA, '/v2/stocks/bars?' + new URLSearchParams({ symbols: syms.join(','), timeframe: '1Day', start: today, end: today + 'T23:59:00Z', feed: 'sip' })); for (const [s, b] of Object.entries(js.bars || {})) closes[s] = b.at(-1)?.c; } } catch {}
    const fills = todays.filter((o) => o.avg_price).map((o) => ({ symbol: o.symbol, side: o.side, price: o.avg_price, close: closes[o.symbol] ?? null, vs_close_pct: closes[o.symbol] ? +(((o.avg_price / closes[o.symbol]) - 1) * (o.side === 'buy' ? 100 : -100)).toFixed(3) : null }));
    const v = { today, filled: fills.length, unfilled: unfilled.map((o) => `${o.side} ${o.symbol} (${o.state})`), strangers: strangers.map((o) => `${o.side} ${o.symbol} ${o.id}`), fills, avg_cost_vs_close_pct: fills.filter((f) => f.vs_close_pct != null).length ? +(fills.filter((f) => f.vs_close_pct != null).reduce((a, f) => a + f.vs_close_pct, 0) / fills.filter((f) => f.vs_close_pct != null).length).toFixed(3) : null, equity: r.money.equity };
    state.verify = [...(state.verify || []), v].slice(-500); saveState(state);
    if (strangers.length) { writeFileSync(HALT, `Orders today that the bot did not place: ${v.strangers.join(', ')}. Check Robinhood, then: node live-dip.mjs resume`); await notify('Dip bot HALTED: unknown orders in the account', v.strangers.join('\n'), { priority: 5, tags: 'rotating_light' }); }
    else if (unfilled.length) await notify('Dip bot: some orders did not fill', v.unfilled.join('\n'), { priority: 4, tags: 'warning' });
    else if (h?.placed?.length) await notify(`Dip bot ${today}: all ${fills.length} filled`, `Account $${(r.money.equity || 0).toFixed(2)}. Avg cost vs close: ${v.avg_cost_vs_close_pct ?? 'n/a'}% (negative = better than close)`, { priority: 2, tags: 'white_check_mark' });
    console.log(JSON.stringify(v, null, 1));
  } catch (e) { await notify('Dip bot: verify failed', String(e.message).slice(0, 500), { priority: 4, tags: 'warning' }); process.exitCode = 1; }
}

function cmdStatus() {
  const s = loadState();
  console.log(JSON.stringify({ mode: MODE, halted: existsSync(HALT) ? readFileSync(HALT, 'utf8') : false, token_hours_left: Math.round((tokenSecondsLeft() || 0) / 3600), positions: s.positions, peak_equity: s.peak_equity, last_runs: s.history.slice(-3).map((h) => ({ today: h.today, mode: h.mode, placed: h.placed?.length, failed: h.failed?.length, error: h.error })), last_verify: s.verify?.at(-1) }, null, 1));
}

const cmd = process.argv[2];
if (import.meta.url === `file://${process.argv[1]}`) {
  const run = { login: async () => { await login(); console.log('Next: node live-dip.mjs doctor'); }, doctor: cmdDoctor, health: cmdHealth, trade: () => cmdTrade(), verify: cmdVerify, status: cmdStatus,
    halt: () => { writeFileSync(HALT, 'Stopped by hand ' + new Date().toISOString()); console.log('halted'); }, resume: () => { try { unlinkSync(HALT); } catch {} console.log('resumed'); } }[cmd];
  if (!run) { console.log('usage: node live-dip.mjs login|doctor|health|trade|verify|status|halt|resume'); process.exit(2); }
  Promise.resolve(run()).catch(async (e) => { console.error(e); await notify('Dip bot: ' + cmd + ' crashed', String(e?.message || e).slice(0, 500), { priority: 4 }); process.exit(1); });
}
