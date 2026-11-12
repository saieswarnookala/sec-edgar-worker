"""Short-side / opposite-direction tests: can our strategies make money when the market falls?
Point-in-time S&P 500 incl. delisted stocks (Johnbrick123/sp500-data), 1998-2026. Close-to-close, 0.15% cost per side,
short borrow fee 1%/yr (S&P 500 stocks are usually cheaper), no interest on idle cash. Not financial advice.
  dip_long     our dip rule (reference, simplified: no volume filter / parking)
  dip_inverse  short exactly what dip_long buys (sanity check)
  rip_short    mirror of dip: weak stock (below 200-day) that jumped >= X% more than SPY in 5 days -> short,
               cover when close < 5-day average or after 5 days
  drift_short  mirror of drift: stock lagged SPY by >= Y% on its earnings reaction day -> short next close, hold H days
  spy_*        market timing with SPY: short when below its 200-day average (else cash / else long)
"""
import os, sys, json, urllib.request
import numpy as np, pandas as pd
OUT = sys.argv[1] if len(sys.argv) > 1 else "data/short_side.json"
REL = "https://github.com/Johnbrick123/sp500-data/releases/download/snapshot-2026-11/"
for f in ["prices.parquet", "membership_intervals.parquet"]:
    if not os.path.exists("/tmp/" + f): urllib.request.urlretrieve(REL + f, "/tmp/" + f)
px = pd.read_parquet("/tmp/prices.parquet", columns=["date", "ticker", "adj_close"]); px["date"] = pd.to_datetime(px.date); px = px[px.date >= "1996-06-01"]
mem = pd.read_parquet("/tmp/membership_intervals.parquet"); mem["start"] = pd.to_datetime(mem.start); mem["end"] = pd.to_datetime(mem.end)
px = px[px.ticker.isin(set(mem.ticker) | {"SPY"})]
dates = pd.DatetimeIndex(sorted(px[px.ticker == "SPY"].date.unique())); T = sorted(px.ticker.unique())
C = px.pivot_table(index="date", columns="ticker", values="adj_close").reindex(index=dates, columns=T); del px
tick = [t for t in T if t != "SPY"]; ti = {t: i for i, t in enumerate(tick)}; D = len(dates)
V = C[tick].notna().values; Cf = C.ffill(); P = Cf[tick].values; spy = Cf["SPY"].values
M = np.zeros((D, len(tick)), bool)
for _, m in mem.iterrows():
    if m.ticker in ti: M[(dates >= m.start) & (dates < (m.end if pd.notna(m.end) else pd.Timestamp("2100-01-01"))), ti[m.ticker]] = True
M &= V
lastv = np.array([np.where(V[:, j])[0][-1] if V[:, j].any() else D - 1 for j in range(len(tick))])
r5 = (Cf[tick] / Cf[tick].shift(5) - 1).values - (spy / np.roll(spy, 5) - 1)[:, None]
above200 = (Cf[tick] > Cf[tick].rolling(200).mean()).values
ma5 = Cf[tick].rolling(5).mean().values
spy200 = spy > pd.Series(spy).rolling(200).mean().values; spy100 = spy > pd.Series(spy).rolling(100).mean().values
START = int(np.searchsorted(dates.values, np.datetime64("1998-01-02"))); T04 = int(np.searchsorted(dates.values, np.datetime64("2004-09-01")))
COST, FEE = 0.0015, 0.01

# earnings reaction (stock minus SPY on reaction day), stored on the reaction day
SEC = json.load(open("data/sec_events_sic.json"))["tickers"]; ds = dates.strftime("%Y-%m-%d").values
RX = np.full((D, len(tick)), np.nan)
for t, j in ti.items():
    for d, mi in (SEC.get(t) or {}).get("events", []):
        k = int(np.searchsorted(ds, d))
        if k < D and ds[k] == d and mi >= 570: k += 1
        if 1 <= k < D and M[k, j] and P[k - 1, j] > 0: RX[k, j] = P[k, j] / P[k - 1, j] - 1 - (spy[k] / spy[k - 1] - 1)

def sim(sig, side, slots=10, exit_smart=True, hold=5, start=START, gate=None):
    """sig[t,j] True -> open position at close t (side +1 long / -1 short). Returns daily equity curve."""
    cash = 1.0; pos = {}   # j -> [shares, entry_t]
    curve = np.empty(D - start); n = 0
    for k, t in enumerate(range(start, D)):
        for j in list(pos):
            sh, t0 = pos[j]; p = P[min(t, lastv[j]), j]
            if side < 0: cash -= abs(sh) * p * FEE / 252
            done = t >= lastv[j] or (t - t0 >= hold) or (exit_smart and t - t0 >= 1 and (P[t, j] > ma5[t, j] if side > 0 else P[t, j] < ma5[t, j]))
            if done: cash += sh * p - abs(sh) * p * COST; del pos[j]
        eq = cash + sum(sh * P[t, j] for j, (sh, _) in pos.items())
        if gate is None or gate[t]:
            c = np.where(sig[t] & M[t])[0]
            c = [j for j in c[np.argsort(r5[t, c] * side)] if j not in pos]   # most extreme first
            for j in c[: max(0, slots - len(pos))]:
                amt = eq / slots; sh = side * amt / P[t, j]; cash -= sh * P[t, j] + amt * COST; pos[j] = [sh, t]; n += 1
        curve[k] = cash + sum(sh * P[t, j] for j, (sh, _) in pos.items())
    return pd.Series(curve, index=dates[start:]), n

