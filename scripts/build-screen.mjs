// Builds data/screen.json: top 15 "high P/E but profitable + growing" US stocks per market-cap bucket.
// Runs in GitHub Actions (no CPU limits). Prices + market cap: Nasdaq screener. Earnings + sales: SEC XBRL frames.
// Usage: SEC_USER_AGENT="Name email" node scripts/build-screen.mjs [out=data/screen.json]

import { writeFileSync, mkdirSync } from 'node:fs';
import { dirname } from 'node:path';

export const RULES = {
  per_bucket: 15,
  min_price: 1,
  min_net_margin: 0.03,     // avoids P/E blown up by tiny profits
  min_sales_growth: 0.05,   // sales up at least 5% vs the year before
  min_profit_growth: 0,     // profit up vs the year before
  max_pe: 200,              // drops one-off outliers
};

export const BUCKETS = [
  { bucket: 'Mega', min: 200e9, max: Infinity },
  { bucket: 'Large', min: 10e9, max: 200e9 },
  { bucket: 'Mid', min: 2e9, max: 10e9 },
  { bucket: 'Small', min: 300e6, max: 2e9 },
  { bucket: 'Micro', min: 50e6, max: 300e6 },
];

const NASDAQ_URL = 'https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=10000&offset=0&download=true';
const TICKERS_URL = 'https://www.sec.gov/files/company_tickers.json';
const FRAME_URL = (tag, period) => `https://data.sec.gov/api/xbrl/frames/us-gaap/${tag}/USD/${period}.json`;
const REVENUE_TAGS = ['RevenueFromContractWithCustomerExcludingAssessedTax', 'Revenues', 'RevenueFromContractWithCustomerIncludingAssessedTax', 'SalesRevenueNet'];

const num = (s) => {
  if (s == null) return null;
  const n = Number(String(s).replace(/[$,%\s]/g, ''));
  return Number.isFinite(n) ? n : null;
};
const normSym = (s) => String(s || '').trim().toUpperCase().replace(/[/.]/g, '-');

