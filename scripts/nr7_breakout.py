"""Crabel NR7 / NR4 breakout (Nov 17 2026). Research only, not financial advice.
Idea (Toby Crabel 1990): a day whose high-low range is the narrowest of the last 7 (NR7) or 4 (NR4) days is a 'contraction';
a bigger move often follows. Trade: next day, buy if price breaks above the NR day's high (buy-stop at that high, or at the open
if it gaps above). Stop at the NR day's low. Exits: same-day close (day trade), 2R target else close, or hold 3 days.
Daily open/high/low/close only; if the stop and the target are both inside the same day we assume the STOP hit first.
Point-in-time S&P 500 members 1999-2026, price >= $5. Costs 0.05%/side + 0.05% slippage on stop fills.
Fair baseline: the SAME breakout trade on every ordinary day (not NR) -> does the contraction add anything?
DRY=random|planted: random-walk OHLC (no edge) / NR7 breakouts given +1% next-day drift (must be found)."""
import os, json, urllib.request
import numpy as np, pandas as pd
DRY = os.environ.get("DRY", "")
OUT = "data/nr7_breakout.json" if not DRY else f"/tmp/nr7_{DRY}.json"
COST, SLIP = 0.0005, 0.0005
if DRY:
    rng = np.random.default_rng(2); D, N = 3000, 400
    dates = pd.bdate_range("2004-01-02", periods=D)
    C = 50 * np.exp(np.cumsum(rng.normal(0.0003, 0.018, (D, N)), axis=0)); O = np.vstack([C[:1], C[:-1]]) * np.exp(rng.normal(0, 0.004, (D, N)))
    span = np.abs(rng.normal(0, 0.012, (D, N))) * C; H = np.maximum(O, C) + span * rng.random((D, N)); L = np.minimum(O, C) - span * rng.random((D, N))
    SP = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, D))); MEM = np.ones((D, N), bool)
else:
    REL = "https://github.com/Johnbrick123/sp500-data/releases/download/snapshot-2026-11/"
    for f in ["prices.parquet", "membership_intervals.parquet"]:
        if not os.path.exists("/tmp/" + f): urllib.request.urlretrieve(REL + f, "/tmp/" + f)
    px = pd.read_parquet("/tmp/prices.parquet", columns=["date", "ticker", "open", "high", "low", "close", "adj_close"])
    px["date"] = pd.to_datetime(px.date); px = px[px.date >= "1998-01-01"]
    mem = pd.read_parquet("/tmp/membership_intervals.parquet"); mem["start"] = pd.to_datetime(mem.start); mem["end"] = pd.to_datetime(mem.end)
    px = px[px.ticker.isin(set(mem.ticker) | {"SPY"})]
    f = px.adj_close / px.close                                   # put open/high/low on the adjusted scale
    for c in ("open", "high", "low"): px[c] = px[c] * f
    dates = pd.DatetimeIndex(sorted(px[px.ticker == "SPY"].date.unique())); T = sorted(px.ticker.unique())
    P = lambda v: px.pivot_table(index="date", columns="ticker", values=v, dropna=False).reindex(index=dates, columns=T)
    Op, Hp, Lp, Cp = P("open"), P("high"), P("low"), P("adj_close"); RAW = P("close")
    tick = [t for t in T if t != "SPY"]
    M = pd.DataFrame(False, index=dates, columns=tick)
    for _, m in mem.iterrows():
        if m.ticker in M.columns:
            e = m.end if pd.notna(m.end) else pd.Timestamp("2100-01-01")
            M.loc[(M.index >= m.start) & (M.index < e), m.ticker] = True
    O, H, L, C = Op[tick].values, Hp[tick].values, Lp[tick].values, Cp[tick].values
    SP = Cp["SPY"].ffill().values; MEM = M.values & (RAW[tick].values >= 5)
D, N = C.shape; dn = dates.values
with np.errstate(all="ignore"):
    R = H - L; ok = np.isfinite(R) & (R > 0) & np.isfinite(O) & np.isfinite(C) & MEM
    def nr(k): return ok & (R <= pd.DataFrame(R).rolling(k, min_periods=k).min().values)
    MA200 = pd.DataFrame(C).rolling(200, min_periods=150).mean().values
    up = C > MA200
