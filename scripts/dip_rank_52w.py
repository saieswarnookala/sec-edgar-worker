"""Dip-bot ranking test (Nov 15 2026): when more dips fire than free slots, which to buy first? Research only.
Live dip rules on point-in-time S&P 500 (1999-2026): member, price >= $5, above 200-day avg, 5-day return >= 10% worse than SPY,
volume over the drop <= 2x normal. Buy at close, sell when close > 5-day avg (after >= 1 day) or max 5 days. 10 slots x 10%,
idle money in SPY when SPY > its 100-day avg, else cash. Cost 0.05%/side (stress 0.15%). Also bot 6 tuned rules (8%/150-day/hold 7).
Rankings: today's 'biggest 5-day drop first' vs 'deepest below 52-week high first' and variants."""
import os, json, time, urllib.request
import numpy as np, pandas as pd
REL = "https://github.com/Johnbrick123/sp500-data/releases/download/snapshot-2026-11/"
for f in ["prices.parquet", "membership_intervals.parquet"]:
    if not os.path.exists("/tmp/" + f): urllib.request.urlretrieve(REL + f, "/tmp/" + f)
px = pd.read_parquet("/tmp/prices.parquet", columns=["date", "ticker", "close", "adj_close", "volume"])
px["date"] = pd.to_datetime(px.date); px = px[px.date >= "1997-01-01"]
mem = pd.read_parquet("/tmp/membership_intervals.parquet"); mem["start"] = pd.to_datetime(mem.start); mem["end"] = pd.to_datetime(mem.end)
px = px[px.ticker.isin(set(mem.ticker) | {"SPY"})]
dates = pd.DatetimeIndex(sorted(px[px.ticker == "SPY"].date.unique())); ALLT = sorted(px.ticker.unique())
P = lambda v: px.pivot_table(index="date", columns="ticker", values=v, dropna=False).reindex(index=dates, columns=ALLT)
A, RAW, VOL = P("adj_close"), P("close"), P("volume"); del px
tick = [t for t in ALLT if t != "SPY"]; D = len(dates)
M = pd.DataFrame(False, index=dates, columns=tick)
for _, m in mem.iterrows():
    if m.ticker in M.columns:
        e = m.end if pd.notna(m.end) else pd.Timestamp("2100-01-01")
        M.loc[(M.index >= m.start) & (M.index < e), m.ticker] = True
valid = A[tick].notna(); M &= valid & valid.shift(-1, fill_value=False)
Cs = A[tick].ffill(); spy = A["SPY"].ffill()
ex5 = (Cs / Cs.shift(5) - 1).sub(spy / spy.shift(5) - 1, axis=0)
vr = VOL[tick].rolling(5).mean() / VOL[tick].shift(5).rolling(50).mean()
base_ok = M & (RAW[tick] >= 5) & (vr <= 2.0)
SIG = {(d, k): (base_ok & (Cs > Cs.rolling(k).mean()) & (ex5 <= -d)).values for d, k in ((0.10, 200), (0.08, 150))}
H52 = (Cs / Cs.rolling(252, min_periods=200).max() - 1).values      # 0 = at the 52-week high, -0.3 = 30% below
C, M5, RK, SP = Cs.values, Cs.rolling(5).mean().values, ex5.values, spy.values
spyr = np.r_[0, SP[1:] / SP[:-1] - 1]; park_on = np.r_[False, (spy > spy.rolling(100).mean()).values[:-1]]
dn = dates.values; t0 = int(np.searchsorted(dn, np.datetime64("1999-01-01")))
nz = lambda x: 0.0 if x != x else x
KEYS = {"drop": lambda t, j: RK[t, j],                                   # today's rule
        "far20 first": lambda t, j: (0 if nz(H52[t, j]) <= -0.20 else 1, RK[t, j]),
        "deepest below high": lambda t, j: nz(H52[t, j]),
        "nearest high first (opposite)": lambda t, j: -nz(H52[t, j]),
        "random": None}
