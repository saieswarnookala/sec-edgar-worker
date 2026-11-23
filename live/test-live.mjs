// Tests for the live Robinhood runner. Uses a local fake Robinhood MCP server; never touches a real account.
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, writeFileSync, readFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createServer } from 'node:http';
import { buildOrderArgs, planToOrders, checkLimits, fitBuys, readPositions, readOrders, readMoney, formatTradeAlert } from './orders.mjs';

const mode = process.argv[2];
if (!mode) {
  let n = 0; const ok = (name, f) => { f(); n++; console.log('ok  ', name); };
  const schema = { inputSchema: { type: 'object', properties: { account_number: { type: 'string' }, symbol: { type: 'string' }, side: { enum: ['BUY', 'SELL'] }, type: { enum: ['MARKET', 'LIMIT'] }, quantity: { type: 'number' }, dollar_amount: { type: 'number' } }, required: ['account_number', 'symbol', 'side', 'type'] } };
  ok('maps a dollar order onto the schema (enum case respected)', () => assert.deepEqual(buildOrderArgs(schema, { symbol: 'AAPL', side: 'buy', dollars: 99.999 }, 'A1').args, { account_number: 'A1', symbol: 'AAPL', side: 'BUY', type: 'MARKET', dollar_amount: 99.99 }));
  ok('maps a share sell', () => assert.equal(buildOrderArgs(schema, { symbol: 'AAPL', side: 'sell', shares: 0.1234567 }, 'A1').args.quantity, 0.123456));
  ok('fails closed when the schema has no dollar field', () => { const s2 = JSON.parse(JSON.stringify(schema)); delete s2.inputSchema.properties.dollar_amount; assert.equal(buildOrderArgs(s2, { symbol: 'X', side: 'buy', dollars: 5 }, 'A1').ok, false); });
  ok('fails closed on an unknown required field', () => { const s2 = JSON.parse(JSON.stringify(schema)); s2.inputSchema.properties.ref = { type: 'string' }; s2.inputSchema.required.push('ref'); assert.match(buildOrderArgs(s2, { symbol: 'X', side: 'buy', dollars: 5 }, 'A1').error, /ref/); });
  ok('sells come before buys', () => {
    const o = planToOrders({ sells: [{ symbol: 'A', qty: 1, reason: 'x' }], buys: [{ symbol: 'B', qty: 0.5, dip_pct: -12 }], parkTrades: [{ symbol: 'SPY', qty: 0.1, side: 'sell', reason: 'r' }, { symbol: 'QQQ', qty: 0.2, side: 'buy', reason: 'p' }] }, { B: 200, QQQ: 500 });
    assert.deepEqual(o.map((x) => x.side + x.symbol), ['sellSPY', 'sellA', 'buyB', 'buyQQQ']); assert.equal(o[2].dollars, 100);
  });
  ok('non-fractional stock falls back to whole shares', () => { const o = planToOrders({ sells: [], buys: [{ symbol: 'B', qty: 2.5, dip_pct: -12 }], parkTrades: [] }, { B: 40 }, () => false); assert.equal(o[0].shares, 2); });
  ok('limits: blocks oversized, unknown symbol, over-selling, duplicates', () => {
    const p = checkLimits([{ symbol: 'AAA', side: 'buy', dollars: 500 }, { symbol: 'ZZZ', side: 'buy', dollars: 10 }, { symbol: 'BBB', side: 'sell', shares: 2 }, { symbol: 'ZZZ', side: 'buy', dollars: 10 }], { equity: 1000, held: { BBB: 1 }, prices: { AAA: 10, BBB: 10, ZZZ: 1 }, allowed: new Set(['AAA', 'BBB']), maxOrderUsd: 200 });
    assert.ok(p.some((x) => /too big/.test(x)) && p.some((x) => /universe/.test(x)) && p.some((x) => /more BBB/.test(x)) && p.some((x) => /duplicate/.test(x)));
  });
  ok('limits: a parking buy may be most of the account, a dip buy may not', () => {
    const base = { equity: 1000, held: {}, prices: { IEF: 100, AAA: 10 }, allowed: new Set(['IEF', 'AAA']), maxOrderUsd: 200 };
    assert.deepEqual(checkLimits([{ symbol: 'IEF', side: 'buy', dollars: 700, why: 'parking' }], base), []);
    assert.ok(checkLimits([{ symbol: 'AAA', side: 'buy', dollars: 300, why: 'dip -12%' }], base).some((x) => /too big/.test(x)));
    assert.ok(checkLimits([{ symbol: 'IEF', side: 'buy', dollars: 1200, why: 'parking' }], base).some((x) => /too big|exceed/.test(x)));
  });
  ok('limits: clean plan passes', () => assert.deepEqual(checkLimits([{ symbol: 'AAA', side: 'buy', dollars: 100 }], { equity: 1000, held: {}, prices: { AAA: 10 }, allowed: new Set(['AAA']), maxOrderUsd: 200 }), []));
  ok('Robinhood format: string amounts, gfd, regular hours, stable ref_id', () => {
    const rs = { inputSchema: { type: 'object', properties: { account_number: { type: 'string' }, symbol: { type: 'string' }, side: { type: 'string' }, type: { type: 'string' }, quantity: { type: 'string' }, dollar_amount: { type: 'string' }, time_in_force: { type: 'string' }, market_hours: { type: 'string' }, ref_id: { type: 'string' } }, required: ['account_number', 'symbol', 'side', 'type'] } };
    const a = buildOrderArgs(rs, { symbol: 'SPY', side: 'buy', dollars: 99.996, refKey: 'k1' }, 'A1').args, b = buildOrderArgs(rs, { symbol: 'SPY', side: 'buy', dollars: 50, refKey: 'k1' }, 'A1').args;
    assert.equal(a.dollar_amount, '99.99'); assert.equal(a.time_in_force, 'gfd'); assert.equal(a.market_hours, 'regular_hours'); assert.equal(a.type, 'market');
    assert.match(a.ref_id, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/); assert.equal(a.ref_id, b.ref_id);
    assert.equal(buildOrderArgs(rs, { symbol: 'SPY', side: 'sell', shares: 0.1234567 }, 'A1').args.quantity, '0.123456');
  });
  ok('buys shrink to buying power', () => { const o = fitBuys([{ symbol: 'A', side: 'buy', dollars: 100 }, { symbol: 'B', side: 'buy', dollars: 100 }], 100, {}); assert.ok(o.every((x) => x.dollars <= 50)); });
  ok('reads positions/orders/money from nested replies', () => {
    assert.deepEqual(readPositions({ results: [{ symbol: 'aapl', quantity: '0.5' }, { instrument: { symbol: 'SPY' }, quantity: 2 }] }), { AAPL: 0.5, SPY: 2 });
    assert.equal(readOrders({ orders: [{ id: 'o1', symbol: 'A', side: 'BUY', state: 'filled', average_price: '10.5' }] })[0].avg_price, 10.5);
    assert.deepEqual(readMoney({ portfolio: { total_value: '1000.5', buying_power: { amount: '200' } } }), { equity: 1000.5, buying_power: 200 });
  });
  ok('alert: quiet day and a failed order read clearly', () => {
    const q = formatTradeAlert({ mode: 'live', today: 'D', time: '15:48', signals: [], keep: [{ symbol: 'K' }], orders: [], placed: [], failed: [], skipped: [], park: 'SPY', account: 1000, buyingPower: 5, slots: 10 });
    assert.match(q.title, /no trades today/); assert.match(q.body, /none today, so no new buys/); assert.match(q.body, /Dip stocks (held now|it would hold): 1 of/);
    const f = formatTradeAlert({ mode: 'live', today: 'D', time: '15:48', signals: [['X', -0.12], ['Y', -0.11]], keep: [], orders: [{ symbol: 'X', side: 'buy', dollars: 100, why: 'dip -12%' }], placed: [], failed: [{ symbol: 'X', side: 'buy', dollars: 100, error: 'too close to the close, skipped' }], skipped: [], park: null, account: 1000, buyingPower: 900, slots: 1 });
    assert.match(f.title, /1 order NOT placed/); assert.match(f.body, /NOT PLACED: too close/); assert.match(f.body, /Y -11.0% -> skip: all 1 slots used/);
    const z = formatTradeAlert({ mode: 'dry', today: '2026-11-17', time: '15:52', signals: [['MRNA', -0.15], ['GPN', -0.13]], spy5: -0.012, moves: { MRNA: -0.162, GPN: -0.142 }, keep: [], orders: [], placed: [], failed: [], skipped: [], park: null, account: 10, buyingPower: 10, slots: 10 });
    assert.match(z.body, /1\) STOCKS PICKED \(S&P 500, down 10%\+ in 5 days, still above 200-day trend\)/); assert.match(z.body, /MRNA -16.2% \(SPY -1.2%\) -> BUY|MRNA -16.2% \(SPY -1.2%\) -> skip/); assert.match(z.body, /Dip stocks it would hold: 0 of 10 slots/); assert.match(z.body, /none: nothing to sell, no dip could be bought \(see 1\), idle money already in cash/); assert.match(z.body, /Idle money: kept in cash \(SPY is below its 100-day average/); assert.match(z.body, /Account: \$10.00 total, \$10.00 free to buy with/);
    const z2 = formatTradeAlert({ mode: 'dry', today: '2026-11-17', time: '16:26', signals: [['MRNA', -0.15]], spy5: -0.022, moves: { MRNA: -0.175 }, planBuys: ['MRNA'], frac: { MRNA: false }, prices: { MRNA: 23.1 }, keep: [], orders: [], placed: [], failed: [], skipped: [], park: null, account: 10, buyingPower: 10, slots: 10 });
    assert.match(z2.body, /MRNA -17.5% \(SPY -2.2%\) -> skip: Robinhood says no fractional shares for MRNA, and the \$1.00 slot can't buy 1 whole share \(\$23.10\)/);
    assert.equal(f.priority, 4);
  });
  process.env.SENTINEL_HOME = mkdtempSync(join(tmpdir(), 'live-'));
  const { readFractional } = await import('./live-dip.mjs');
  ok('Robinhood fractional answer: yes / no / unclear', () => {
    assert.equal(readFractional({ fractional_tradability: 'tradable' }), true); assert.equal(readFractional({ is_fractional_tradable: false }), false);
    assert.equal(readFractional({ symbol: 'MRNA', tradable: true }), undefined); assert.equal(readFractional([{ fractional_tradability: 'untradable' }]), false);
    // Robinhood's real reply for MRNA on Nov 17 2026: regular-hours fractional OK, extended-hours not -> fractional
    const real = { data: { results: [{ symbol: 'MRNA', tradeable: true, fractional_tradability: 'tradable', extended_hours_fractional_tradability: false, all_day_tradability: 'tradable' }] }, guide: 'Fractional and dollar-based orders place only in regular_hours' };
    assert.equal(readFractional(real), true); assert.equal(readFractional(JSON.stringify(real)), true);
  });
  const { tradeWindow } = await import('./live-dip.mjs');
  const { parseConfig } = await import('./live-dip.mjs');
  ok('config: inline comments stripped, quotes kept, blanks empty', () => {
    const c = parseConfig('LIVE_MODE=live                 # dry = plan\nMAX_DRAWDOWN=0.35   # stop\nRH_ACCOUNT=   # number\nNTFY_TOPIC="a#b"\n# X=1\nBAD line');
    assert.deepEqual(c, { LIVE_MODE: 'live', MAX_DRAWDOWN: '0.35', RH_ACCOUNT: '', NTFY_TOPIC: 'a#b' });
  });
  ok('trade window follows the real close (normal and half days)', () => {
    assert.deepEqual(tradeWindow(960), { start: 947, end: 958, cutoff: 958.75 });   // 3:47-3:58, last order 3:58:45
    assert.deepEqual(tradeWindow(780), { start: 767, end: 778, cutoff: 778.75 });   // half day: 12:47-12:58
  });
  for (const m of ['dry', 'live', 'livev3', 'preview', 'v32intra', 'v32preview', 'auth', 'claude', 'claudebad']) { const r = spawnSync(process.execPath, [new URL(import.meta.url).pathname, m], { encoding: 'utf8' }); process.stdout.write(r.stdout); if (r.status !== 0) { console.error(r.stderr); process.exit(1); } }
  console.log(`${n} unit tests passed + dry and live runs against a fake Robinhood`);
} else if (mode === 'claude' || mode === 'claudebad') {
  // Claude Code fallback: every call goes through (fake) `claude -p`; we check each call it makes.
  const home = mkdtempSync(join(tmpdir(), 'live-'));
  const tools = JSON.parse(JSON.stringify([{ name: 'get_portfolio', inputSchema: { type: 'object', properties: { account_number: { type: 'string' } } } }, { name: 'get_equity_positions', inputSchema: { type: 'object', properties: { account_number: { type: 'string' } } } }, { name: 'get_equity_orders', inputSchema: { type: 'object', properties: { account_number: { type: 'string' } } } }, { name: 'get_equity_tradability', inputSchema: { type: 'object', properties: { symbol: { type: 'string' } } } }, { name: 'place_equity_order', inputSchema: { type: 'object', properties: { account_number: { type: 'string' }, symbol: { type: 'string' }, side: { enum: ['buy', 'sell'] }, type: { enum: ['market', 'limit'] }, quantity: { type: 'string' }, dollar_amount: { type: 'string' }, time_in_force: { type: 'string' }, market_hours: { type: 'string' }, ref_id: { type: 'string' } }, required: ['account_number', 'symbol', 'side', 'type'] } }]));
  writeFileSync(join(home, 'tools.json'), JSON.stringify(tools));
  writeFileSync(join(home, 'dip-state.json'), JSON.stringify({ positions: [{ symbol: 'AAA', entry_date: '2026-10-01', qty: 0.25 }], history: [] }));
  const fake = join(home, 'fake.json');
  Object.assign(process.env, { SENTINEL_HOME: home, EXECUTOR: 'claude', CLAUDE_BIN: new URL('./test-fixtures/fake-claude.mjs', import.meta.url).pathname, FAKE_CLAUDE_STATE: fake, FAKE_CLAUDE_MISBEHAVE: mode === 'claudebad' ? '1' : '0', LIVE_MODE: 'live', RH_ACCOUNT: '5RH000111', NTFY_TOPIC: '' });
  const { cmdTrade } = await import('./live-dip.mjs');
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York' }).format(new Date());
  const days = ['2026-10-01', '2026-10-02', '2026-10-05', '2026-10-06', '2026-10-07', '2026-10-08', today];
  const gather = async () => ({ members: ['AAA', 'CCC', 'NOFR'], etfs: ['SPY', 'QQQ', 'BIL'], prices: { AAA: 40, CCC: 250, NOFR: 20, SPY: 600, QQQ: 500 }, closes: { AAA: [40, 40, 40, 40, 40] }, scores: { CCC: -0.15, NOFR: -0.12 }, park: 'SPY', volInfo: {} });
  await cmdTrade({ force: true, gather, getDays: async () => days });
  const h = JSON.parse(readFileSync(join(home, 'dip-state.json'), 'utf8')).history.at(-1), placed = JSON.parse(readFileSync(fake, 'utf8')).placed;
  if (mode === 'claude') {
    assert.ok(!h.error, 'run error: ' + h.error); assert.equal(placed.length, 4); assert.equal(h.placed.length, 4);
    console.log('ok   Claude Code mode placed', placed.map((a) => `${a.side} ${a.symbol}`).join(', '), '(each call checked)');
  } else {
    assert.ok(existsSync(join(home, 'HALT')), 'changed order amount must halt the bot'); assert.match(h.error, /changed the arguments/);
    assert.ok(!placed.some((p, i) => i > 0 && p.side === 'buy' && placed.indexOf(p) > placed.findIndex((x) => +x.dollar_amount > 500)), 'no further orders after the bad one');
    console.log('ok   Claude Code changing an order amount is caught: bot halted, no more orders');
  }
  process.exit(0);
} else if (mode === 'auth') {
  // expired / missing login: fail closed, place nothing, never open a browser
  const home = mkdtempSync(join(tmpdir(), 'live-'));
  writeFileSync(join(home, 'dip-state.json'), JSON.stringify({ positions: [], history: [] }));
  Object.assign(process.env, { SENTINEL_HOME: home, RH_MCP_URL: 'http://localhost:9/mcp', LIVE_MODE: 'live', RH_ACCOUNT: '5RH000111', NTFY_TOPIC: '' });
  const { cmdTrade } = await import('./live-dip.mjs');
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York' }).format(new Date());
  await cmdTrade({ force: true, gather: async () => { throw new Error('should not get here'); }, getDays: async () => [today] });
  const h = JSON.parse(readFileSync(join(home, 'dip-state.json'), 'utf8')).history.at(-1);
  assert.match(h.error, /Not signed in/); assert.ok(!h.placed);
  console.log('ok   missing/expired login: no trades, alert sent');
  process.exit(0);
} else {
  // ---- fake Robinhood MCP server ----
  const { McpServer } = await import('@modelcontextprotocol/sdk/server/mcp.js');
  const { StreamableHTTPServerTransport } = await import('@modelcontextprotocol/sdk/server/streamableHttp.js');
  const { z } = await import('zod');
  const placed = [], V32 = mode.startsWith('v32');
  // v3.2 fake account: holdings follow the orders placed (market orders fill at the test prices)
  const PX = { AAA: 40, BBB: 11, CCC: 250, NOFR: 20, SPY: 600, EWZ: 30 };
  const v32Held = () => {
    const q = { AAA: 0.25, SPY: 1.4, BBB: 5 }, avg = { AAA: 30, SPY: 550, BBB: 10 };
    for (const a of placed) q[a.symbol] = (q[a.symbol] || 0) + (a.side === 'buy' ? 1 : -1) * (a.quantity ? +a.quantity : +a.dollar_amount / PX[a.symbol]);
    return Object.entries(q).filter(([, v]) => v > 1e-9).map(([symbol, v]) => ({ symbol, quantity: String(+v.toFixed(6)), average_buy_price: String(avg[symbol] ?? PX[symbol]) }));
  };
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York' }).format(new Date());
  const mk = () => {
    const s = new McpServer({ name: 'fake-rh', version: '1' });
    const j = (o) => ({ content: [{ type: 'text', text: JSON.stringify(o) }] });
    s.tool('get_accounts', {}, async () => j({ accounts: [{ account_number: '5RH000111', agentic_allowed: true }] }));
    s.tool('get_portfolio', { account_number: z.string() }, async () => j({ total_value: '1000.00', buying_power: placed.some((p) => p.side === 'sell') ? '230.00' : '20.00' }));
    s.tool('get_equity_positions', { account_number: z.string() }, async () => j({ positions: V32 ? v32Held() : [{ symbol: 'AAA', quantity: '0.25' }, { symbol: 'SPY', quantity: '1.4' }] }));
    s.tool('get_equity_orders', { account_number: z.string() }, async () => j({ orders: V32 ? placed.map((a, i) => ({ id: 'ord' + (i + 1), symbol: a.symbol, side: a.side, state: 'filled', created_at: new Date().toISOString() })) : [] }));
    s.tool('get_equity_tradability', { symbol: z.string() }, async ({ symbol }) => j({ symbol, tradable: true, fractional_tradability: symbol === 'NOFR' ? 'untradable' : 'tradable' }));
    const sch = { account_number: z.string(), symbol: z.string(), side: z.enum(['buy', 'sell']), type: z.enum(['market', 'limit']), quantity: z.string().optional(), dollar_amount: z.string().optional(), time_in_force: z.string().optional(), market_hours: z.string().optional(), ref_id: z.string().optional() };
    s.tool('review_equity_order', sch, async (a) => j({ ok: true, warnings: [] }));
    s.tool('place_equity_order', sch, async (a) => { placed.push(a); return j({ id: 'ord' + placed.length, state: 'queued' }); });
    return s;
  };
  const srv = createServer(async (req, res) => {
    let body = ''; for await (const c of req) body += c;
    const t = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined }); const s = mk(); await s.connect(t);
    await t.handleRequest(req, res, body ? JSON.parse(body) : undefined);
  }).listen(0);
  await new Promise((r) => srv.on('listening', r));
  const home = mkdtempSync(join(tmpdir(), 'live-'));
  writeFileSync(join(home, 'rh-auth.json'), JSON.stringify({ tokens: { access_token: 'x', token_type: 'Bearer', expires_in: 86400 }, saved_at: Date.now() }));
  writeFileSync(join(home, 'dip-state.json'), JSON.stringify({ positions: [{ symbol: 'AAA', entry_date: '2026-10-01', qty: 0.25 }, ...(V32 ? [{ symbol: 'BBB', entry_date: today, qty: 5, dollars: 50, entry_px: 10, bought_intraday: true }] : [])], history: [] }));
  Object.assign(process.env, { SENTINEL_HOME: home, RH_MCP_URL: `http://localhost:${srv.address().port}/mcp`, LIVE_MODE: ['livev3', 'preview'].includes(mode) || V32 ? 'live' : mode, LIVE_STRATEGY: V32 ? 'v32' : ['livev3', 'preview'].includes(mode) ? 'v3' : '', RH_ACCOUNT: '5RH000111', NTFY_TOPIC: '' });
  const { cmdTrade, cmdIntraday, intradayPlan } = await import('./live-dip.mjs');
  const days = ['2026-10-01', '2026-10-02', '2026-10-05', '2026-10-06', '2026-10-07', '2026-10-08', today];
  const gather = ['livev3', 'preview'].includes(mode)
    // v3: SPY below its 100-day -> no Clear Leader target (park null); IEF above its 100-day -> park in IEF. SPY and EWZ have ETF dips, but SPY is held as parking.
    ? async () => ({ members: ['AAA', 'CCC', 'NOFR'], etfs: ['SPY', 'QQQ', 'BIL'], prices: { AAA: 40, CCC: 250, NOFR: 20, SPY: 600, QQQ: 500, EWZ: 30, IEF: 100 }, closes: { AAA: [40, 40, 40, 40, 40], IEF: Array(120).fill(90) }, scores: { CCC: -0.15, NOFR: -0.12 }, etfScores: { SPY: -0.06, EWZ: -0.07 }, park: null, volInfo: {} })
    : async () => ({ members: ['AAA', 'CCC', 'NOFR'], etfs: ['SPY', 'QQQ', 'BIL'], prices: { AAA: 40, CCC: 250, NOFR: 20, SPY: 600, QQQ: 500 }, closes: { AAA: [40, 40, 40, 40, 40] }, scores: { CCC: -0.15, NOFR: -0.12 }, park: 'SPY', volInfo: {} });
  if (V32) {
    // AAA: bought by v3.0 weeks ago (no entry_px; Robinhood avg $30, now $40 = +33%) -> target sell. BBB: bought today at $10, now $11 (+10%) -> must NOT sell (no same-day round trips).
    const g32 = async () => ({ members: ['AAA', 'BBB', 'CCC', 'NOFR'], etfs: ['SPY', 'QQQ', 'BIL'], prices: { ...PX }, closes: { AAA: [40, 40, 40, 40, 40], BBB: [10, 10, 10, 10, 10] }, scores: { CCC: -0.15, NOFR: -0.12 }, etfScores: { SPY: -0.06, EWZ: -0.07 }, park: 'SPY', volInfo: {} });
    const getDays = async () => days, path = join(home, 'dip-state.json');
    const pp = { today, days, equity: 1000, cash: 0, prices: { X: 105, Y: 106 }, park: 'SPY', parkHeld: {} };
    assert.equal(intradayPlan({ ...pp, positions: [{ symbol: 'X', entry_date: today, entry_px: 100 }], held: { X: 1 } }).sells.length, 0, 'never sells a same-day buy, even at +5%');
    assert.equal(intradayPlan({ ...pp, positions: [{ symbol: 'Y', entry_date: days.at(-2), entry_px: 100 }], held: { Y: 1 } }).sells.length, 1, 'sells at +5% from day 2');
    assert.equal(intradayPlan({ ...pp, positions: [{ symbol: 'X', entry_date: days.at(-2), entry_px: 101 }], held: { X: 1 } }).sells.length, 0, 'no sell below +5%');
    const full = intradayPlan({ ...pp, positions: Array.from({ length: 10 }, (_, i) => ({ symbol: 'S' + i, entry_date: today, entry_px: 1 })), held: Object.fromEntries(Array.from({ length: 10 }, (_, i) => ['S' + i, 1])), scores: { Z: -0.2 }, prices: { ...pp.prices, Z: 10 }, cash: 500 });
    assert.equal(full.buys.length, 0, 'no buys when all 10 slots are full');
    console.log('ok   v3.2 rules: no same-day sell, +5% sell from day 2, slots respected');
    if (mode === 'v32preview') {
      const before = readFileSync(path, 'utf8');
      await cmdIntraday({ gather: g32, getDays, preview: true }); srv.close();
      assert.equal(placed.length, 0, 'preview-intraday must not place orders'); assert.equal(readFileSync(path, 'utf8'), before, 'preview-intraday must not change the saved state');
      assert.ok(!existsSync(join(home, 'HALT'))); console.log('ok   preview-intraday (config LIVE_MODE=live): 0 orders placed, state unchanged'); process.exit(0);
    }
    await cmdIntraday({ gather: g32, getDays, nowMin: 700 });
    let st = JSON.parse(readFileSync(path, 'utf8')), r1 = st.intraday.at(-1);
    assert.ok(!r1.error, 'intraday error: ' + r1.error); assert.ok(!existsSync(join(home, 'HALT')), 'intraday must not halt');
    const sd = r1.placed.map((p) => p.side + ' ' + p.symbol);
    assert.ok(sd.includes('sell AAA'), 'inherited v3.0 position sold at +5% using Robinhood avg price: ' + sd);
    assert.ok(!sd.includes('sell BBB'), 'same-day buy BBB not sold: ' + sd);
    assert.ok(sd.includes('buy CCC') && sd.includes('buy NOFR') && sd.includes('buy EWZ'), 'stock + ETF dips bought: ' + sd);
    assert.ok(sd.includes('sell SPY') && !sd.includes('buy SPY'), 'buys funded by selling part of parked SPY: ' + sd);
    assert.ok(sd.lastIndexOf('sell SPY') < sd.findIndex((x) => x.startsWith('buy')), 'sells before buys');
    const spySold = +placed.find((a) => a.symbol === 'SPY').quantity; assert.ok(spySold > 0.3 && spySold < 0.6, 'sells only what the buys need (~0.45 SPY): ' + spySold);
    for (const s of ['CCC', 'NOFR', 'EWZ']) { const p = st.positions.find((x) => x.symbol === s); assert.ok(p && p.entry_date === today && p.entry_px === PX[s], s + ' recorded with entry price'); }
    assert.equal(st.positions.find((x) => x.symbol === 'EWZ').kind, 'etf'); assert.ok(!st.positions.some((x) => x.symbol === 'AAA'), 'AAA removed after its sell');
    const n1 = placed.length;
    await cmdIntraday({ gather: g32, getDays, nowMin: 715 });
    st = JSON.parse(readFileSync(path, 'utf8')); assert.ok(!st.intraday.at(-1).error, 'check 2 error: ' + st.intraday.at(-1).error);
    assert.equal(placed.length, n1, 'second check places nothing: ' + JSON.stringify(placed.slice(n1)));
    await cmdIntraday({ gather: g32, getDays, nowMin: 585 }); await cmdIntraday({ gather: g32, getDays, nowMin: 945 }); assert.equal(placed.length, n1, 'nothing outside 10:00 to close-20');
    await cmdTrade({ force: true, gather: g32, getDays });
    srv.close();
    st = JSON.parse(readFileSync(path, 'utf8')); const h = st.history.at(-1);
    assert.ok(!h.error, 'final run error: ' + h.error); assert.ok(!existsSync(join(home, 'HALT')), 'final run must not halt');
    const fs = (h.placed || []).map((p) => p.side + ' ' + p.symbol);
    assert.ok(!fs.some((x) => /^sell (BBB|CCC|NOFR|EWZ)$/.test(x)), 'final run sells nothing bought today: ' + fs);
    assert.ok(!fs.some((x) => /^buy (CCC|NOFR|EWZ|BBB)$/.test(x)), 'final run does not re-buy held dips: ' + fs);
    assert.equal(h.strategy, 'v32');
    console.log('ok   v3.2 intraday live run:', sd.join(', '), '| 2nd check: 0 orders | final run:', fs.join(', ') || 'no orders');
    process.exit(0);
  }
  if (mode === 'preview') {   // config says LIVE_MODE=live, but preview must place nothing and save nothing
    const before = readFileSync(join(home, 'dip-state.json'), 'utf8');
    await cmdTrade({ gather, getDays: async () => days, preview: true }); srv.close();
    assert.equal(placed.length, 0, 'preview must not place orders'); assert.equal(readFileSync(join(home, 'dip-state.json'), 'utf8'), before, 'preview must not change the saved state');
    assert.ok(!existsSync(join(home, 'HALT'))); console.log('ok   preview (config LIVE_MODE=live): full v3 plan computed, 0 orders placed, state unchanged'); process.exit(0);
  }
  await cmdTrade({ force: true, gather, getDays: async () => days });
  srv.close();
  const st = JSON.parse(readFileSync(join(home, 'dip-state.json'), 'utf8')), h = st.history.at(-1);
  if (mode === 'livev3') {
    assert.ok(!h.error, 'run error: ' + h.error); assert.ok(!existsSync(join(home, 'HALT')), 'v3 must not halt (ETF dips and IEF are allowed symbols)');
    const sd = h.placed.map((p) => p.side + ' ' + p.symbol);
    assert.equal(h.strategy, 'v3'); assert.equal(h.park, 'IEF', 'bonds instead of cash when SPY is weak');
    assert.ok(sd.includes('sell SPY') && sd.includes('buy IEF'), 'parking switches SPY -> IEF: ' + sd);
    assert.ok(sd.includes('buy EWZ') && !sd.includes('buy SPY'), 'ETF dip EWZ bought; SPY (held as parking) is not an ETF dip: ' + sd);
    assert.ok(sd.includes('buy CCC'), 'stock dips still come first: ' + sd);
    const ewz = st.positions.find((p) => p.symbol === 'EWZ');
    assert.ok(ewz && ewz.kind === 'etf' && ewz.entry_date === today, 'ETF dip recorded as a position with kind etf (10-day max hold)');
    assert.ok(!st.positions.some((p) => p.symbol === 'IEF'), 'IEF parking is not a dip position');
    console.log('ok   v3 live run:', sd.join(', '), '| park IEF, EWZ tracked as an ETF dip');
    process.exit(0);
  }
  assert.ok(!h.error, 'run error: ' + h.error);
  assert.ok(!existsSync(join(home, 'HALT')), 'should not halt');
  const sides = h.placed.map((p) => p.side + ' ' + p.symbol);
  assert.ok(sides.includes('sell AAA') && sides.findIndex((x) => x.startsWith('buy')) > sides.lastIndexOf('sell AAA'), 'max-hold exit, sells before buys: ' + sides);
  assert.ok(sides.includes('buy CCC') && sides.includes('buy NOFR'), 'buys the dips: ' + sides);
  const ccc = h.placed.find((p) => p.symbol === 'CCC'), nofr = h.placed.find((p) => p.symbol === 'NOFR');
  assert.ok(ccc.dollars > 0 && ccc.dollars <= 100.01, 'CCC is a ~$100 fractional dollar order');
  assert.ok(nofr.shares >= 1 && Number.isInteger(nofr.shares), 'non-fractional stock uses whole shares');
  if (mode === 'dry') { assert.equal(placed.length, 0, 'dry run must not place orders'); console.log('ok   dry run plans', sides.join(', '), 'and places nothing'); }
  else { assert.equal(placed.length, h.placed.length); assert.equal(placed[0].side, 'sell'); assert.ok(st.positions.some((p) => p.symbol === 'CCC' && p.entry_date === today) && !st.positions.some((p) => p.symbol === 'AAA')); console.log('ok   live run placed', placed.length, 'orders on the fake broker:', placed.map((a) => `${a.side} ${a.symbol} ${a.dollar_amount ?? a.quantity}`).join(', ')); }
  process.exit(0);
}

