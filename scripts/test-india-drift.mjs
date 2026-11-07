import assert from 'node:assert/strict';
import { parseNseTime, reactionIndex, simulate, stats, cleanSeries, dedupeEvents, liquidityUniverse } from './india-drift.mjs';
assert.deepEqual(parseNseTime('16-Jan-2025 20:20:21'), { date: '2025-01-16', mins: 1220 });
const days = ['2025-01-15', '2025-01-16', '2025-01-17', '2025-01-20'];
assert.equal(reactionIndex(days, { date: '2025-01-16', mins: 1220 }), 2); // after close -> next session
assert.equal(reactionIndex(days, { date: '2025-01-16', mins: 600 }), 1);  // during session -> same day
assert.equal(reactionIndex(days, { date: '2025-01-18', mins: 600 }), 3);  // weekend -> Monday
// simulate: one stock doubles after entry; 1 slot, hold 2
const D = ['d0', 'd1', 'd2', 'd3', 'd4', 'd5'];
const px = { A: { d0: { o: 10, c: 10 }, d1: { o: 10, c: 11 }, d2: { o: 10, c: 15 }, d3: { o: 18, c: 20 }, d4: { o: 20, c: 20 }, d5: { o: 20, c: 20 } } };
const { eq, trades } = simulate(D, px, [{ sym: 'A', ri: 1, react: 0.1 }], { thr: 5, hold: 2, slots: 1 });
assert.equal(trades.length, 1); assert.ok(Math.abs(trades[0] - (2 - 1 - 0.003)) < 1e-9);
assert.ok(eq[5] > 1.99 && eq[5] < 2);
assert.equal(simulate(D, px, [{ sym: 'A', ri: 1, react: 0.03 }], { thr: 5, hold: 2, slots: 1 }).trades.length, 0); // below threshold
const s = stats(['2020-01-01', '2021-01-01'], [1, 1.1]); assert.ok(Math.abs(s.cagr - 10) < 0.2);
// spike removal
const cs = cleanSeries({ a: { c: 100 }, b: { c: 10 }, c: { c: 101 }, d: { c: 102 } }); assert.ok(!cs.b && cs.c);
const keep = cleanSeries({ a: { c: 100 }, b: { c: 140 }, c: { c: 141 } }); assert.ok(keep.b); // real jump that holds
// dedupe: results feed + announcement of same quarter -> one
const dd = dedupeEvents([{ date: '2025-04-20', mins: 1000 }, { date: '2025-04-20', mins: 990 }, { date: '2025-07-20', mins: 900 }]);
assert.equal(dd.length, 2); assert.equal(dd[0].mins, 990);
// liquidity universe: picks highest traded value
const LD = Array.from({ length: 200 }, (_, i) => `2020-${String(1 + Math.floor(i / 28)).padStart(2, '0')}-${String(1 + (i % 28)).padStart(2, '0')}`);
const LP = { BIG: {}, SMALL: {} }; for (const d of LD) { LP.BIG[d] = { tv: 1e9 }; LP.SMALL[d] = { tv: 1e3 }; }
const um = liquidityUniverse(LD, LP, ['BIG', 'SMALL'], 1); assert.ok(um.get(199).has('BIG') && !um.get(199).has('SMALL'));
console.log('india drift tests passed');
