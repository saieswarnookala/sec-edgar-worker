// Opening-range breakout on "stocks in play" (Zarattini, Barbon & Aziz 2024 style). Research only, no orders.
// Universe: CURRENT S&P 500 (data/sp500_tickers.json) -> survivorship bias. Alpaca SIP 5-min + daily bars.
// Filters (prior 14 days): open > $5, avg daily volume >= 1M, ATR14 > $0.50.
// Stocks in play: top 20 by relative volume of the 9:30-9:35 bar vs its own 14-day average (>= 1x).
// Green first bar -> buy stop at its high; red -> sell-short stop at its low ("long" version skips shorts).
// Stop = 10% of ATR14 from the fill. Exit at the close. Risk 1% of equity per trade, max 4x leverage (20 slots).
// Costs: $0.0035/share commission + 1bp slippage per side. Entry and stop in the same 5-min bar = stopped (conservative).
import { writeFileSync, readFileSync, mkdirSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

export const COMM = 0.0035, SLIP = 0.0001, RISK = 0.01, LEV = 4, TOP = 20;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const fmt = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
export function et(t) { const o = Object.fromEntries(fmt.formatToParts(new Date(t)).map((x) => [x.type, x.value])); return { d: `${o.year}-${o.month}-${o.day}`, m: (+o.hour % 24) * 60 + +o.minute }; }

// One trade on one day. bs = regular-session 5-min bars [{o,h,l,c}], bs[0] = opening bar.
// Returns null (no entry) or {dir, fill, exit, shares, pnl}.
export function tradeDay(bs, atr, equity) {
  const f = bs[0]; const dir = f.c > f.o ? 1 : f.c < f.o ? -1 : 0; if (!dir) return null;
  const lvl = dir > 0 ? f.h : f.l, sd = 0.1 * atr;
  let fill = null, exit = null;
  for (let i = 1; i < bs.length && exit == null; i++) {
    const b = bs[i];
    if (fill == null) {
      if (dir > 0 ? b.h < lvl : b.l > lvl) continue;
      fill = dir > 0 ? Math.max(lvl, b.o) : Math.min(lvl, b.o);
      const st = fill - dir * sd;
      if (dir > 0 ? b.l <= st : b.h >= st) exit = st;
      continue;
    }
    const st = fill - dir * sd;
    if (dir > 0 ? b.l <= st : b.h >= st) exit = dir > 0 ? Math.min(st, b.o) : Math.max(st, b.o);
  }
  if (fill == null) return null;
  if (exit == null) exit = bs[bs.length - 1].c;
  const shares = Math.floor(Math.min(equity * RISK / sd, equity * LEV / TOP / fill));
  if (shares < 1) return null;
  const pnl = dir * (exit - fill) * shares - 2 * COMM * shares - SLIP * (fill + exit) * shares;
  return { dir, fill, exit, shares, pnl };
}

export function stats(cv) {
  let pk = 0, dd = 0; for (const [, e] of cv) { pk = Math.max(pk, e); dd = Math.max(dd, 1 - e / pk); }
  const yrs = (Date.parse(cv.at(-1)[0]) - Date.parse(cv[0][0])) / 31557600000;
  const ye = {}; for (const [d, e] of cv) ye[d.slice(0, 4)] = e;
  let prev = cv[0][1]; const yearly = Object.entries(ye).map(([y, e]) => { const r = e / prev - 1; prev = e; return { year: +y, ret: +(r * 100).toFixed(2) }; });
  const rets = cv.slice(1).map(([, e], i) => e / cv[i][1] - 1); const mu = rets.reduce((a, b) => a + b, 0) / rets.length;
  const sdv = Math.sqrt(rets.reduce((a, b) => a + (b - mu) ** 2, 0) / rets.length);
  const tot = cv.at(-1)[1] / cv[0][1];
  return { start: cv[0][0], end: cv.at(-1)[0], cagr: +((tot ** (1 / yrs) - 1) * 100).toFixed(2), total: +((tot - 1) * 100).toFixed(2), max_dd: +(dd * 100).toFixed(2), sharpe: +(mu / sdv * Math.sqrt(252)).toFixed(2), yearly };
}

async function main(OUT) {
  const START = process.env.ORB_START || '2021-01-01';
  const H = { 'APCA-API-KEY-ID': process.env.APCA_API_KEY_ID, 'APCA-API-SECRET-KEY': process.env.APCA_API_SECRET_KEY };
  const NOW = new Date(Date.now() - 3600e3).toISOString();
  let reqs = 0;
  async function bars(symbols, tf, start, end) {
    const out = {};
    for (let i = 0; i < symbols.length; i += 100) {
      let token = null;
      do {
        const p = new URLSearchParams({ symbols: symbols.slice(i, i + 100).join(','), timeframe: tf, start, end, limit: '10000', adjustment: 'split', feed: 'sip' });
        if (token) p.set('page_token', token);
        let j = null;
        for (let a = 0; a < 5 && !j; a++) {
          const r = await fetch('https://data.alpaca.markets/v2/stocks/bars?' + p, { headers: H }); reqs++;
          if (r.ok) j = await r.json(); else { const t = await r.text(); if (a === 4) throw new Error(`alpaca ${r.status} ${t}`); await sleep(3000 * (a + 1)); }
        }
        for (const [s, arr] of Object.entries(j.bars || {})) (out[s] ||= []).push(...arr);
        token = j.next_page_token; await sleep(320);
      } while (token);
    }
    return out;
  }
  mkdirSync(OUT, { recursive: true });
  const syms = JSON.parse(readFileSync('data/sp500_tickers.json', 'utf8')).tickers.map((t) => t.symbol);
  const pre = new Date(Date.parse(START) - 45 * 86400e3).toISOString().slice(0, 10) + 'T00:00:00Z';
  const daily = await bars([...syms, 'SPY'], '1Day', pre, NOW);
  console.log('daily symbols', Object.keys(daily).length, 'reqs', reqs);
  const info = {};
  for (const s of syms) {
    const a = daily[s]; if (!a) continue;
    for (let i = 15; i < a.length; i++) {
      let tr = 0, v = 0;
      for (let k = i - 14; k < i; k++) { tr += Math.max(a[k].h - a[k].l, Math.abs(a[k].h - a[k - 1].c), Math.abs(a[k].l - a[k - 1].c)); v += a[k].v; }
      (info[et(a[i].t).d] ||= {})[s] = { atr: tr / 14, vol: v / 14 };
    }
  }
  const firstVols = {};
  const V = { both: { eq: 1, curve: [], trades: 0, wins: 0, longs: 0, shorts: 0, sumR: 0 }, long: { eq: 1, curve: [], trades: 0, wins: 0, longs: 0, shorts: 0, sumR: 0 } };
  const sample = [];
  for (let m0 = new Date(START + 'T00:00:00Z'); m0.toISOString() < NOW;) {
    const m1 = new Date(Date.UTC(m0.getUTCFullYear(), m0.getUTCMonth() + 1, 1));
    const raw = await bars(syms, '5Min', m0.toISOString(), m1.toISOString() < NOW ? m1.toISOString() : NOW);
    const byDay = {};
    for (const [s, arr] of Object.entries(raw)) for (const b of arr) { const e = et(b.t); if (e.m < 570 || e.m >= 960) continue; ((byDay[e.d] ||= {})[s] ||= []).push(b); }
    for (const d of Object.keys(byDay).sort()) {
      const cands = [];
      for (const [s, bs] of Object.entries(byDay[d])) {
        const f = bs[0]; if (et(f.t).m !== 570) continue;
        const h = (firstVols[s] ||= []); const avg = h.length >= 14 ? h.slice(-14).reduce((x, y) => x + y, 0) / 14 : null;
        h.push(f.v); if (h.length > 14) h.shift();
        const inf = info[d]?.[s]; if (!avg || !inf || f.o <= 5 || inf.vol < 1e6 || inf.atr <= 0.5 || f.c === f.o) continue;
        const rv = f.v / avg; if (rv >= 1) cands.push({ s, rv, bs, atr: inf.atr });
      }
      cands.sort((a, b) => b.rv - a.rv);
      for (const [vn, X] of Object.entries(V)) {
        const eq0 = X.eq * 25000; let pnl = 0;
        for (const c of cands.slice(0, TOP)) {
          if (vn === 'long' && c.bs[0].c < c.bs[0].o) continue;
          const t = tradeDay(c.bs, c.atr, eq0); if (!t) continue;
          pnl += t.pnl; X.trades++; if (t.pnl > 0) X.wins++; t.dir > 0 ? X.longs++ : X.shorts++;
          X.sumR += t.pnl / (t.shares * 0.1 * c.atr);
          if (vn === 'both' && sample.length < 300 && Math.random() < 0.02) sample.push({ d, s: c.s, rv: +c.rv.toFixed(1), ...t, pnl: +t.pnl.toFixed(2) });
        }
        X.eq *= 1 + pnl / eq0; X.curve.push([d, X.eq]);
      }
    }
    console.log(m0.toISOString().slice(0, 7), 'both', V.both.eq.toFixed(3), 'long', V.long.eq.toFixed(3), 'reqs', reqs);
    m0 = m1;
  }
  const first = V.both.curve[0][0];
  const spyA = daily.SPY.map((b) => [et(b.t).d, b.c]).filter(([d]) => d >= first);
  const res = { generated: new Date().toISOString(), start_input: START, universe: `current S&P 500 (${syms.length}), survivorship bias`, rules: 'see header of scripts/build-orb.mjs', versions: {}, sample_trades: sample };
  for (const [k, X] of Object.entries(V)) res.versions[k] = { ...stats(X.curve), trades: X.trades, win_rate: +(100 * X.wins / X.trades).toFixed(1), avg_R: +(X.sumR / X.trades).toFixed(3), longs: X.longs, shorts: X.shorts };
  res.versions.spy = stats(spyA.map(([d, c]) => [d, c / spyA[0][1]]));
  writeFileSync(`${OUT}/orb.json`, JSON.stringify(res, null, 1));
  console.log(JSON.stringify(res.versions, (k, v) => (k === 'yearly' ? undefined : v), 1));
}
if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  main(process.argv[2] || 'data').catch((e) => { console.error(e); try { mkdirSync(process.argv[2] || 'data', { recursive: true }); writeFileSync(`${process.argv[2] || 'data'}/orb_error.txt`, String(e.stack || e)); } catch {} process.exit(1); });
}
