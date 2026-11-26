// node test-journal.mjs — offline test for the VM shadow journal (fake state, fake network; never touches a real account)
import assert from 'node:assert/strict';
import { dayRecord, liveTradePct, update, report, makeIO } from './journal.mjs';
const state = {
  history: [{ today: '2026-11-25', ny_time: '15:47', mode: 'live', account_value: 102.1, signal_list: ['CRWD -10.4%', 'ABC -11.0%'], placed: [{ symbol: 'XLE', side: 'sell', why: 'bounced' }, { symbol: 'ABC', side: 'buy', why: 'dip -11%' }] }],
  intraday: [{ today: '2026-11-25', ny_time: '10:00', mode: 'live', placed: [{ symbol: 'CRWD', side: 'buy', why: 'dip -10.4% (intraday)' }, { symbol: 'IEF', side: 'sell', why: 'parking: fund' }] }],
  verify: [{ today: '2026-11-25', fills: [{ symbol: 'CRWD', side: 'buy', price: 200 }] }, { today: '2026-11-27', fills: [{ symbol: 'CRWD', side: 'sell', price: 210 }] }],
};
let n = 0; const ok = (name, f) => Promise.resolve(f()).then(() => { n++; console.log('ok  ', name); });
await ok('signals from intraday + 3:47 run, parking ignored, live buys flagged', () => {
  const r = dayRecord(state, '2026-11-25'); assert.deepEqual(r.map((x) => [x.symbol, x.first_seen, x.live_bought]), [['CRWD', '10:00', true], ['ABC', '15:47', true]]);
});
await ok('live trade result from the bot\'s own fills', () => assert.equal(liveTradePct(state, 'CRWD', '2026-11-25'), 5));
const fakeFetch = async (url) => {
  const J = (o) => ({ ok: true, status: 200, json: async () => o });
  if (url.includes('/v1beta1/news')) return J({ news: [{ headline: 'Analyst downgrades CRWD to neutral', symbols: ['CRWD'], created_at: '2026-11-24T14:00:00Z' }, { headline: 'Market wrap', symbols: ['A', 'B', 'C', 'D'] }] });
  if (url.includes('/bars')) return J({ bars: ['2026-11-25', '2026-11-26', '2026-11-27', '2026-12-01', '2026-12-02', '2026-12-03'].map((d, i) => ({ t: d + 'T05:00:00Z', c: 100 + i })) });
  if (url.includes('anthropic')) return J({ content: [{ text: '{"cause":"analyst_downgrade","firm_specific":true,"severity":1,"verdict":"take","reason":"rating change, no business damage"}' }] });
  if (url.includes('company_tickers')) return J({ 0: { ticker: 'CRWD', cik_str: 1535527 } });
  if (url.includes('submissions')) return J({ filings: { recent: { form: ['8-K'], filingDate: ['2026-11-24'], items: ['2.02,9.01'] } } });
  return { ok: false, status: 404, json: async () => ({}) };
};
await ok('update: tags, 8-K, brain (3 votes), outcome, live trade; nothing about account size', async () => {
  const journal = { entries: [] };
  const io = makeIO({ APCA_API_KEY_ID: 'k', APCA_API_SECRET_KEY: 's', SEC_USER_AGENT: 'x y@z', ANTHROPIC_API_KEY: 'a' }, fakeFetch);
  assert.equal(await update({ state, journal, date: '2026-11-25', io }), 2);
  const e = journal.entries.find((x) => x.symbol === 'CRWD');
  assert.deepEqual(e.tags, ['downgrade']); assert.equal(e.headlines, 1); assert.deepEqual(e.sec_8k_items, ['2.02']);
  assert.equal(e.brain.verdict, 'take'); assert.equal(e.brain.agree, 3); assert.equal(e.outcome.ret5_pct, 5); assert.equal(e.outcome.live_trade_pct, 5);
  assert.ok(!JSON.stringify(journal).includes('102.1'));
  assert.equal(await update({ state, journal, date: '2026-11-25', io }), 0);   // second run adds nothing
  assert.match(report(journal), /By brain verdict[\s\S]*take/);
});
await ok('no Claude key -> no brain label, rest still works', async () => {
  const journal = { entries: [] }; await update({ state, journal, date: '2026-11-25', io: makeIO({}, fakeFetch) });
  assert.equal(journal.entries[0].brain, null); assert.equal(journal.entries[0].sec_8k_items, null);
});
console.log(`${n} journal tests passed`);
