"""Where does money go when the US market crashes? (Nov 18 2026). Research only, not financial advice.
Crashes = every SPY fall of 10%+ from a high since 1995 (found automatically from SPY total-return prices): peak -> bottom.
For each crash: what each asset did from the peak to the bottom, and in the 3 months after the bottom.
Price moves show where buyers went (an asset that rises while stocks fall is being bought). Plus the money-flow data that is free:
FRED weekly money-market fund assets (retail WRMFNS, institutional WIMFNS: cash piles = 'moved to cash'), 10-year and 2-year
Treasury yields (falling yield = bonds being bought), junk-bond spread (rising = credit being sold).
Assets (Yahoo adjclose = with dividends; older funds fill the years before an ETF existed):
  Treasuries long TLT<-VUSTX, mid IEF<-VFITX, short SHY<-VFISX; TIPS TIP<-VIPSX; corporate LQD<-VWESX; junk HYG<-VWEHX;
  gold GLD<-GC=F; silver SLV<-SI=F; oil CL=F; dollar UUP<-DX-Y.NYB; yen and Swiss franc (vs dollar); bitcoin (2014+);
  US sectors XLU XLP XLV XLK XLE XLF XLY XLI XLB; REITs VNQ<-VGSIX; developed intl EFA<-VGTSX; emerging EEM<-VEIEX;
  India in USD INDA<-EPI<-Sensex/INR; low-volatility stocks USMV (2011+).
DRY=1: synthetic prices (no network) to test the code."""
import os, json, time, urllib.request, urllib.parse, io
import numpy as np, pandas as pd
DRY = os.environ.get("DRY", ""); OUT = "data/crash_flows.json" if not DRY else "/tmp/crash_flows_dry.json"
START, MIN_DROP = "1995-01-01", 0.10
def ydaily(sym, adj=True):
    if DRY:
        rng = np.random.default_rng(abs(hash(sym)) % 2**32); d = pd.bdate_range(START, "2026-11-13")
        return pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, len(d)))), index=d)
    err = None
    for a in range(5):
        try:
            u = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?period1=0&period2={int(time.time())}&interval=1d&events=div%2Csplit"
            j = json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=60))["chart"]["result"][0]
            q = j["indicators"]; v = ((q.get("adjclose") or [{}])[0].get("adjclose") if adj else None) or q["quote"][0]["close"]
            s = pd.Series({pd.Timestamp(time.strftime("%Y-%m-%d", time.gmtime(t))): x for t, x in zip(j["timestamp"], v) if x and x > 0})
            time.sleep(0.4); return s[~s.index.duplicated()].sort_index()
        except Exception as e: err = e; time.sleep(3 * (a + 1))
    print("Yahoo failed", sym, err, flush=True); return pd.Series(dtype=float)