// verify must not call the bot's own order a stranger when Robinhood's order id differs from the reply id (Nov 19 AMD halt)
{
  const { matchOurOrders, uuidsIn } = await import('./live-dip.mjs');
  const placed = [{ side: 'buy', symbol: 'AMD', id: 'aaaaaaaa-0000-0000-0000-000000000001', ids: ['aaaaaaaa-0000-0000-0000-000000000001'] }];
  const todays = [{ side: 'buy', symbol: 'AMD', id: '6aff604b-664a-46bc-9eb1-e239a3961011', state: 'filled' }, { side: 'buy', symbol: 'AMD', id: 'bbbbbbbb-0000-0000-0000-000000000002', state: 'filled' }, { side: 'sell', symbol: 'TSLA', id: 'cccccccc-0000-0000-0000-000000000003', state: 'filled' }];
  const mine = matchOurOrders(placed, todays);
  if (!mine.has(todays[0]) || mine.has(todays[1]) || mine.has(todays[2])) throw new Error('matchOurOrders wrong');
  const byId = matchOurOrders([{ side: 'buy', symbol: 'AMD', ids: ['bbbbbbbb-0000-0000-0000-000000000002'] }], todays);
  if (!byId.has(todays[1]) || byId.has(todays[0])) throw new Error('id match should win');
  if (uuidsIn({ a: { approval_id: 'X 6AFF604B-664A-46BC-9EB1-E239A3961011' } }).size !== 1) throw new Error('uuidsIn');
  console.log('ok   verify: own order matched even when Robinhood order id differs; extra same-stock order still a stranger');
}

