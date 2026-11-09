# Dip strategy with idle money parked in Clear Leader instead of SPY. PIT S&P 500 1998-2026. Research only.
# Clear Leader monthly positions come from scripts/clear_leader_long.py (same rules); daily returns of the held ETF (or its stand-in) are used day by day.
import os, json, urllib.request, urllib.parse, time, traceback, sys
import pandas as pd, numpy as np
def ydaily(sym):
    for a in range(4):
        try:
            u = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?period1=0&period2={int(time.time())}&interval=1d&events=div%2Csplit"
            j = json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=60))["chart"]["result"][0]
            q = j["indicators"]; adj = (q.get("adjclose") or [{}])[0].get("adjclose") or q["quote"][0]["close"]
            s = pd.Series({pd.Timestamp(time.strftime("%Y-%m-%d", time.gmtime(t))): v for t, v in zip(j["timestamp"], adj) if v and v > 0})
            return s[~s.index.duplicated()].sort_index()
        except Exception as e: err = e; time.sleep(3 * (a + 1))
    print("daily fail", sym, err); return pd.Series(dtype=float)
def fetch(url, dest):
    import time
    for i in range(6):
        try:
            urllib.request.urlretrieve(url, dest); return
        except Exception as e:
            print("download retry", i + 1, url, e, flush=True); time.sleep(20 * (i + 1))
    raise RuntimeError("download failed: " + url)
