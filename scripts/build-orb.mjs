// Opening-range breakout on "stocks in play" (Zarattini, Barbon & Aziz 2024 style). Research only, no orders.
// Universe: current S&P 500 (data/sp500_tickers.json) -> survivorship bias. Alpaca SIP 5-min + daily bars.
// Daily: price>$5, 14d avg vol>=1M, ATR14>$0.50. Pick top 20 by relative volume of the 9:30 5-min bar (>=1x its 14-day avg).
// Green first bar -> buy stop at its high; red -> short stop at its low (long-only version skips shorts).
// Stop = 10% of ATR14 from fill. Exit at the close. Risk 1% of equity per trade, max 4x total leverage.
// Costs: $0.0035/share + 1bp slippage per side. Same-bar entry+stop counts as stopped (conservative).
import { writeFileSync, readFileSync, mkdirSync } from 'node:fs';
const OUT = process.argv[2] || 'data';
const START = process.env.ORB_START || '2021-01-01';
const env = process.env, H = { 'APCA-API-KEY-ID': env.APCA_API_KEY_ID, 'APCA-API-SECRET-KEY': env.APCA_API_SECRET_KEY };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
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
        if (r.ok) j = await r.json(); else { if (a === 4) throw new Error(`alpaca ${r.status} ${await r.text()}`); await sleep(3000 * (a + 1)); }
      }
      for (const [s, arr] of Object.entries(j.bars || {})) (out[s] ||= []).push(...arr);
      token = j.next_page_token; await sleep(330);
    } while (token);
  }
  return out;
}
const fmt = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
function et(t) { const o = Object.fromEntries(fmt.formatToParts(new Date(t)).map((x) => [x.type, x.value])); return { d: `${o.year}-${o.month}-${o.day}`, m: (+o.hour % 24) * 60 + +o.minute }; }
const COMM = 0.0035, SLIP = 0.0001, RISK = 0.01, LEV = 4, TOP = 20;

