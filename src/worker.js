// SEC EDGAR MCP server for Cloudflare Workers (free plan friendly)
// Endpoint:  POST /mcp/<ACCESS_TOKEN>         (MCP Streamable HTTP, stateless JSON)
// Debug:     GET  /api/<ACCESS_TOKEN>/financials?symbol=LULU
//            GET  /api/<ACCESS_TOKEN>/lookup?symbol=LULU
//            GET  /health
// Secrets:   SEC_USER_AGENT ("Your Name you@email.com"), ACCESS_TOKEN
// Optional:  KV binding CACHE (12h result cache)

const TICKERS_URL = 'https://www.sec.gov/files/company_tickers_exchange.json';
const SUBMISSIONS_URL = (cik) => `https://data.sec.gov/submissions/CIK${cik}.json`;
const CONCEPT_URL = (cik, tag) => `https://data.sec.gov/api/xbrl/companyconcept/CIK${cik}/us-gaap/${tag}.json`;

const FORMS = new Set(['10-K', '10-K/A', '10-Q', '10-Q/A', '10-KT', '10-KT/A']);
const DAY = 86400000;
const CACHE_VERSION = 'v2';
const SUBREQUEST_BUDGET = 46; // free plan hard limit is 50

// kind: flow (summable, quarters derived from YTD), avg (per-share style, no derivation), inst (balance sheet)
const FIELDS = {
  revenue: { kind: 'flow', unit: 'USD', history: true, tags: ['RevenueFromContractWithCustomerExcludingAssessedTax', 'Revenues', 'SalesRevenueNet', 'RevenueFromContractWithCustomerIncludingAssessedTax', 'SalesRevenueGoodsNet'] },
  net_income: { kind: 'flow', unit: 'USD', history: true, tags: ['NetIncomeLoss', 'ProfitLoss'] },
  cost_of_revenue: { kind: 'flow', unit: 'USD', tags: ['CostOfGoodsAndServicesSold', 'CostOfRevenue', 'CostOfGoodsSold'] },
  gross_profit: { kind: 'flow', unit: 'USD', tags: ['GrossProfit'] },
  operating_income: { kind: 'flow', unit: 'USD', tags: ['OperatingIncomeLoss'] },
  pretax_income: { kind: 'flow', unit: 'USD', tags: ['IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest', 'IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments'] },
  interest_expense: { kind: 'flow', unit: 'USD', tags: ['InterestExpense', 'InterestExpenseNonoperating', 'InterestExpenseDebt'] },
  operating_cf: { kind: 'flow', unit: 'USD', tags: ['NetCashProvidedByUsedInOperatingActivities', 'NetCashProvidedByUsedInOperatingActivitiesContinuingOperations'] },
  capex: { kind: 'flow', unit: 'USD', tags: ['PaymentsToAcquirePropertyPlantAndEquipment', 'PaymentsToAcquireProductiveAssets'] },
  shares_diluted: { kind: 'avg', unit: 'shares', tags: ['WeightedAverageNumberOfDilutedSharesOutstanding'] },
  total_assets: { kind: 'inst', unit: 'USD', tags: ['Assets'] },
  current_assets: { kind: 'inst', unit: 'USD', tags: ['AssetsCurrent'] },
  current_liabilities: { kind: 'inst', unit: 'USD', tags: ['LiabilitiesCurrent'] },
  equity: { kind: 'inst', unit: 'USD', tags: ['StockholdersEquity', 'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest'] },
  cash: { kind: 'inst', unit: 'USD', tags: ['CashAndCashEquivalentsAtCarryingValue', 'CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents'] },
  lt_debt: { kind: 'inst', unit: 'USD', noMerge: true, tags: ['LongTermDebtNoncurrent', 'LongTermDebt'] },
  lt_debt_current: { kind: 'inst', unit: 'USD', tags: ['LongTermDebtCurrent', 'DebtCurrent'] },
  short_term_borrowings: { kind: 'inst', unit: 'USD', tags: ['ShortTermBorrowings', 'CommercialPaper'] },
  op_lease_total: { kind: 'inst', unit: 'USD', tags: ['OperatingLeaseLiability'] },
  op_lease_noncurrent: { kind: 'inst', unit: 'USD', tags: ['OperatingLeaseLiabilityNoncurrent'] },
  op_lease_current: { kind: 'inst', unit: 'USD', tags: ['OperatingLeaseLiabilityCurrent'] },
  finance_lease: { kind: 'inst', unit: 'USD', tags: ['FinanceLeaseLiability'] },
  shares_out: { kind: 'inst', unit: 'shares', tags: ['CommonStockSharesOutstanding'] },
};

