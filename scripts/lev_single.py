"""Leverage on single stocks (Nov 22 2026, Sai's idea: '2x Oracle-style ETFs with dips / a trend filter'). Research only, not financial advice.
A) DIP BOT v3.0 WITH LEVERAGE: same signals (point-in-time S&P 500, 1999-2026), but each dip stock is held at 1.5x or 2x.
   Costs: '2x ETF style' = (L-1) x T-bill borrowing + 0.5% x (L-1) + 1.1%/yr fund fee (single-stock 2x ETFs charge ~1.0-1.3%);
   'margin' = (L-1) x (T-bill + 3%) (broker margin interest). Variant: leverage only when SPY is above its 100-day average at the buy.
   NOTE: real 2x single-stock ETFs exist for only ~40 big names; leverage on ANY dip stock means margin (Reg T allows 2x overnight).
B) SINGLE STOCKS WITH A TREND FILTER: hold a stock at 1x/2x while it closes 2% above its 200-day average, cash (T-bills) when 2% below.
   Universe 1 (fair): every S&P 500 member on 2000-01-03, followed until delisting (then T-bills) - includes the losers.
   Universe 2 (HINDSIGHT, for comparison only): stocks that have a 2x ETF today (ORCL, NVDA, TSLA, AAPL, MSFT, AMZN, GOOGL, META, AMD, NFLX, AVGO, MU).
   Equal money in each stock at the start, no rebalancing.
C) CHECK: simulated 2x vs real 2x single-stock ETFs (NVDL, TSLL, AAPU, MSFU, AMZU, ORCX if available) on the same days (Yahoo).
DRY=1: fake data."""
import os, sys, json, time, urllib.request, urllib.parse
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stack_and_rebound as S
OUT = "data/lev_single.json" if not S.DRY else "/tmp/lev_single_dry.json"
LIVE = dict(fill="close", park="cl", cs=0.0008, ce=0.0003); REAL = dict(fill="open", park="cl", cs=0.0015, ce=0.0005); V3 = dict(etf=True, bond=True)
RES = {"note": __doc__, "built": str(pd.Timestamp.today().date()), "dry": S.DRY or None, "A_dip_bot_leverage": {}, "B_trend_single_stocks": {}, "C_check_vs_real_etfs": {}}
# ---------------- A
VERS = [("1x (v3.0 as is)", {}), ("1.5x, 2x-ETF-style costs", dict(lev=1.5, lev_cost=0.5 * 0.005 + 0.011)), ("2x, 2x-ETF-style costs", dict(lev=2.0, lev_cost=0.005 + 0.011)),
        ("2x, margin costs (T-bill + 3%)", dict(lev=2.0, lev_cost=0.03)), ("2x only when SPY is above its 100-day avg, ETF-style costs", dict(lev=2.0, lev_cost=0.016, lev_trend=True))]
for cn, cost in (("live-like (buy at the 3:45 close)", LIVE), ("realistic (next open, higher costs)", REAL)):
    for vn, kw in VERS:
        cv, tr = S.sim(**V3, **cost, **kw); o = S.summ(cv, tr); k = f"{cn} | {vn}"; RES["A_dip_bot_leverage"][k] = o
        a = o.get("1999-2026", {}); print(f"DIP {k:95s} {a.get('per_year_pct')}%/yr worst {a.get('worst_drop_pct')}% | 2008 {o.get('2008 crash', {}).get('return_pct')} 2020 {o.get('2020 covid', {}).get('return_pct')} 2022 {o.get('2022 bear', {}).get('return_pct')}", flush=True)
