import assert from 'node:assert/strict';
import { reactionIndex, simulate, parse8k, COST, COMBOS } from './scripts/earnings-drift.mjs';
const dates = ['2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05', '2024-01-08'];
assert.equal(reactionIndex(dates, '2024-01-03', 480), 1);   // pre-market -> same day
assert.equal(reactionIndex(dates, '2024-01-03', 990), 2);   // after close -> next day
assert.equal(reactionIndex(dates, '2024-01-06', 600), 4);   // weekend -> Monday
assert.equal(reactionIndex(dates, '2024-01-08', 990), -1);  // beyond data
const O = { A: [10, 10, 10, 11, 12] }, C = { A: [10, 10, 11, 12, 12] };
const sig = []; sig[2] = [{ s: 'A', r: 0.06, strong: true }];
const c = { th: 0.05, h: 2, n: 1, cl: 'any' };
const r = simulate(dates, O, C, sig, c, 0);
assert.equal(r.trades, 1); assert.ok(Math.abs(r.curve.at(-1)[1] - 1.2 * (1 - COST) ** 2) < 1e-12);
assert.equal(simulate(dates, O, C, sig, { ...c, th: 0.08 }, 0).trades, 0);
sig[2][0].strong = false; assert.equal(simulate(dates, O, C, sig, { ...c, cl: 'strong' }, 0).trades, 0);
const r2 = simulate(dates, O, C, sig, { ...c, n: 2 }, 0); assert.ok(Math.abs(r2.curve.at(-1)[1] - (0.5 + 0.5 * 1.2 * (1 - COST) ** 2)) < 1e-12);
const ev = parse8k([{ form: ['8-K', '8-K', '10-Q', '8-K'], items: ['2.02,9.01', '5.02', '', '2.02'], filingDate: ['2024-01-25', '2024-02-01', '2024-01-30', '2015-05-01'], acceptanceDateTime: ['2024-01-25T16:05:12.000Z', '', '', '2015-05-01T08:00:00.000Z'] }]);
assert.deepEqual(ev, [{ day: '2024-01-25', min: 965 }]);
assert.equal(COMBOS.length, 64);
console.log('earnings drift tests passed');
