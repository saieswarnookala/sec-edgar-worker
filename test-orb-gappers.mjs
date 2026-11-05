import assert from 'node:assert/strict';
import { sim, ret, dayResults, pickLists, runChunk, merge, COMBOS, REF, COMM } from './scripts/orb-gappers.mjs';
import { makeApi } from './scripts/orb-research.mjs';
import { rmSync } from 'node:fs';
const B = (o, h, l, c, m = 600) => ({ o, h, l, c, m });
assert.deepEqual(sim(101, [B(100.8, 101.5, 100.7, 101.2), B(101.2, 104, 101, 104)], 0.5, 0), { fill: 101, exit: 104 });
assert.deepEqual(sim(101, [B(100.8, 101.5, 100, 100.2)], 0.5, 2), { fill: 101, exit: 100.5 });
assert.equal(sim(101, [B(100.8, 101.2, 100.9, 101.1), B(101.1, 102.6, 101, 102.4)], 0.5, 3).exit, 102.5);
assert.equal(sim(101, [B(100.8, 101.2, 100.9, 101.1), B(101.1, 102.4, 101, 102.3), B(102.3, 102.3, 102, 102.1)], 0.5, 3).exit, 102.1);
assert.equal(sim(101, [B(100.8, 101.2, 100.9, 101.1), B(101.1, 102.6, 101, 102.4)], 0.5, 1.5).exit, 101.75);
assert.equal(sim(101, [B(100.8, 101.2, 100.9, 101.1), B(99, 99.5, 98, 99)], 0.5, 2).exit, 99);
assert.equal(sim(101, [B(100.8, 100.9, 100, 100.5)], 0.5, 2), null);
assert.ok(Math.abs(ret(100, 101, 0.5, 5, 0.05) - Math.min(0.02, 0.008) * (1 - 2 * (COMM + 0.05))) < 1e-12);
assert.equal(COMBOS.length, 3 * 4 * 3 * 4 * 4 * 2 * 2); assert.ok(COMBOS.some((c) => c.key === REF));
// day: one gap-up long winner, one gap-down short-OR (skipped: long only), one 2% gapper excluded at gap3
const ob = (o, c) => [B(o, Math.max(o, c) + 0.1, Math.min(o, c) - 0.1, c, 570)];
const picks = [
  { s: 'UP', rv: 5, gap: 0.04, atr: 1, ob: ob(50, 51), m: [B(51, 51.2, 50.9, 51.1, 575), B(51.1, 53.5, 51, 53.4, 600), B(53.4, 53.5, 53, 53.2, 959)] },
  { s: 'DN', rv: 4, gap: -0.05, atr: 1, ob: ob(50, 49), m: [B(49, 49.1, 47, 47, 575)] },
  { s: 'SM', rv: 3, gap: 0.025, atr: 1, ob: ob(50, 51), m: [B(51, 51.2, 50, 50.1, 575)] },
];
const d = dayResults(picks);
assert.equal(d[REF][1], 1); assert.ok(d[REF][0] > 0);           // only UP traded, wins at 2R
assert.equal(d['or5|s1|t5|tgt2|gap2|abs|slip0.01'][1], 2);     // SM included at 2%, stopped
assert.ok(d['or5|s1|t5|tgt2|gap2|abs|slip0.01'][0] < d[REF][0]);
assert.equal(pickLists(picks).length, 3);
// end to end with fake Alpaca
let seed = 11; const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
const fake = async (url) => { const u = new URL(url);
  if (u.pathname.endsWith('/assets')) return { ok: true, json: async () => ['AAA', 'BBB', 'CCC', 'DDD', 'EEE'].map((s) => ({ symbol: s, exchange: 'NYSE', tradable: true, name: s + ' Corp' })) };
  const p = u.searchParams, tf = p.get('timeframe'), s0 = Date.parse(p.get('start')), e0 = Date.parse(p.get('end')), bars = {};
  for (const sym of p.get('symbols').split(',')) { const a = []; let px = 40 + 20 * rnd();
    if (tf === '1Day') { for (let t = s0; t <= e0; t += 86400e3) { const dd = new Date(t); if (dd.getUTCDay() % 6 === 0) continue; const ms = Date.UTC(dd.getUTCFullYear(), dd.getUTCMonth(), dd.getUTCDate(), 4); const c = px * (1 + (rnd() - 0.5) * 0.04); a.push({ t: new Date(ms).toISOString(), o: px, h: Math.max(px, c) * 1.01, l: Math.min(px, c) * 0.99, c, v: 3e6 }); px = c; } }
    else { const st = tf === '5Min' ? 300e3 : 60e3; for (let t = s0; t <= e0; t += st) { const c = px * (1 + (rnd() - 0.48) * 0.008); a.push({ t: new Date(t).toISOString(), o: px, h: Math.max(px, c) * 1.002, l: Math.min(px, c) * 0.998, c, v: 1e5 * (0.3 + 2 * rnd()) }); px = c; } }
    bars[sym] = a; }
  return { ok: true, json: async () => ({ bars, next_page_token: null }) }; };
const api = makeApi({ APCA_API_KEY_ID: 'x', APCA_API_SECRET_KEY: 'y', ORB_PAUSE: '0' }, fake);
rmSync('/tmp/gapt', { recursive: true, force: true });
const now = Date.parse('2021-03-01T00:00:00Z');
await runChunk(2020, '/tmp/gapt', { api, now, log: () => {} });
await runChunk(2021, '/tmp/gapt', { api, now, log: () => {} });
const out = merge('/tmp/gapt', '/tmp/gapt', () => {});
assert.ok(out.reference && out.reference.pre && out.reference.is, 'ref periods');
assert.ok(out.reference.pre.trades > 0, 'trades'); assert.equal(out.all.length, COMBOS.length);
assert.ok(out.sensitivity.p.length === 4 && out.robust_top15.length === 15);
console.log('ORB gappers tests passed; fake ref pre:', JSON.stringify(out.reference.pre), 'reqs', api.reqs);