// ---------- helpers ----------
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const spanDays = (start, end) => Math.round((Date.parse(end) - Date.parse(start)) / DAY) + 1;
const nextDay = (d) => new Date(Date.parse(d) + DAY).toISOString().slice(0, 10);
const padCik = (cik) => String(cik).padStart(10, '0');
const normSymbol = (s) => String(s || '').trim().toUpperCase().replace(/\./g, '-');

class Sec {
  constructor(env) {
    if (!env.SEC_USER_AGENT) throw new Error('SEC_USER_AGENT secret is not set');
    this.ua = env.SEC_USER_AGENT;
    this.count = 0;
  }
  async get(url) {
    for (let attempt = 0; attempt < 3; attempt++) {
      if (this.count >= SUBREQUEST_BUDGET) throw new Error('Subrequest budget exceeded');
      this.count++;
      const res = await fetch(url, { headers: { 'User-Agent': this.ua, Accept: 'application/json' } });
      if (res.status === 429 || res.status === 503) { await sleep(600 * (attempt + 1)); continue; }
      return res;
    }
    throw new Error('SEC rate limited, try again in a minute');
  }
}

async function pool(items, limit, fn) {
  const out = new Array(items.length);
  let i = 0;
  const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (i < items.length) { const k = i++; out[k] = await fn(items[k]); }
  });
  await Promise.all(workers);
  return out;
}

// ---------- ticker lookup (string search, no full JSON.parse: keeps CPU under 10ms) ----------
async function findTicker(sec, symbol) {
  const res = await sec.get(TICKERS_URL);
  if (!res.ok) throw new Error(`SEC tickers file HTTP ${res.status}`);
  const txt = await res.text();
  const needle = `,"${symbol}","`;
  let from = 0;
  while (true) {
    const i = txt.indexOf(needle, from);
    if (i < 0) return null;
    const end = txt.indexOf(']', i);
    let s = txt.lastIndexOf('[', i);
    for (let tries = 0; s >= 0 && tries < 4; tries++) {
      try {
        const row = JSON.parse(txt.slice(s, end + 1)); // [cik, name, ticker, exchange]
        if (Array.isArray(row) && row[2] === symbol) {
          return { cik: padCik(row[0]), name: row[1], ticker: row[2], exchange: row[3] || null };
        }
        break;
      } catch { s = txt.lastIndexOf('[', s - 1); }
    }
    from = i + needle.length;
  }
}

async function getSubmissionsMeta(sec, cik) {
  const res = await sec.get(SUBMISSIONS_URL(cik));
  if (!res.ok) return {};
  const txt = await res.text();
  const pick = (re) => { const m = txt.match(re); return m ? m[1] : null; };
  const fye = pick(/"fiscalYearEnd"\s*:\s*"(\d{4})"/);
  return {
    sic: pick(/"sic"\s*:\s*"(\d*)"/),
    sic_description: pick(/"sicDescription"\s*:\s*"([^"]*)"/),
    fiscal_year_end: fye ? `${fye.slice(0, 2)}-${fye.slice(2)}` : null,
    state_of_incorporation: pick(/"stateOfIncorporation"\s*:\s*"([^"]*)"/),
  };
}

// ---------- XBRL series builders ----------
function factsOf(json, unit) {
  const arr = json?.units?.[unit];
  return Array.isArray(arr) ? arr.filter((f) => FORMS.has(f.form) && f.end && typeof f.val === 'number') : [];
}

