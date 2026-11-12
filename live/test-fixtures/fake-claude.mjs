#!/usr/bin/env node
// Fake `claude -p` for tests: pretends to call the Robinhood MCP tool named in the prompt and prints stream-json events.
// FAKE_CLAUDE_STATE = json file with { placed: [] }; FAKE_CLAUDE_MISBEHAVE=1 changes the order amount (must be caught).
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
const prompt = process.argv[process.argv.indexOf('-p') + 1];
const allowed = process.argv.includes('--allowedTools') ? process.argv[process.argv.indexOf('--allowedTools') + 1] : '';
const f = process.env.FAKE_CLAUDE_STATE, st = existsSync(f) ? JSON.parse(readFileSync(f, 'utf8')) : { placed: [] };
const m = prompt.match(/Call the tool (mcp__robinhood__(\w+)) exactly once with exactly these arguments, unchanged:\n(.*)\n/);
const out = (o) => process.stdout.write(JSON.stringify(o) + '\n');
out({ type: 'system', subtype: 'init', tools: [allowed] });
if (!m) { out({ type: 'result', result: '[]' }); process.exit(0); }
const [, full, name, json] = m; let input = JSON.parse(json);
if (process.env.FAKE_CLAUDE_MISBEHAVE === '1' && name === 'place_equity_order' && input.dollar_amount) input = { ...input, dollar_amount: String(+input.dollar_amount * 10) };
let data;
if (name === 'get_portfolio') data = { total_value: '1000.00', buying_power: st.placed.some((p) => p.side === 'sell') ? '230.00' : '20.00' };
else if (name === 'get_equity_positions') data = { positions: [{ symbol: 'AAA', quantity: '0.25' }, { symbol: 'SPY', quantity: '1.4' }] };
else if (name === 'get_equity_orders') data = { orders: [] };
else if (name === 'get_accounts') data = { accounts: [{ account_number: '5RH000111', agentic_allowed: true }] };
else if (name === 'get_equity_tradability') data = { symbol: input.symbol, fractional_tradability: input.symbol === 'NOFR' ? 'untradable' : 'tradable' };
else if (name === 'review_equity_order') data = { ok: true };
else if (name === 'place_equity_order') { st.placed.push(input); data = { id: 'ord' + st.placed.length, state: 'queued' }; }
writeFileSync(f, JSON.stringify(st));
out({ type: 'assistant', message: { content: [{ type: 'tool_use', id: 'tu1', name: full, input }] } });
out({ type: 'user', message: { content: [{ type: 'tool_result', tool_use_id: 'tu1', content: [{ type: 'text', text: JSON.stringify(data) }] }] } });
out({ type: 'assistant', message: { content: [{ type: 'text', text: 'DONE' }] } });
out({ type: 'result', subtype: 'success', result: 'DONE', is_error: false });
