"""Combined test (Nov 14 2026): today's dip bot + the ETF dip rule sharing the same 10 slots. Research only, not financial advice.
Stock rule = live paper-dip.mjs: point-in-time S&P 500 member, price >= $5, above 200-day avg, 5-day return at least 10% worse
than SPY's, volume over the drop <= 2x normal; biggest drop first. Sell when the close is back above the 5-day avg (after
>= 1 day) or after 5 days. ETF rule: 29 index/sector/country ETFs, 5-day drop >= 5% (or 3-day >= 3%), above 200-day avg,
same sell rule, max hold 5 or 10 days. Stocks get slots first; ETFs fill what's left (or ETFs only when no stock dip).
Each trade = 10% of the account, bought at the close (the live bot trades just before the close).
Idle money: SPY when SPY is above its 100-day avg, else cash (the bot's crash rule; the live bot parks in its Clear Leader ETF).
Costs per side: stocks 0.05%, ETFs 0.02% (stress: 0.15% / 0.05%)."""
import os, json, time, urllib.request, urllib.parse
import numpy as np, pandas as pd

REL = "https://github.com/Johnbrick123/sp500-data/releases/download/snapshot-2026-11/"
for f in ["prices.parquet", "membership_intervals.parquet"]:
    if not os.path.exists("/tmp/" + f):
        for i in range(6):
            try: urllib.request.urlretrieve(REL + f, "/tmp/" + f); break
            except Exception as e: print("retry", e, flush=True); time.sleep(20 * (i + 1))
px = pd.read_parquet("/tmp/prices.parquet", columns=["date", "ticker", "close", "adj_close", "volume"])
px["date"] = pd.to_datetime(px.date); px = px[px.date >= "1997-06-01"]
mem = pd.read_parquet("/tmp/membership_intervals.parquet"); mem["start"] = pd.to_datetime(mem.start); mem["end"] = pd.to_datetime(mem.end)
px = px[px.ticker.isin(set(mem.ticker) | {"SPY"})]
dates = pd.DatetimeIndex(sorted(px[px.ticker == "SPY"].date.unique())); ALLT = sorted(px.ticker.unique())
P = lambda v: px.pivot_table(index="date", columns="ticker", values=v, dropna=False).reindex(index=dates, columns=ALLT)
A, RAW, VOL = P("adj_close"), P("close"), P("volume"); del px
tick = [t for t in ALLT if t != "SPY"]
M = pd.DataFrame(False, index=dates, columns=tick)
for _, m in mem.iterrows():
    if m.ticker in M.columns:
        e = m.end if pd.notna(m.end) else pd.Timestamp("2100-01-01")
        M.loc[(M.index >= m.start) & (M.index < e), m.ticker] = True
valid = A[tick].notna()
M &= valid & valid.shift(-1, fill_value=False)
Cs = A[tick].ffill(); spy = A["SPY"].ffill()
ex5 = (Cs / Cs.shift(5) - 1).sub(spy / spy.shift(5) - 1, axis=0)
vr = VOL[tick].rolling(5).mean() / VOL[tick].shift(5).rolling(50).mean()
sigS = M & (Cs > Cs.rolling(200).mean()) & (ex5 <= -0.10) & (RAW[tick] >= 5) & (vr <= 2.0)
ma5S = Cs.rolling(5).mean()
print("stocks", len(tick), dates[0].date(), dates[-1].date(), "stock signals", int(sigS.values.sum()), flush=True)

ETFS = ["SPY", "QQQ", "IWM", "DIA", "MDY", "XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY", "XLRE", "XLC",
        "EFA", "EEM", "EWJ", "EWG", "EWU", "EWC", "EWA", "EWZ", "EWH", "EWT", "EWY", "INDA", "FXI"]
