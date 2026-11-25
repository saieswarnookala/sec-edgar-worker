"""Crypto lab, Solana add-on (Nov 25 2026): does adding SOL as a third coin help the 50-day trend bot? Research only, not financial advice.
Rule (same as paper bot 15): hold a coin while its price is above its 50-day average, else T-bills; decided on weekday closes,
traded on the next weekday close (ETF route), 0.05%/side + yearly ETF fee. Sleeves rebalanced to target weights on the 1st of each month.
Compares: BTC+ETH 50/50 (today's bot) vs BTC+ETH+SOL thirds vs 40/40/20 vs SOL alone, plus buy-and-hold of each mix.
Checks: periods with and without SOL's 2020-21 bubble, a block-bootstrap of the 3-coin minus 2-coin gap,
correlations, and the real SOL ETF (BSOL) since launch vs the coin. DRY=1: fake prices."""
import os, json, time, urllib.request
import numpy as np, pandas as pd
DRY = os.environ.get("DRY") == "1"; OUT = "data/crypto_sol.json" if not DRY else "/tmp/crypto_sol_dry.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
def yahoo(sym, start=1400000000):
    if DRY:
        rng = np.random.default_rng(abs(hash(sym)) % 2**32)
        ix = pd.date_range("2025-10-28" if sym in ("BSOL", "GSOL") else "2014-09-17", "2026-11-24")
        if sym in ("BSOL", "GSOL"): ix = ix[ix.weekday < 5]
        if sym == "^IRX": return pd.Series(2.0, index=ix)
        return pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0015, 0.045, len(ix)))), index=ix)
    for a in range(3):
        try:   # always period1/period2: range=max returns sparse bars
            j = json.loads(urllib.request.urlopen(urllib.request.Request(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?period1={start}&period2={int(time.time())}&interval=1d", headers=UA), timeout=60).read())["chart"]["result"][0]
            s = pd.Series(j["indicators"]["quote"][0]["close"], index=pd.to_datetime(j["timestamp"], unit="s").normalize(), dtype=float)
            s = s[~s.index.duplicated(keep="last")]; return s[s > 0].dropna()
        except Exception as e: print("retry", sym, e, flush=True); time.sleep(5)
    return None
COINS = {c: yahoo(f"{c}-USD") for c in ("BTC", "ETH", "SOL")}
for c, s in COINS.items():
    if s is None or len(s) < 500: raise SystemExit("no data " + c)
    print(c, s.index[0].date(), s.index[-1].date(), len(s), flush=True)
cal = pd.date_range(COINS["BTC"].index[0], COINS["BTC"].index[-1]); D = len(cal)
PX = pd.DataFrame({c: s.reindex(cal).ffill() for c, s in COINS.items()}); R = PX.pct_change().fillna(0.0)
cash_r = ((1 + yahoo("^IRX").reindex(cal).ffill().bfill().clip(0, 8) / 100) ** (1 / 365) - 1).values
wd = cal.weekday.values
FEE = {"BTC": 0.0025, "ETH": 0.0025, "SOL": 0.0025}; COST = 0.0005; N = 50
SOL0 = PX["SOL"].first_valid_index() + pd.Timedelta(days=N + 5)   # first day SOL has a 50-day average
def signal(coin):
    p = PX[coin].values; ma = PX[coin].rolling(N).mean().values
    return np.where(np.isfinite(ma), (p > ma).astype(float), np.nan)
def sleeve(coin, hold=False):
    """daily returns of one coin under the rule (weekday ETF route) or buy-and-hold"""
    r = R[coin].values; sig = signal(coin); w = 1.0 if hold else 0.0; out = np.zeros(D); decided = None
    for t in range(1, D):
        if not np.isfinite(PX[coin].values[t - 1]): continue
        rr = w * r[t] + (1 - w) * cash_r[t] - w * FEE[coin] / 365; out[t] = rr
        w = w * (1 + r[t]) / (1 + rr) if rr > -1 else 0.0
        if hold: continue
        if wd[t - 1] < 5 and np.isfinite(sig[t - 1]): decided = sig[t - 1]
        if decided is not None and wd[t] < 5 and abs(decided - w) > 0.5:
            out[t] -= COST * abs(decided - w) * (1 + rr); w = decided
    return pd.Series(out, index=cal)
RULE = {c: sleeve(c) for c in COINS}; HOLD = {c: sleeve(c, True) for c in COINS}
def mix(parts, weights, start):
    """sleeves rebalanced to target weights on the 1st of each month"""
    df = pd.DataFrame({c: parts[c] for c in weights}).loc[start:]; tw = np.array([weights[c] for c in df.columns])
    w = tw.copy(); eq = []; e = 1.0
    for d, row in zip(df.index, df.values):
        if d.day == 1: w = tw.copy()
        g = w * (1 + row); e *= g.sum(); w = g / g.sum(); eq.append(e)
    return pd.Series(eq, index=df.index)
def stats(eq):
    eq = eq / eq.iloc[0]; y = max((eq.index[-1] - eq.index[0]).days, 1) / 365; dr = eq.pct_change().dropna(); k = len(eq) / y
    return {"per_year_pct": round((eq.iloc[-1] ** (1 / y) - 1) * 100, 1), "worst_drop_pct": round(float((eq / eq.cummax() - 1).min()) * 100, 1),
            "sharpe": round(float(dr.mean() / dr.std() * np.sqrt(k)), 2) if dr.std() > 0 else None}
MIXES = {"BTC+ETH 50/50 (today's bot)": {"BTC": .5, "ETH": .5}, "BTC+ETH+SOL thirds": {"BTC": 1 / 3, "ETH": 1 / 3, "SOL": 1 / 3},
         "BTC 40 / ETH 40 / SOL 20": {"BTC": .4, "ETH": .4, "SOL": .2}, "SOL alone": {"SOL": 1.0}}
PERIODS = {"all (SOL era)": (SOL0, None), "2020-2021 (SOL bubble)": (SOL0, "2021-12-31"), "2022 (crash)": ("2022-01-01", "2022-12-31"),
           "2023-2026": ("2023-01-01", None), "last 2 years": (cal[-1] - pd.Timedelta(days=730), None)}
res = {"note": "50-day rule, weekdays/ETF route, 0.05%/side + 0.25%/yr. SOL data from Yahoo SOL-USD. Not financial advice.",
       "sol_start": str(SOL0.date()), "end": str(cal[-1].date()), "table": {}}
for nm, wts in MIXES.items():
    for kind, parts in (("rule", RULE), ("hold", HOLD)):
        eq_all = mix(parts, wts, SOL0)
        row = {}
        for pn, (a, b) in PERIODS.items():
            e = eq_all.loc[a:b] if b else eq_all.loc[a:]
            if len(e) > 150: row[pn] = stats(e)
        res["table"][f"{nm} | {kind}"] = row
# does the 3rd coin add anything beyond luck? block bootstrap (30-day blocks) of the daily gap, from 2022 (bubble removed) and full
def boot(a, b, start, n=2000, blk=30):
    d = (a - b).loc[start:].values; L = len(d); rng = np.random.default_rng(7); means = []
    for _ in range(n):
        idx = np.concatenate([np.arange(s, s + blk) % L for s in rng.integers(0, L, L // blk + 1)])[:L]; means.append(d[idx].mean())
    m = np.array(means) * 365 * 100
    return {"gap_pts_per_year": round(float(d.mean() * 365 * 100), 1), "chance_gap_above_0_pct": round(float((m > 0).mean() * 100), 1),
            "range_90pct": [round(float(np.percentile(m, 5)), 1), round(float(np.percentile(m, 95)), 1)]}
two = mix(RULE, MIXES["BTC+ETH 50/50 (today's bot)"], SOL0).pct_change().fillna(0)
three = mix(RULE, MIXES["BTC+ETH+SOL thirds"], SOL0).pct_change().fillna(0)
t20 = mix(RULE, MIXES["BTC 40 / ETH 40 / SOL 20"], SOL0).pct_change().fillna(0)
res["luck_check"] = {"thirds vs 2-coin, full": boot(three, two, SOL0), "thirds vs 2-coin, 2022+": boot(three, two, "2022-01-01"),
                     "40/40/20 vs 2-coin, 2022+": boot(t20, two, "2022-01-01")}
dr = R.loc["2022-01-01":].copy(); dr = dr[dr.index.weekday < 5]
res["correlation_daily_2022plus"] = {f"{a}-{b}": round(float(dr[a].corr(dr[b])), 2) for a, b in (("BTC", "ETH"), ("BTC", "SOL"), ("ETH", "SOL"))}
sig_sol = pd.Series(signal("SOL"), index=cal)
res["sol_rule_stats"] = {"switches_per_year": round(float(np.nansum(np.abs(np.diff(np.nan_to_num(sig_sol.loc[SOL0:].values)))) / (len(sig_sol.loc[SOL0:]) / 365)), 1),
                         "pct_time_in": round(float(np.nanmean(sig_sol.loc[SOL0:].values)) * 100, 0), "today_in": bool(sig_sol.iloc[-1] == 1),
                         "today_vs_avg_pct": round(float(PX["SOL"].iloc[-1] / PX["SOL"].rolling(N).mean().iloc[-1] - 1) * 100, 1)}
# real SOL ETF since launch: rule on SOL-USD decided each weekday, traded at that day's ETF close vs holding the ETF
etf = {}
for sym in ("BSOL", "GSOL"):
    s = yahoo(sym, 1730000000)
    if s is None or len(s) < 60: etf[sym] = "no data"; continue
    s = s[s.index.weekday < 5]; er = s.pct_change().fillna(0); sg = sig_sol.reindex(s.index).ffill().fillna(0).values
    cr = pd.Series(cash_r, index=cal).reindex(s.index).fillna(0).values * 1.4   # weekday steps cover weekends
    w = 0.0; e = 1.0; eq = []
    for i in range(len(s)):
        e *= 1 + (w * er.values[i] + (1 - w) * cr[i]) if i else 1
        if abs(sg[i] - w) > 0.5: e *= 1 - COST; w = sg[i]
        eq.append(e)
    eq = pd.Series(eq, index=s.index); hold = s / s.iloc[0]
    coin = PX["SOL"].reindex(s.index).ffill(); track = float(np.corrcoef(er.values[1:], coin.pct_change().fillna(0).values[1:])[0, 1])
    etf[sym] = {"from": str(s.index[0].date()), "days": len(s), "rule": stats(eq), "hold_etf": stats(hold), "daily_corr_with_SOL": round(track, 3)}
res["real_sol_etf"] = etf
os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True); json.dump(res, open(OUT, "w"), indent=1)
for k, v in res["table"].items(): print(k, {p: (x["per_year_pct"], x["worst_drop_pct"]) for p, x in v.items()})
print(json.dumps({k: res[k] for k in ("luck_check", "correlation_daily_2022plus", "sol_rule_stats", "real_sol_etf")}, indent=1))