def main():
    g = {"__name__": "cl"}; exec(open("scripts/clear_leader_long.py").read(), g)
    ASSETS = g["ASSETS"]; CLROWS = {k: g["run"](crash=c)[0] for k, c in [("cl", False), ("cl_crash", True)]}
    DAILY = {}
    for etf, alts in ASSETS.items():
        for s in [etf] + alts:
            DAILY[s] = ydaily(s); time.sleep(0.4)
    def asset_ret(etf, day_index):
        out = pd.Series(np.nan, index=day_index)
        for s in [etf] + ASSETS[etf]:  # ETF first, stand-ins fill gaps before launch
            d = DAILY.get(s)
            if d is None or d.empty: continue
            r = d.pct_change().reindex(day_index)
            out = out.fillna(r)
        return out
    # ---- stock data
    REL = "https://github.com/Johnbrick123/sp500-data/releases/download/snapshot-2026-11/"
    for f in ["prices.parquet", "membership_intervals.parquet"]:
        if not os.path.exists("/tmp/" + f): fetch(REL + f, "/tmp/" + f)
    px = pd.read_parquet("/tmp/prices.parquet", columns=["date", "ticker", "open", "close", "adj_close"])
    px["date"] = pd.to_datetime(px.date); px = px[px.date >= "1997-01-01"]
    mem = pd.read_parquet("/tmp/membership_intervals.parquet"); mem["start"] = pd.to_datetime(mem.start); mem["end"] = pd.to_datetime(mem.end)
    px = px[px.ticker.isin(set(mem.ticker) | {"SPY"})]; px["aopen"] = px.open * px.adj_close / px.close
    dates = pd.DatetimeIndex(sorted(px[px.ticker == "SPY"].date.unique())); ALLT = sorted(px.ticker.unique())
    P = lambda v: px.pivot_table(index="date", columns="ticker", values=v, dropna=False).reindex(index=dates, columns=ALLT)
    C, O = P("adj_close"), P("aopen"); del px
    valid = C.notna(); Cf = C.ffill(); tick = [t for t in ALLT if t != "SPY"]
    M = pd.DataFrame(False, index=dates, columns=tick)
    for _, m in mem.iterrows():
        if m.ticker in M.columns:
            e = m.end if pd.notna(m.end) else pd.Timestamp("2100-01-01")
            M.loc[(M.index >= m.start) & (M.index < e), m.ticker] = True
    M &= valid[tick] & valid[tick].shift(-1, fill_value=False)
    spy = Cf["SPY"]; spyr = spy.pct_change().fillna(0).values
    trend = (spy > spy.rolling(210).mean()).shift(1, fill_value=False).values
    # ---- Clear Leader daily parking returns
    mon = dates.strftime("%Y-%m"); PARK = {"spy_always": spyr, "spy_trend": np.where(trend, spyr, 0.0), "cash": np.zeros(len(dates))}
    RET = {e: asset_ret(e, dates) for e in ASSETS}
    CLINFO = {}
    for key, rows in CLROWS.items():
        posm = {r["m"]: r["pos"] for r in rows}; mret = {r["m"]: r["r"] for r in rows}
        arr = np.zeros(len(dates)); fb = 0
        for m in sorted(set(mon)):
            idx = np.where(mon == m)[0]
            if m not in posm: arr[idx] = spyr[idx]; continue
            d = RET[posm[m]].values[idx]
            if np.isnan(d).any():
                arr[idx] = (1 + mret[m]) ** (1 / len(idx)) - 1; fb += 1
            else: arr[idx] = d
        PARK[key] = arr; CLINFO[key] = {"months_monthly_fallback": fb, "months_held": {k: int(v) for k, v in pd.Series(list(posm.values())).value_counts().items()}}
    above = Cf[tick] > Cf[tick].rolling(200).mean()
    Rt = Cf[tick].pct_change().fillna(0).values; OC = (Cf[tick] / O[tick] - 1).fillna(0).values
    over5 = (Cf[tick] > Cf[tick].rolling(5).mean()).values
    rl = Cf[tick].pct_change(5).sub(spy.pct_change(5), axis=0)
    S = ((rl <= -0.10) & above & M).values; R = (-rl).values
    D = len(dates); START = int(np.searchsorted(dates.values, np.datetime64("1998-01-01")))
    def sim(park, hold=3, cost=0.0005, entry="close", smart=False, mx=5, trade=True, slots=10):
        eq = 1.0; curve = np.ones(D); pos = []; tr = []; inv = []
        for t in range(START, D):
            used = sum(p[2] for p in pos); day = 0.0
            for p in pos:
                gg = OC[t, p[0]] if (entry == "open" and p[1] == 0) else Rt[t, p[0]]
                p[3] *= 1 + gg; day += p[2] * gg
            day += max(0.0, 1 - used) * park[t]; inv.append(used); eq *= 1 + day
            keep = []
            for p in pos:
                gg = OC[t, p[0]] if (entry == "open" and p[1] == 0) else Rt[t, p[0]]
                p[1] += 1; p[2] *= (1 + gg) / (1 + day)
                if p[1] >= (mx if smart else hold) or (smart and over5[t, p[0]]):
                    eq *= 1 - cost * p[2]; tr.append(p[3] - 1 - 2 * cost)
                else: keep.append(p)
            pos = keep; used = sum(p[2] for p in pos)
            if trade:
                held = {p[0] for p in pos}
                new = [c for c in sorted(np.where(S[t])[0], key=lambda c: -R[t, c]) if c not in held][: max(0, slots - len(pos))]
                if new:
                    w = min(0.10, max(0.0, 1 - used) / len(new))
                    for c in new: pos.append([c, 0, w, 1.0]); eq *= 1 - cost * w
            curve[t] = eq
        c = pd.Series(curve[START:], index=dates[START:]); p = c.pct_change().fillna(0); yrs = len(p) / 252
        per = {}
        for a, b in [("1998", "2002"), ("2003", "2007"), ("2008", "2009"), ("2010", "2015"), ("2016", "2020"), ("2021", "2026")]:
            q = p[(p.index >= a) & (p.index <= b + "-12-31")]; per[a + "-" + b] = round(100 * ((1 + q).prod() ** (252 / max(len(q), 1)) - 1), 1)
        o = {"cagr": round(100 * (c.iloc[-1] ** (1 / yrs) - 1), 1), "dd": round(100 * (c / c.cummax() - 1).min(), 1), "per": per, "invested_pct": round(100 * float(np.mean(inv)), 1)}
        if tr: o["win_rate"] = round(100 * float((np.array(tr) > 0).mean()), 1)
        return o
    sc = spy.iloc[START:] / spy.iloc[START]
    OUT = {"SPY": {"cagr": round(100 * (sc.iloc[-1] ** (252 / len(sc)) - 1), 1), "dd": round(100 * (sc / sc.cummax() - 1).min(), 1)}, "clear_leader_info": CLINFO, "results": []}
    sma = lambda n: (spy > spy.rolling(n).mean()).shift(1, fill_value=False).values
    rows = [("Clear Leader + crash filter (monthly, 10-mo avg)", PARK["cl_crash"])]
    for n in (50, 100, 150, 200):
        rows.append((f"Clear Leader, cash when SPY below {n}-day avg (checked daily)", np.where(sma(n), PARK["cl"], 0.0)))
        rows.append((f"CL + crash filter, plus cash when SPY below {n}-day avg", np.where(sma(n), PARK["cl_crash"], 0.0)))
    rows.append(("SPY trend (current)", PARK["spy_trend"]))
    for en, kw in [("Smart exit, ideal", dict(smart=True)), ("Smart exit, realistic (next open + 0.15%)", dict(smart=True, entry="open", cost=0.0015))]:
        for nm, pk in rows:
            s = sim(pk, **kw); s.update(setup=en, parking=nm); OUT["results"].append(s); print(en, nm, s["cagr"], s["dd"], flush=True)
    os.makedirs("data", exist_ok=True); json.dump(OUT, open("data/dip_fast_crash.json", "w"), indent=1, default=float)
try:
    main()
except Exception:
    os.makedirs("data", exist_ok=True); json.dump({"error": traceback.format_exc()}, open("data/dip_fast_crash.json", "w")); print(traceback.format_exc()); sys.exit(1)