def yahoo(sym):
    for a in range(4):
        try:
            u = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?period1=0&period2={int(time.time())}&interval=1d&events=div%2Csplit"
            j = json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=60))["chart"]["result"][0]
            adj = (j["indicators"].get("adjclose") or [{}])[0].get("adjclose") or j["indicators"]["quote"][0]["close"]
            s = pd.Series(adj, index=pd.to_datetime([time.strftime("%Y-%m-%d", time.gmtime(t)) for t in j["timestamp"]])).dropna()
            return s[~s.index.duplicated()].sort_index()
        except Exception as e: err = e; time.sleep(3 * (a + 1))
    print("fail", sym, err, flush=True); return None
E = {}
for s in ETFS:
    x = yahoo(s); time.sleep(0.4)
    if x is not None: E[s] = x
Ce_raw = pd.DataFrame(E).reindex(dates)
Ce = Ce_raw.ffill()
okE = Ce_raw.notna() & Ce_raw.notna().shift(-1, fill_value=False)
ma200E, ma5E = Ce.rolling(200).mean(), Ce.rolling(5).mean()
sigE = {"5-day drop 5%+": okE & (Ce > ma200E) & (Ce / Ce.shift(5) - 1 <= -0.05),
        "3-day drop 3%+": okE & (Ce > ma200E) & (Ce / Ce.shift(3) - 1 <= -0.03)}
rankE = {"5-day drop 5%+": Ce / Ce.shift(5) - 1, "3-day drop 3%+": Ce / Ce.shift(3) - 1}
print("ETFs", list(Ce.columns), flush=True)

S_C, S_M5, S_SIG, S_RK = Cs.values, ma5S.values, sigS.values, ex5.values
E_C, E_M5 = Ce.values, ma5E.values
SP = spy.values; spyr = np.r_[0, SP[1:] / SP[:-1] - 1]
park_on = np.r_[False, (spy > spy.rolling(100).mean()).values[:-1]]   # decided at yesterday's close
dn = dates.values; START = np.datetime64("1999-01-01")

def sim(etf_rule=None, etf_hold=5, mode="fill", slots=10, w=0.10, cs=0.0005, ce=0.0002, stocks=True):
    if etf_rule: E_SIG, E_RK = sigE[etf_rule].values, rankE[etf_rule].values
    pos, eq, curve, trades = [], 1.0, np.ones(len(dates)), []
    t0 = int(np.searchsorted(dn, START))
    for t in range(t0, len(dates)):
        r = 0.0
        for p in pos:
            Cx = S_C if p["k"] == "S" else E_C
            r += w * (Cx[t, p["j"]] / Cx[t - 1, p["j"]] - 1)
        if park_on[t]: r += (1 - w * len(pos)) * spyr[t]
        eq *= 1 + r
        keep = []
        for p in pos:
            Cx, Mx = (S_C, S_M5) if p["k"] == "S" else (E_C, E_M5)
            age = t - p["d"]; mh = 5 if p["k"] == "S" else etf_hold
            if age >= 1 and (Cx[t, p["j"]] > Mx[t, p["j"]] or age >= mh):
                c = cs if p["k"] == "S" else ce; eq *= 1 - w * 2 * c
                trades.append((p["d"], p["k"], Cx[t, p["j"]] / p["px"] - 1 - 2 * c))
            else: keep.append(p)
        pos = keep
        held = {(p["k"], p["j"]) for p in pos}
        free = slots - len(pos)
        if free > 0 and stocks:
            c = [j for j in np.flatnonzero(S_SIG[t]) if ("S", j) not in held]
            c.sort(key=lambda j: S_RK[t, j])
            for j in c[:free]: pos.append({"k": "S", "j": j, "d": t, "px": S_C[t, j]})
            nstock_today = len(c)
        else: nstock_today = 0
        free = slots - len(pos)
        if etf_rule and free > 0 and (mode == "fill" or nstock_today == 0):
            c = [j for j in np.flatnonzero(E_SIG[t]) if ("E", j) not in held and not np.isnan(E_C[t, j])]
            c.sort(key=lambda j: E_RK[t, j])
            for j in c[:free]: pos.append({"k": "E", "j": j, "d": t, "px": E_C[t, j]})
        curve[t] = eq
    out = {}
    for name, a, b in (("1999-2026", "1999-01-01", "2100-01-01"), ("1999-2012", "1999-01-01", "2013-01-01"), ("2013-2026", "2013-01-01", "2100-01-01"),
                       ("2008", "2008-01-01", "2009-01-01"), ("2020", "2020-01-01", "2021-01-01"), ("2022", "2022-01-01", "2023-01-01")):
        idx = np.flatnonzero((dn >= np.datetime64(a)) & (dn < np.datetime64(b)) & (dn >= START))
        c = curve[idx] / curve[idx[0]]; yrs = len(idx) / 252; s = SP[idx] / SP[idx[0]]
        tr = [x for x in trades if a <= str(dn[x[0]])[:10] < b]
        st, et = [x for x in tr if x[1] == "S"], [x for x in tr if x[1] == "E"]
        out[name] = {"per_year_pct": round((c[-1] ** (1 / yrs) - 1) * 100, 1) if yrs > 1.5 else round((c[-1] - 1) * 100, 1),
                     "worst_drop_pct": round(float((c / np.maximum.accumulate(c) - 1).min()) * 100, 1),
                     "spy_pct": round((s[-1] ** (1 / yrs) - 1) * 100, 1) if yrs > 1.5 else round((s[-1] - 1) * 100, 1),
                     "spy_worst_drop_pct": round(float((s / np.maximum.accumulate(s) - 1).min()) * 100, 1),
                     "stock_trades_per_month": round(len(st) / (yrs * 12), 1), "etf_trades_per_month": round(len(et) / (yrs * 12), 1),
                     "win_pct": round(float(np.mean([x[2] > 0 for x in tr])) * 100, 1) if tr else None,
                     "stock_avg_trade_pct": round(float(np.mean([x[2] for x in st])) * 100, 2) if st else None,
                     "etf_avg_trade_pct": round(float(np.mean([x[2] for x in et])) * 100, 2) if et else None}
    return out

