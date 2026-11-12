// Tests for the live Robinhood runner. Uses a local fake Robinhood MCP server; never touches a real account.
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, writeFileSync, readFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createServer } from 'node:http';
import { buildOrderArgs, planToOrders, checkLimits, fitBuys, readPositions, readOrders, readMoney } from './orders.mjs';

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
  process.env.SENTINEL_HOME = mkdtempSync(join(tmpdir(), 'live-'));
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
  for (const m of ['dry', 'live', 'auth', 'claude', 'claudebad']) { const r = spawnSync(process.execPath, [new URL(import.meta.url).pathname, m], { encoding: 'utf8' }); process.stdout.write(r.stdout); if (r.status !== 0) { console.error(r.stderr); process.exit(1); } }
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
  Object.assign(process.env, { SENTINEL_HOME: home, RH_MCP_URL: 'http://localhost:9/mcp', LIVE_MODE: 'live', NTFY_TOPIC: '' });
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
  const placed = [];
  const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York' }).format(new Date());
  const mk = () => {
    const s = new McpServer({ name: 'fake-rh', version: '1' });
    const j = (o) => ({ content: [{ type: 'text', text: JSON.stringify(o) }] });
    s.tool('get_accounts', {}, async () => j({ accounts: [{ account_number: '5RH000111', agentic_allowed: true }] }));
    s.tool('get_portfolio', { account_number: z.string() }, async () => j({ total_value: '1000.00', buying_power: placed.some((p) => p.side === 'sell') ? '230.00' : '20.00' }));
    s.tool('get_equity_positions', { account_number: z.string() }, async () => j({ positions: [{ symbol: 'AAA', quantity: '0.25' }, { symbol: 'SPY', quantity: '1.4' }] }));
    s.tool('get_equity_orders', { account_number: z.string() }, async () => j({ orders: [] }));
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
  writeFileSync(join(home, 'dip-state.json'), JSON.stringify({ positions: [{ symbol: 'AAA', entry_date: '2026-10-01', qty: 0.25 }], history: [] }));
  Object.assign(process.env, { SENTINEL_HOME: home, RH_MCP_URL: `http://localhost:${srv.address().port}/mcp`, LIVE_MODE: mode, RH_ACCOUNT: '5RH000111', NTFY_TOPIC: '' });
  const { cmdTrade } = await import('./live-dip.mjs');
  const days = ['2026-10-01', '2026-10-02', '2026-10-05', '2026-10-06', '2026-10-07', '2026-10-08', today];
  const gather = async () => ({ members: ['AAA', 'CCC', 'NOFR'], etfs: ['SPY', 'QQQ', 'BIL'], prices: { AAA: 40, CCC: 250, NOFR: 20, SPY: 600, QQQ: 500 }, closes: { AAA: [40, 40, 40, 40, 40] }, scores: { CCC: -0.15, NOFR: -0.12 }, park: 'SPY', volInfo: {} });
  await cmdTrade({ force: true, gather, getDays: async () => days });
  srv.close();
  const st = JSON.parse(readFileSync(join(home, 'dip-state.json'), 'utf8')), h = st.history.at(-1);
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
