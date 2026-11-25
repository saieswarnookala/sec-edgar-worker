"""Crypto lab, round 3 (Nov 25 2026): how to actually run the BTC/ETH trend rule. Research only, not financial advice.
Rule: hold the coin when its price is above its N-day average (N = 50 / 100 / 140), else T-bills.
Execution variants:
  - 7 days: decided on each day's close, traded the next day's close (as rounds 1-2)
  - weekdays only (ETF route, IBIT/ETHA): decided on weekday closes, traded on the NEXT weekday close (a weekend signal waits for Monday)
  - weekly: decided Friday, traded Monday
Buffer: switch in only above average x (1 + b), out only below average x (1 - b); b = 0 / 2% / 5%.
Sleeves: BTC only (from 2015-06), ETH only and 50/50 BTC+ETH (from 2018-06; halves rebalanced on the 1st of each month).
Costs: ETF route 0.05%/side + 0.25%/yr fee; Robinhood 0.95%/side. DRY=1: fake prices."""
import os, json, time, urllib.request
import numpy as np, pandas as pd
DRY = os.environ.get("DRY") == "1"; OUT = "data/crypto_lab3.json" if not DRY else "/tmp/crypto_lab3_dry.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
def yahoo(sym):
    if DRY:
        rng = np.random.default_rng(abs(hash(sym)) % 2**32); ix = pd.date_range("2014-09-17", "2026-11-24")
        if sym == "^IRX": return pd.Series(2.0, index=ix)
        return pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0015, 0.04, len(ix)))), index=ix)
    for a in range(3):
        try:
            j = json.loads(urllib.request.urlopen(urllib.request.Request(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1=1400000000&period2={int(time.time())}&interval=1d", headers=UA), timeout=60).read())["chart"]["result"][0]
            s = pd.Series(j["indicators"]["quote"][0]["close"], index=pd.to_datetime(j["timestamp"], unit="s").normalize(), dtype=float)
            s = s[~s.index.duplicated(keep="last")]; return s[s > 0]
        except Exception as e: print("retry", sym, e, flush=True); time.sleep(5)
    raise SystemExit("no data " + sym)
BTC, ETH = yahoo("BTC-USD"), yahoo("ETH-USD"); cal = pd.date_range(BTC.index[0], BTC.index[-1]); D = len(cal)
PX = pd.DataFrame({"BTC": BTC.reindex(cal).ffill(), "ETH": ETH.reindex(cal).ffill()}); R = PX.pct_change().fillna(0.0)
cash_r = ((1 + yahoo("^IRX").reindex(cal).ffill().bfill().clip(0, 8) / 100) ** (1 / 365) - 1).values
wd = cal.weekday.values
def signal(coin, n, b):
    p = PX[coin].values; ma = PX[coin].rolling(n).mean().values; s = np.zeros(D); on = 0.0
    for t in range(D):
        if not np.isfinite(ma[t]): continue
        if p[t] > ma[t] * (1 + b): on = 1.0
        elif p[t] < ma[t] * (1 - b): on = 0.0
        s[t] = on
    return s
def run(coin, sig, mode, cost, fee, start):
    """mode: '7d' | 'weekdays' | 'weekly'. Returns equity and number of trades."""
    r = R[coin].values; e = 1.0; w = 0.0; eq = np.ones(D); s0 = int(np.searchsorted(cal, start)); n_tr = 0; decided = None
    for t in range(1, D):
        if t <= s0: continue
        rr = w * r[t] + (1 - w) * cash_r[t] - w * fee / 365; e *= 1 + rr
        w = w * (1 + r[t]) / (1 + rr) if rr > -1 else 0.0
        d_ok = {"7d": True, "weekdays": wd[t - 1] < 5, "weekly": wd[t - 1] == 4}[mode]       # yesterday was a decision day
        if d_ok: decided = sig[t - 1]
        t_ok = True if mode == "7d" else wd[t] < 5                                            # trades only on weekdays for the ETF routes
        if decided is not None and t_ok and abs(decided - w) > 0.5:
            e *= 1 - cost * abs(decided - w); w = decided; n_tr += 1
        eq[t] = e
    return eq, n_tr
def summ(eq, start):
    s = pd.Series(eq, index=cal); s = s[s.index >= start]; out = {}
    for nm, a, b in (("all", "2014", "2100"), ("2018-2021", "2018", "2022"), ("2022-2026", "2022", "2100"), ("2023-2026", "2023", "2100")):
        x = s[(s.index >= a) & (s.index < b)]
        if len(x) < 200: continue
        x = x / x.iloc[0]; y = len(x) / 365
        out[nm] = {"per_year_pct": round((x.iloc[-1] ** (1 / y) - 1) * 100, 1), "worst_drop_pct": round(float((x / x.cummax() - 1).min()) * 100, 1)}
    y22 = s[(s.index >= "2022-01-01") & (s.index < "2023-01-01")]
    if len(y22) > 300: out["2022_pct"] = round((y22.iloc[-1] / y22.iloc[0] - 1) * 100, 1)
    return out
def blend(e1, e2, start):
    r1 = np.r_[0, e1[1:] / e1[:-1] - 1]; r2 = np.r_[0, e2[1:] / e2[:-1] - 1]; a = b = 0.5; out = np.ones(D); s0 = int(np.searchsorted(cal, start))
    for t in range(s0 + 1, D):
        if cal[t].day == 1: tot = a + b; a = b = tot / 2
        a *= 1 + r1[t]; b *= 1 + r2[t]; out[t] = a + b
    return out
def pr(n, o): print(f"{n:76s} " + " | ".join(f"{k} {v['per_year_pct']}/{v['worst_drop_pct']}" if isinstance(v, dict) else f"{k} {v}" for k, v in o.items()), flush=True)
COST = {"ETF route": (0.0005, 0.0025), "Robinhood": (0.0095, 0.0)}
S_BTC, S_ETH = pd.Timestamp("2015-06-01"), pd.Timestamp("2018-06-01")
RES = {"note": __doc__, "results": {}}
for cl, (c, fee) in COST.items():
    for coin, st in (("BTC", S_BTC), ("ETH", S_ETH)):
        eq, _ = run(coin, np.ones(D), "7d", c, fee, st); RES["results"][f"{coin} only | hold | {cl}"] = summ(eq, st)
    e1, _ = run("BTC", np.ones(D), "7d", c, fee, S_ETH); e2, _ = run("ETH", np.ones(D), "7d", c, fee, S_ETH); RES["results"][f"50/50 BTC+ETH | hold | {cl}"] = summ(blend(e1, e2, S_ETH), S_ETH)
    for n in (50, 100, 140):
        for b in (0.0, 0.02, 0.05):
            sb, se = signal("BTC", n, b), signal("ETH", n, b)
            for mode in ("7d", "weekdays", "weekly"):
                if cl == "ETF route" and mode == "7d": continue                  # ETFs can't trade on weekends
                lab = f"{n}-day, buffer {int(b*100)}%, {mode} | {cl}"
                eb, tb = run("BTC", sb, mode, c, fee, S_BTC); RES["results"][f"BTC only | {lab}"] = summ(eb, S_BTC) | {"trades_per_year": round(tb / ((cal[-1] - S_BTC).days / 365), 1)}
                eb2, _ = run("BTC", sb, mode, c, fee, S_ETH); ee, te = run("ETH", se, mode, c, fee, S_ETH)
                RES["results"][f"ETH only | {lab}"] = summ(ee, S_ETH); RES["results"][f"50/50 BTC+ETH | {lab}"] = summ(blend(eb2, ee, S_ETH), S_ETH)
for k, v in RES["results"].items(): pr(k, v)
json.dump(RES, open(OUT, "w"), indent=1, default=float); print("wrote", OUT)
