"""Where should idle money go when SPY is below its 100-day average? (Nov 18 2026). Research only, not financial advice.
Base bot = live rules: point-in-time S&P 500, price >= $5, above 200-day avg, 5-day return >= 10% worse than SPY, volume <= 2x;
10 slots x 10%, buy at the close, sell when close > 5-day avg (after >= 1 day) or after 5 days. Idle money: SPY (stand-in for the
Clear Leader ETF) when SPY > its 100-day avg (yesterday's close), else CASH. Costs 0.05%/side on stocks and on every parking switch.
Question: on the 'cash' days, would another market do better than cash? Each alternative is tested two ways:
  plain   = always hold it on cash days
  checked = hold it only if it is itself above its own 100-day avg, else cash
Alternatives (Yahoo daily, total-return 'adjclose'; older stand-ins before an ETF existed):
  India in USD: INDA (2012+) <- EPI (2008+) <- Sensex/INR (price only); T-bills: ^IRX yield; long Treasuries TLT <- VUSTX;
  mid Treasuries IEF <- VFITX; gold GLD <- GC=F; developed intl EFA <- VGTSX; emerging EEM <- VEIEX; 50/50 TLT+GLD;
  'strongest of' = each 21 days pick the alternative with the best 63-day return among those above their 100-day avg, else T-bills.
Before an alternative has any data, those days count as cash (coverage is reported).
Checks: an alternative that is all zeros must equal the cash bot exactly; DRY=planted gives one fake alternative +0.05%/day (must win).
DRY=1|planted: fake alternatives (no network); stock data is real (sp500-data release)."""
import os, json, time, urllib.request, urllib.parse
import numpy as np, pandas as pd
DRY = os.environ.get("DRY", ""); OUT = os.environ.get("OUT", "data/cash_alternatives.json" if not DRY else f"/tmp/cash_alt_{DRY}.json")
START = os.environ.get("START", "1999-06-01"); COST = 0.0005
REL = "https://github.com/Johnbrick123/sp500-data/releases/download/snapshot-2026-11/"
for f in ["prices.parquet", "membership_intervals.parquet"]:
    if not os.path.exists("/tmp/" + f): urllib.request.urlretrieve(REL + f, "/tmp/" + f)
px = pd.read_parquet("/tmp/prices.parquet", columns=["date", "ticker", "close", "adj_close", "volume"])
px["date"] = pd.to_datetime(px.date); px = px[px.date >= "1997-06-01"]
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
SIG = (M & (RAW[tick] >= 5) & (vr <= 2.0) & (Cs > Cs.rolling(200).mean()) & (ex5 <= -0.10)).values
C, M5, RK = Cs.values, Cs.rolling(5).mean().values, ex5.values
spyr = np.r_[0, spy.values[1:] / spy.values[:-1] - 1]; park_on = np.r_[False, (spy > spy.rolling(100).mean()).values[:-1]]
dn = dates.values; t0 = int(np.searchsorted(dn, np.datetime64(START))); ds = [str(d)[:10] for d in dn]

# ---------------- alternatives: daily returns aligned to US trading days (0 where no data)
def ydaily(sym, adj=True):
    err = None
    for a in range(5):
        try:
            u = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?period1=0&period2={int(time.time())}&interval=1d&events=div%2Csplit"
            j = json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=60))["chart"]["result"][0]
            q = j["indicators"]; v = ((q.get("adjclose") or [{}])[0].get("adjclose") if adj else None) or q["quote"][0]["close"]
            s = pd.Series({pd.Timestamp(time.strftime("%Y-%m-%d", time.gmtime(t))): x for t, x in zip(j["timestamp"], v) if x and x > 0})
            return s[~s.index.duplicated()].sort_index()
        except Exception as e: err = e; time.sleep(3 * (a + 1))
    print("Yahoo failed", sym, err, flush=True); return pd.Series(dtype=float)
def on_us_days(s):
    """price series -> level on each US trading day (last known value, max 5 days stale), NaN before it starts"""
    if s.empty: return pd.Series(np.nan, index=dates)
    return s.reindex(s.index.union(dates)).ffill(limit=5).reindex(dates)
def chain(*syms):
    """newest ETF first; older stand-ins fill the days before it existed. Returns (daily return array, level series, first date)"""
    rets = pd.Series(np.nan, index=dates)
    for s in syms:
        lvl = on_us_days(s) if isinstance(s, pd.Series) else on_us_days(ydaily(s)); time.sleep(0.4)
        r = lvl.pct_change(fill_method=None)
        rets = rets.where(rets.notna(), r)
    first = rets.first_valid_index()
    lvl = (1 + rets.fillna(0)).cumprod().where(rets.notna().cumsum() > 0)
    return rets.fillna(0).values, lvl, (str(first)[:10] if first is not None else None)
