"""India via US-listed ETFs for Sai's Roth IRA (Nov 22 2026), test #10 of the India strategy report. No PFIC, no India tax, no tax on switching in a Roth.
ETFs (Yahoo adjusted closes, so dividends and fund fees are included): INDA (MSCI India, 2012), SMIN (India small cap, 2012), EPI (WisdomTree India earnings, 2008),
INDY (India 50, 2009), GLD (gold), BIL (T-bills = cash), SPY. Tracking check: INDA vs Nifty 50 (^NSEI, price only) converted to USD with INR=X.
Rules: signal on the month-end close, trade the NEXT day's close. Cost 0.05% per buy and per sell (ETF spread). Roth: before tax = after tax.
DRY=1: fake prices (code test)."""
import os, json, time, datetime, urllib.request
import numpy as np, pandas as pd
DRY = os.environ.get("DRY") == "1"; OUT = "data/india_usproxy.json" if not DRY else "/tmp/india_usproxy_dry.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
SYMS = ["INDA", "SMIN", "EPI", "INDY", "GLD", "BIL", "SPY", "^NSEI", "INR=X"]
def yahoo(sym):
    if DRY:
        rng = np.random.default_rng(abs(hash(sym)) % 2**32); ix = pd.bdate_range("2008-02-01", "2026-11-20")
        if sym == "INR=X": return pd.Series(np.exp(np.cumsum(rng.normal(0.00012, 0.004, len(ix)))) * 45, index=ix)
        mu, vol = {"BIL": (0.00006, 0.0003), "GLD": (0.0003, 0.01)}.get(sym, (0.0004, 0.013))
        s = pd.Series(100 * np.exp(np.cumsum(rng.normal(mu, vol, len(ix)))), index=ix)
        return s[s.index >= {"INDA": "2012-02-03", "SMIN": "2012-02-09", "INDY": "2009-11-20", "BIL": "2007-05-30"}.get(sym, "2008-02-01")]
    for a in range(4):
        try:
            j = json.loads(urllib.request.urlopen(urllib.request.Request(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?period1=1104537600&period2={int(time.time())}&interval=1d&events=div%2Csplit", headers=UA), timeout=60).read())["chart"]["result"][0]
            q = j["indicators"]; adj = (q.get("adjclose") or [{}])[0].get("adjclose") or q["quote"][0]["close"]
            s = pd.Series(adj, index=pd.to_datetime(j["timestamp"], unit="s").normalize()).dropna(); s = s[~s.index.duplicated(keep="last")]
            return s[s > 0]
        except Exception as e: print("retry", sym, e, flush=True); time.sleep(5 * (a + 1))
    raise SystemExit("no data for " + sym)
import urllib.parse
D = {s: yahoo(s) for s in SYMS}
for s, v in D.items(): print(f"{s:6s} {v.index[0].date()} to {v.index[-1].date()} ({len(v)} days)", flush=True)
cal = D["SPY"].index; cal = cal[cal >= "2008-03-01"]
P = pd.DataFrame({s: D[s].reindex(cal).ffill(limit=5) for s in SYMS if s not in ("^NSEI", "INR=X")})
R = P.pct_change(); R = R.where(R.abs() < 0.3)
COST = 0.0005
me = [i for i in range(len(cal) - 1) if cal[i].month != cal[i + 1].month]
def ret(i, k, lb):  # trailing lb-month return at row i
    j = i - 21 * lb
    if j < 0 or not (np.isfinite(P[k].iat[i]) and np.isfinite(P[k].iat[j])): return None
    return P[k].iat[i] / P[k].iat[j] - 1
def engine(pick, start="2008-03-01"):
    w = {}; pend = None; eq = 1.0; curve = np.full(len(cal), np.nan); on = False; sw = 0
    for i in range(len(cal)):
        if on:
            r = sum(wi * (R[k].iat[i] if np.isfinite(R[k].iat[i]) else 0) for k, wi in w.items()); eq *= 1 + r
            w = {k: wi * (1 + (R[k].iat[i] if np.isfinite(R[k].iat[i]) else 0)) / (1 + r) for k, wi in w.items()}; curve[i] = eq
        if pend is not None:
            tv = sum(abs(pend.get(k, 0) - w.get(k, 0)) for k in set(pend) | set(w)); eq *= 1 - COST * tv
            if set(pend) != set(w): sw += 1
            w = dict(pend); pend = None
            if not on: on = True; curve[i] = eq
        if i in me and cal[i] >= pd.Timestamp(start):
            t = pick(i)
            if t is not None: pend = t
    c = pd.Series(curve, index=cal).dropna(); return c, sw / max(len(c) / 252, 0.1)
def stats(c, a=None, b=None):
    c = c[(c.index >= (a or c.index[0])) & (c.index < (b or "2100-01-01"))]
    if len(c) < 150: return None
    y = len(c) / 252; c = c / c.iloc[0]
    return {"cagr": round(float(c.iloc[-1] ** (1 / y) - 1) * 100, 1) if y > 1.5 else None, "total": round(float(c.iloc[-1] - 1) * 100, 1), "dd": round(float((c / c.cummax() - 1).min()) * 100, 1)}
def summ(c, sw):
    return {"all": stats(c), "2012_2019": stats(c, "2012-01-01", "2020-01-01"), "2020_2026": stats(c, "2020-01-01"), "test_2019_2026": stats(c, "2019-01-01"),
            "2022": stats(c, "2022-01-01", "2023-01-01"), "switches_per_year": round(sw, 1), "start": str(c.index[0].date())}
ST = "2013-03-01"   # common start: 12 months after INDA/SMIN listed, so every rule has a full lookback
RES = {"note": __doc__, "built": str(datetime.date.today()), "dry": DRY or None, "common_start": ST, "rules": {}}
def pr(k, o): a = o["all"]; print(f"{k:72s} {a['cagr']:>5}% dd {a['dd']:>6} | 19-26 {o['test_2019_2026']['cagr'] if o['test_2019_2026'] else None} | 2022 {o['2022']['total'] if o['2022'] else None}% | sw/yr {o['switches_per_year']}", flush=True)
def add(k, pick):
    c, sw = engine(pick, ST); RES["rules"][k] = summ(c, sw); pr(k, RES["rules"][k])
for s in ("INDA", "SMIN", "EPI", "INDY", "SPY", "GLD"): add(f"Buy & hold {s}", lambda i, s=s: {s: 1.0})
add("Buy & hold 50% INDA + 50% SPY (rebalance monthly)", lambda i: {"INDA": 0.5, "SPY": 0.5})
for s in ("INDA", "SMIN"):
    def tr(i, s=s):
        m = P[s].iloc[: i + 1].resample("ME").last(); return {s: 1.0} if len(m) >= 10 and m.iloc[-1] > m.iloc[-10:].mean() else {"BIL": 1.0}
    add(f"10-month average rule: {s} or cash (BIL)", tr)
def dual(uni, lb, buf):
    held = {"k": None}
    def pick(i):
        sc = {k: ret(i, k, lb) for k in uni}; sc = {k: v for k, v in sc.items() if v is not None}
        if not sc: return None
        b = max(sc, key=sc.get); h = held["k"]
        if h in sc and sc[b] - sc[h] < buf: b = h                       # switch buffer
        held["k"] = b; return {b: 1.0}
    return pick
for lbl, uni in (("INDA / GLD / cash", ["INDA", "GLD", "BIL"]), ("SMIN / GLD / cash", ["SMIN", "GLD", "BIL"]), ("INDA / SMIN / GLD / cash", ["INDA", "SMIN", "GLD", "BIL"]),
                 ("SPY / INDA / GLD / cash (global)", ["SPY", "INDA", "GLD", "BIL"])):
    for lb in (6, 12):
        for buf in (0.0, 0.02):
            add(f"Dual momentum {lbl} | best {lb}-month return | buffer {int(buf * 100)}%", dual(uni, lb, buf))
for lb in (6, 12):
    def sz(i, lb=lb):
        sc = {k: ret(i, k, lb) for k in ("INDA", "SMIN")}; cash = ret(i, "BIL", lb) or 0
        sc = {k: v for k, v in sc.items() if v is not None}
        if not sc: return None
        b = max(sc, key=sc.get); return {b: 1.0} if sc[b] > cash else {"BIL": 1.0}
    add(f"Large vs small: INDA or SMIN, best {lb}-month return, cash if neither beats T-bills", sz)
# tracking: INDA vs Nifty 50 (price) in USD
n_usd = (D["^NSEI"] / D["INR=X"].reindex(D["^NSEI"].index).ffill()).dropna()
m_inda = D["INDA"].resample("ME").last().pct_change(); m_n = n_usd.resample("ME").last().pct_change()
j = pd.concat([m_inda, m_n], axis=1, keys=["inda", "n50usd"], sort=True).dropna(); j = j[j.index >= "2012-03-01"]
y = len(j) / 12; cg = lambda s: round(float(((1 + s).prod()) ** (1 / y) - 1) * 100, 1)
RES["tracking_inda_vs_nifty50_usd"] = {"monthly_correlation": round(float(j.corr().iloc[0, 1]), 3), "inda_cagr": cg(j["inda"]), "nifty50_price_usd_cagr": cg(j["n50usd"]),
    "note": "Nifty 50 here is the PRICE index (no dividends, ~1.3%/yr); INDA includes dividends minus its 0.61%/yr fee", "inr_change_per_year_pct": round(float((D['INR=X'].iloc[-1] / D['INR=X'][D['INR=X'].index >= '2012-03-01'].iloc[0]) ** (1 / y) - 1) * 100, 1)}
print("TRACKING", RES["tracking_inda_vs_nifty50_usd"], flush=True)
os.makedirs("data", exist_ok=True); json.dump(RES, open(OUT, "w"), indent=1, default=float); print("wrote", OUT, flush=True)
