"""S&P 500 additions and removals (Nov 15 2026). Research only, not financial advice.
Known effects: stocks ADDED to the index jump between the announcement and the effective date (index funds must buy), then
may give some back; stocks REMOVED get dumped by index funds and have historically bounced back over the following months.
Data: point-in-time S&P 500 membership 1999-2026 (start = first day as a member, end = first day no longer a member).
We don't have announcement dates (usually ~5 trading days before the change), so:
  - 'add: last 5 days before joining' shows the run-up (NOT tradeable without the announcement date; shown for context)
  - 'add: buy on first day as member' and 'removed: buy on first day out' are tradeable from public lists.
Removed stocks that keep trading are measured to their last price if they stop trading inside the window (no survivor bias
from dropping them). Removals with no price after the end date (mostly takeovers) can't be bought and are skipped.
Returns after 0.2% round-trip costs, vs SPY; t-stats average events per day first."""
import os, json, urllib.request
OUT_IC = "data/index_changes.json" if os.environ.get("DRY") != "1" else "/tmp/index_changes_dry.json"   # never overwrite real results in a test run
import numpy as np, pandas as pd
REL = "https://github.com/Johnbrick123/sp500-data/releases/download/snapshot-2026-11/"
for f in ["prices.parquet", "membership_intervals.parquet"]:
    if not os.path.exists("/tmp/" + f): urllib.request.urlretrieve(REL + f, "/tmp/" + f)
px = pd.read_parquet("/tmp/prices.parquet", columns=["date", "ticker", "adj_close"]); px["date"] = pd.to_datetime(px.date)
px = px[px.date >= "1998-06-01"]
mem = pd.read_parquet("/tmp/membership_intervals.parquet"); mem["start"] = pd.to_datetime(mem.start); mem["end"] = pd.to_datetime(mem.end)
A = px.pivot_table(index="date", columns="ticker", values="adj_close"); dates = A.index; dn = dates.values
SP = A["SPY"].ffill().values; D = len(dates)
COST, H = 0.002, (5, 20, 60, 120, 250)
def path(tk):
    s = A[tk].values if tk in A.columns else None
    return s
def fwd(s, t, h):
    """return from close t to close t+h; if the stock stops trading earlier, use its last price (delisting)"""
    if s is None or t >= D or not np.isfinite(s[t]): return None
    u = min(t + h, D - 1)
    if u - t < h and t + h >= D: return None                 # window runs past today's data
    seg = s[t:u + 1]; ok = np.flatnonzero(np.isfinite(seg))
    return seg[ok[-1]] / s[t] - 1, SP[t + ok[-1]] / SP[t] - 1
def event_table(evs, label, shift=0):
    out = {"events": len(evs)}
    for h in H:
        rows = []
        for tk, t in evs:
            t2 = t + shift
            if t2 < 0: continue
            r = fwd(path(tk), t2, h)
            if r: rows.append((t2, r[0] - COST, r[0] - COST - r[1]))
        if len(rows) < 10: continue
        X = pd.DataFrame(rows, columns=["t", "ret", "ex"]); g = X.groupby("t").ex.mean()
        out[f"{h}d"] = {"n": len(X), "avg_pct": round(X.ret.mean() * 100, 2), "vs_spy_pct": round(X.ex.mean() * 100, 2), "median_vs_spy_pct": round(X.ex.median() * 100, 2),
                        "beat_spy_pct": round((X.ex > 0).mean() * 100, 1), "t_stat": round(g.mean() / (g.std() / np.sqrt(len(g))), 2) if len(g) > 2 else None}
    return out
first_day = mem.start.min()
adds, rems = [], []
for _, m in mem.iterrows():
    if m.start > pd.Timestamp("1999-01-01") and m.start != first_day:
        t = int(np.searchsorted(dn, np.datetime64(m.start)))
        if t < D: adds.append((m.ticker, t, m.start))
    if pd.notna(m.end) and m.end > pd.Timestamp("1999-01-01"):
        t = int(np.searchsorted(dn, np.datetime64(m.end)))
        s = path(m.ticker)
        if t < D and s is not None and np.isfinite(s[t]): rems.append((m.ticker, t, m.end))
print("additions", len(adds), "| removals still trading on removal day", len(rems), flush=True)
RES = {}
for half, a, b in (("1999-2026", "1999", "2100"), ("1999-2012", "1999", "2013"), ("2013-2026", "2013", "2100")):
    sel = lambda E: [(tk, t) for tk, t, d in E if a <= str(d.year) < b]
    RES[half] = {"add: last 5 days before joining (run-up, not tradeable)": event_table(sel(adds), "pre", shift=-5),
                 "add: buy on first day as member": event_table(sel(adds), "post"),
                 "removed: buy on first day out": event_table(sel(rems), "rem"),
                 "removed: buy 20 days after removal": event_table(sel(rems), "rem20", shift=20)}
    for k, v in RES[half].items():
        print(half, f"{k:55s} n={v['events']:4d} ", " | ".join(f"{h}d {v[f'{h}d']['vs_spy_pct']:+.2f}% (t {v[f'{h}d']['t_stat']})" for h in H if f"{h}d" in v and k.startswith("add: last") is False or (f"{h}d" in v and h == 5)), flush=True)
json.dump({"note": __doc__, "built": str(pd.Timestamp.today().date()), "additions": len(adds), "removals_tradeable": len(rems), "results": RES},
          open(OUT_IC, "w"), indent=1, default=float)
print("wrote", OUT_IC)