# ---------------- B
dn = S.dn; D = S.D; C = S.S_C; tb = S.TBILL_R
d0 = int(np.searchsorted(dn, np.datetime64("2000-01-03")))
mem = S.mem; members0 = sorted(set(mem[(mem.start <= pd.Timestamp("2000-01-03")) & (mem.end >= pd.Timestamp("2000-01-03"))].ticker) & set(S.tick)) if not S.DRY else S.tick[:300]
ETF2X = [t for t in ["ORCL", "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "GOOGL", "GOOG", "META", "FB", "AMD", "NFLX", "AVGO", "MU"] if t in S.TI]
if S.DRY: ETF2X = S.tick[:10]
def curves(j, start):
    p = C[:, j]; fin = np.isfinite(p)
    if not fin[start:].any(): return None
    a = start + int(np.argmax(fin[start:])); last = a + int(np.flatnonzero(fin[a:])[-1]) if fin[a:].any() else a
    r = np.zeros(D); seg = p[a:last + 1]; rr = np.r_[0, seg[1:] / seg[:-1] - 1]; rr = np.nan_to_num(rr, nan=0.0); r[a:last + 1] = rr
    sma = pd.Series(p).rolling(200, min_periods=200).mean().values; on = False; sig = np.zeros(D, bool)
    for i in range(a, last + 1):
        if np.isfinite(sma[i]) and np.isfinite(p[i]): on = (p[i] > sma[i] * 1.02) if not on else not (p[i] < sma[i] * 0.98)
        sig[i] = on
    held = np.r_[False, sig[:-1]]; alive = np.zeros(D, bool); alive[a + 1:last + 1] = True
    out = {}
    for L in (1, 2):
        lr = np.maximum(L * r - (L - 1) * tb - ((L - 1) * 0.005 + (0.011 if L > 1 else 0.0)) / 252, -0.99)   # a 2x fund can be wiped out, not go negative
        hold_d = np.where(alive, lr, tb)                                      # after delisting: T-bills
        trend_d = np.where(alive & held, lr, tb) - np.abs(np.diff(np.r_[0, (alive & held).astype(float)])) * 0.001
        out[f"{L}x hold"] = np.cumprod(1 + hold_d[start:]); out[f"{L}x with 200-day trend"] = np.cumprod(1 + trend_d[start:])
    return out
def basket(names, start, label):
    cs = {}; per = {}
    for t in names:
        c = curves(S.TI[t], start)
        if c is None: continue
        per[t] = {k: round(float(v[-1] ** (252 / len(v)) - 1) * 100, 1) for k, v in c.items()}
        for k, v in c.items(): cs.setdefault(k, []).append(v)
    o = {"stocks": len(per)}
    for k, lst in cs.items():
        port = np.mean(lst, axis=0); y = len(port) / 252
        o[k] = {"per_year_pct": round(float(port[-1] ** (1 / y) - 1) * 100, 1), "worst_drop_pct": round(float((port / np.maximum.accumulate(port) - 1).min()) * 100, 1),
                "median_stock_per_year_pct": float(np.median([p[k] for p in per.values()])), "stocks_losing_90pct_plus": int(sum(v[-1] < 0.1 for v in lst))}
    o["share_where_2x_trend_beat_1x_hold_pct"] = round(100 * float(np.mean([p["2x with 200-day trend"] > p["1x hold"] for p in per.values()])), 1)
    o["share_where_2x_trend_beat_1x_trend_pct"] = round(100 * float(np.mean([p["2x with 200-day trend"] > p["1x with 200-day trend"] for p in per.values()])), 1)
    print(f"BASKET {label} ({len(per)} stocks): " + " | ".join(f"{k} {o[k]['per_year_pct']}/{o[k]['worst_drop_pct']} med {o[k]['median_stock_per_year_pct']} wiped {o[k]['stocks_losing_90pct_plus']}" for k in cs) +
          f" | 2x trend beat 1x hold in {o['share_where_2x_trend_beat_1x_hold_pct']}%", flush=True)
    return o, per
o1, _ = basket(members0, d0, "S&P 500 members on 2000-01-03 (fair)"); RES["B_trend_single_stocks"]["all S&P 500 members on 2000-01-03 (survivorship-free)"] = o1
o2, per2 = basket(ETF2X, d0, "stocks with a 2x ETF today (HINDSIGHT)"); RES["B_trend_single_stocks"]["stocks with a 2x ETF today (hindsight list)"] = o2
RES["B_trend_single_stocks"]["per_stock_hindsight_list"] = per2
for t, v in per2.items(): print(f"   {t:6s} " + " | ".join(f"{k} {x}%" for k, x in v.items()), flush=True)
# ---------------- C
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
def yahoo(sym):
    j = json.loads(urllib.request.urlopen(urllib.request.Request(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?period1=1577836800&period2={int(time.time())}&interval=1d&events=div%2Csplit", headers=UA), timeout=60).read())["chart"]["result"][0]
    q = j["indicators"]; adj = (q.get("adjclose") or [{}])[0].get("adjclose") or q["quote"][0]["close"]
    s = pd.Series(adj, index=pd.to_datetime(j["timestamp"], unit="s").normalize()).dropna(); return s[~s.index.duplicated(keep="last")]
if not S.DRY:
    irx = pd.Series(tb * 252, index=pd.DatetimeIndex(dn))
    for etf, und in (("NVDL", "NVDA"), ("TSLL", "TSLA"), ("AAPU", "AAPL"), ("MSFU", "MSFT"), ("AMZU", "AMZN"), ("ORCX", "ORCL")):
        try:
            e = yahoo(etf); u = yahoo(und); ix = e.index.intersection(u.index); ix = ix[ix >= e.index[0] + pd.Timedelta(days=5)]
            if len(ix) < 120: RES["C_check_vs_real_etfs"][etf] = "too little history"; continue
            ur = u.reindex(ix).pct_change().fillna(0); t_ = irx.reindex(ix, method="ffill").fillna(0.04) / 252
            sim = (1 + 2 * ur - t_ - (0.005 + 0.011) / 252).cumprod(); real = e.reindex(ix) / e.reindex(ix).iloc[0]; y = (ix[-1] - ix[0]).days / 365.25
            RES["C_check_vs_real_etfs"][etf] = {"from": str(ix[0].date()), "simulated_total_pct": round(float(sim.iloc[-1] - 1) * 100, 1), "real_total_pct": round(float(real.iloc[-1] - 1) * 100, 1), "years": round(y, 1)}
            print("CHECK", etf, RES["C_check_vs_real_etfs"][etf], flush=True)
        except Exception as ex: RES["C_check_vs_real_etfs"][etf] = f"no data ({ex})"; print("CHECK", etf, "no data", ex, flush=True)
json.dump(RES, open(OUT, "w"), indent=1, default=float); print("wrote", OUT, flush=True)