function latestBy(facts, keyFn) {
  const m = new Map();
  for (const f of facts) {
    const k = keyFn(f);
    const p = m.get(k);
    if (!p || f.filed > p.filed) m.set(k, f);
  }
  return m;
}

// flow: annual (350-380d), quarterly direct (80-100d) + derived from YTD differences (Q2, Q3, Q4 = FY - 9M)
export function flowSeries(facts) {
  const uniq = latestBy(facts.filter((f) => f.start), (f) => `${f.start}|${f.end}`);
  const annual = new Map();
  const quarterly = new Map();
  const byStart = new Map();
  for (const f of uniq.values()) {
    const d = spanDays(f.start, f.end);
    if (d >= 350 && d <= 380) annual.set(f.end, f.val);
    if (d >= 80 && d <= 100) quarterly.set(f.end, f.val);
    if (!byStart.has(f.start)) byStart.set(f.start, []);
    byStart.get(f.start).push(f);
  }
  for (const arr of byStart.values()) {
    arr.sort((a, b) => (a.end < b.end ? -1 : 1));
    for (let i = 1; i < arr.length; i++) {
      const a = arr[i - 1];
      const b = arr[i];
      const gap = spanDays(nextDay(a.end), b.end);
      const da = spanDays(a.start, a.end);
      if (gap >= 80 && gap <= 100 && da >= 80 && da <= 290 && !quarterly.has(b.end)) {
        quarterly.set(b.end, b.val - a.val);
      }
    }
  }
  return { annual, quarterly };
}

export function avgSeries(facts) {
  const uniq = latestBy(facts.filter((f) => f.start), (f) => `${f.start}|${f.end}`);
  const annual = new Map();
  const quarterly = new Map();
  for (const f of uniq.values()) {
    const d = spanDays(f.start, f.end);
    if (d >= 350 && d <= 380) annual.set(f.end, f.val);
    if (d >= 80 && d <= 100) quarterly.set(f.end, f.val);
  }
  return { annual, quarterly };
}

export function instSeries(facts) {
  const uniq = latestBy(facts.filter((f) => !f.start), (f) => f.end);
  const points = new Map();
  for (const [end, f] of uniq) points.set(end, f.val);
  return { points };
}

function mergeInto(base, add) {
  for (const key of Object.keys(add)) {
    for (const [k, v] of add[key]) if (!base[key].has(k)) base[key].set(k, v);
  }
  return base;
}

function latestDate(series) {
  let max = '';
  for (const m of Object.values(series)) for (const k of m.keys()) if (k > max) max = k;
  return max;
}

async function fetchField(sec, cik, name, spec) {
  const build = spec.kind === 'flow' ? flowSeries : spec.kind === 'avg' ? avgSeries : instSeries;
  let merged = null;
  let tag = null;
  for (const t of spec.tags) {
    const res = await sec.get(CONCEPT_URL(cik, t));
    if (res.status === 404) continue;
    if (!res.ok) throw new Error(`SEC concept ${t} HTTP ${res.status}`);
    const facts = factsOf(await res.json(), spec.unit);
    if (!facts.length) continue;
    const s = build(facts);
    merged = merged ? mergeInto(merged, s) : s;
    tag = tag || t;
    if (spec.noMerge) break;
    const recent = Date.now() - Date.parse(latestDate(merged) || '1900-01-01') < 550 * DAY;
    const enough = !spec.history || merged.annual.size >= 11;
    if (recent && enough) break;
  }
  return { name, tag, series: merged };
}

function instAt(series, date) {
  if (!series?.points) return null;
  if (series.points.has(date)) return series.points.get(date);
  const t = Date.parse(date);
  let best = null;
  let bestGap = 8 * DAY;
  for (const [k, v] of series.points) {
    const gap = Math.abs(Date.parse(k) - t);
    if (gap < bestGap) { best = v; bestGap = gap; }
  }
  return best;
}

const sumKnown = (...xs) => (xs.some((x) => x != null) ? xs.reduce((a, x) => a + (x ?? 0), 0) : null);

