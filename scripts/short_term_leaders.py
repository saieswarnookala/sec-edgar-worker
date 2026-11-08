# Short-term leaders research: survivorship-free S&P 500 (Johnbrick123/sp500-data), point-in-time members.
# Tests many signal x entry x hold variants, overlapping cohorts, idle -> SPY, costs per side. Research only.
import os, json, urllib.request
import pandas as pd, numpy as np
REL = "https://github.com/Johnbrick123/sp500-data/releases/download/snapshot-2026-11/"
for f in ["prices.parquet", "membership_intervals.parquet"]:
    if not os.path.exists("/tmp/" + f): urllib.request.urlretrieve(REL + f, "/tmp/" + f)
import pyarrow.parquet as pq
cols = pq.ParquetFile("/tmp/prices.parquet").schema.names
LOG = {"price_columns": cols}
use = ["date", "ticker", "open", "close", "adj_close"] + (["volume"] if "volume" in cols else [])
px = pd.read_parquet("/tmp/prices.parquet", columns=use); px["date"] = pd.to_datetime(px.date)
START = "1998-01-01"; px = px[px.date >= "1997-06-01"]
mem = pd.read_parquet("/tmp/membership_intervals.parquet"); mem["start"] = pd.to_datetime(mem.start); mem["end"] = pd.to_datetime(mem.end)
px = px[px.ticker.isin(set(mem.ticker) | {"SPY"})]
px["aopen"] = px.open * px.adj_close / px.close
if "volume" in px: px["dv"] = px.volume * px.close
dates = sorted(px[px.ticker == "SPY"].date.unique()); 
P = lambda v: px.pivot_table(index="date", columns="ticker", values=v).reindex(dates)
C, O = P("adj_close"), P("aopen"); valid = C.notna()
DV = P("dv") if "dv" in px else None
del px
Cf = C.ffill(); r = Cf.pct_change()
spy = r["SPY"].fillna(0); tick = [t for t in C.columns if t != "SPY"]
# PIT membership mask
M = pd.DataFrame(False, index=dates, columns=tick)
for _, m in mem.iterrows():
    if m.ticker not in M.columns: continue
    e = m.end if pd.notna(m.end) else pd.Timestamp("2100-01-01")
    M.loc[(M.index >= m.start) & (M.index < e), m.ticker] = True
M &= valid[tick] & valid[tick].shift(-1, fill_value=False)  # tradable today and tomorrow
LOG["days"], LOG["tickers"], LOG["avg_members"] = len(dates), len(tick), float(M.sum(1)[M.index >= START].mean())
R = {k: Cf[tick] / Cf[tick].shift(k) - 1 for k in (1, 5, 20)}
RV = (DV[tick] / DV[tick].rolling(20).mean().shift(1)) if DV is not None else None
ex = {k: R[k].sub(R[k].index.map(lambda d: 0), axis=0) for k in R}
spyk = {k: Cf["SPY"] / Cf["SPY"].shift(k) - 1 for k in (1, 5, 20)}
for k in R: ex[k] = R[k].sub(spyk[k], axis=0)
Rt, Ot = r[tick], (Cf[tick] / O[tick] - 1)  # close-to-close; open-to-close
on = (O[tick] / Cf[tick].shift(1) - 1)          # overnight
def picks(score, n, mask):
    s = score.where(mask)
    rk = s.rank(axis=1, ascending=False, method="first")
    return (rk <= n)
def run(pk, hold, entry="close", cost=0.0005):
    """pk: bool picks on signal day t. entry close t or open t+1. returns daily portfolio returns."""
    pk = pk.astype(float); port = pd.Series(0.0, index=dates); w = 1.0 / hold
    for k in range(1, hold + 1):
        sel = pk.shift(k) if entry == "close" else pk.shift(k)  # cohort formed on t, live on t+k
        cnt = sel.sum(1)
        if entry == "open" and k == 1: day = Ot
        else: day = Rt
        mean = (sel * day.fillna(0)).sum(1) / cnt.replace(0, np.nan)
        port += w * mean.fillna(spy)  # empty cohort parked in SPY
    port -= (2 * cost) / hold
    return port