V = [("A. today's dip bot (stocks only)", dict()),
     ("B. + ETF 5-day 5% dips fill free slots, hold<=5", dict(etf_rule="5-day drop 5%+", etf_hold=5)),
     ("C. + ETF 5-day 5% dips fill free slots, hold<=10", dict(etf_rule="5-day drop 5%+", etf_hold=10)),
     ("D. + ETF 5-day 5% dips only on days with no stock dip", dict(etf_rule="5-day drop 5%+", etf_hold=10, mode="no-stock-days")),
     ("E. + ETF 3-day 3% dips fill free slots, hold<=10", dict(etf_rule="3-day drop 3%+", etf_hold=10)),
     ("F. B with 12 slots of 8.3%", dict(etf_rule="5-day drop 5%+", etf_hold=10, slots=12, w=1 / 12)),
     ("G. ETF dips only (no stocks)", dict(etf_rule="5-day drop 5%+", etf_hold=10, stocks=False)),
     ("A. stress costs", dict(cs=0.0015, ce=0.0005)),
     ("C. stress costs", dict(etf_rule="5-day drop 5%+", etf_hold=10, cs=0.0015, ce=0.0005))]
res = {}
for name, kw in V:
    res[name] = sim(**kw); a = res[name]
    print(name, "|", a["1999-2026"]["per_year_pct"], a["1999-2026"]["worst_drop_pct"], "| early", a["1999-2012"]["per_year_pct"], "late", a["2013-2026"]["per_year_pct"],
          "| 2008", a["2008"]["per_year_pct"], "2020", a["2020"]["per_year_pct"], "2022", a["2022"]["per_year_pct"],
          "| trades/mo", a["1999-2026"]["stock_trades_per_month"], "+", a["1999-2026"]["etf_trades_per_month"], "win", a["1999-2026"]["win_pct"], flush=True)
json.dump({"note": __doc__, "results": res}, open("data/combined_dip_etf.json", "w"), indent=1)
