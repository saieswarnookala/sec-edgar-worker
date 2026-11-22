"""Robustness check for '2x S&P 500 with a trend filter' (Nov 22 2026). Research only, not financial advice.
Rule tested in three_markets.py: hold a 2x index fund while the index closes 2% above its 200-day average; go to T-bills when it closes 2% below;
signal at the close, trade the NEXT close. Leverage simulated daily: L x index return - (L-1) x (T-bill + spread) - fund fee (1x 0.09%, 2x 0.89%, 3x 0.91%).
Checks: 1) settings grid (average 100/150/200/250 days x band 0/1/2/3%) on SPY 1994-2026 and the S&P price index 1960-2026
        2) other markets: Nasdaq-100 (^NDX price from 1985, QQQ total return from 1999), Russell 2000 (IWM from 2000), developed intl (EFA from 2001),
           emerging (EEM from 2003), Dow (DIA from 1998)
        3) placebo: 1,000 random in/out schedules with the SAME number of switches and time invested (in/out spell lengths reshuffled)
        4) crash episodes (1987, 1990, 1998, 2000-02, 2008, 2011, 2015-16, 2018 Q4, 2020, 2022) vs holding 1x
        5) every start year 1994-2016 to now, and higher costs (0.2% per switch, borrowing spread 1.5%)
DRY=1: fake data."""
import os, json, time, urllib.request, urllib.parse
import numpy as np, pandas as pd
DRY = os.environ.get("DRY") == "1"; OUT = "data/lev_robust.json" if not DRY else "/tmp/lev_robust_dry.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
def yahoo(sym, p1=-1325635200):
    if DRY:
        rng = np.random.default_rng(abs(hash(sym)) % 2**32); ix = pd.bdate_range("1955-01-03", "2026-11-20")
        if sym == "^IRX": return pd.Series(4.0, index=ix)
        s = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.011, len(ix)))), index=ix)
        return s[s.index >= {"SPY": "1993-02-01", "QQQ": "1999-03-10", "IWM": "2000-05-26", "EFA": "2001-08-27", "EEM": "2003-04-14", "DIA": "1998-01-20", "^NDX": "1985-10-01"}.get(sym, "1955-01-03")]
    for a in range(4):
        try:
            j = json.loads(urllib.request.urlopen(urllib.request.Request(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?period1={p1}&period2={int(time.time())}&interval=1d&events=div%2Csplit", headers=UA), timeout=60).read())["chart"]["result"][0]
            q = j["indicators"]; adj = (q.get("adjclose") or [{}])[0].get("adjclose") or q["quote"][0]["close"]
            s = pd.Series(adj, index=pd.to_datetime(j["timestamp"], unit="s").normalize()).dropna(); s = s[~s.index.duplicated(keep="last")]
            return s[s > 0]
        except Exception as e: print("retry", sym, e, flush=True); time.sleep(5 * (a + 1))
    raise SystemExit("no data for " + sym)
X = {s: yahoo(s) for s in ["^GSPC", "^IRX", "SPY", "^NDX", "QQQ", "IWM", "EFA", "EEM", "DIA"]}
for s, v in X.items(): print(f"{s:6s} {v.index[0].date()} .. {v.index[-1].date()} ({len(v)})", flush=True)
irx = X["^IRX"]
FEE = {1: 0.0009, 2: 0.0089, 3: 0.0091}
def signal(px, ma, band):
    sma = px.rolling(ma).mean().values; p = px.values; on = False; out = np.zeros(len(p), bool)
    for i in range(len(p)):
        if np.isfinite(sma[i]): on = (p[i] > sma[i] * (1 + band)) if not on else not (p[i] < sma[i] * (1 - band))
        out[i] = on
    return out
def run(px, L=2, ma=200, band=0.02, start=None, cost=0.0005, spread=0.005, sig=None):
    ix = px.index; tb = irx.reindex(ix).ffill().bfill().clip(0, 20).values / 100; tbd = (1 + tb) ** (1 / 252) - 1
    r = px.pct_change().fillna(0).values; lr = L * r - (L - 1) * (tbd + spread / 252) - FEE[L] / 252
    s = signal(px, ma, band) if sig is None else sig
    h = np.r_[0, s[:-1]].astype(float)                                   # decided at close t, held from t+1
    d = h * lr + (1 - h) * tbd - np.abs(np.diff(np.r_[0, h])) * cost
    st = np.searchsorted(ix.values, np.datetime64(start or ix[260])); c = np.cumprod(1 + d[st:])
    return pd.Series(c, index=ix[st:]), s[st:], h[st:]
def stats(c):
    y = (c.index[-1] - c.index[0]).days / 365.25; c = c / c.iloc[0]
    return {"per_year_pct": round(float(c.iloc[-1] ** (1 / y) - 1) * 100, 1), "worst_drop_pct": round(float((c / c.cummax() - 1).min()) * 100, 1)}
def hold(px, start, L=1): return run(px, L=L, start=start, sig=np.ones(len(px), bool))[0]
RES = {"note": __doc__, "built": str(pd.Timestamp.today().date()), "dry": DRY or None}
# 1) settings grid
G = {}
for nm, px, st in (("SPY total return 1994-2026", X["SPY"], "1994-01-03"), ("S&P price index 1960-2026", X["^GSPC"], "1960-01-04")):
    rows = {}
    for ma in (100, 150, 200, 250):
        for band in (0.0, 0.01, 0.02, 0.03):
            c, s, h = run(px, 2, ma, band, st); o = stats(c); o["switches_per_year"] = round(float(np.abs(np.diff(h)).sum() / ((c.index[-1] - c.index[0]).days / 365.25)), 1)
            rows[f"{ma}-day, band {int(band * 100)}%"] = o
    cg = [v["per_year_pct"] for v in rows.values()]; dd = [v["worst_drop_pct"] for v in rows.values()]
    b1 = stats(hold(px, st)); b2 = stats(hold(px, st, 2))
    G[nm] = {"rows": rows, "summary": {"min": min(cg), "median": float(np.median(cg)), "max": max(cg), "worst_drop_median": float(np.median(dd)), "worst_drop_worst": min(dd),
                                        "beat_1x_hold": sum(x > b1["per_year_pct"] for x in cg), "of": len(cg)}, "1x_hold": b1, "2x_hold": b2}
    print(f"GRID {nm}: 2x trend {min(cg)}..{max(cg)} (median {np.median(cg)}), drops median {np.median(dd)} worst {min(dd)} | 1x hold {b1} | beat 1x {G[nm]['summary']['beat_1x_hold']}/{len(cg)}", flush=True)
RES["1_settings_grid"] = G
# 2) other markets
M = {}
for nm, sym in (("Nasdaq-100 price index (^NDX) 1986-2026", "^NDX"), ("Nasdaq-100 total return (QQQ) 2000-2026", "QQQ"), ("Russell 2000 (IWM) 2001-2026", "IWM"),
                ("Developed intl (EFA) 2002-2026", "EFA"), ("Emerging (EEM) 2004-2026", "EEM"), ("Dow (DIA) 1999-2026", "DIA")):
    px = X[sym]; st = str((px.index[0] + pd.Timedelta(days=400)).date()); o = {"1x hold": stats(hold(px, st)), "2x hold": stats(hold(px, st, 2))}
    for L in (1, 2, 3): o[f"{L}x with 200-day, 2% band"] = stats(run(px, L, 200, 0.02, st)[0])
    M[nm] = o; print(f"MKT {nm:42s} " + " | ".join(f"{k} {v['per_year_pct']}/{v['worst_drop_pct']}" for k, v in o.items()), flush=True)
RES["2_other_markets"] = M
# 3) placebo: reshuffle in/out spell lengths
px = X["SPY"]; st = "1994-01-03"; c_real, s_real, h_real = run(px, 2, 200, 0.02, st); real = stats(c_real)
full_sig = signal(px, 200, 0.02); i0 = np.searchsorted(px.index.values, np.datetime64(st))
seg = full_sig[i0:]; runs_ = []; cur = seg[0]; n_ = 0
for v in seg:
    if v == cur: n_ += 1
    else: runs_.append((cur, n_)); cur = v; n_ = 1
runs_.append((cur, n_)); ins = [n for v, n in runs_ if v]; outs = [n for v, n in runs_ if not v]
rng = np.random.default_rng(42); pl = []
for k in range(1000 if not DRY else 60):
    a = list(rng.permutation(ins)); b = list(rng.permutation(outs)); first = bool(rng.integers(2)); s_ = []
    while a or b:
        if first and a: s_ += [True] * a.pop()
        elif b: s_ += [False] * b.pop()
        elif a: s_ += [True] * a.pop()
        first = not first
    sig = np.r_[full_sig[:i0], np.array(s_[:len(seg)], bool)]; pl.append(stats(run(px, 2, 200, 0.02, st, sig=sig)[0]))
pc = np.array([p["per_year_pct"] for p in pl]); pd_ = np.array([p["worst_drop_pct"] for p in pl])
RES["3_placebo"] = {"real_rule": real, "placebo_median_per_year": float(np.median(pc)), "placebo_p95": float(np.percentile(pc, 95)), "placebo_max": float(pc.max()),
                    "share_beating_real_pct": round(float((pc >= real["per_year_pct"]).mean()) * 100, 1), "placebo_median_worst_drop": float(np.median(pd_)), "n": len(pl)}
print("PLACEBO", RES["3_placebo"], flush=True)
# 4) crash episodes (S&P price index for 1987/1990, SPY from 1994)
EP = [("1987 crash", "1987-08-25", "1987-12-04"), ("1990 Gulf War", "1990-07-16", "1990-10-11"), ("1998 LTCM", "1998-07-17", "1998-10-08"), ("2000-02 dot-com bust", "2000-03-24", "2002-10-09"),
      ("2008 crisis", "2007-10-09", "2009-03-09"), ("2011 debt ceiling", "2011-04-29", "2011-10-03"), ("2015-16 China/oil", "2015-05-21", "2016-02-11"),
      ("2018 Q4", "2018-09-20", "2018-12-24"), ("2020 COVID", "2020-02-19", "2020-03-23"), ("2022 bear", "2022-01-03", "2022-10-12")]
E = {}
for nm, a, b in EP:
    px = X["^GSPC"] if a < "1994" else X["SPY"]; c2, _, _ = run(px, 2, 200, 0.02, "1960-01-04" if a < "1994" else "1994-01-03"); c1 = hold(px, "1960-01-04" if a < "1994" else "1994-01-03")
    seg = lambda c: float(c[(c.index >= a) & (c.index <= b)].iloc[-1] / c[c.index < a].iloc[-1] - 1) * 100
    E[nm] = {"1x hold_pct": round(seg(c1), 1), "2x trend_pct": round(seg(c2), 1)}
    print(f"CRASH {nm:22s} 1x {E[nm]['1x hold_pct']:>6}%  2x trend {E[nm]['2x trend_pct']:>6}%", flush=True)
RES["4_crashes"] = E
# 5) start years + higher costs
px = X["SPY"]; S5 = {}
for y in range(1994, 2017):
    st = f"{y}-01-03"; a2 = stats(run(px, 2, 200, 0.02, st)[0]); a1 = stats(hold(px, st)); S5[str(y)] = {"2x trend": a2, "1x hold": a1}
wins = sum(v["2x trend"]["per_year_pct"] > v["1x hold"]["per_year_pct"] for v in S5.values())
RES["5_start_years"] = {"rows": S5, "2x_trend_beat_1x_hold": wins, "of": len(S5)}
print(f"STARTS 2x trend beat 1x hold in {wins}/{len(S5)} start years; " + " ".join(f"{k}:{v['2x trend']['per_year_pct']}v{v['1x hold']['per_year_pct']}" for k, v in S5.items()), flush=True)
RES["5_costs"] = {"base (0.05%/switch, +0.5% borrow)": real, "0.2% per switch": stats(run(px, 2, 200, 0.02, "1994-01-03", cost=0.002)[0]),
                  "borrow spread 1.5%": stats(run(px, 2, 200, 0.02, "1994-01-03", spread=0.015)[0]),
                  "both": stats(run(px, 2, 200, 0.02, "1994-01-03", cost=0.002, spread=0.015)[0])}
print("COSTS", RES["5_costs"], flush=True)
os.makedirs("data", exist_ok=True); json.dump(RES, open(OUT, "w"), indent=1, default=float); print("wrote", OUT, flush=True)