{
  const { rhCloseOn } = await import('./live-dip.mjs');
  const a = { results: [{ symbol: 'AMD', historicals: [{ begins_at: '2026-11-18T05:00:00Z', close_price: '500.10' }, { begins_at: '2026-11-19T05:00:00Z', close_price: '479.30' }] }] };
  const b = { data: { bars: { AMD: [{ t: '2026-11-19T00:00:00Z', c: 479.3 }] } } };
  if (rhCloseOn(a, '2026-11-19') !== 479.3 || rhCloseOn(b, '2026-11-19') !== 479.3 || rhCloseOn(a, '2026-11-20') !== null) throw new Error('rhCloseOn');
  console.log('ok   Robinhood daily close read from historicals in any nesting');
}

{
  const { rhTodayClose } = await import('./live-dip.mjs');
  const r = { data: { results: [{ quote: { symbol: 'AMD', last_trade_price: '489.165000', venue_last_trade_time: '2026-11-19T20:59:59.94Z' }, close: { symbol: 'AMD', date: '2026-11-18', price: '530.14' } },
                                 { quote: { symbol: 'XYZ', last_trade_price: '10.5', venue_last_trade_time: '2026-11-19T20:59:00Z' }, close: { symbol: 'XYZ', date: '2026-11-19', price: '10.6' } }] } };
  const c = rhTodayClose(r, '2026-11-19');
  if (c.AMD !== 489.165 || c.XYZ !== 10.6) throw new Error('rhTodayClose ' + JSON.stringify(c));
  console.log('ok   Robinhood quote backup: official close when dated today, else last regular trade (never yesterday\'s close)');
}

