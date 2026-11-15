"""Month-end timing test (Nov 15 2026). Research only, not financial advice.
1) Turn of the month: average SPY/QQQ/IWM daily return by trading day around month-end (-6..+6), split into
   1993-2008, 2009-2015, 2016-2026 and the T+1 era (Jun 2024+). Is the -3..+3 window still better than other days?
2) Pension rebalancing (Harvey, Mazzoleni & Melone 2025 idea): 3 trading days before month-end, if stocks beat bonds
   month-to-date by a lot, pensions must sell stocks -> next days weaker? Return from that close to the close of the
   1st trading day of the next month, by stocks-minus-bonds tercile.
3) Overlays the bots can actually use:
   a) monthly deposit invested on day -4 (before the window) vs day +1 (first day of month) vs day +4: value after 1 year
   b) Clear Leader-style monthly rebalance: does trading at the close of day -4 instead of the last day change results?
      (proxy: hold SPY, switch timing only matters through the window, so measured as SPY return from day -4 to day 0)
Data: Yahoo daily total-return closes. Bonds: IEF (VFITX before 2002)."""
import json, time, urllib.request, urllib.parse
import numpy as np, pandas as pd

def yahoo(sym):
    for a in range(4):
        try:
            u = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?period1=0&period2={int(time.time())}&interval=1d&events=div%2Csplit"
            j = json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=60))["chart"]["result"][0]
            adj = (j["indicators"].get("adjclose") or [{}])[0].get("adjclose") or j["indicators"]["quote"][0]["close"]
            s = pd.Series(adj, index=pd.to_datetime([time.strftime("%Y-%m-%d", time.gmtime(t)) for t in j["timestamp"]])).dropna()
            s = s[s > 0]; return s[~s.index.duplicated()].sort_index()
        except Exception as e: err = e; time.sleep(3 * (a + 1))
    print("FAIL", sym, err, flush=True); return None

SYMS = ["SPY", "QQQ", "IWM", "IEF", "VFITX"]
data = {}
for s in SYMS:
    x = yahoo(s); time.sleep(0.4)
    print("ticker check", s, "rows", 0 if x is None else len(x), "" if x is None else f"{x.index[0].date()}..{x.index[-1].date()}", flush=True)
    if x is not None and len(x) > 250: data[s] = x
missing = [s for s in ["SPY", "IEF"] if s not in data]
if missing: raise SystemExit(f"required tickers missing: {missing}")
spy = data["SPY"]; dates = spy.index[spy.index >= "1993-03-01"]
px = pd.DataFrame({s: v for s, v in data.items()}).reindex(dates).ffill()
bond = px["IEF"].copy()
if "VFITX" in px:   # splice VFITX before IEF existed
    first = px["IEF"].first_valid_index(); sc = px.loc[first, "IEF"] / px.loc[first, "VFITX"]
    bond.loc[:first] = px.loc[:first, "VFITX"] * sc
ret = px.pct_change(); bret = bond.pct_change()
# trading-day position relative to month end: 0 = last trading day of the month, +1 = first day of next month, -1 = day before last
ym = dates.to_period("M"); last_idx = pd.Series(np.arange(len(dates)), index=dates).groupby(ym).transform("max").values
first_idx = pd.Series(np.arange(len(dates)), index=dates).groupby(ym).transform("min").values
i = np.arange(len(dates)); to_end = i - last_idx; from_start = i - first_idx + 1     # to_end: 0,-1,-2..  from_start: 1,2,3..
pos = np.where(-to_end <= 6, to_end, np.where(from_start <= 6, from_start, 99))
PER = {"1993-2008": ("1993-01-01", "2009-01-01"), "2009-2015": ("2009-01-01", "2016-01-01"), "2016-2026": ("2016-01-01", "2100-01-01"),
       "T+1 era (Jun 2024+)": ("2024-06-01", "2100-01-01")}
out = {"note": __doc__, "first_day": str(dates[0].date()), "last_day": str(dates[-1].date())}
tom = {}
for s in ["SPY", "QQQ", "IWM"]:
    if s not in ret: continue
    tom[s] = {}
    for pn, (a, b) in PER.items():
        m = (dates >= a) & (dates < b); r = ret[s][m]; p = pos[m]
        by = {int(k): round(float(r[p == k].mean()) * 1e4, 1) for k in range(-6, 7) if (p == k).any()}
        win = (p >= -3) & (p <= 3) & (p != 99); other = ~win
        tom[s][pn] = {"avg_bps_by_day (0=last day, 1=first day)": by,
                      "window_-3_to_+3_bps": round(float(r[win].mean()) * 1e4, 1), "other_days_bps": round(float(r[other].mean()) * 1e4, 1),
                      "diff_t": round(float((r[win].mean() - r[other].mean()) / np.sqrt(r[win].var() / win.sum() + r[other].var() / other.sum())), 2),
                      "share_of_all_gains_pct": round(float(r[win].sum() / r.sum()) * 100, 0) if r.sum() > 0 else None,
                      "days_in_window_pct": round(float(win.mean()) * 100, 0)}