export async function build({ fetchFn = fetch, ua, now = new Date() }) {
  if (!ua) throw new Error('SEC_USER_AGENT is required');
  const secGet = async (url) => {
    for (let i = 0; i < 4; i++) {
      const r = await fetchFn(url, { headers: { 'User-Agent': ua, Accept: 'application/json' } });
      if (r.status === 404) return null;
      if (r.ok) return r.json();
      await new Promise((res) => setTimeout(res, 1500 * (i + 1)));
    }
    throw new Error(`SEC request failed: ${url}`);
  };

  // 1) Prices + market caps
  const nres = await fetchFn(NASDAQ_URL, {
    headers: {
      'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36',
      Accept: 'application/json, text/plain, */*',
      Origin: 'https://www.nasdaq.com',
      Referer: 'https://www.nasdaq.com/',
    },
  });
  if (!nres.ok) throw new Error(`Nasdaq screener HTTP ${nres.status}`);
  const nj = await nres.json();
  const nrows = nj?.data?.rows || nj?.data?.table?.rows || [];
  if (nrows.length < 1000) throw new Error(`Nasdaq screener returned only ${nrows.length} rows`);

  // 2) Ticker -> CIK
  const tj = await secGet(TICKERS_URL);
  const cikOf = new Map(Object.values(tj).map((r) => [normSym(r.ticker), r.cik_str]));

  // 3) Pick the latest calendar year with good coverage, then the year before
  let year = now.getUTCFullYear() - 1;
  let niNow = await secGet(FRAME_URL('NetIncomeLoss', `CY${year}`));
  if (!niNow || (niNow.data || []).length < 2500) {
    year -= 1;
    niNow = await secGet(FRAME_URL('NetIncomeLoss', `CY${year}`));
  }
  const niPrev = await secGet(FRAME_URL('NetIncomeLoss', `CY${year - 1}`));
  const toMap = (frame) => new Map((frame?.data || []).map((d) => [d.cik, d]));
  const NI = toMap(niNow), NI1 = toMap(niPrev);

  const REV = new Map(), REV1 = new Map();
  for (const tag of REVENUE_TAGS) {
    const [a, b] = [await secGet(FRAME_URL(tag, `CY${year}`)), await secGet(FRAME_URL(tag, `CY${year - 1}`))];
    for (const d of a?.data || []) if (!REV.has(d.cik)) REV.set(d.cik, d);
    for (const d of b?.data || []) if (!REV1.has(d.cik)) REV1.set(d.cik, d);
  }

  // 4) Universe: one row per company (largest market cap share class, ties by volume)
  const byCik = new Map();
  for (const r of nrows) {
    const symbol = normSym(r.symbol);
    if (!symbol || /[\^~]/.test(r.symbol)) continue;
    const cik = cikOf.get(symbol);
    const price = num(r.lastsale), mcap = num(r.marketCap), vol = num(r.volume) || 0;
    if (!cik || price == null || !mcap) continue;
    const prev = byCik.get(cik);
    if (!prev || mcap > prev.market_cap || (mcap === prev.market_cap && vol > prev.volume)) {
      byCik.set(cik, { cik, symbol, name: String(r.name || '').replace(/\s+(Common Stock|Class [A-C] Common Stock|Ordinary Shares).*$/i, '').trim(), sector: r.sector || null, industry: r.industry || null, price, market_cap: mcap, volume: vol });
    }
  }

  // 5) Rules
  const counts = { universe: byCik.size, with_financials: 0, passed: 0 };
  const picks = [];
  for (const c of byCik.values()) {
    const ni = NI.get(c.cik)?.val, ni1 = NI1.get(c.cik)?.val, rev = REV.get(c.cik)?.val, rev1 = REV1.get(c.cik)?.val;
    if ([ni, ni1, rev, rev1].some((v) => v == null)) continue;
    counts.with_financials++;
    if (c.price < RULES.min_price || ni <= 0 || ni1 <= 0 || rev <= 0 || rev1 <= 0) continue;
    const net_margin = ni / rev, sales_growth = rev / rev1 - 1, profit_growth = ni / ni1 - 1, pe = c.market_cap / ni;
    if (net_margin < RULES.min_net_margin || sales_growth < RULES.min_sales_growth || profit_growth <= RULES.min_profit_growth || pe > RULES.max_pe) continue;
    const b = BUCKETS.find((x) => c.market_cap >= x.min && c.market_cap < x.max);
    if (!b) continue;
    counts.passed++;
    picks.push({ ...c, bucket: b.bucket, pe, net_income: ni, revenue: rev, net_margin, sales_growth, profit_growth, fy_end: NI.get(c.cik).end });
  }

  const rows = [];
  for (const b of BUCKETS) {
    picks.filter((p) => p.bucket === b.bucket).sort((x, y) => y.pe - x.pe).slice(0, RULES.per_bucket)
      .forEach((p, i) => rows.push({
        bucket: b.bucket, rank: i + 1, symbol: p.symbol, name: p.name, sector: p.sector, industry: p.industry,
        price: p.price, market_cap: p.market_cap, pe: +p.pe.toFixed(2), net_income: p.net_income, revenue: p.revenue,
        net_margin: +p.net_margin.toFixed(4), sales_growth: +p.sales_growth.toFixed(4), profit_growth: +p.profit_growth.toFixed(4), fy_end: p.fy_end,
      }));
  }

  return {
    generated_at: now.toISOString(),
    earnings_year: `CY${year}`,
    rules: RULES,
    buckets: BUCKETS.map((b) => ({ bucket: b.bucket, min: b.min, max: Number.isFinite(b.max) ? b.max : null })),
    counts,
    rows,
  };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const out = process.argv[2] || 'data/screen.json';
  const result = await build({ ua: process.env.SEC_USER_AGENT });
  mkdirSync(dirname(out), { recursive: true });
  writeFileSync(out, JSON.stringify(result, null, 1));
  console.log(`Wrote ${out}: ${result.rows.length} rows, earnings ${result.earnings_year}`, result.counts);
}