export function buildRows(F, opts = {}) {
  const maxAnnual = opts.maxAnnual ?? 11;
  const maxQuarterly = opts.maxQuarterly ?? 24;
  const dates = (key) => {
    const set = new Set();
    for (const f of ['revenue', 'net_income']) for (const k of F[f]?.series?.[key]?.keys() ?? []) set.add(k);
    return [...set].sort().reverse();
  };
  const debtReported = ['lt_debt', 'lt_debt_current', 'short_term_borrowings'].some((k) => F[k]?.series);
  const leaseReported = ['op_lease_total', 'op_lease_noncurrent', 'op_lease_current', 'finance_lease'].some((k) => F[k]?.series);
  const ltIsTotal = F.lt_debt?.tag === 'LongTermDebt';

  const rows = [];
  for (const [period, key, max] of [['annual', 'annual', maxAnnual], ['quarterly', 'quarterly', maxQuarterly]]) {
    for (const date of dates(key).slice(0, max)) {
      const flow = (n) => F[n]?.series?.[key]?.get(date) ?? null;
      const inst = (n) => instAt(F[n]?.series, date);

      const revenue = flow('revenue');
      const cost = flow('cost_of_revenue');
      const gross = flow('gross_profit') ?? (revenue != null && cost != null ? revenue - cost : null);
      const opInc = flow('operating_income');
      const pretax = flow('pretax_income');
      const intExp = flow('interest_expense');
      const ebit = pretax != null && intExp != null ? pretax + intExp : opInc;

      const totalAssets = inst('total_assets');
      const hasBalance = totalAssets != null;

      const ltRaw = inst('lt_debt');
      const ltCur = inst('lt_debt_current');
      const stb = inst('short_term_borrowings');
      let borrowings = ltIsTotal ? sumKnown(ltRaw, stb) : sumKnown(ltRaw, ltCur, stb);
      if (borrowings == null && hasBalance) borrowings = 0; // nothing reported at this date → no borrowings
      const longTerm = ltIsTotal ? (ltRaw != null ? ltRaw - (ltCur ?? 0) : null) : ltRaw;

      const opTotal = inst('op_lease_total') ?? sumKnown(inst('op_lease_noncurrent'), inst('op_lease_current'));
      let leases = sumKnown(opTotal, inst('finance_lease'));
      if (leases == null && hasBalance) leases = 0;

      const capexRaw = flow('capex');
      rows.push({
        period,
        date,
        revenue,
        gross_profit: gross,
        operating_income: opInc,
        ebit,
        interest_expense: intExp,
        net_income: flow('net_income'),
        operating_cf: flow('operating_cf'),
        capex: capexRaw != null ? Math.abs(capexRaw) : null,
        total_assets: totalAssets,
        current_assets: inst('current_assets'),
        current_liabilities: inst('current_liabilities'),
        equity: inst('equity'),
        cash: inst('cash'),
        borrowings,
        leases,
        debt_total: borrowings != null || leases != null ? (borrowings ?? 0) + (leases ?? 0) : null,
        long_term_debt: longTerm ?? (hasBalance && !debtReported ? 0 : null),
        current_long_term_debt: ltIsTotal ? ltCur : ltCur ?? (hasBalance && !debtReported ? 0 : null),
        shares: inst('shares_out') ?? flow('shares_diluted'),
      });
    }
  }
  return { rows, debtReported, leaseReported };
}

// ---------- tools ----------
async function lookupCompany(env, symbolIn) {
  const symbol = normSymbol(symbolIn);
  if (!symbol) throw new Error('symbol is required');
  const sec = new Sec(env);
  const t = await findTicker(sec, symbol);
  if (!t) throw new Error(`Ticker ${symbol} not found in SEC list (US filers only)`);
  const meta = await getSubmissionsMeta(sec, t.cik);
  return { symbol: t.ticker, cik: t.cik, name: t.name, exchange: t.exchange, ...meta };
}

