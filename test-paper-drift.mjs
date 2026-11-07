import assert from 'node:assert/strict';
import { decide, PAPER, parkOrder } from './scripts/paper-drift.mjs';
assert.equal(PAPER, 'https://paper-api.alpaca.markets');
const days = Array.from({ length: 70 }, (_, i) => `d${String(i).padStart(2, '0')}`), today = days.at(-1);
// old position (61 days) sold, young kept, gone dropped; buys fill free slots by biggest reaction, skip held
const state = { positions: [{ symbol: 'OLD', entry_date: days[days.length - 61], qty: 5 }, { symbol: 'NEW', entry_date: days[days.length - 3], qty: 2 }, { symbol: 'GONE', entry_date: days[60], qty: 1 }] };
const held = { OLD: 5, NEW: 2 };
const signals = [{ symbol: 'A', r: 0.06 }, { symbol: 'B', r: 0.12 }, { symbol: 'NEW', r: 0.2 }, { symbol: 'C', r: 0.07 }];
const d = decide({ today, days, state, held, signals, equity: 100000, prices: { A: 100, B: 50, NEW: 10, C: 20000 } });
assert.deepEqual(d.sells.map((s) => s.symbol), ['OLD']); assert.deepEqual(d.keep.map((p) => p.symbol), ['NEW']);
assert.deepEqual(d.buys.map((b) => [b.symbol, b.qty]), [['B', 200], ['A', 100]]);   // C too expensive for 1/10 slot
// slots cap
const full = { positions: Array.from({ length: 10 }, (_, i) => ({ symbol: 'P' + i, entry_date: days[65] })) };
const h2 = Object.fromEntries(full.positions.map((p) => [p.symbol, 1]));
assert.equal(decide({ today, days, state: full, held: h2, signals, equity: 1e5, prices: { A: 1, B: 1 } }).buys.length, 0);
// SPY parking
assert.equal(parkOrder({ equity: 100000, stockValue: 60000, spyPx: 500, spyHeld: 0 }), 76);      // (98000-60000)/500
assert.equal(parkOrder({ equity: 100000, stockValue: 90000, spyPx: 500, spyHeld: 76 }), -60);    // need room for buys -> sell
assert.equal(parkOrder({ equity: 100000, stockValue: 60000, spyPx: 500, spyHeld: 75 }), 0);      // tiny change skipped
assert.equal(parkOrder({ equity: 100000, stockValue: 120000, spyPx: 500, spyHeld: 10 }), -10);   // never negative target
console.log('paper drift tests passed');
