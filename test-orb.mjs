import assert from 'node:assert/strict';
import { tradeDay, et, stats } from './scripts/build-orb.mjs';
const B = (o, h, l, c) => ({ o, h, l, c });
// green opening bar, breakout, hold to close: long, fill 101, exit 104
let t = tradeDay([B(100, 101, 99.5, 100.8), B(100.8, 101.5, 100.7, 101.2), B(101.2, 104, 101, 104)], 5, 100000);
assert.equal(t.dir, 1); assert.equal(t.fill, 101); assert.equal(t.exit, 104);
assert.equal(t.shares, Math.floor(Math.min(1000 / 0.5, 100000 * 4 / 20 / 101)));
// stopped out after entry (stop = 101 - 0.5)
t = tradeDay([B(100, 101, 99.5, 100.8), B(100.8, 101.2, 100.9, 101.1), B(101.1, 101.1, 100, 100.2)], 5, 100000);
assert.equal(t.exit, 100.5); assert.ok(t.pnl < 0);
// gap through the stop -> exit at the open
t = tradeDay([B(100, 101, 99.5, 100.8), B(100.8, 101.2, 100.9, 101.1), B(99, 99.5, 98, 99)], 5, 100000);
assert.equal(t.exit, 99);
// red bar -> short at the low
t = tradeDay([B(100, 100.5, 99, 99.2), B(99.2, 99.3, 98.5, 98.6), B(98.6, 98.7, 97, 97)], 5, 100000);
assert.equal(t.dir, -1); assert.equal(t.fill, 99); assert.equal(t.exit, 97); assert.ok(t.pnl > 0);
// never breaks out -> no trade; doji -> no trade
assert.equal(tradeDay([B(100, 101, 99.5, 100.8), B(100.8, 100.9, 100, 100.5)], 5, 1e5), null);
assert.equal(tradeDay([B(100, 101, 99, 100), B(100, 102, 99, 101)], 5, 1e5), null);
// same-bar entry and stop -> stopped
t = tradeDay([B(100, 101, 99.5, 100.8), B(100.8, 101.5, 100, 100.2)], 5, 100000); assert.equal(t.exit, 100.5);
// costs: commission + slippage reduce pnl
t = tradeDay([B(100, 101, 99.5, 100.8), B(101, 101, 101, 101)], 5, 100000); assert.ok(t.pnl < 0);
// 9:30 ET in summer and winter
assert.deepEqual(et('2025-07-01T13:30:00Z'), { d: '2025-07-01', m: 570 });
assert.deepEqual(et('2025-01-02T14:30:00Z'), { d: '2025-01-02', m: 570 });
const s = stats([['2024-01-02', 1], ['2024-12-31', 1.1], ['2025-12-31', 1.21]]); assert.equal(s.yearly[1].ret, 10);
console.log('ORB tests passed');