{
  const { parseBars, parseQuotes, compareSignals, gatherSignalsRH } = await import('./rh-data.mjs');
  const bars = parseBars({ data: { results: [{ symbol: 'AMD', bars: [{ begins_at: '2026-11-18T00:00:00Z', close_price: '530.14', volume: 34028588 }, { begins_at: '2026-11-17T00:00:00Z', close_price: '503.41', volume: 36294745 }, { begins_at: '2026-11-16T00:00:00Z', close_price: '1', interpolated: true }] }] } });
  if (bars.AMD.length !== 2 || bars.AMD[0].d !== '2026-11-17' || bars.AMD[1].v !== 34028588) throw new Error('parseBars');
  const q = parseQuotes({ data: { results: [{ quote: { symbol: 'AMD', last_trade_price: '489.165', venue_last_trade_time: '2026-11-19T20:59:59Z', last_non_reg_trade_price: '479.1999', venue_last_non_reg_trade_time: '2026-11-19T21:51:16Z' } }] } });
  if (q.AMD !== 479.1999) throw new Error('parseQuotes should take the newer trade');
  // fake Robinhood: 300 flat days, AMD falls 15% vs SPY -> one dip in both sources -> same picks
  const days = Array.from({ length: 320 }, (_, i) => new Date(Date.UTC(2025, 8, 1) + i * 864e5).toISOString().slice(0, 10)).filter((d) => ![0, 6].includes(new Date(d).getUTCDay()));
  const today = '2026-11-19';
  const fake = { callTool: null };
  const call = async (_c, name, args) => {
    if (name === 'get_equity_quotes') return { data: { results: args.symbols.map((s) => ({ quote: { symbol: s, last_trade_price: s === 'AMD' ? '85' : '100', venue_last_trade_time: today + 'T20:46:00Z' } })) } };
    if (args.interval === 'month') return { data: { results: args.symbols.map((s) => ({ symbol: s, bars: Array.from({ length: 24 }, (_, i) => ({ begins_at: new Date(Date.UTC(2024, 10 + i, 1)).toISOString(), close_price: String(100 + i), volume: 1 })) })) } };
    if (args.interval === '30minute') return { data: { results: args.symbols.map((s) => ({ symbol: s, bars: [{ begins_at: today + 'T15:00:00Z', close_price: '85', volume: 1000 }] })) } };
    return { data: { results: args.symbols.map((s) => ({ symbol: s, bars: days.filter((d) => d < today).map((d, i, all) => ({ begins_at: d + 'T00:00:00Z', close_price: String(50 + 50 * i / (all.length - 1)), volume: 1000000 })) })) } };
  };
  const rg = await gatherSignalsRH({ client: fake, call, today, members: ['AMD', 'MSFT'], now: new Date(today + 'T20:46:00Z') });
  if (Object.keys(rg.scores).join() !== 'AMD' || rg.errors.length) throw new Error('gatherSignalsRH ' + JSON.stringify({ s: rg.scores, e: rg.errors }));
  const c = compareSignals({ ...rg, source: 'alpaca' }, rg);
  if (!c.same_picks || c.price_gap_pct.max !== 0) throw new Error('compareSignals same');
  const c2 = compareSignals({ ...rg, scores: { MSFT: -0.2 } }, rg);
  if (c2.same_picks || c2.stock_dips.only_alpaca[0] !== 'MSFT' || c2.stock_dips.only_robinhood[0] !== 'AMD') throw new Error('compareSignals diff');
  console.log('ok   Robinhood data path: bars/quotes parsed, same dips as the Alpaca path on the same data, differences reported');
}