def spy_timing(rule, start=START, short_gate=spy200, long_when_up=False):
    eq = 1.0; out = []
    for t in range(start, D):
        if t > start:
            r = spy[t] / spy[t - 1] - 1; up = short_gate[t - 1]
            if not up: eq *= 1 - r - FEE / 252
            elif long_when_up: eq *= 1 + r
            if short_gate[t - 1] != short_gate[t - 2]: eq *= 1 - COST * (2 if long_when_up else 1)
        out.append(eq)
    return pd.Series(out, index=dates[start:])

BEARS = {"2000-02 dot-com": ("2000-03-24", "2002-10-09"), "2008 crisis": ("2007-10-09", "2009-03-09"), "2020 covid": ("2020-02-19", "2020-03-23"), "2022 bear": ("2022-01-03", "2022-10-12")}
def stats(c):
    c = c / c.iloc[0]; yrs = len(c) / 252
    b = {}
    for k, (a, z) in BEARS.items():
        s = c[(c.index >= a) & (c.index <= z)]
        b[k] = round((s.iloc[-1] / s.iloc[0] - 1) * 100, 1) if len(s) > 2 else None
    m = c.resample("ME").last().pct_change().dropna(); sm = spyc.reindex(c.index).resample("ME").last().pct_change().dropna()
    down = sm[sm < 0].index.intersection(m.index)
    return {"cagr": round((c.iloc[-1] ** (1 / yrs) - 1) * 100, 1), "max_dd": round(float((c / c.cummax() - 1).min()) * 100, 1), "bears": b,
            "avg_in_spy_down_months": round(float(m.loc[down].mean()) * 100, 2), "corr_spy_monthly": round(float(m.corr(sm.reindex(m.index))), 2)}
spyc = pd.Series(spy[START:] / spy[START], index=dates[START:])
R = {"SPY": stats(spyc)}
dip = (r5 <= -0.10) & above200
def add(name, c, n=None):
    R[name] = stats(c); R[name]["trades"] = n; print(name, R[name], flush=True); CURVES[name] = c
CURVES = {}
c, n = sim(dip, +1); add("dip_long (reference)", c, n)
c, n = sim(dip, -1); add("dip_inverse (short our dip buys)", c, n)
for X in (0.08, 0.10, 0.12):
    c, n = sim((r5 >= X) & ~above200, -1); add(f"rip_short {int(X*100)}% weak stocks", c, n)
c, n = sim(r5 >= 0.10, -1); add("rip_short 10% any stock", c, n)
c, n = sim((r5 >= 0.10) & ~above200, -1, gate=~spy200); add("rip_short 10% only when SPY below 200d", c, n)
for Y in (0.04, 0.06, 0.08):
    for H in (20, 60):
        c, n = sim(RX <= -Y, -1, exit_smart=False, hold=H, start=T04); add(f"drift_short {int(Y*100)}% hold {H}d (2004+)", c, n)
add("spy_short_below_200d_else_cash", spy_timing(None))
add("spy_short_below_100d_else_cash", spy_timing(None, short_gate=spy100))
add("spy_long_above_short_below_200d", spy_timing(None, long_when_up=True))
# combine with the live dip strategy (realistic daily curve) 70/30, monthly rebalanced
try:
    dipc = pd.read_csv("data/dip_curve.csv", index_col=0, parse_dates=True)["realistic"]
    def blend(a, b, w):
        idx = a.index.intersection(b.index); ra, rb = a.reindex(idx).pct_change().fillna(0), b.reindex(idx).pct_change().fillna(0); m = idx.to_period("M"); v = 1.0; out = []
        for i in range(len(idx)):
            if i == 0 or m[i] != m[i - 1]: va, vb = v * w, v * (1 - w)
            va *= 1 + ra.iloc[i]; vb *= 1 + rb.iloc[i]; v = va + vb; out.append(v)
        return pd.Series(out, index=idx)
    R["live_dip_strategy"] = stats(dipc.reindex(dates[START:]).ffill())
    R["combos_70_dip_30_x"] = {}
    for name in ["rip_short 10% weak stocks", "drift_short 6% hold 60d (2004+)", "spy_short_below_200d_else_cash"]:
        R["combos_70_dip_30_x"][name] = stats(blend(dipc, CURVES[name], 0.7)); print("70/30", name, R["combos_70_dip_30_x"][name], flush=True)
except FileNotFoundError: pass
json.dump(R, open(OUT, "w"), indent=1, default=float)
