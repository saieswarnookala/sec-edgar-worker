"""Options research: is there an edge we can use?
1) Real CBOE strategy indices (Yahoo): PUT (sell cash-secured SPX puts), BXM (covered calls), BXMD, vs SPY total return.
2) Synthetic monthly SPY options backtest 1990-2026, priced with Black-Scholes at VIX-based implied vol
   (puts priced with skew), 3% of premium lost to bid-ask per trade, cash earns the 13-week T-bill rate.
   Strategies: buy calls, buy protective puts, sell puts, covered calls, with / without our SPY-trend filter.
Approximation, not real option prices; real index results in (1) are the check. Not financial advice."""
import json, math, time, urllib.request, urllib.parse
import numpy as np, pandas as pd
def yahoo(sym):
    for i in range(4):
        try:
            u = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?period1=0&period2={int(time.time())}&interval=1d&events=div%2Csplit"
            j = json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=60))["chart"]["result"][0]
            ts = pd.to_datetime(j["timestamp"], unit="s").normalize(); q = j["indicators"]
            close = q["quote"][0]["close"]; adj = q.get("adjclose", [{}])[0].get("adjclose", close)
            return pd.DataFrame({"close": close, "adj": adj}, index=ts).dropna().groupby(level=0).last()
        except Exception as e:
            print("retry", sym, e, flush=True); time.sleep(10 * (i + 1))
    return None
D = {s: yahoo(s) for s in ["SPY", "^GSPC", "^VIX", "^IRX", "^PUT", "^BXM", "^BXMD", "^CNDR"]}
print({k: (None if v is None else (str(v.index[0].date()), len(v))) for k, v in D.items()}, flush=True)
OUT = {"note": "Not financial advice. Synthetic = Black-Scholes at VIX-based IV; real = CBOE indices."}
BEARS = {"2000-02": ("2000-03-24", "2002-10-09"), "2008": ("2007-10-09", "2009-03-09"), "2020": ("2020-02-19", "2020-03-23"), "2022": ("2022-01-03", "2022-10-12")}
def stats(c, spyc=None):
    c = c.dropna(); c = c / c.iloc[0]; yrs = len(c) / 252
    o = {"start": str(c.index[0].date()), "cagr": round((c.iloc[-1] ** (1 / yrs) - 1) * 100, 1), "max_dd": round(float((c / c.cummax() - 1).min()) * 100, 1),
         "vol": round(float(c.pct_change().std() * math.sqrt(252) * 100), 1)}
    for k, (a, z) in BEARS.items():
        s = c[(c.index >= a) & (c.index <= z)]
        if len(s) > 2: o[k] = round((s.iloc[-1] / s.iloc[0] - 1) * 100, 1)
    return o
# ---- 1) real indices vs SPY total return over the same dates
real = {}
for k in ["^PUT", "^BXM", "^BXMD", "^CNDR"]:
    if D[k] is None or len(D[k]) < 500: continue
    idx = D[k].index.intersection(D["SPY"].index)
    real[k] = {"index": stats(D[k]["close"].reindex(idx)), "SPY_same_dates": stats(D["SPY"]["adj"].reindex(idx))}
    print(k, real[k], flush=True)
OUT["real_indices"] = real
# ---- 2) synthetic monthly options on the S&P 500 (cash = T-bill)
spx = D["^GSPC"]["close"]; vix = D["^VIX"]["close"]; irx = D["^IRX"]["close"] if D["^IRX"] is not None else None
df = pd.DataFrame({"px": spx, "vix": vix}).dropna(); df = df[df.index >= "1990-01-02"]
df["rf"] = (irx.reindex(df.index).ffill() / 100).fillna(0.03) if irx is not None else 0.03
spy = D["SPY"]["adj"]; tr = spy.reindex(df.index).pct_change()     # total return incl. dividends (SPY from 1993)
pr = df.px.pct_change(); df["tr"] = tr.fillna(pr + 0.02 / 252)        # before 1993: price + ~2%/yr dividends
df["ma200"] = df.px > df.px.rolling(200).mean()
N = math.erf
def bs(S, K, T, v, r, call):
    if T <= 0 or v <= 0: return max(0.0, (S - K) if call else (K - S))
    d1 = (math.log(S / K) + (r + v * v / 2) * T) / (v * math.sqrt(T)); d2 = d1 - v * math.sqrt(T)
    Nf = lambda x: 0.5 * (1 + N(x / math.sqrt(2)))
    return S * Nf(d1) - K * math.exp(-r * T) * Nf(d2) if call else K * math.exp(-r * T) * Nf(-d2) - S * Nf(-d1)
def iv(vixv, mny, call):   # simple skew: OTM puts dearer, OTM calls cheaper (vol points per 1% moneyness)
    v = vixv / 100
    return max(0.05, v + (0.0035 * mny * 100 if not call else -0.002 * mny * 100))