SIGS = {"NR7": nr(7), "NR4": nr(4)}
SIGS["ordinary day (baseline)"] = ok & ~nr(4)
if DRY == "planted":                                              # +1% the next day after an NR7 breakout
    for t, j in zip(*np.nonzero(SIGS["NR7"][:-1])):
        if H[t + 1, j] > H[t, j]: C[t + 1, j] *= 1.01; H[t + 1, j] = max(H[t + 1, j], C[t + 1, j]); L[t + 1, j] = max(L[t + 1, j], L[t, j] * 1.0001)
def trades(sig, mode, trend=False):
    out = []
    ts, js = np.nonzero(sig[:-4] & (up[:-4] if trend else True))
    for t, j in zip(ts, js):
        u = t + 1; hi, lo = H[t, j], L[t, j]
        if not (np.isfinite(H[u, j]) and H[u, j] > hi): continue          # no breakout -> no trade
        entry = max(O[u, j], hi); risk = entry - lo
        if risk <= 0: continue
        if mode == "close":
            ex = lo * (1 - SLIP) if L[u, j] <= lo else C[u, j]
        elif mode == "2R":
            tgt = entry + 2 * risk
            ex = lo * (1 - SLIP) if L[u, j] <= lo else (tgt if H[u, j] >= tgt else C[u, j])
        else:                                                              # hold 3 days, stop at the NR low
            ex = None
            for k in range(0, 3):
                v = u + k
                if L[v, j] <= lo: ex = lo * (1 - SLIP); break
            if ex is None: ex = C[u + 2, j]
        if not np.isfinite(ex): continue                               # stock stopped trading inside the window
        hold = 1 if mode != "3d" else 3
        r = ex / entry - 1 - 2 * COST
        s = SP[min(u + hold - 1, D - 1)] / SP[u - 1] - 1
        out.append((t, r, r - s))
    return np.array(out) if out else np.zeros((0, 3))
def stats(X):
    if len(X) < 20: return {"n": int(len(X))}
    g = pd.Series(X[:, 1]).groupby(X[:, 0].astype(int)).mean()
    return {"n": int(len(X)), "avg_pct": round(X[:, 1].mean() * 100, 3), "win_pct": round((X[:, 1] > 0).mean() * 100, 1),
            "vs_spy_pct": round(X[:, 2].mean() * 100, 3), "t_vs_spy": round(g.mean() / (g.std() / np.sqrt(len(g))), 2) if len(g) > 2 else None,
            "avg_win_pct": round(X[X[:, 1] > 0, 1].mean() * 100, 2) if (X[:, 1] > 0).any() else None,
            "avg_loss_pct": round(X[X[:, 1] <= 0, 1].mean() * 100, 2) if (X[:, 1] <= 0).any() else None,
            "profit_factor": round(X[X[:, 1] > 0, 1].sum() / -X[X[:, 1] <= 0, 1].sum(), 2) if (X[:, 1] <= 0).any() else None}
t0 = int(np.searchsorted(dn, np.datetime64("1999-06-01" if not DRY else "2005-01-01")))
half = lambda X, a, b: X[(dn[X[:, 0].astype(int)] >= np.datetime64(a)) & (dn[X[:, 0].astype(int)] < np.datetime64(b))] if len(X) else X
RES = {}
for name, sig in SIGS.items():
    sig = sig.copy(); sig[:t0] = False
    for mode in ("close", "2R", "3d"):
        for trend in (False, True):
            X = trades(sig, mode, trend); key = f"{name} | exit {mode}{' | above 200-day' if trend else ''}"
            RES[key] = {"all": stats(X), "1999-2012": stats(half(X, "1999", "2013")), "2013-2026": stats(half(X, "2013", "2100"))}
            a = RES[key]["all"]
            print(f"{key:52s} n={a['n']:7d} avg {a.get('avg_pct')}% win {a.get('win_pct')}% PF {a.get('profit_factor')} vs SPY {a.get('vs_spy_pct')}% (t {a.get('t_vs_spy')}) | early {RES[key]['1999-2012']['all' if False else 'n'] and RES[key]['1999-2012'].get('avg_pct')} late {RES[key]['2013-2026'].get('avg_pct')}", flush=True)
json.dump({"note": __doc__, "dry": DRY or None, "built": str(pd.Timestamp.today().date()), "results": RES}, open(OUT, "w"), indent=1, default=float)
print("wrote", OUT)
