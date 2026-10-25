// Live data for the Stock analysis tab, returned in the same shapes the dashboard page expects.
import { getFinancials, lookupCompany, secListing } from '../../src/worker.js';

const DAY = 86400;
async function cached(request, ctx, ttl, make) {
  const key = new Request(new URL(request.url).toString(), { method: 'GET' });
  const cache = caches.default;
  const hit = await cache.match(key);
  if (hit) return hit;
  const res = await make();
  if (res.ok) { const copy = new Response(res.clone().body, res); copy.headers.set('Cache-Control', `public, max-age=${ttl}`); ctx.waitUntil(cache.put(key, copy)); }
  return res;
}
const json = (x, status = 200) => new Response(JSON.stringify(x), { status, headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' } });
const text = (x, status = 200) => new Response(x, { status, headers: { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' } });
const SYM_RE = /^[A-Z][A-Z0-9.\-]{0,9}$/;

// company: SEC ticker list -> rows shaped like a symbol search
async function company(env, symbol) {
  const t = await secListing(env, symbol);
  if (!t) return [];
  const ex = String(t.exchange || '').toLowerCase();
  const [exchange, mic] = ex === 'nasdaq' ? ['NASDAQ', 'XNGS'] : ex === 'nyse' ? ['NYSE', 'XNYS'] : [t.exchange || 'OTC', 'OTC'];
  return [{ symbol: t.ticker.replace(/-/g, '.'), instrument_name: t.name, exchange, mic_code: mic, country: 'United States', currency: 'USD', instrument_type: 'Common Stock' }];
}

// prices: Alpaca daily bars (split + dividend adjusted) as "datetime;open;high;low;close;volume", newest first
async function prices(env, symbol) {
  if (!env.APCA_API_KEY_ID || !env.APCA_API_SECRET_KEY) throw new Error('Price data is not configured (Alpaca keys missing).');
  const end = new Date(Date.now() - 3600e3).toISOString();
  const p = new URLSearchParams({ symbols: symbol, timeframe: '1Day', start: '2000-01-01', end, limit: '10000', adjustment: 'all', feed: 'sip' });
  const bars = [];
  for (let page = 0; page < 3; page++) {
    const r = await fetch('https://data.alpaca.markets/v2/stocks/bars?' + p, { headers: { 'APCA-API-KEY-ID': env.APCA_API_KEY_ID, 'APCA-API-SECRET-KEY': env.APCA_API_SECRET_KEY } });
    if (!r.ok) throw new Error(`Alpaca HTTP ${r.status}`);
    const js = await r.json();
    for (const b of (js.bars && js.bars[symbol]) || []) bars.push(b);
    if (!js.next_page_token) break;
    p.set('page_token', js.next_page_token);
  }
  if (!bars.length) throw new Error(`No prices found for ${symbol}`);
  bars.sort((a, b) => (a.t < b.t ? 1 : -1));
  return ['datetime;open;high;low;close;volume', ...bars.map((b) => [b.t.slice(0, 10), b.o, b.h, b.l, b.c, b.v].join(';'))].join('\n');
}

// profile: FMP company profile when a key is set, else SEC registration details
async function profile(env, symbol) {
  if (env.FMP_API_KEY) {
    try {
      const r = await fetch(`https://financialmodelingprep.com/stable/profile?symbol=${encodeURIComponent(symbol)}&apikey=${env.FMP_API_KEY}`);
      if (r.ok) { const js = await r.json(); if (Array.isArray(js) && js.length) return js; }
    } catch {}
  }
  const c = await lookupCompany(env, symbol);
  return [{ symbol: c.symbol, companyName: c.name, description: '', industry: c.sic_description || '', sector: '', website: c.website || null }];
}

export async function handleData(request, env, ctx, kind) {
  const url = new URL(request.url);
  const symbol = String(url.searchParams.get('symbol') || '').trim().toUpperCase();
  if (!SYM_RE.test(symbol)) return json({ error: 'Invalid ticker' }, 400);
  const secSym = symbol.replace(/\./g, '-');
  try {
    if (kind === 'company') return await cached(request, ctx, DAY, async () => json(await company(env, secSym)));
    if (kind === 'prices') return await cached(request, ctx, 6 * 3600, async () => text(await prices(env, symbol)));
    if (kind === 'profile') return await cached(request, ctx, 7 * DAY, async () => json(await profile(env, secSym)));
    if (kind === 'statements') return json(await getFinancials(env, secSym));
  } catch (e) {
    return json({ error: String(e && e.message || e).slice(0, 300) }, 502);
  }
  return json({ error: 'Unknown data feed' }, 404);
}
