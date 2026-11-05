// Funding-rate (cash-and-carry) arbitrage backtest. Research only, no orders. Not financial advice.
// Long spot coin + short same-size USDT perpetual on Binance -> price moves cancel; collect funding (paid by longs when rate > 0).
// Data: Binance public archive data.binance.vision (monthly fundingRate CSVs). Benchmark: T-bills (BIL via Alpaca, if keys).
// Capital efficiency E: 0.5 = half capital in spot, half as USDT margin for a 1x short (safe); 1.0 = spot used as collateral (portfolio margin).
// Costs: entering or exiting a hedged position = 0.15% of notional (spot 0.10% + perp 0.05%). Cash earns 0 when off (see T-bill column).
// Ignores: basis noise at entry/exit, exchange failure risk, borrow/transfer costs, taxes.
import { writeFileSync, mkdirSync, existsSync, readFileSync } from 'node:fs';
import { execSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';
export const COINS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'DOGEUSDT'], SIDE_COST = 0.0015;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export function parseFunding(csv) { // -> [{t, r}]
  const out = [];
  for (const line of csv.split(/\r?\n/)) { const c = line.split(','); if (c.length < 2 || !/^\d{12,}/.test(c[0])) continue; out.push({ t: +c[0], r: +c[c.length - 1] }); }
  return out;
}
export function toDaily(rows) { const d = {}; for (const x of rows) { const k = new Date(x.t).toISOString().slice(0, 10); d[k] = (d[k] || 0) + x.r; } return d; }

// daily: {date: summed funding rate}. dates: sorted list. Returns daily portfolio returns [[date, ret, on]].
// mode 'always' | 'filter'. filter: on when trailing LB-day avg annualized funding > th, off when it drops below th/2 (hysteresis).
export function simulate(dates, daily, { E = 0.5, mode = 'always', th = 0.1, lb = 7 } = {}) {
  let on = false; const out = [], hist = [];
  for (const d of dates) {
    const f = daily[d]; if (f == null) { out.push([d, 0, on]); continue; }
    let r = 0;
    if (on) r += E * f;                                    // earn today's funding if positioned
    hist.push(f); if (hist.length > lb) hist.shift();
    const ann = (hist.reduce((a, b) => a + b, 0) / hist.length) * 365;
    const want = mode === 'always' ? true : on ? ann > th / 2 : hist.length >= lb && ann > th;
    if (want !== on) { r -= E * SIDE_COST; on = want; }
    out.push([d, r, on]);
  }
  return out;
}
// rotation: each day hold the coin with highest trailing avg funding if above th; switching coins costs 2 sides.
export function rotate(dates, dailyBy, { E = 0.5, th = 0.1, lb = 7 } = {}) {
  let cur = null; const hist = {}, out = [];
  for (const d of dates) {
    let r = 0; if (cur && dailyBy[cur][d] != null) r += E * dailyBy[cur][d];
    let best = null, bestAnn = -1e9;
    for (const [c, dd] of Object.entries(dailyBy)) { const f = dd[d]; if (f == null) continue; (hist[c] ||= []).push(f); if (hist[c].length > lb) hist[c].shift();
      if (hist[c].length < lb) continue; const ann = (hist[c].reduce((a, b) => a + b, 0) / lb) * 365; if (ann > bestAnn) { bestAnn = ann; best = c; } }
    let want = best && bestAnn > th ? best : null;
    if (cur && want !== cur) { const curAnn = hist[cur] ? (hist[cur].reduce((a, b) => a + b, 0) / hist[cur].length) * 365 : -1; if (curAnn > th / 2 && (!want || bestAnn < curAnn * 1.5)) want = cur; }
    if (want !== cur) { if (cur) r -= E * SIDE_COST; if (want) r -= E * SIDE_COST; cur = want; }
    out.push([d, r, cur]);
  }
  return out;
}
export function stats(rets) {
  let e = 1, pk = 1, dd = 0; const yr = {}, mo = {};
  for (const [d, r] of rets) { e *= 1 + r; pk = Math.max(pk, e); dd = Math.max(dd, 1 - e / pk); yr[d.slice(0, 4)] = (yr[d.slice(0, 4)] ?? 1) * (1 + r); mo[d.slice(0, 7)] = (mo[d.slice(0, 7)] ?? 1) * (1 + r); }
  const yrs = Math.max(rets.length / 365, 1 / 365), m = Object.values(mo);
  return { cagr: +((e ** (1 / yrs) - 1) * 100).toFixed(2), total: +((e - 1) * 100).toFixed(1), max_dd: +(dd * 100).toFixed(2),
    worst_month: +((Math.min(...m) - 1) * 100).toFixed(2), neg_months_pct: +(100 * m.filter((x) => x < 1).length / m.length).toFixed(1),
    days_on_pct: +(100 * rets.filter((x) => x[2]).length / rets.length).toFixed(1), yearly: Object.fromEntries(Object.entries(yr).map(([k, v]) => [k, +((v - 1) * 100).toFixed(2)])) };
}