async function getFinancials(env, symbolIn) {
  const symbol = normSymbol(symbolIn);
  if (!symbol) throw new Error('symbol is required');
  const cacheKey = `fin:${CACHE_VERSION}:${symbol}`;
  if (env.CACHE) {
    try { const hit = await env.CACHE.get(cacheKey, 'json'); if (hit) return { ...hit, cached: true }; } catch {}
  }
  const sec = new Sec(env);
  const t = await findTicker(sec, symbol);
  if (!t) throw new Error(`Ticker ${symbol} not found in SEC list (US filers only)`);
  const [meta, fields] = await Promise.all([
    getSubmissionsMeta(sec, t.cik),
    pool(Object.entries(FIELDS), 4, ([name, spec]) => fetchField(sec, t.cik, name, spec)),
  ]);
  const F = Object.fromEntries(fields.map((f) => [f.name, f]));
  if (!F.revenue.series && !F.net_income.series) throw new Error(`No XBRL financials for ${symbol}`);
  const { rows } = buildRows(F);
  const out = {
    symbol: t.ticker,
    cik: t.cik,
    name: t.name,
    exchange: t.exchange,
    fiscal_year_end: meta.fiscal_year_end ?? null,
    source: 'SEC EDGAR XBRL',
    tags: Object.fromEntries(fields.filter((f) => f.tag).map((f) => [f.name, f.tag])),
    fetched_at: new Date().toISOString(),
    rows,
  };
  if (env.CACHE) {
    try { await env.CACHE.put(cacheKey, JSON.stringify(out), { expirationTtl: 43200 }); } catch {}
  }
  return out;
}

async function getScreen(env) {
  // 1) KV key "screen" (uploaded by refresh.sh from your Mac)  2) SCREEN_URL (GitHub Action), if set
  if (env.CACHE) {
    const kv = await env.CACHE.get('screen', 'json').catch(() => null);
    if (kv && Array.isArray(kv.rows)) return kv;
  }
  if (!env.SCREEN_URL || env.SCREEN_URL.includes('<your-github-user>')) throw new Error('No screen yet: run ./refresh.sh on your Mac (or set up the GitHub Action)');
  const res = await fetch(env.SCREEN_URL, { headers: { Accept: 'application/json' }, cf: { cacheTtl: 300 } });
  if (!res.ok) throw new Error(`Screen file HTTP ${res.status} (has the GitHub Action run yet?)`);
  const data = await res.json();
  if (!Array.isArray(data.rows)) throw new Error('Screen file has no rows');
  return data;
}

// Full universe (~3,600 rows) is passed through as text to keep CPU low on the free plan.
async function getUniverseText(env) {
  if (!env.SCREEN_URL || env.SCREEN_URL.includes('<your-github-user>')) throw new Error('SCREEN_URL is not set');
  const url = env.SCREEN_URL.replace(/screen\.json$/, 'universe.json');
  const res = await fetch(url, { headers: { Accept: 'application/json' }, cf: { cacheTtl: 300 } });
  if (!res.ok) throw new Error(`Universe file HTTP ${res.status} (has the GitHub Action run yet?)`);
  return res.text();
}

const TOOLS = [
  {
    name: 'get_universe',
    description: 'Every profitable US stock (market cap >= $50M) with bucket, price, market_cap, pe, net_margin, sales_g1/g3/g5 and profit_g1/g3/g5 (yearly growth, CAGR for 3Y/5Y), de (borrowings / equity, leases excluded) and fy_end. Rebuilt each weekday. For custom screens.',
    inputSchema: { type: 'object', properties: {} },
  },
  {
    name: 'get_screen',
    description: 'Daily screen of US stocks: top 15 per market-cap bucket (Mega, Large, Mid, Small, Micro) with the highest P/E among profitable, growing companies (net margin >= 3%, sales growth >= 5%, profit growth > 0, P/E <= 200). Rows: bucket, rank, symbol, name, sector, industry, price, market_cap, pe, net_income, revenue, net_margin, sales_growth, profit_growth, fy_end.',
    inputSchema: { type: 'object', properties: {} },
  },
  {
    name: 'get_financials',
    description: 'Annual (last ~11 FY) and quarterly (last ~24 Q) financials for a US SEC filer from EDGAR XBRL. Quarters are single 3-month values (YTD differences resolved, Q4 = FY - 9M). capex is positive. borrowings excludes leases; debt_total = borrowings + leases.',
    inputSchema: { type: 'object', properties: { symbol: { type: 'string', description: 'US ticker, e.g. LULU, BRK.B' } }, required: ['symbol'] },
  },
  {
    name: 'lookup_company',
    description: 'Resolve a US ticker to SEC CIK, name, exchange, SIC code/description and fiscal year end.',
    inputSchema: { type: 'object', properties: { symbol: { type: 'string' } }, required: ['symbol'] },
  },
];