def stats(p):
    p = p[p.index >= START]; eq = (1 + p).cumprod(); yrs = len(p) / 252
    cagr = eq.iloc[-1] ** (1 / yrs) - 1; dd = (eq / eq.cummax() - 1).min()
    sh = p.mean() / p.std() * np.sqrt(252) if p.std() > 0 else 0
    per = {}
    for a, b in [("1998", "2002"), ("2003", "2007"), ("2008", "2009"), ("2010", "2015"), ("2016", "2020"), ("2021", "2026")]:
        q = p[(p.index >= a) & (p.index <= b + "-12-31")]
        per[a + "-" + b] = round(100 * ((1 + q).prod() ** (252 / max(len(q), 1)) - 1), 1)
    return {"cagr": round(100 * cagr, 1), "dd": round(100 * dd, 1), "sharpe": round(sh, 2), "per": per}
OUT = {"SPY": stats(spy)}
mask = M
VAR = []
def add(name, pk, holds=(1, 3, 5, 10, 20), entries=("close", "open")):
    for h in holds:
        for e in entries:
            s = stats(run(pk, h, e)); s.update(name=name, hold=h, entry=e); VAR.append(s)
N = 10
add("top10 1d winners", picks(ex[1], N, mask))
add("top10 1d losers (reversal)", picks(-ex[1], N, mask))
add("top10 5d winners", picks(ex[5], N, mask))
add("top10 5d losers (reversal)", picks(-ex[5], N, mask))
add("top10 20d winners", picks(ex[20], N, mask))
if RV is not None:
    hv = mask & (RV >= 2)
    add("1d winners, volume>=2x", picks(ex[1], N, hv))
    add("1d losers, volume>=2x", picks(-ex[1], N, hv))
    add("5d winners, volume>=2x", picks(ex[5], N, hv))
    # Medhat-Schmeling: 20d winners among high turnover (top quintile of RV20 ratio)
    rv20 = DV[tick].rolling(20).mean() / DV[tick].rolling(120).mean()
    hiq = rv20.where(mask).rank(axis=1, pct=True) >= 0.8
    add("20d winners, high-turnover quintile", picks(ex[20], N, mask & hiq))
    add("20d losers, low-turnover quintile (reversal)", picks(-ex[20], N, mask & (rv20.where(mask).rank(axis=1, pct=True) <= 0.2)))
    add("1d winners, low volume (<1x)", picks(ex[1], N, mask & (RV < 1)))
# overnight vs intraday split for 1d winners / losers
for nm, sc in [("1d winners", ex[1]), ("1d losers", -ex[1])]:
    pk = picks(sc, N, mask).astype(float)
    for leg, ser in [("overnight (close->next open)", on), ("intraday (next open->close)", Ot)]:
        sel = pk.shift(1); p = ((sel * ser.fillna(0)).sum(1) / sel.sum(1).replace(0, np.nan)).fillna(0) - 0.001
        s = stats(p); s.update(name=f"{nm} {leg}", hold=1, entry="split"); VAR.append(s)
# random baseline: random 10 members, hold 5, close
rng = np.random.default_rng(7); RB = []
for i in range(30):
    rnd = pd.DataFrame(rng.random(M.shape), index=dates, columns=tick)
    RB.append(stats(run(picks(rnd, N, mask), 5, "close"))["cagr"])
OUT["random_hold5_cagr"] = {"median": float(np.median(RB)), "p95": float(np.percentile(RB, 95)), "max": float(max(RB))}
VAR.sort(key=lambda v: -v["cagr"])
OUT["variants"] = VAR; OUT["log"] = LOG
os.makedirs("data", exist_ok=True); json.dump(OUT, open("data/short_term_leaders.json", "w"), indent=1)
print(json.dumps(OUT["SPY"]), OUT["random_hold5_cagr"])
for v in VAR[:25]: print(v["name"], v["hold"], v["entry"], v["cagr"], v["dd"], v["sharpe"], v["per"])
print("...worst"); [print(v["name"], v["hold"], v["entry"], v["cagr"], v["dd"]) for v in VAR[-6:]]