async function main() {
  mkdirSync(OUT, { recursive: true });
  let syms = JSON.parse(readFileSync('data/sp500_tickers.json', 'utf8')); syms = syms.map((x) => (x.symbol || x).replace('.', '-').replace('-', '.'));
  const pre = new Date(Date.parse(START) - 40 * 86400e3).toISOString().slice(0, 10);
  const daily = await bars([...syms, 'SPY'], '1Day', pre, NOW);
  console.log('daily symbols', Object.keys(daily).length, 'reqs', reqs);
  // per symbol per date: ATR14, avgVol14 (prior days)
  const info = {}; // info[d][sym] = {atr, vol}
  for (const s of syms) {
    const a = daily[s]; if (!a) continue;
    for (let i = 15; i < a.length; i++) {
      let tr = 0, v = 0;
      for (let k = i - 14; k < i; k++) { tr += Math.max(a[k].h - a[k].l, Math.abs(a[k].h - a[k - 1].c), Math.abs(a[k].l - a[k - 1].c)); v += a[k].v; }
      const d = et(a[i].t).d; (info[d] ||= {})[s] = { atr: tr / 14, vol: v / 14 };
    }
  }
  const first = {}; // first[sym] = array of prior 9:30 bar volumes
  const versions = { both: { eq: 1, curve: [], trades: 0, wins: 0, longs: 0, shorts: 0 }, long: { eq: 1, curve: [], trades: 0, wins: 0, longs: 0, shorts: 0 } };
  let m0 = new Date(START + 'T00:00:00Z');
  while (m0.toISOString() < NOW) {
    const m1 = new Date(Date.UTC(m0.getUTCFullYear(), m0.getUTCMonth() + 1, 1));
    const end = m1.toISOString() < NOW ? m1.toISOString() : NOW;
    const raw = await bars(syms, '5Min', m0.toISOString(), end);
    const byDay = {}; // byDay[d][sym] = regular-session bars
    for (const [s, arr] of Object.entries(raw)) for (const b of arr) { const e = et(b.t); if (e.m < 570 || e.m >= 960) continue; ((byDay[e.d] ||= {})[s] ||= []).push(b); }
    for (const d of Object.keys(byDay).sort()) {
      const cands = [];
      for (const [s, bs] of Object.entries(byDay[d])) {
        const f = bs[0]; if (et(f.t).m !== 570) continue;
        const hist = (first[s] ||= []); const avg = hist.length >= 14 ? hist.slice(-14).reduce((x, y) => x + y, 0) / 14 : null; hist.push(f.v); if (hist.length > 20) hist.shift();
        const inf = info[d]?.[s]; if (!avg || !inf || f.o <= 5 || inf.vol < 1e6 || inf.atr <= 0.5) continue;
        const rv = f.v / avg; if (rv < 1 || f.c === f.o) continue;
        cands.push({ s, rv, dir: f.c > f.o ? 1 : -1, f, bs, atr: inf.atr });
      }
      cands.sort((a, b) => b.rv - a.rv);
      const pick = cands.slice(0, TOP);
      for (const [vn, V] of Object.entries(versions)) {
        let pnl = 0;
        for (const c of pick) {
          if (vn === 'long' && c.dir < 0) continue;
          const lvl = c.dir > 0 ? c.f.h : c.f.l, sd = 0.1 * c.atr;
          let fill = null, exit = null;
          for (let i = 1; i < c.bs.length; i++) {
            const b = c.bs[i];
            if (fill == null) {
              if (c.dir > 0 ? b.h >= lvl : b.l <= lvl) { fill = c.dir > 0 ? Math.max(lvl, b.o) : Math.min(lvl, b.o); const st = fill - c.dir * sd; if (c.dir > 0 ? b.l <= st : b.h >= st) { exit = st; break; } }
              continue;
            }
            const st = fill - c.dir * sd;
            if (c.dir > 0 ? b.l <= st : b.h >= st) { exit = c.dir > 0 ? Math.min(st, b.o) : Math.max(st, b.o); break; }
          }
          if (fill == null) continue;
          if (exit == null) exit = c.bs[c.bs.length - 1].c;
          const sh = Math.floor(Math.min(V.eq * 1e5 * RISK / sd, V.eq * 1e5 * LEV / TOP / fill));
          if (sh < 1) continue;
          const g = c.dir * (exit - fill) * sh - 2 * COMM * sh - SLIP * (fill + exit) * sh;
          pnl += g; V.trades++; if (g > 0) V.wins++; c.dir > 0 ? V.longs++ : V.shorts++;
        }
        V.eq *= 1 + pnl / (V.eq * 1e5); V.curve.push([d, V.eq]);
      }
    }
    console.log(m0.toISOString().slice(0, 7), 'both', versions.both.eq.toFixed(3), 'long', versions.long.eq.toFixed(3), 'reqs', reqs);
    m0 = m1;
  }
  const spyA = daily.SPY.map((b) => [et(b.t).d, b.c]).filter(([d]) => d >= versions.both.curve[0][0]);
  const spy = spyA.map(([d, c]) => [d, c / spyA[0][1]]);
  const stats = (cv) => { let pk = 0, dd = 0; for (const [, e] of cv) { pk = Math.max(pk, e); dd = Math.max(dd, 1 - e / pk); } const yrs = (Date.parse(cv.at(-1)[0]) - Date.parse(cv[0][0])) / 31557600000; const yr = {}; let prev = 1; for (const [d, e] of cv) yr[d.slice(0, 4)] = e; const yearly = Object.entries(yr).map(([y, e]) => { const r = e / prev - 1; prev = e; return { year: +y, ret: +(r * 100).toFixed(2) }; }); return { start: cv[0][0], end: cv.at(-1)[0], cagr: +((cv.at(-1)[1] ** (1 / yrs) - 1) * 100).toFixed(2), total: +((cv.at(-1)[1] - 1) * 100).toFixed(2), max_dd: +(dd * 100).toFixed(2), yearly }; };
  const res = { generated: new Date().toISOString(), rules: 'ORB stocks-in-play, see script header', universe: 'current S&P 500 (survivorship bias)', versions: {} };
  for (const [k, V] of Object.entries(versions)) res.versions[k] = { ...stats(V.curve), trades: V.trades, win_rate: +(100 * V.wins / V.trades).toFixed(1), longs: V.longs, shorts: V.shorts };
  res.versions.spy = stats(spy);
  writeFileSync(`${OUT}/orb.json`, JSON.stringify(res, null, 1));
  console.log(JSON.stringify(res.versions, (k, v) => (k === 'yearly' ? undefined : v)));
}
main().catch((e) => { console.error(e); writeFileSync(`${OUT}/orb_error.txt`, String(e.stack || e)); process.exit(1); });