async function fetchBuf(url, tries = 5) {
  for (let a = 0; ; a++) { try { const r = await fetch(url); if (r.status === 404) return null; if (r.ok) return Buffer.from(await r.arrayBuffer()); if (a >= tries) throw new Error(`${r.status} ${url}`); } catch (e) { if (a >= tries) throw e; } await sleep(1000 * 2 ** a); }
}
async function loadCoin(sym, log) {
  const rows = []; const now = new Date(); let miss = 0;
  for (let y = 2019; y <= now.getUTCFullYear(); y++) for (let m = 1; m <= 12; m++) {
    if (Date.UTC(y, m - 1) >= Date.UTC(now.getUTCFullYear(), now.getUTCMonth())) break;
    const ym = `${y}-${String(m).padStart(2, '0')}`, buf = await fetchBuf(`https://data.binance.vision/data/futures/um/monthly/fundingRate/${sym}/${sym}-fundingRate-${ym}.zip`);
    if (!buf) { miss++; continue; }
    writeFileSync('/tmp/f.zip', buf); rows.push(...parseFunding(execSync('unzip -p /tmp/f.zip').toString()));
  }
  // current month from the public API (may be geo-blocked; fine if it fails)
  try { const st = Date.UTC(now.getUTCFullYear(), now.getUTCMonth()); const r = await fetch(`https://fapi.binance.com/fapi/v1/fundingRate?symbol=${sym}&startTime=${st}&limit=1000`);
    if (r.ok) for (const x of await r.json()) rows.push({ t: +x.fundingTime, r: +x.fundingRate }); } catch {}
  const seen = new Set(), uniq = rows.filter((x) => (seen.has(x.t) ? false : seen.add(x.t))).sort((a, b) => a.t - b.t);
  log(sym, 'funding prints', uniq.length, 'from', uniq[0] && new Date(uniq[0].t).toISOString().slice(0, 10), 'missing months', miss);
  return uniq;
}
async function tbills(start, log) {
  if (!process.env.APCA_API_KEY_ID) return null;
  try { const H = { 'APCA-API-KEY-ID': process.env.APCA_API_KEY_ID, 'APCA-API-SECRET-KEY': process.env.APCA_API_SECRET_KEY };
    const p = new URLSearchParams({ symbols: 'BIL', timeframe: '1Day', start, end: new Date(Date.now() - 3600e3).toISOString(), adjustment: 'all', feed: 'sip', limit: '10000' });
    let bars = [], tok = null; do { if (tok) p.set('page_token', tok); const j = await (await fetch('https://data.alpaca.markets/v2/stocks/bars?' + p, { headers: H })).json(); bars.push(...(j.bars?.BIL || [])); tok = j.next_page_token; } while (tok);
    const out = bars.slice(1).map((b, i) => [b.t.slice(0, 10), b.c / bars[i].c - 1, true]); return out;
  } catch (e) { log('BIL failed', e.message); return null; }
}
async function main(outDir = 'data', log = console.log) {
  const dailyBy = {}, raw = {};
  for (const c of COINS) { const rows = await loadCoin(c, log); if (rows.length) { raw[c] = rows; dailyBy[c] = toDaily(rows); } }
  if (!dailyBy.BTCUSDT) throw new Error('no BTC funding data (archive blocked?)');
  const all = [...new Set(Object.values(dailyBy).flatMap((d) => Object.keys(d)))].sort();
  const res = { generated: new Date().toISOString(), notes: ['Long spot + short perp, Binance USDT-M funding.', 'E=0.5: half capital as 1x short margin; E=1.0: spot as collateral (portfolio margin, more risk).', 'Costs 0.15% of notional per side. Off = cash at 0%; compare with T-bills.', 'Ignores exchange-failure risk (e.g. FTX), basis noise, taxes.'], coins: {}, rotation: {}, tbills: null };
  for (const [c, d] of Object.entries(dailyBy)) {
    const dates = all.filter((x) => x >= Object.keys(d).sort()[0]), fr = raw[c].map((x) => x.r);
    const info = { start: dates[0], prints: fr.length, avg_annual_funding_pct: +((Object.values(d).reduce((a, b) => a + b, 0) / Object.keys(d).length) * 365 * 100).toFixed(2), negative_prints_pct: +(100 * fr.filter((x) => x < 0).length / fr.length).toFixed(1), versions: {} };
    for (const E of [0.5, 1]) { info.versions[`always_E${E}`] = stats(simulate(dates, d, { E, mode: 'always' }));
      for (const th of [0.05, 0.1, 0.2]) info.versions[`filter${th * 100}_E${E}`] = stats(simulate(dates, d, { E, mode: 'filter', th })); }
    res.coins[c] = info;
  }
  const rotDates = all.filter((x) => x >= '2021-01-01');
  for (const E of [0.5, 1]) for (const th of [0.05, 0.1, 0.2]) res.rotation[`rot${th * 100}_E${E}`] = stats(rotate(rotDates, dailyBy, { E, th }));
  const bil = await tbills('2019-09-01', log);
  if (bil) { res.tbills = stats(bil); res.tbills_from_2021 = stats(bil.filter(([d]) => d >= '2021-01-01')); }
  mkdirSync(outDir, { recursive: true }); writeFileSync(`${outDir}/funding_arb.json`, JSON.stringify(res, null, 1));
  for (const [c, i] of Object.entries(res.coins)) { log(`\n== ${c} from ${i.start}: avg funding ${i.avg_annual_funding_pct}%/yr, negative ${i.negative_prints_pct}% of prints`);
    for (const [k, v] of Object.entries(i.versions)) log('  ', k.padEnd(14), 'cagr', v.cagr, 'dd', v.max_dd, 'worst mo', v.worst_month, 'on', v.days_on_pct, JSON.stringify(v.yearly)); }
  for (const [k, v] of Object.entries(res.rotation)) log('ROT', k, 'cagr', v.cagr, 'dd', v.max_dd, JSON.stringify(v.yearly));
  if (res.tbills) log('T-BILLS (BIL)', res.tbills.cagr, JSON.stringify(res.tbills.yearly));
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main(process.argv[2] || 'data').catch((e) => { console.error(e); try { mkdirSync('data', { recursive: true }); writeFileSync('data/funding_arb_error.txt', String(e.stack || e)); } catch {} process.exit(1); });
