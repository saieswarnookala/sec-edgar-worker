// node test-clear-leader-alert.mjs — offline checks for the Slack alert
import { readFileSync } from 'node:fs';
import * as A from './scripts/clear-leader-alert.mjs';
let fails = 0; const ok = (c, m) => { console.log((c ? 'ok   ' : 'FAIL ') + m); if (!c) fails++; };

// time windows (New York)
ok(A.phaseFor(15 * 60 + 5) === 'preview' && A.phaseFor(17 * 60 + 30) === 'final' && A.phaseFor(12 * 60) === null, 'alert windows: ~3 pm preview, after-close final, nothing midday');
ok(A.nyNow(new Date('2026-10-30T19:05:00Z')).hhmm === '15:05' && A.nyNow(new Date('2026-12-31T20:05:00Z')).hhmm === '15:05', 'New York time handles daylight saving (Oct = EDT, Dec = EST)');

// last trading day (calendar mocked)
const cal = (days) => async () => days.map((date) => ({ date }));
ok(await A.isLastTradingDay('2026-10-30', {}, cal(['2026-10-30', '2026-11-02'])), 'Fri Oct 30 is the last trading day of October');
ok(!(await A.isLastTradingDay('2026-10-29', {}, cal(['2026-10-29', '2026-10-30']))), 'Thu Oct 29 is not');
ok(!(await A.isLastTradingDay('2026-10-31', {}, cal(['2026-11-02']))), 'a weekend day is not');
ok(await A.isLastTradingDay('2026-12-31', {}, async () => { throw new Error('offline'); }), 'falls back to "last weekday" if the calendar is unreachable');

// decision + message on real month-end data: holding SPY at Aug 31, signal DBC at Sep 30 -> switch
const L = readFileSync('data/etf_monthly.csv', 'utf8').trim().split('\n'); const h = L[0].split(',');
const rows = L.slice(1).map((l) => Object.fromEntries(l.split(',').map((v, i) => [h[i], i ? +v : v])));
const d = A.decide(rows);
ok(d.holding === 'SPY' && d.now.pos === 'DBC' && d.switch, `Sep 30, 2026: switch SPY → DBC (got ${d.holding} → ${d.now.pos})`);
const mkBars = (p) => Array.from({ length: 20 }, (_, i) => ({ d: '2026-09-' + String(i + 1).padStart(2, '0'), h: p * 1.01, l: p * 0.99, c: p }));
const bars = Object.fromEntries([...h.slice(1)].map((s) => [s, mkBars(rows[rows.length - 1][s])]));
const msg = A.message({ phase: 'final', d, bars, nyTime: '2026-09-30 17:30' });
ok(/SWITCH confirmed/.test(msg) && /\*Sell SPY\*/.test(msg) && /\*Buy DBC\*/.test(msg) && /buy range \$\d/.test(msg) && /don’t chase above/.test(msg), 'final message: sell SPY, buy DBC, with price ranges');
const pre = A.message({ phase: 'preview', d, bars, nyTime: '2026-09-30 15:05' });
ok(/switch likely at today’s close/.test(pre), 'preview message warns before the close');
const same = A.decide(rows.slice(0, -1)); // Aug 31: no switch
ok(!same.switch && A.message({ phase: 'preview', d: same, bars, nyTime: 'x' }) === null && /no change/.test(A.message({ phase: 'final', d: same, bars, nyTime: 'x' })), 'no switch: no preview, final says "no change, keep holding"');
ok(Math.abs(A.atr14(mkBars(100)) - 2) < 1e-9, 'ATR(14) from daily highs/lows');
console.log(fails ? `\n${fails} FAILED` : '\nall passed'); process.exitCode = fails ? 1 : 0;