def sim(rank="drop", sigk=(0.10, 200), hold=5, slots=10, w=0.10, cost=0.0005, only_far=False, seed=0):
    sg = SIG[sigk]; pos, eq, curve, trades, crowded = [], 1.0, np.ones(D), [], 0
    rng = np.random.default_rng(seed)
    for t in range(t0, D):
        r = sum(w * (C[t, p[0]] / C[t - 1, p[0]] - 1) for p in pos)
        if park_on[t]: r += (1 - w * len(pos)) * spyr[t]
        eq *= 1 + r; keep = []
        for p in pos:
            age = t - p[1]
            if age >= 1 and (C[t, p[0]] > M5[t, p[0]] or age >= hold): eq *= 1 - w * 2 * cost; trades.append((p[1], C[t, p[0]] / p[2] - 1 - 2 * cost))
            else: keep.append(p)
        pos = keep; held = {p[0] for p in pos}; free = slots - len(pos)
        if free > 0:
            c = [j for j in np.flatnonzero(sg[t]) if j not in held and (not only_far or nz(H52[t, j]) <= -0.20)]
            if len(c) > free: crowded += 1
            if rank == "random": rng.shuffle(c)
            else: c.sort(key=lambda j: KEYS[rank](t, j))
            for j in c[:free]: pos.append((j, t, C[t, j]))
        curve[t] = eq
    out = {"crowded_days": crowded}
    for name, a, b in (("1999-2026", "1999-01-01", "2100-01-01"), ("1999-2012", "1999-01-01", "2013-01-01"), ("2013-2026", "2013-01-01", "2100-01-01"), ("2022", "2022-01-01", "2023-01-01")):
        idx = np.flatnonzero((dn >= np.datetime64(a)) & (dn < np.datetime64(b)) & (np.arange(D) >= t0))
        cv = curve[idx] / curve[idx[0]]; y = len(idx) / 252; tr = [x[1] for x in trades if a <= str(dn[x[0]])[:10] < b]
        out[name] = {"per_year_pct": round((cv[-1] ** (1 / y) - 1) * 100, 1) if y > 1.5 else round((cv[-1] - 1) * 100, 1),
                     "worst_drop_pct": round(float((cv / np.maximum.accumulate(cv) - 1).min()) * 100, 1),
                     "trades_per_month": round(len(tr) / (y * 12), 1), "avg_trade_pct": round(float(np.mean(tr)) * 100, 2) if tr else None}
    return out
# trade-level: all signals, deep vs near the high (no slot limit)
lv = {}
for sigk, hold in (((0.10, 200), 5), ((0.08, 150), 7)):
    rows = []
    for t in range(t0, D - hold):
        for j in np.flatnonzero(SIG[sigk][t]):
            for k in range(1, hold + 1):
                u = t + k
                if C[u, j] > M5[u, j] or k == hold: rows.append((str(dn[t])[:4] < "2013", nz(H52[t, j]), C[u, j] / C[t, j] - 1 - 0.001)); break
    X = pd.DataFrame(rows, columns=["early", "h", "r"])
    for lab, f in (("20%+ below high", X.h <= -0.20), ("10-20% below", (X.h > -0.20) & (X.h <= -0.10)), ("within 10% of high", X.h > -0.10)):
        g = X[f]; lv[f"{sigk} {lab}"] = {"n": len(g), "avg": round(g.r.mean() * 100, 2), "early": round(g[g.early].r.mean() * 100, 2), "late": round(g[~g.early].r.mean() * 100, 2), "win": round((g.r > 0).mean() * 100, 1)}
        print("TRADES", sigk, lab, lv[f"{sigk} {lab}"], flush=True)
V = []
for sigk, hold, tag in (((0.10, 200), 5, "today"), ((0.08, 150), 7, "bot6")):
    for rk in KEYS: V.append((f"{tag} | {rk}", dict(rank=rk, sigk=sigk, hold=hold)))
    V.append((f"{tag} | only 20%+ below high", dict(rank="drop", sigk=sigk, hold=hold, only_far=True)))
    V.append((f"{tag} | far20 first, 15 slots", dict(rank="far20 first", sigk=sigk, hold=hold, slots=15, w=1/15)))
    V.append((f"{tag} | drop, 15 slots", dict(rank="drop", sigk=sigk, hold=hold, slots=15, w=1/15)))
    V.append((f"{tag} | STRESS drop", dict(rank="drop", sigk=sigk, hold=hold, cost=0.0015)))
    V.append((f"{tag} | STRESS far20 first", dict(rank="far20 first", sigk=sigk, hold=hold, cost=0.0015)))
res = {}
for name, kw in V:
    a = res[name] = sim(**kw)
    print(f"{name:42s} {a['1999-2026']['per_year_pct']}%/yr worst {a['1999-2026']['worst_drop_pct']} | early {a['1999-2012']['per_year_pct']} late {a['2013-2026']['per_year_pct']} 2022 {a['2022']['per_year_pct']} | tr/mo {a['1999-2026']['trades_per_month']} avg {a['1999-2026']['avg_trade_pct']} crowded {a['crowded_days']}", flush=True)
rnd = [sim(rank="random", seed=s)["1999-2026"]["per_year_pct"] for s in range(1, 11)]
print("today rules, random order x10:", rnd, flush=True)
json.dump({"note": __doc__, "trade_level": lv, "results": res, "random_order_today_10_seeds": rnd}, open("data/dip_rank_52w.json", "w"), indent=1)
