import assert from 'node:assert/strict';
import { simTrade, tradeRet, orOf, dayResults, stats, runChunk, merge, makeApi, COMBOS, et } from './scripts/orb-research.mjs';
import { rmSync } from 'node:fs';
const B = (o, h, l, c, m = 0) => ({ o, h, l, c, m });
// long: fill at level, hold to close
assert.deepEqual(simTrade(1, 101, [B(100.8, 101.5, 100.7, 101.2), B(101.2, 104, 101, 104)], 0.5, 'close'), { fill: 101, exit: 104 });
// stop in entry bar -> stopped
assert.deepEqual(simTrade(1, 101, [B(100.8, 101.5, 100, 100.2)], 0.5, 'close'), { fill: 101, exit: 100.5 });
// gap through stop -> exit at open
assert.equal(simTrade(1, 101, [B(100.8, 101.2, 100.9, 101.1), B(99, 99.5, 98, 99)], 0.5, 'close').exit, 99);
// 2R target hit
assert.equal(simTrade(1, 101, [B(100.8, 101.2, 100.9, 101.1), B(101.1, 102.5, 101, 102.4)], 0.5, '2R').exit, 102);
// stop before target in same bar (conservative)
assert.equal(simTrade(1, 101, [B(100.8, 101.2, 100.9, 101.1), B(101.1, 102.5, 100.4, 102)], 0.5, '2R').exit, 100.5);
// trailing: rises to 103 then falls -> exit 102.5
assert.equal(simTrade(1, 101, [B(100.8, 101.2, 100.9, 101.1), B(101.1, 103, 101, 102.9), B(102.9, 102.9, 102, 102.1)], 0.5, 'trail1R').exit, 102.5);
// short side
assert.deepEqual(simTrade(-1, 99, [B(99.2, 99.3, 98.5, 98.6), B(98.6, 98.7, 97, 97)], 0.5, 'close'), { fill: 99, exit: 97 });
// no breakout
assert.equal(simTrade(1, 101, [B(100.8, 100.9, 100, 100.5)], 0.5, 'close'), null);
// sizing + costs
assert.ok(Math.abs(tradeRet(1, 100, 101, 0.5, 20) - Math.min(0.02, 0.002) * (1 - 0.027)) < 1e-12);
// opening range
assert.deepEqual(orOf([B(100, 101, 99, 100.5), B(100.5, 102, 100, 101)], 2), { dir: 1, hi: 102, lo: 99 });
assert.equal(orOf([B(100, 101, 99, 100)], 1), null);
assert.equal(COMBOS.length, 3 * 4 * 2 * 2 * 3 * 2 * 2);
// stats
const s = stats([['2024-01-02', 0.1], ['2024-12-31', -0.5]]); assert.equal(s.max_dd, 50);
assert.deepEqual(et('2025-07-01T13:30:00Z'), { d: '2025-07-01', m: 570 });
// end-to-end with fake Alpaca
let seed = 7; const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
const fake = async (url) => {
  const u = new URL(url);
  if (u.pathname.endsWith('/assets')) return { ok: true, json: async () => ['AAA', 'BBB', 'CCC', 'DDD'].map((s) => ({ symbol: s, exchange: 'NASDAQ', tradable: true, name: s + ' Inc' })).concat([{ symbol: 'QQQ', exchange: 'NASDAQ', tradable: true, name: 'Invesco QQQ Trust' }]) };
  const p = u.searchParams, tf = p.get('timeframe'), s0 = Date.parse(p.get('start')), e0 = Date.parse(p.get('end')), bars = {};
  for (const sym of p.get('symbols').split(',')) { const a = []; let px = 50 + sym.charCodeAt(0) % 7;
    if (tf === '1Day') { for (let t = s0; t <= e0; t += 86400e3) { const d = new Date(t); if (d.getUTCDay() % 6 === 0) continue; const ms = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), 4); const c = px * (1 + (rnd() - 0.5) * 0.04); a.push({ t: new Date(ms).toISOString(), o: px, h: Math.max(px, c) * 1.01, l: Math.min(px, c) * 0.99, c, v: 3e6 }); px = c; } }
    else { const st = tf === '5Min' ? 300e3 : 60e3; for (let t = s0; t <= e0; t += st) { const c = px * (1 + (rnd() - 0.49) * 0.006); a.push({ t: new Date(t).toISOString(), o: px, h: Math.max(px, c) * 1.001, l: Math.min(px, c) * 0.999, c, v: 1e5 * (0.3 + 2 * rnd()) }); px = c; } }
    bars[sym] = a; }
  return { ok: true, json: async () => ({ bars, next_page_token: null }) };
};
process.env.ORB_PAUSE = '0';
const api = makeApi({ APCA_API_KEY_ID: 'x', APCA_API_SECRET_KEY: 'y', ORB_PAUSE: '0' }, fake);
rmSync('/tmp/orbt', { recursive: true, force: true });
const now = Date.parse('2025-03-15T00:00:00Z');
await runChunk('wide', 2024, '/tmp/orbt', { api, now, log: () => {} });
await runChunk('wide', 2025, '/tmp/orbt', { api, now, log: () => {} });
const out = merge('/tmp/orbt', '/tmp/orbt', () => {});
const w = out.universes.wide; assert.ok(w.top10.length === 10 && w.all.length === COMBOS.length, 'rows');
assert.ok(w.top10[0].is.trades > 0 && w.top10[0].oos.trades >= 0, 'trades');
console.log('ORB research tests passed; fake top combo:', w.top10[0].key, JSON.stringify(w.top10[0].is), 'reqs', api.reqs);
