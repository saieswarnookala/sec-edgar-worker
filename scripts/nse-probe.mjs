// Probe: can GitHub Actions fetch NSE results/board-meeting dates for free?
import { writeFileSync, mkdirSync } from 'node:fs';
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36';
let cookie = '';
async function get(url, ref = 'https://www.nseindia.com/') {
  const r = await fetch(url, { headers: { 'user-agent': UA, accept: 'application/json, text/plain, */*', 'accept-language': 'en-US,en;q=0.9', referer: ref, cookie } });
  const sc = r.headers.getSetCookie?.() || []; if (sc.length) cookie = [...new Set([...cookie.split('; ').filter(Boolean), ...sc.map((c) => c.split(';')[0])])].join('; ');
  const text = await r.text(); return { status: r.status, text };
}
const out = { at: new Date().toISOString(), tests: [] };
const home = await get('https://www.nseindia.com/'); out.home = home.status;
await get('https://www.nseindia.com/companies-listing/corporate-filings-financial-results');
const urls = {
  results: (s) => `https://www.nseindia.com/api/corporates-financial-results?index=equities&symbol=${s}&period=Quarterly`,
  boardMeetings: (s) => `https://www.nseindia.com/api/corporate-board-meetings?index=equities&symbol=${s}`,
  announcements: (s) => `https://www.nseindia.com/api/corporate-announcements?index=equities&symbol=${s}&from_date=01-01-2016&to_date=31-12-2016`,
};
for (const s of ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK']) for (const [k, f] of Object.entries(urls)) {
  let r; try { r = await get(f(s), 'https://www.nseindia.com/companies-listing/corporate-filings-financial-results'); } catch (e) { r = { status: 'ERR ' + e.message, text: '' }; }
  let n = null, first = null, last = null, sample = null;
  try { const j = JSON.parse(r.text); const arr = Array.isArray(j) ? j : j.data || []; n = arr.length; sample = arr[0];
    const ds = arr.map((x) => x.filingDate || x.broadcastDate || x.bm_date || x.an_dt || x.toDate || x.sort_date).filter(Boolean); first = ds[ds.length - 1]; last = ds[0]; } catch {}
  out.tests.push({ symbol: s, kind: k, status: r.status, count: n, newest: last, oldest: first, sample: sample && JSON.stringify(sample).slice(0, 400), body: n == null ? r.text.slice(0, 200) : undefined });
  await new Promise((z) => setTimeout(z, 1200));
}
mkdirSync('data', { recursive: true }); writeFileSync('data/nse_probe.json', JSON.stringify(out, null, 2));
for (const t of out.tests) console.log(t.symbol, t.kind, t.status, t.count, t.oldest, '->', t.newest);