def fred(series):
    if DRY:
        d = pd.date_range(START, "2026-11-13", freq="W-MON"); return pd.Series(np.linspace(1000, 3000, len(d)), index=d)
    for a in range(5):
        try:
            txt = urllib.request.urlopen(urllib.request.Request(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}", headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read().decode()
            df = pd.read_csv(io.StringIO(txt)); df.columns = ["date", "v"]
            s = pd.to_numeric(df.v, errors="coerce"); s.index = pd.to_datetime(df.date); return s.dropna()
        except Exception as e: err = e; time.sleep(3 * (a + 1))
    print("FRED failed", series, err, flush=True); return pd.Series(dtype=float)

spy = ydaily("SPY"); spy = spy[spy.index >= START]; days = spy.index
if len(spy) < 5000: raise SystemExit(f"SPY history too short ({len(spy)} days)")
def on_days(s): return s.reindex(s.index.union(days)).ffill(limit=5).reindex(days) if len(s) else pd.Series(np.nan, index=days)
def chain(*parts):
    """newest first; older stand-ins fill earlier days. -> level series on SPY days"""
    r = pd.Series(np.nan, index=days)
    for p in parts:
        lvl = on_days(p if isinstance(p, pd.Series) else ydaily(p)); r = r.where(r.notna(), lvl.pct_change(fill_method=None))
    return (1 + r.fillna(0)).cumprod().where(r.notna().cumsum() > 0)
inv = lambda s: 1 / s if len(s) else s
sx, inr = ydaily("^BSESN", adj=False), ydaily("INR=X", adj=False); j = sx.index.intersection(inr.index)
ASSETS = {
    "Long Treasuries": chain("TLT", "VUSTX"), "Mid Treasuries": chain("IEF", "VFITX"), "Short Treasuries": chain("SHY", "VFISX"),
    "TIPS (inflation bonds)": chain("TIP", "VIPSX"), "Corporate bonds": chain("LQD", "VWESX"), "Junk bonds": chain("HYG", "VWEHX"),
    "Gold": chain("GLD", "GC=F"), "Silver": chain("SLV", "SI=F"), "Oil": chain("CL=F"),
    "US dollar": chain("UUP", ydaily("DX-Y.NYB", adj=False)), "Japanese yen": chain(inv(ydaily("JPY=X", adj=False))), "Swiss franc": chain(inv(ydaily("CHF=X", adj=False))),
    "Bitcoin": chain("BTC-USD"),
    "Utilities": chain("XLU"), "Consumer staples": chain("XLP"), "Health care": chain("XLV"), "Tech": chain("XLK"), "Energy": chain("XLE"),
    "Financials": chain("XLF"), "Consumer discretionary": chain("XLY"), "Industrials": chain("XLI"), "Materials": chain("XLB"),
    "Low-volatility US stocks": chain("USMV", "SPLV"), "REITs": chain("VNQ", "VGSIX"),
    "Developed intl": chain("EFA", "VGTSX"), "Emerging": chain("EEM", "VEIEX"), "India (USD)": chain("INDA", "EPI", (sx[j] / inr[j]).dropna()),
}
print("asset data starts:", {k: (str(v.first_valid_index())[:10] if v.notna().any() else None) for k, v in ASSETS.items()}, flush=True)

# ---------------- find crashes: SPY falls >= 10% from its high
peak_lvl, peak_day, episodes, low = spy.iloc[0], days[0], [], None
for d, v in spy.items():
    if v >= peak_lvl:
        if low and low[1] / peak_lvl - 1 <= -MIN_DROP: episodes.append((peak_day, low[0], low[1] / peak_lvl - 1))
        peak_lvl, peak_day, low = v, d, None
    elif not low or v < low[1]: low = (d, v)
if low and low[1] / peak_lvl - 1 <= -MIN_DROP: episodes.append((peak_day, low[0], low[1] / peak_lvl - 1))
print(f"{len(episodes)} crashes of {MIN_DROP*100:.0f}%+ since {START}", flush=True)

FL = {"Money-market funds, retail ($bn)": fred("WRMFNS"), "Money-market funds, institutional ($bn)": fred("WIMFNS"),
      "10-yr Treasury yield (%)": fred("DGS10"), "2-yr Treasury yield (%)": fred("DGS2"), "Junk-bond spread (%)": fred("BAMLH0A0HYM2")}
def at(s, d):
    s = s[s.index <= d]; return float(s.iloc[-1]) if len(s) else None
def ret(lvl, a, b):
    x, y = lvl.asof(a) if lvl.notna().any() else np.nan, lvl.asof(b) if lvl.notna().any() else np.nan
    return round((y / x - 1) * 100, 1) if np.isfinite(x) and np.isfinite(y) and lvl.first_valid_index() is not None and lvl.first_valid_index() <= a else None
CR = []
for p, t, dd in episodes:
    after = days[min(days.get_loc(t) + 63, len(days) - 1)]
    row = {"peak": str(p)[:10], "bottom": str(t)[:10], "spy_drop_pct": round(dd * 100, 1), "days": int(days.get_loc(t) - days.get_loc(p)),
           "spy_3mo_after_bottom_pct": ret(spy, t, after),
           "during": {k: ret(v, p, t) for k, v in ASSETS.items()}, "after_3mo": {k: ret(v, t, after) for k, v in ASSETS.items()}, "flows": {}}
    for k, s in FL.items():
        a, b = at(s, p), at(s, t)
        if a is not None and b is not None and s.index[0] <= p: row["flows"][k] = {"at_peak": round(a, 2), "at_bottom": round(b, 2), "change": round(b - a, 2)}
    CR.append(row)
    up = sorted([(v, k) for k, v in row["during"].items() if v is not None], reverse=True)
    print(f"{row['peak']} -> {row['bottom']} SPY {row['spy_drop_pct']}% | best: " + ", ".join(f"{k} {v:+}%" for v, k in up[:5]) + " | worst: " + ", ".join(f"{k} {v:+}%" for v, k in up[-3:])
          + " | " + "; ".join(f"{k.split(' (')[0]} {v['change']:+}" for k, v in row["flows"].items()), flush=True)
# summary across crashes
SUM = {}
for k in ASSETS:
    xs = [c["during"][k] for c in CR if c["during"][k] is not None]; ys = [c["after_3mo"][k] for c in CR if c["after_3mo"][k] is not None]
    big = [c["during"][k] for c in CR if c["during"][k] is not None and c["spy_drop_pct"] <= -20]
    if xs: SUM[k] = {"crashes_with_data": len(xs), "avg_during_pct": round(float(np.mean(xs)), 1), "median_during_pct": round(float(np.median(xs)), 1),
                     "times_up_during": int(sum(x > 0 for x in xs)), "avg_in_bear_markets_20pct_plus": round(float(np.mean(big)), 1) if big else None,
                     "bear_markets_with_data": len(big), "avg_3mo_after_bottom_pct": round(float(np.mean(ys)), 1) if ys else None}
SUM["SPY"] = {"crashes_with_data": len(CR), "avg_during_pct": round(float(np.mean([c["spy_drop_pct"] for c in CR])), 1),
              "avg_3mo_after_bottom_pct": round(float(np.mean([c["spy_3mo_after_bottom_pct"] for c in CR if c["spy_3mo_after_bottom_pct"] is not None])), 1)}
for k, v in sorted(SUM.items(), key=lambda kv: -(kv[1].get("median_during_pct") or -99)):
    print(f"{k:28s} up in {v.get('times_up_during')}/{v['crashes_with_data']} crashes | median {v.get('median_during_pct')}% avg {v['avg_during_pct']}% | bear mkts {v.get('avg_in_bear_markets_20pct_plus')}% | 3mo after bottom {v.get('avg_3mo_after_bottom_pct')}%", flush=True)
json.dump({"note": __doc__, "built": str(pd.Timestamp.today().date()), "dry": DRY or None, "crashes": CR, "summary": SUM}, open(OUT, "w"), indent=1, default=float)
print("wrote", OUT, flush=True)