ALT = {}
if DRY:
    rng = np.random.default_rng(7)
    for k in ("India (USD)", "Long Treasuries", "Mid Treasuries", "Gold", "Developed intl", "Emerging"):
        r = rng.normal(0.0002, 0.012, D); ALT[k] = (r, pd.Series((1 + r).cumprod(), index=dates), ds[0])
    ALT["T-bills"] = (np.full(D, 0.02 / 252), pd.Series((1 + 0.02 / 252) ** np.arange(D), index=dates), ds[0])
else:
    sensex, inr = ydaily("^BSESN", adj=False), ydaily("INR=X", adj=False)          # INR=X = rupees per dollar
    j = sensex.index.intersection(inr.index); sx_usd = (sensex[j] / inr[j]).dropna()
    print("Sensex/INR from", sx_usd.index.min() if len(sx_usd) else None, flush=True)
    ALT["India (USD)"] = chain("INDA", "EPI", sx_usd)
    irx = ydaily("^IRX", adj=False); irx = irx.reindex(irx.index.union(dates)).ffill(limit=10).reindex(dates)
    tb = (irx / 100 / 252).shift(1)
    ALT["T-bills"] = (tb.fillna(0).values, (1 + tb.fillna(0)).cumprod().where(tb.notna().cumsum() > 0), str(tb.first_valid_index())[:10])
    ALT["Long Treasuries"] = chain("TLT", "VUSTX")
    ALT["Mid Treasuries"] = chain("IEF", "VFITX")
    ALT["Gold"] = chain("GLD", "GC=F")
    ALT["Developed intl"] = chain("EFA", "VGTSX")
    ALT["Emerging"] = chain("EEM", "VEIEX")
if DRY == "planted": ALT["PLANTED +0.05%/day"] = (np.full(D, 0.0005), pd.Series(1.0005 ** np.arange(D), index=dates), ds[0])
r50 = 0.5 * ALT["Long Treasuries"][0] + 0.5 * ALT["Gold"][0]
ALT["50/50 Treasuries + gold"] = (r50, pd.Series((1 + r50).cumprod(), index=dates), max(ALT["Long Treasuries"][2] or "9", ALT["Gold"][2] or "9"))
COVER = {k: v[2] for k, v in ALT.items()}
print("alternative data starts:", COVER, flush=True)
def above100(lvl):          # yesterday's close above its 100-day avg (False where unknown)
    a = (lvl > lvl.rolling(100, min_periods=100).mean()).fillna(False).values
    return np.r_[False, a[:-1]]
TREND = {k: above100(v[1]) for k, v in ALT.items()}
MOM = {k: np.r_[np.nan, (v[1] / v[1].shift(63) - 1).values[:-1]] for k, v in ALT.items()}
POOL = [k for k in ("India (USD)", "Long Treasuries", "Mid Treasuries", "Gold", "Developed intl", "Emerging") if k in ALT]

def sim(off_choice, cost=COST):
    """off_choice(t, state) -> name of the alternative to hold on a cash day, or None = cash"""
    pos, eq, curve = [], 1.0, np.ones(D); held_park, st = "CASH", {}
    days_alt = 0; trades = []
    for t in range(t0, D):
        want = "SPY" if park_on[t] else (off_choice(t, st) or "CASH")
        idle = 1 - 0.10 * len(pos)
        if want != held_park:                                            # switch parking at yesterday's close
            eq *= 1 - idle * cost * ((held_park != "CASH") + (want != "CASH")); held_park = want
        r = sum(0.10 * (C[t, j] / C[t - 1, j] - 1) for j, _, _ in pos)
        if held_park == "SPY": r += idle * spyr[t]
        elif held_park != "CASH": r += idle * ALT[held_park][0][t]; days_alt += 1
        eq *= 1 + r; keep = []
        for j, e, bp in pos:
            age = t - e
            if age >= 1 and (C[t, j] > M5[t, j] or age >= 5): eq *= 1 - 0.10 * cost; trades.append(C[t, j] / bp - 1)
            else: keep.append((j, e, bp))
        pos = keep; held = {j for j, _, _ in pos}
        for j in sorted([j for j in np.flatnonzero(SIG[t]) if j not in held], key=lambda j: RK[t, j])[:10 - len(pos)]:
            pos.append((j, t, C[t, j])); eq *= 1 - 0.10 * cost
        curve[t] = eq
    return curve, days_alt, len(trades)
PER = [("1999-2026", START, "2100-01-01"), ("1999-2012", START, "2013-01-01"), ("2013-2026", "2013-01-01", "2100-01-01"),
       ("2008-2026", "2008-03-01", "2100-01-01"),
       ("dot-com crash 2000-02", "2000-03-24", "2002-10-10"), ("2008 crash", "2007-10-09", "2009-03-10"), ("2011 drop", "2011-04-29", "2011-10-04"),
       ("2018 Q4", "2018-09-20", "2018-12-25"), ("2020 covid", "2020-02-19", "2020-03-24"), ("2022 bear", "2022-01-03", "2022-10-13")]
