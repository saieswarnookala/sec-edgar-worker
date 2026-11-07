import assert from 'node:assert/strict';
import { parseNseTime, reactionIndex, simulate, stats } from './india-drift.mjs';
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
console.log('india drift tests passed');
