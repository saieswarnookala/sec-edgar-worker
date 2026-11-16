import assert from 'node:assert/strict';
import { volumeRatio, volFraction, sessionMinute, inWindow, volScale, virtualStep, dipScore, shouldExit, parkSymbol, decide, etfDipScore, ETF_MAX_HOLD, TUNED, mixStep, MIX, siCandidates, parseSI, shortFilter, fetchShortInterest } from './scripts/paper-dip.mjs';
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
ok('half day: trade window is 12:00-12:57 pm, normal day 3:00-3:57 pm', () => {
  assert.ok(inWindow(15 * 60 + 25) && !inWindow(12 * 60 + 25) && !inWindow(15 * 60 + 58));
  assert.ok(inWindow(12 * 60 + 25, 780) && !inWindow(15 * 60 + 25, 780) && !inWindow(12 * 60 + 58, 780));
});
ok('half day: volume curve squeezed into the 9:30-1:00 session', () => {
  assert.equal(sessionMinute(900), 900);
  assert.equal(sessionMinute(780, 780), 960);                        // 1:00 pm close = end of curve; 12:28 on a half day ~ 3:00 on a normal day
  assert.ok(Math.abs(volFraction(sessionMinute(12 * 60 + 28, 780)) - volFraction(15 * 60)) < 0.02);
});
ok('vol sizing: calm market -> half size, jumpy -> 1.5x', () => {
  const calm = [], jumpy = []; let a = 400, b = 400;
  for (let i = 0; i < 300; i++) { a *= 1 + (i < 250 ? 0.015 : 0.002) * (i % 2 ? 1 : -1); calm.push(a); b *= 1 + (i < 250 ? 0.003 : 0.03) * (i % 2 ? 1 : -1); jumpy.push(b); }
  const c = volScale(calm), j = volScale(jumpy);
  assert.ok(c.scale < 0.6 && c.scale >= 0.5, 'calm ' + JSON.stringify(c)); assert.ok(j.scale > 1.4 && j.scale <= 1.5, 'jumpy ' + JSON.stringify(j));
  assert.equal(volScale([400, 401, 402]).scale, 1);                      // not enough history -> normal size
});
ok('vol bot: virtual buy sized by scale, then sells on bounce', () => {
  const days = ['2026-11-09', '2026-11-10', '2026-11-11'];
  let r = virtualStep({ vs: undefined, today: '2026-11-10', days, prices: { CCC: 50, QQQ: 500 }, closes: {}, scores: { CCC: -0.15 }, park: 'QQQ', scale: 0.5 });
  assert.equal(r.vs.positions.length, 1); assert.ok(Math.abs(r.vs.positions[0].qty * 50 - 500) < 1);   // 5% of $10k
  assert.ok(Object.keys(r.vs.park).includes('QQQ'));
  const r2 = virtualStep({ vs: r.vs, today: '2026-11-11', days, prices: { CCC: 60, QQQ: 500 }, closes: { CCC: [50, 50, 50, 50] }, scores: {}, park: 'QQQ', scale: 1 });
  assert.equal(r2.vs.positions.length, 0); assert.equal(r2.vs.trades[0].ret_pct, 20);
  assert.ok(Math.abs(r2.equity - 10100) < 1, 'equity ' + r2.equity);  // +$100 on the $500 position
});
ok('etf dip: uptrend ETF down 6% over 5 days qualifies; 4% does not; downtrend skipped', () => {
  const c = [...Array(200).fill(80), ...Array(10).fill(100)];
  assert.ok(etfDipScore(c, 94) <= -0.05); assert.equal(etfDipScore(c, 96), null);
  assert.equal(etfDipScore([...Array(200).fill(150), ...Array(10).fill(100)], 94), null);
});
ok('etf sleeve: stocks get slots first, ETFs fill the rest; none without etfScores (live bot unchanged)', () => {
  const days = ['2026-11-09', '2026-11-10'], prices = { S1: 50, E1: 100, E2: 200, QQQ: 500 };
  const st = { positions: Array.from({ length: 8 }, (_, i) => ({ symbol: 'K' + i, entry_date: '2026-11-10', qty: 1 })) };
  const held = Object.fromEntries(st.positions.map((p) => [p.symbol, 1])); for (let i = 0; i < 8; i++) prices['K' + i] = 1000;
  const d = decide({ today: '2026-11-10', days, state: st, held, equity: 10000, prices, closes: {}, scores: { S1: -0.12 }, park: 'QQQ', parkHeld: {}, etfScores: { E1: -0.06, E2: -0.09 } });
  assert.deepEqual(d.buys.map((b) => b.symbol + ':' + (b.kind || 'stock')), ['S1:stock', 'E2:etf']);   // 2 free slots: stock first, then the bigger ETF dip
  const d0 = decide({ today: '2026-11-10', days, state: st, held, equity: 10000, prices, closes: {}, scores: { S1: -0.12 }, park: 'QQQ', parkHeld: {} });
  assert.deepEqual(d0.buys.map((b) => b.symbol), ['S1']);
});
ok('etf sleeve: ETF held up to 10 days, stock only 5', () => {
  const days = Array.from({ length: 12 }, (_, i) => `2026-11-${String(i + 1).padStart(2, '0')}`);
  const st = { positions: [{ symbol: 'E1', kind: 'etf', entry_date: days[0], qty: 1 }, { symbol: 'S1', entry_date: days[0], qty: 1 }] };
  const d = decide({ today: days[6], days, state: st, held: { E1: 1, S1: 1 }, equity: 10000, prices: { E1: 90, S1: 90, QQQ: 500 }, closes: { E1: [100, 100, 100, 100], S1: [100, 100, 100, 100] }, scores: {}, park: 'QQQ', parkHeld: {} });
  assert.deepEqual(d.sells.map((x) => x.symbol), ['S1']); assert.equal(ETF_MAX_HOLD, 10);
  const d2 = decide({ today: days[10], days, state: st, held: { E1: 1 }, equity: 10000, prices: { E1: 90, QQQ: 500 }, closes: { E1: [100, 100, 100, 100] }, scores: {}, park: 'QQQ', parkHeld: {} });
  assert.match(d2.sells[0].reason, /max 10/);
});
ok('etf virtual bot keeps the ETF tag across days', () => {
  const days = ['2026-11-09', '2026-11-10', '2026-11-11'];
  const r = virtualStep({ vs: undefined, today: '2026-11-10', days, prices: { E1: 100, QQQ: 500 }, closes: {}, scores: {}, park: 'QQQ', scale: 1, etfScores: { E1: -0.07 } });
  assert.equal(r.vs.positions[0].kind, 'etf');
  const r2 = virtualStep({ vs: r.vs, today: '2026-11-11', days, prices: { E1: 99, QQQ: 500 }, closes: { E1: [100, 100, 100, 100] }, scores: {}, park: 'QQQ', scale: 1 });
  assert.equal(r2.vs.positions.length, 1, 'ETF still held (below its 5-day avg, day 1 of 10)');
});
ok('tuned dip: 8% drop with 150-day trend qualifies where the 10%/200-day rule does not', () => {
  const closes = [...Array(60).fill(60), ...Array(145).fill(70), ...Array(5).fill(100)], spy = Array(210).fill(500);
  assert.equal(dipScore(closes, 91, spy, 500), null);                       // 9% dip: too small for the live rule
  assert.ok(dipScore(closes, 91, spy, 500, TUNED) <= -0.08);                 // but fine for the tuned rule
  assert.equal(dipScore([...Array(100).fill(200), ...Array(110).fill(100)], 91, spy, 500, TUNED), null);   // below its 150-day avg
});
ok('tuned dip: stocks held up to 7 days', () => {
  const days = Array.from({ length: 12 }, (_, i) => `2026-11-${String(i + 1).padStart(2, '0')}`);
  const st = { positions: [{ symbol: 'S1', entry_date: days[0], qty: 1 }] }, args = { days, state: st, held: { S1: 1 }, equity: 10000, prices: { S1: 90, QQQ: 500 }, closes: { S1: [100, 100, 100, 100] }, scores: {}, park: 'QQQ', parkHeld: {} };
  assert.equal(decide({ ...args, today: days[6], stockMaxHold: TUNED.maxHold }).sells.length, 0);
  assert.match(decide({ ...args, today: days[7], stockMaxHold: TUNED.maxHold }).sells[0].reason, /max 7/);
  assert.match(decide({ ...args, today: days[6] }).sells[0].reason, /max 5/);   // live bot unchanged
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
{
  // fractional sizing for a small live account: $1,000 with a $600 stock still gets a ~$100 slot
  const days = ['2026-11-06', '2026-11-09'];
  const d = decide({ today: '2026-11-09', days, equity: 1000, state: { positions: [] }, held: {}, prices: { BIG: 600, SMALL: 20, QQQ: 500 },
    closes: {}, scores: { BIG: -0.15, SMALL: -0.11 }, park: 'QQQ', parkHeld: {}, fractional: true });
  const big = d.buys.find((b) => b.symbol === 'BIG');
  if (!big || Math.abs(big.qty * 600 - 100) > 0.01 || big.qty >= 1) throw new Error('fractional buy ' + JSON.stringify(d.buys));
  const pk = d.parkTrades.find((t) => t.symbol === 'QQQ');
  if (!pk || pk.side !== 'buy' || Math.abs(pk.qty * 500 - 780) > 0.01) throw new Error('fractional parking ' + JSON.stringify(d.parkTrades));
  const whole = decide({ today: '2026-11-09', days, equity: 1000, state: { positions: [] }, held: {}, prices: { BIG: 600, QQQ: 500 }, closes: {}, scores: { BIG: -0.15 }, park: 'QQQ', parkHeld: {} });
  if (whole.buys.length) throw new Error('whole shares should skip a $600 stock in a $100 slot');
  ok('mix bot 7: 4 drift + 6 dip slots, drift held 60 days, dip smart exit, parking', () => {
  const days = Array.from({ length: 70 }, (_, i) => `d${String(i).padStart(2, '0')}`);
  const prices = { SPY: 500, QQQ: 400 }, scores = {}, drift = [];
  for (let i = 0; i < 8; i++) { prices['D' + i] = 50; scores['D' + i] = -0.10 - i / 100; prices['E' + i] = 20; drift.push({ symbol: 'E' + i, r: 0.05 + i / 100 }); }
  let r = mixStep({ vs: undefined, today: days[0], days, prices, closes: {}, scores, park: 'QQQ', driftSignals: drift });
  const k = (kind) => r.vs.positions.filter((p) => p.kind === kind);
  assert.equal(k('drift').length, MIX.driftSlots); assert.equal(k('dip').length, MIX.dipSlots);
  assert.deepEqual(k('drift').map((p) => p.symbol), ['E7', 'E6', 'E5', 'E4']);          // biggest reactions first
  assert.deepEqual(k('dip').map((p) => p.symbol), ['D7', 'D6', 'D5', 'D4', 'D3', 'D2']); // biggest dips first
  assert.equal(r.equity, 10000); assert.equal(r.vs.park.QQQ, undefined);                  // 100% invested -> nothing parked
  // day 1: dips bounce above their 5-day average -> sold; drift kept; freed money parked
  const p1 = { ...prices }; for (let i = 0; i < 8; i++) p1['D' + i] = 60;
  const closes = Object.fromEntries(Object.keys(p1).map((s) => [s, [50, 50, 50, 50]]));
  r = mixStep({ vs: r.vs, today: days[1], days, prices: p1, closes, scores: {}, park: 'QQQ', driftSignals: [] });
  assert.equal(r.vs.positions.length, 4); assert.ok(r.vs.park.QQQ > 0); assert.ok(r.equity > 10000);
  assert.equal(r.vs.trades.filter((t) => t.kind === 'dip' && t.ret_pct === 20).length, 6);
  // day 60: drift positions sold after 60 trading days
  r = mixStep({ vs: r.vs, today: days[59], days, prices: p1, closes, scores: {}, park: null, driftSignals: [] });
  assert.equal(r.vs.positions.length, 4);
  r = mixStep({ vs: r.vs, today: days[60], days, prices: p1, closes, scores: {}, park: null, driftSignals: [] });
  assert.equal(r.vs.positions.length, 0); assert.ok(/drift max 60/.test(r.done.join(' ')));
  assert.equal(Object.keys(r.vs.park).length, 0);                                           // park null = cash
  assert.ok(Math.abs(r.vs.cash - r.equity) < 0.01);
});
{
  const q = '"accountingYearMonthNumber"|"symbolCode"|"issueName"|"currentShortPositionQuantity"|"averageDailyVolumeQuantity"|"daysToCoverQuantity"\n"20261015"|"AAPL"|"Apple Inc."|"100"|"50"|"2.00"\n"20261015"|"BRK.B"|"Berkshire"|"900"|"100"|"9.00"\n';
  const u = 'accountingYearMonthNumber|symbolCode|issueName|currentShortPositionQuantity|averageDailyVolumeQuantity|daysToCoverQuantity\n20190614|XYZ|Foo "Bar Inc|10|5|\n20190614|AAPL|Apple Inc.|47003511|26629536|1.77\n';
  assert.deepEqual(parseSI(q), { AAPL: 2, 'BRK.B': 9 }); assert.deepEqual(parseSI(u), { XYZ: 2, AAPL: 1.77 });
  const c = siCandidates('2026-11-16'); assert.ok(c.includes('20261030') && c.includes('20261015')); assert.ok(!c.some((d) => d > '20261104'));   // >= 12 days old
  assert.equal(c[0], '20261030');
  const r = shortFilter({ AAPL: -0.12, 'BRK-B': -0.15, NEW: -0.11 }, { AAPL: 2, 'BRK.B': 9 });
  assert.deepEqual(Object.keys(r.kept).sort(), ['AAPL', 'NEW']); assert.deepEqual(r.skipped, { 'BRK-B': 9 });
  const big = q + Array(400).fill('"20261030"|"ZZZ"|"Z"|"1"|"1"|"1.00"').join('\n');
  const fake = async (url) => ({ ok: url.endsWith('shrt20261030.csv'), text: async () => big });
  const got = await fetchShortInterest('2026-11-16', fake); assert.equal(got.date, '20261030'); assert.equal(got.dtc['BRK.B'], 9);
  console.log('ok   bot 8 FINRA parse/candidates/filter/fetch');
}
console.log('ok   fractional sizing for small live account');
}