def summarize(curve):
    out = {}
    for name, a, b in PER:
        ix = np.flatnonzero((dn >= np.datetime64(a)) & (dn < np.datetime64(b)) & (np.arange(D) >= t0))
        if len(ix) < 15: out[name] = {}; continue
        cv = curve[ix] / curve[ix[0] - 1 if ix[0] > t0 else ix[0]]; y = len(ix) / 252
        dd = round(float((cv / np.maximum.accumulate(np.r_[1, cv])[1:] - 1).min()) * 100, 1)
        out[name] = ({"per_year_pct": round((cv[-1] ** (1 / y) - 1) * 100, 1)} if y > 3 else {"return_pct": round((cv[-1] - 1) * 100, 1)}) | {"worst_drop_pct": dd}
    ix = np.arange(t0, D); cv = curve[ix]
    roll = cv[756:] / cv[:-756] if len(cv) > 756 else np.array([np.nan])
    out["worst_3yr_pct"] = round(float((np.nanmin(roll) - 1) * 100), 1)
    yrs = pd.Series(curve[t0:], index=dates[t0:]).resample("YE").last(); yr = yrs.pct_change(); yr.iloc[0] = yrs.iloc[0] / curve[t0 - 1] - 1
    out["years"] = {str(k.year): round(float(v) * 100, 1) for k, v in yr.items()}
    return out

def plain(k): return lambda t, st: k
def checked(k): return lambda t, st: k if TREND[k][t] else None
def strongest(t, st):
    if st.get("next", -1) <= t or st.get("last", -2) != t - 1:
        ok = [(MOM[k][t], k) for k in POOL if TREND[k][t] and np.isfinite(MOM[k][t])]
        st["pick"] = max(ok)[1] if ok else "T-bills"; st["next"] = t + 21
    st["last"] = t; return st["pick"]
VARS = {"cash (rules as now)": lambda t, st: None, "stay in SPY (no cash rule)": lambda t, st: "SPY_STAY"}
for k in ALT:
    VARS[f"{k} (plain)"] = plain(k)
    if k != "T-bills": VARS[f"{k} (only if above its 100-day)"] = checked(k)
VARS["strongest of 6, if above its 100-day, else T-bills"] = strongest
RES = {}
park_on_saved = park_on.copy()
for name, fn in VARS.items():
    if name.startswith("stay in SPY"):
        park_on[:] = True; cv, da, nt = sim(lambda t, st: None); park_on[:] = park_on_saved
    else: cv, da, nt = sim(fn)
    RES[name] = summarize(cv) | {"days_in_alternative": da, "stock_trades": nt}
    cs = summarize(sim(fn, cost=0.002)[0]) if not name.startswith("stay") else None
    if cs: RES[name]["cost_0.2pct_side_per_year"] = cs["1999-2026"]["per_year_pct"]
    a = RES[name]; g = lambda p, f="per_year_pct": a.get(p, {}).get(f)
    print(f"{name:52s} {g('1999-2026')}%/yr worst {g('1999-2026','worst_drop_pct')}% | 99-12 {g('1999-2012')} 13-26 {g('2013-2026')} 08-26 {g('2008-2026')} | "
          f"dotcom {g('dot-com crash 2000-02','return_pct')} 2008 {g('2008 crash','return_pct')} covid {g('2020 covid','return_pct')} 2022 {g('2022 bear','return_pct')} | 3yr worst {a['worst_3yr_pct']} | alt days {da}", flush=True)
# checks
ALT["ZERO"] = (np.zeros(D), ALT["T-bills"][1], ds[0])
z, c0 = sim(plain("ZERO"), cost=0)[0], sim(lambda t, st: None, cost=0)[0]
assert np.allclose(z, c0), "an all-zero alternative must equal cash"
print("check ok: all-zero alternative = cash bot", flush=True)
if DRY == "planted":
    assert RES["PLANTED +0.05%/day (plain)"]["1999-2026"]["per_year_pct"] > RES["cash (rules as now)"]["1999-2026"]["per_year_pct"] + 1, "planted edge not found"
    print("check ok: planted edge found", flush=True)
json.dump({"note": __doc__, "built": str(pd.Timestamp.today().date()), "dry": DRY or None, "data_starts": COVER,
           "share_of_days_spy_below_100d_pct": round(float((~park_on[t0:]).mean()) * 100, 1), "results": RES}, open(OUT, "w"), indent=1, default=float)
print("wrote", OUT, flush=True)