out["turn_of_month"] = tom
# 2) pension rebalancing signal
rows = []
for mo in sorted(set(ym)):
    idx = np.flatnonzero(ym == mo)
    if len(idx) < 8: continue
    sig_day = idx[-4]                 # close of day -3
    nxt = np.flatnonzero(ym == mo + 1)
    if not len(nxt): continue
    end_day = nxt[0]                  # close of day +1
    mstart = idx[0] - 1
    if mstart < 0: continue
    s_mtd = px["SPY"].iloc[sig_day] / px["SPY"].iloc[mstart] - 1; b_mtd = bond.iloc[sig_day] / bond.iloc[mstart] - 1
    fwd = px["SPY"].iloc[end_day] / px["SPY"].iloc[sig_day] - 1
    rows.append({"month": str(mo), "gap": s_mtd - b_mtd, "fwd": fwd, "date": dates[sig_day]})
pr = pd.DataFrame(rows)
pens = {}
for pn, (a, b) in PER.items():
    q = pr[(pr.date >= a) & (pr.date < b)]
    if len(q) < 12: continue
    lo, hi = q.gap.quantile([1 / 3, 2 / 3])
    g = {"stocks lagged bonds (bottom third)": q[q.gap <= lo], "middle": q[(q.gap > lo) & (q.gap < hi)], "stocks beat bonds (top third)": q[q.gap >= hi]}
    pens[pn] = {k: {"months": len(v), "avg_fwd_bps": round(float(v.fwd.mean()) * 1e4, 1), "up_pct": round(float((v.fwd > 0).mean()) * 100, 0)} for k, v in g.items()}
    pens[pn]["corr_gap_vs_fwd"] = round(float(q.gap.corr(q.fwd)), 3)
out["pension_rebalancing"] = pens
# 3a) monthly deposit timing: invest $1 each month on day -4, day +1 or day +4; value 12 months later in SPY
def entry_day(mo, which):
    idx = np.flatnonzero(ym == mo)
    if which == "-4": return idx[-5] if len(idx) >= 5 else None
    nxt = np.flatnonzero(ym == mo + 1)
    if which == "+1": return nxt[0] if len(nxt) else None
    if which == "+4": return nxt[3] if len(nxt) >= 4 else None
dep = {}
for pn, (a, b) in PER.items():
    res = {}
    for w in ("-4", "+1", "+4"):
        g = []
        for mo in sorted(set(ym)):
            e = entry_day(mo, w)
            if e is None or not (a <= str(dates[e].date()) < b) or e + 252 >= len(dates): continue
            g.append(px["SPY"].iloc[e + 252] / px["SPY"].iloc[e] - 1)
        res[f"buy on day {w}"] = {"n": len(g), "avg_12m_return_pct": round(float(np.mean(g)) * 100, 2) if g else None}
    dep[pn] = res
out["deposit_timing"] = dep
# 3b) rebalance a few days early: SPY return from day -4 close to day 0 close (what you'd gain/lose by being in vs out)
early = {}
for pn, (a, b) in PER.items():
    v = []
    for mo in sorted(set(ym)):
        idx = np.flatnonzero(ym == mo)
        if len(idx) < 6 or not (a <= str(dates[idx[-1]].date()) < b): continue
        v.append(px["SPY"].iloc[idx[-1]] / px["SPY"].iloc[idx[-5]] - 1)
    v = np.array(v); early[pn] = {"months": len(v), "avg_bps_day-4_to_0": round(float(v.mean()) * 1e4, 1), "any_4_days_avg_bps": round(float(ret["SPY"][(dates >= a) & (dates < b)].mean() * 4) * 1e4, 1)}
out["last_4_days"] = early
json.dump(out, open("data/month_end.json", "w"), indent=1, default=str)
for s, v in tom.items():
    for pn, x in v.items(): print(s, pn, "window", x["window_-3_to_+3_bps"], "other", x["other_days_bps"], "t", x["diff_t"], "share", x["share_of_all_gains_pct"])
print(json.dumps(pens, indent=1)); print(json.dumps(dep, indent=1)); print(json.dumps(early, indent=1))
