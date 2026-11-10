import assert from 'node:assert/strict';
import { volumeRatio, volFraction, dipScore, shouldExit, parkSymbol, decide } from './scripts/paper-dip.mjs';
let n = 0; const ok = (name, f) => { f(); n++; console.log('ok  ', name); };
const flat = (v, k = 210) => Array(k).fill(v);
ok('dip: uptrend stock down 12% vs flat SPY qualifies', () => {
  const c = [...Array(200).fill(80), ...Array(10).fill(100)]; const sc = dipScore(c, 88, flat(400), 400);
  assert.ok(sc <= -0.10 && sc > -0.13);
});
ok('dip: stock below its 200-day average is skipped', () => { assert.equal(dipScore([...Array(200).fill(150), ...Array(10).fill(100)], 88, flat(400), 400), null); });
ok('dip: 8% drop is not enough', () => { assert.equal(dipScore([...Array(200).fill(80), ...Array(10).fill(100)], 92, flat(400), 400), null); });
ok('dip: market fell too -> relative drop counts', () => { assert.equal(dipScore([...Array(200).fill(80), ...Array(10).fill(100)], 88, flat(400), 380), null); });
ok('exit: not on entry day', () => { assert.equal(shouldExit({ age: 0, closes: [90, 90, 90, 90], px: 120 }), null); });
ok('exit: bounce above 5-day avg', () => { assert.match(shouldExit({ age: 2, closes: [100, 95, 90, 88], px: 96 }), /bounced/); });
ok('exit: max hold', () => { assert.match(shouldExit({ age: 5, closes: [100, 95, 90, 88], px: 80 }), /max/); });
ok('park: cash when SPY below 100-day avg', () => { assert.equal(parkSymbol({ clPos: 'QQQ', spyCloses: flat(500, 120), spyPx: 480 }), null); assert.equal(parkSymbol({ clPos: 'QQQ', spyCloses: flat(500, 120), spyPx: 520 }), 'QQQ'); });
ok('decide: exits, entries, parking resize', () => {
  const days = ['2026-11-02', '2026-11-03', '2026-11-04', '2026-11-05', '2026-11-06', '2026-11-09'];
  const d = decide({ today: '2026-11-09', days, equity: 10000, state: { positions: [{ symbol: 'AAA', entry_date: '2026-11-03', qty: 10 }, { symbol: 'BBB', entry_date: '2026-11-06', qty: 10 }] },
    held: { AAA: 10, BBB: 10, SPY: 15 }, prices: { AAA: 101, BBB: 50, CCC: 40, DDD: 20, QQQ: 500, SPY: 600 },
    closes: { AAA: [100, 100, 100, 100], BBB: [60, 58, 56, 55] }, scores: { CCC: -0.15, DDD: -0.11 }, park: 'QQQ', parkHeld: { SPY: 15 } });
  assert.deepEqual(d.sells.map((s) => s.symbol), ['AAA']);         // AAA closed above its 5-day average -> sell; BBB still below -> keep
  assert.deepEqual(d.buys.map((b) => b.symbol), ['CCC', 'DDD']);
  assert.equal(d.buys[0].qty, 25);                                  // 10% of $10k / $40
  assert.ok(d.parkTrades.some((t) => t.symbol === 'SPY' && t.side === 'sell'));
  assert.ok(d.parkTrades.some((t) => t.symbol === 'QQQ' && t.side === 'buy'));
});
console.log(`\n${n} passed`);

// volume filter
{
  const base = Array(54).fill(1000);
  const quiet = volumeRatio(base, 1500), heavy = volumeRatio([...Array(50).fill(1000), 3000, 3000, 3000, 3000], 4000);
  if (!(Math.abs(quiet - 1.1) < 1e-9)) throw new Error('quiet ratio ' + quiet);
  if (!(Math.abs(heavy - 3.2) < 1e-9)) throw new Error('heavy ratio ' + heavy);
  if (volumeRatio(Array(20).fill(1), 1) !== null) throw new Error('short history should be null');
  if (!(volFraction(930) === 0.74 && volFraction(960) === 1 && volFraction(500) === 0)) throw new Error('vol curve');
  console.log('ok   volume filter ratio and curve');
}
