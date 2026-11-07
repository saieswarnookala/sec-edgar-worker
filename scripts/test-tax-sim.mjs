import assert from 'node:assert/strict';
import { simTax } from './tax-sim.mjs';
// 3 years of dates, one stock that doubles during a trade in year 1, flat benchmark
const dates = [], O = { A: [] }, C = { A: [] }, B = [];
for (let y = 2020; y <= 2022; y++) for (let m = 1; m <= 12; m++) for (const d of [1, 15]) dates.push(`${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`);
for (let t = 0; t < dates.length; t++) { const p = t < 2 ? 10 : 20; O.A.push(p); C.A.push(p); B.push(100); }
const signals = []; signals[1] = [{ s: 'A', r: 0.1 }];
const base = { dates, O, C, B, signals, th: 0.05, h: 3, n: 1, cost: 0 };
const pre = simTax({ ...base, rate: 0 }); assert.ok(Math.abs(pre.final - 2) < 1e-9, 'doubles pre-tax');
const post = simTax({ ...base, rate: 0.24 }); assert.ok(Math.abs(post.final - 1.76) < 1e-9, 'pays 24% of the gain');
assert.equal(post.trades, 1);
// loss carryforward: lose 50% in year 1 then double in year 2 -> net gain 0, no tax
const O2 = { A: [] }, C2 = { A: [] };
for (let t = 0; t < dates.length; t++) { const p = t < 2 ? 10 : t < 27 ? 5 : 10; O2.A.push(p); C2.A.push(p); }
const s2 = []; s2[1] = [{ s: 'A', r: 0.1 }]; s2[26] = [{ s: 'A', r: 0.1 }];
const lc = simTax({ dates, O: O2, C: C2, B, signals: s2, th: 0.05, h: 3, n: 1, cost: 0, rate: 0.24 });
assert.ok(Math.abs(lc.final - 1) < 1e-9 && lc.taxPaid === 0, 'loss carried forward ' + JSON.stringify(lc));
// parking: no signals, benchmark +50% -> park earns it, taxed at rate
const B3 = dates.map((d, t) => (t < dates.length - 1 ? 100 : 150));
const pk = simTax({ dates, O, C, B: B3, signals: [], th: 0.05, h: 3, n: 1, cost: 0, rate: 0.2, park: true, ltRate: 0.15 });
assert.ok(Math.abs(pk.final - 1.4) < 1e-9, 'park gain taxed ' + pk.final); assert.ok(pk.benchCagr > 0);
console.log('tax-sim tests passed');
