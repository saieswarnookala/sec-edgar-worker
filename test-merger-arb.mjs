import assert from 'node:assert/strict';
import { stats, retMap, corr, crash } from './scripts/merger-arb.mjs';
const pts = [['2020-01-02', 100], ['2020-06-01', 80], ['2020-12-31', 110], ['2021-12-31', 121]];
const s = stats(pts); assert.equal(s.max_dd, 20); assert.equal(s.yearly['2020'], 10); assert.equal(s.yearly['2021'], 10);
const a = retMap([['a', 1], ['b', 2], ['c', 1]]), c = corr(a, a); assert.equal(c.corr, 1); assert.equal(c.beta_to_spy, 1);
assert.deepEqual(crash(pts, '2020-01-01', '2020-07-01'), { ret: -20, max_drop: 20 });
console.log('merger arb tests passed');