SPREAD = 0.03; H = 21; T = H / 252
dates = df.index; n = len(df)
def run(kind, otm=0.0, spend=0.02, gate=False):
    """Monthly roll every 21 trading days.
    buy_call: spend `spend` of capital on calls (strike +otm), rest in T-bills.
    put_hedge: hold S&P total return + buy puts (strike -otm) with notional = portfolio.
    sell_put: cash-secured: collect premium on puts (strike -otm), notional = capital, cash in T-bills.
    covered_call: hold S&P total return, sell calls (strike +otm) on full notional."""
    eq = 1.0; out = np.empty(n); i = 0
    while i < n:
        j = min(i + H, n - 1); S0 = df.px.iloc[i]; S1 = df.px.iloc[j]; r = df.rf.iloc[i]; vx = df.vix.iloc[i]
        days = j - i; grow_tb = (1 + r) ** (days / 252)
        mkt = float((1 + df.tr.iloc[i + 1:j + 1]).prod()) if j > i else 1.0
        active = (not gate) or bool(df.ma200.iloc[i])
        if kind == "spx": end = eq * mkt
        elif kind == "buy_call":
            K = S0 * (1 + otm); p = bs(S0, K, T, iv(vx, otm, True), r, True) * (1 + SPREAD)
            if active: units = eq * spend / p; end = (eq - eq * spend) * grow_tb + units * max(0, S1 - K) * (1 - SPREAD * 0.5)
            else: end = eq * grow_tb
        elif kind == "put_hedge":
            K = S0 * (1 - otm); p = bs(S0, K, T, iv(vx, otm, False), r, False) * (1 + SPREAD)
            units = eq / S0; cost = units * p if active else 0
            end = (eq - cost) * mkt + (units * max(0, K - S1) * (1 - SPREAD * 0.5) if active else 0)
        elif kind == "sell_put":
            K = S0 * (1 - otm); p = bs(S0, K, T, iv(vx, otm, False), r, False) * (1 - SPREAD)
            if active: units = eq / K; end = (eq + units * p) * grow_tb - units * max(0, K - S1)
            else: end = eq * grow_tb
        elif kind == "covered_call":
            K = S0 * (1 + otm); p = bs(S0, K, T, iv(vx, otm, True), r, True) * (1 - SPREAD)
            units = eq / S0
            if active: end = eq * mkt + units * p * grow_tb - units * max(0, S1 - K)
            else: end = eq * grow_tb
        out[i:j + 1] = np.linspace(eq, end, j - i + 1) if j > i else end
        eq = end; i = j if j > i else n
    return pd.Series(out, index=dates)
S = {}
cfg = {"S&P 500 total return": ("spx", {}),
       "Buy ATM calls, 2% of capital/month": ("buy_call", dict(otm=0.0, spend=0.02)),
       "Buy 5% OTM calls, 2%/month": ("buy_call", dict(otm=0.05, spend=0.02)),
       "Buy ATM calls 2%, only when above 200d": ("buy_call", dict(otm=0.0, spend=0.02, gate=True)),
       "S&P + 5% OTM protective puts": ("put_hedge", dict(otm=0.05)),
       "S&P + 10% OTM protective puts": ("put_hedge", dict(otm=0.10)),
       "Sell ATM puts (cash-secured)": ("sell_put", dict(otm=0.0)),
       "Sell 5% OTM puts (cash-secured)": ("sell_put", dict(otm=0.05)),
       "Sell 5% OTM puts, only when above 200d": ("sell_put", dict(otm=0.05, gate=True)),
       "Covered call ATM": ("covered_call", dict(otm=0.0)),
       "Covered call 2% OTM": ("covered_call", dict(otm=0.02)),
       "Covered call 2% OTM, only when above 200d": ("covered_call", dict(otm=0.02, gate=True))}
for name, (k, kw) in cfg.items():
    c = run(k, **kw); S[name] = stats(c); print(name, S[name], flush=True)
OUT["synthetic"] = S
# calibration check: synthetic sell-ATM-put vs real PUT index, synthetic ATM covered call vs real BXM, same dates
cal = {}
for real_k, syn in [("^PUT", "Sell ATM puts (cash-secured)"), ("^BXM", "Covered call ATM")]:
    if D[real_k] is None: continue
    k, kw = cfg[syn]; c = run(k, **kw); idx = c.index.intersection(D[real_k].index)
    cal[real_k] = {"real": stats(D[real_k]["close"].reindex(idx)), "synthetic": stats(c.reindex(idx))}
OUT["calibration"] = cal; print("calibration", cal, flush=True)
json.dump(OUT, open("data/options_research.json", "w"), indent=1, default=float)
