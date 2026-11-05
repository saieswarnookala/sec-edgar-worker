import assert from 'node:assert/strict';
import { parseFunding, toDaily, simulate, rotate, stats, SIDE_COST } from './scripts/funding-arb.mjs';
const csv = 'calc_time,funding_interval_hours,last_funding_rate\n1577836800000,8,0.0001\n1577865600000,8,0.0001\n1577894400000,8,-0.00005\n1577923200000,8,0.0003\n';
const rows = parseFunding(csv); assert.equal(rows.length, 4);
const d = toDaily(rows); assert.ok(Math.abs(d['2020-01-01'] - 0.00015) < 1e-12); assert.ok(Math.abs(d['2020-01-02'] - 0.0003) < 1e-12);
assert.equal(parseFunding('1577836800000,0.0002\n').length, 1);  // headerless 2-column
// always: enter day 1 (cost), earn from day 2
const dates = ['a', 'b', 'c'], dd = { a: 0.001, b: 0.001, c: 0.001 };
const s = simulate(dates, dd, { E: 1, mode: 'always' });
assert.ok(Math.abs(s[0][1] + SIDE_COST) < 1e-12); assert.ok(Math.abs(s[1][1] - 0.001) < 1e-12);
const s5 = simulate(dates, dd, { E: 0.5, mode: 'always' }); assert.ok(Math.abs(s5[1][1] - 0.0005) < 1e-12);
// filter: low funding never turns on
const low = { a: 0.00001, b: 0.00001, c: 0.00001 };
assert.equal(simulate(dates, low, { E: 1, mode: 'filter', th: 0.1, lb: 2 }).filter((x) => x[2]).length, 0);
// filter: high funding turns on after lookback, then off when it goes negative
const ds = ['1', '2', '3', '4', '5', '6'], hi = { 1: 0.001, 2: 0.001, 3: 0.001, 4: -0.002, 5: -0.002, 6: 0.0 };
const f = simulate(ds, hi, { E: 1, mode: 'filter', th: 0.1, lb: 2 }); assert.equal(f[1][2], true); assert.equal(f[1][1], -SIDE_COST); assert.equal(f.at(-1)[2], false);
// rotation picks the higher-funding coin
const r = rotate(['x', 'y', 'z'], { A: { x: 0.001, y: 0.001, z: 0.001 }, B: { x: 0.0001, y: 0.0001, z: 0.0001 } }, { E: 1, th: 0.1, lb: 1 });
assert.equal(r[0][2], 'A');
const st = stats([['2020-01-01', 0.1, true], ['2020-02-01', -0.5, true]]); assert.equal(st.max_dd, 50); assert.equal(st.yearly['2020'], -45);
console.log('funding arb tests passed');