const PROTOCOLS = ['2025-11-25', '2025-06-18', '2025-03-26', '2024-11-05'];
const ok = (id, result) => ({ jsonrpc: '2.0', id, result });
const fail = (id, code, message) => ({ jsonrpc: '2.0', id, error: { code, message } });

async function handleRpc(msg, env) {
  if (!msg || msg.jsonrpc !== '2.0' || typeof msg.method !== 'string') return fail(msg?.id ?? null, -32600, 'Invalid Request');
  const { id, method, params } = msg;
  if (id === undefined || id === null) return null; // notification
  switch (method) {
    case 'initialize':
      return ok(id, {
        protocolVersion: PROTOCOLS.includes(params?.protocolVersion) ? params.protocolVersion : PROTOCOLS[1],
        capabilities: { tools: { listChanged: false } },
        serverInfo: { name: 'sec-edgar-mcp', version: '2.0.0' },
      });
    case 'ping':
      return ok(id, {});
    case 'tools/list':
      return ok(id, { tools: TOOLS });
    case 'tools/call': {
      const name = params?.name;
      const args = params?.arguments ?? {};
      try {
        let data;
        if (name === 'get_universe') return ok(id, { content: [{ type: 'text', text: await getUniverseText(env) }] });
        if (name === 'get_screen') data = await getScreen(env);
        else if (name === 'get_financials') data = await getFinancials(env, args.symbol);
        else if (name === 'lookup_company') data = await lookupCompany(env, args.symbol);
        else return fail(id, -32602, `Unknown tool: ${name}`);
        return ok(id, { content: [{ type: 'text', text: JSON.stringify(data) }], structuredContent: data });
      } catch (e) {
        return ok(id, { content: [{ type: 'text', text: `Error: ${e.message}` }], isError: true });
      }
    }
    default:
      return fail(id, -32601, `Method not found: ${method}`);
  }
}

function tokenOk(given, env) {
  const want = env.ACCESS_TOKEN || '';
  if (!want || !given || given.length !== want.length) return false;
  let diff = 0;
  for (let i = 0; i < want.length; i++) diff |= want.charCodeAt(i) ^ given.charCodeAt(i);
  return diff === 0;
}

const json = (body, status = 200, headers = {}) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...headers } });

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const parts = url.pathname.split('/').filter(Boolean);

    if (url.pathname === '/health') return json({ ok: true });

    if (parts[0] === 'api' && tokenOk(parts[1], env) && request.method === 'GET') {
      try {
        const symbol = url.searchParams.get('symbol');
        if (parts[2] === 'financials') return json(await getFinancials(env, symbol));
        if (parts[2] === 'screen') return json(await getScreen(env));
        if (parts[2] === 'universe') return new Response(await getUniverseText(env), { headers: { 'Content-Type': 'application/json' } });
        if (parts[2] === 'lookup') return json(await lookupCompany(env, symbol));
      } catch (e) {
        return json({ error: e.message }, 400);
      }
      return json({ error: 'not found' }, 404);
    }

    if (parts[0] !== 'mcp' || parts.length !== 2 || !tokenOk(parts[1], env)) return json({ error: 'not found' }, 404);

    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405, headers: { Allow: 'POST' } });

    let body;
    try { body = await request.json(); } catch { return json(fail(null, -32700, 'Parse error'), 400); }

    if (Array.isArray(body)) {
      const out = (await Promise.all(body.map((m) => handleRpc(m, env)))).filter(Boolean);
      return out.length ? json(out) : new Response(null, { status: 202 });
    }
    const out = await handleRpc(body, env);
    return out ? json(out) : new Response(null, { status: 202 });
  },
};
