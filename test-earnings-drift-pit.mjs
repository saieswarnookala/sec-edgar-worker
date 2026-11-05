import assert from 'node:assert/strict';
import { parseTable, parseChanges, membership, norm, parseDate, buildSignals, evaluate } from './scripts/earnings-drift-pit.mjs';
const html = `<table class="wikitable" id="changes"><thead><tr><th rowspan="2">Date</th><th colspan="2">Added</th><th colspan="2">Removed</th><th rowspan="2">Reason</th></tr>
<tr><th>Ticker</th><th>Security</th><th>Ticker</th><th>Security</th></tr></thead><tbody>
<tr><td rowspan="2">March 24, 2025</td><td><a href="x">DASH</a></td><td>DoorDash</td><td>BWA</td><td>BorgWarner Inc.</td><td>cap<sup>[5]</sup></td></tr>
<tr><td>TKO</td><td>TKO Group Holdings</td><td>TFX</td><td>Teleflex</td><td>cap</td></tr>
<tr><td>June 7, 2022</td><td>VRTX</td><td>Vertex</td><td>TWTR</td><td>Twitter, Inc.</td><td>acq</td></tr>
<tr><td>May 1, 2015</td><td>OLD</td><td>Old Co</td><td>GONE</td><td>Gone Co</td><td>x</td></tr></tbody></table>`;
const rows = parseTable(html, 'changes');
const ch = parseChanges(rows);
assert.equal(ch.length, 4); assert.deepEqual(ch[0].date, '2025-03-24'); assert.ok(ch.some((c) => c.addT === 'TKO' && c.date === '2025-03-24' && c.remT === 'TFX'));
assert.equal(ch[2].remN, 'Twitter, Inc.'); assert.equal(parseDate('September 2, 2016'), '2016-09-02');
const mem = membership([{ symbol: 'DASH', name: 'DoorDash', cik: 1 }, { symbol: 'TKO', name: 'TKO', cik: 2 }, { symbol: 'VRTX', name: 'Vertex', cik: 3 }, { symbol: 'AAPL', name: 'Apple', cik: 4 }], ch);
const g = (s) => mem.find((m) => m.symbol === s);
assert.equal(g('DASH').start, '2025-03-24'); assert.equal(g('VRTX').start, '2022-06-07'); assert.equal(g('AAPL').start, '0000-01-01');
assert.equal(g('TWTR').end, '2022-06-07'); assert.equal(g('TWTR').start, '0000-01-01'); assert.ok(g('TWTR').removed);
assert.equal(g('BWA').end, '2025-03-24'); assert.equal(mem.filter((m) => m.symbol === 'GONE').length, 0);
assert.equal(norm('Twitter, Inc.'), 'TWITTER'); assert.equal(norm('TWITTER INC'), 'TWITTER'); assert.equal(norm('Johnson & Johnson'), 'JOHNSON AND JOHNSON');
// signals: PIT filter drops events before membership
const dates = ['2022-06-01', '2022-06-02', '2022-06-03', '2022-06-06', '2022-06-07', '2022-06-08', '2022-06-09'];
const R = { V: [100, 100, 110, 110, 110, 121, 121] }, C = { SPY: [1, 1, 1, 1, 1, 1, 1], V: R.V }, Hh = { V: R.V.map((x) => x + 1) }, L = { V: R.V.map((x) => x - 1) };
const ev = { 3: [{ day: '2022-06-03', min: 480 }, { day: '2022-06-08', min: 480 }] };
const m = [{ id: 'V', cik: 3, start: '2022-06-07', end: '9999' }];
assert.equal(buildSignals(m, ev, dates, R, Hh, L, C, false).n, 2);
assert.equal(buildSignals(m, ev, dates, R, Hh, L, C, true).n, 1);
const O = { V: R.V, SPY: C.SPY }; const S = buildSignals(m, ev, dates, R, Hh, L, C, true).signals;
const e = evaluate(dates, O, { ...C }, S, 0, 'thr8|hold60|n10|any'); assert.ok(e.ref && e.all.length === 64 && e.spy.all);
console.log('earnings drift PIT tests passed');
