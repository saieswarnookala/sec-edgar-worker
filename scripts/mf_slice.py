"""Managed-futures slice next to Dip bot v3.0 in Sai's Roth IRA (Nov 22 2026). Research only, not financial advice.
Question: does adding 10/20/30% of a managed-futures (trend-following) fund to the v3.0 dip bot improve the whole portfolio (return, worst drop, worst
12 months, Sharpe), as the research suggested (DBMF +21.6% / KMLM +24.2% in 2022 while SPY fell 18.2%)?
Data: v3.0 daily curve from stack_and_rebound.py (point-in-time S&P 500; 'live-like' = buy at the 3:45 close, 'realistic' = next open, higher costs).
Funds (Yahoo adjusted closes, fees included): AQMIX (AQR Managed Futures, from 2010), DBMF (iMGP DBi Managed Futures ETF, from mid-2019),
KMLM (KFA Mount Lucas Managed Futures, from Dec 2020); GLD and IEF as other diversifiers; SPY for reference.
Monthly rebalance back to the split. Roth: no tax. Periods start when each fund has data (AQMIX period = the long test).
DRY=1: fake data (code test)."""
import os, sys, json, time, urllib.request, urllib.parse
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stack_and_rebound as S
OUT = "data/mf_slice.json" if not S.DRY else "/tmp/mf_slice_dry.json"
LIVE = dict(fill="close", park="cl", cs=0.0008, ce=0.0003); REAL = dict(fill="open", park="cl", cs=0.0015, ce=0.0005); V3 = dict(etf=True, bond=True)
dn, t0, D = S.dn, S.t0, S.D
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
FUNDS = ["AQMIX", "DBMF", "KMLM", "GLD", "IEF", "SPY", "BIL"]
def yahoo(sym):
    if S.DRY:
        rng = np.random.default_rng(abs(hash(sym)) % 2**32); ix = pd.bdate_range("2008-01-02", "2026-11-20")
        s = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.008, len(ix)))), index=ix)
        return s[s.index >= {"AQMIX": "2010-01-06", "DBMF": "2019-05-08", "KMLM": "2020-12-02"}.get(sym, "2008-01-02")]
    for a in range(4):
        try:
            j = json.loads(urllib.request.urlopen(urllib.request.Request(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?period1=1199145600&period2={int(time.time())}&interval=1d&events=div%2Csplit", headers=UA), timeout=60).read())["chart"]["result"][0]
            q = j["indicators"]; adj = (q.get("adjclose") or [{}])[0].get("adjclose") or q["quote"][0]["close"]
            s = pd.Series(adj, index=pd.to_datetime(j["timestamp"], unit="s").normalize()).dropna(); s = s[~s.index.duplicated(keep="last")]
            return s[s > 0]
        except Exception as e: print("retry", sym, e, flush=True); time.sleep(5 * (a + 1))
    raise SystemExit("no data for " + sym)
F = {s: yahoo(s) for s in FUNDS}
for s, v in F.items(): print(f"{s:6s} {v.index[0].date()} .. {v.index[-1].date()} ({len(v)} days)", flush=True)
cv_live, _ = S.sim(**V3, **LIVE); cv_real, _ = S.sim(**V3, **REAL)
def mret_curve(cv): s = pd.Series(cv[t0 - 1:], index=pd.DatetimeIndex(dn[t0 - 1:])); return s.resample("ME").last().pct_change()
M = {"v3.0 live-like": mret_curve(cv_live), "v3.0 realistic": mret_curve(cv_real)}
for s, v in F.items(): M[s] = v.resample("ME").last().pct_change()
M = pd.DataFrame(M); M = M[M.index <= pd.Timestamp(dn[-1])]
rf = M["BIL"].fillna(0)
def stats(r):
    r = r.dropna(); cv = (1 + r).cumprod(); y = len(r) / 12; ex = r - rf.reindex(r.index).fillna(0)
    return {"per_year_pct": round(float(cv.iloc[-1] ** (1 / y) - 1) * 100, 1), "worst_drop_pct": round(float((cv / cv.cummax() - 1).min()) * 100, 1),
            "worst_12m_pct": round(float(((1 + r).rolling(12).apply(np.prod, raw=True) - 1).min()) * 100, 1),
            "sharpe": round(float(ex.mean() / ex.std() * np.sqrt(12)), 2) if ex.std() > 0 else None,
            "y2022_pct": round(float((1 + r[(r.index >= "2022-01-01") & (r.index < "2023-01-01")]).prod() - 1) * 100, 1) if (r.index.year == 2022).any() else None,
            "months": len(r), "start": str(r.index[0].date())}
RES = {"note": __doc__, "built": str(pd.Timestamp.today().date()), "dry": S.DRY or None, "periods": {}}
for fund in ("AQMIX", "DBMF", "KMLM"):
    start = F[fund].index[0] + pd.offsets.MonthEnd(1)
    sub = M[M.index > start].copy(); P = {}
    for base in ("v3.0 live-like", "v3.0 realistic", "SPY"):
        P[f"100% {base}"] = stats(sub[base])
        for w in (0.1, 0.2, 0.3):
            P[f"{int((1 - w) * 100)}% {base} + {int(w * 100)}% {fund}"] = stats((1 - w) * sub[base] + w * sub[fund])
        for other in ("GLD", "IEF"):
            P[f"80% {base} + 20% {other} (compare)"] = stats(0.8 * sub[base] + 0.2 * sub[other])
    P[f"100% {fund}"] = stats(sub[fund])
    P["monthly_correlation"] = sub[["v3.0 live-like", "SPY", fund, "GLD", "IEF"]].corr().round(2).to_dict()
    RES["periods"][f"{fund} era (from {start.date()})"] = P
    print(f"== {fund} era from {start.date()}", flush=True)
    for k, v in P.items():
        if k != "monthly_correlation": print(f"{k:48s} {v['per_year_pct']:>5}%  worst {v['worst_drop_pct']:>6}%  worst12m {v['worst_12m_pct']:>6}%  sharpe {v['sharpe']}  2022 {v['y2022_pct']}", flush=True)
    print("corr", P["monthly_correlation"].get(fund), flush=True)
json.dump(RES, open(OUT, "w"), indent=1, default=float); print("wrote", OUT, flush=True)
