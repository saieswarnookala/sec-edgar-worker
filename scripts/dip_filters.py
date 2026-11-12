# Dip strategy improvement tests (one mode per run): skip earnings dips, skip high-volume dips, max stocks per industry, dip vs industry peers, stop-loss.
# Base = current best: dip >=10% vs SPY over 5 days, above 200-day avg, smart exit (close > 5-day avg, max 5 days), 10 slots, Clear Leader parking, cash when SPY < 100-day avg. PIT S&P 500 1998-2026. Research only.
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
    import pyarrow.parquet as pq
    hasv = "volume" in pq.read_schema("/tmp/prices.parquet").names
    px = pd.read_parquet("/tmp/prices.parquet", columns=["date", "ticker", "open", "close", "adj_close"] + (["volume"] if hasv else []))
    px["date"] = pd.to_datetime(px.date); px = px[px.date >= "1997-01-01"]
    mem = pd.read_parquet("/tmp/membership_intervals.parquet"); mem["start"] = pd.to_datetime(mem.start); mem["end"] = pd.to_datetime(mem.end)
    px = px[px.ticker.isin(set(mem.ticker) | {"SPY"})]; px["aopen"] = px.open * px.adj_close / px.close
    dates = pd.DatetimeIndex(sorted(px[px.ticker == "SPY"].date.unique())); ALLT = sorted(px.ticker.unique())
    P = lambda v: px.pivot_table(index="date", columns="ticker", values=v, dropna=False).reindex(index=dates, columns=ALLT)
    C, O = P("adj_close"), P("aopen"); VOL = P("volume") if hasv else None; del px
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
    LASTC = [None]
    def sim(park, hold=3, cost=0.0005, entry="close", smart=False, mx=5, trade=True, slots=10, sig=None, cap=None, stop=None):
        SS = S if sig is None else sig
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
                if p[1] >= (mx if smart else hold) or (smart and over5[t, p[0]]) or (stop is not None and p[3] - 1 <= -stop):
                    eq *= 1 - cost * p[2]; tr.append(p[3] - 1 - 2 * cost)
                else: keep.append(p)
            pos = keep; used = sum(p[2] for p in pos)
            if trade:
                held = {p[0] for p in pos}
                new = []; cnt = {}
                for p in pos: cnt[GRP[p[0]]] = cnt.get(GRP[p[0]], 0) + 1
                for c in sorted(np.where(SS[t])[0], key=lambda c: -R[t, c]):
                    if len(new) >= max(0, slots - len(pos)): break
                    if c in held: continue
                    if cap is not None and GRP[c] is not None and cnt.get(GRP[c], 0) >= cap: continue
                    new.append(c); cnt[GRP[c]] = cnt.get(GRP[c], 0) + 1
                if new:
                    w = min(1.0 / slots, max(0.0, 1 - used) / len(new))
                    for c in new: pos.append([c, 0, w, 1.0]); eq *= 1 - cost * w
            curve[t] = eq
        c = pd.Series(curve[START:], index=dates[START:]); p = c.pct_change().fillna(0); yrs = len(p) / 252
        LASTC[0] = c
        per = {}
        for a, b in [("1998", "2002"), ("2003", "2007"), ("2008", "2009"), ("2010", "2015"), ("2016", "2020"), ("2021", "2026")]:
            q = p[(p.index >= a) & (p.index <= b + "-12-31")]; per[a + "-" + b] = round(100 * ((1 + q).prod() ** (252 / max(len(q), 1)) - 1), 1)
        o = {"cagr": round(100 * (c.iloc[-1] ** (1 / yrs) - 1), 1), "dd": round(100 * (c / c.cummax() - 1).min(), 1), "per": per, "invested_pct": round(100 * float(np.mean(inv)), 1)}
        if tr: o["win_rate"] = round(100 * float((np.array(tr) > 0).mean()), 1)
        return o
    sc = spy.iloc[START:] / spy.iloc[START]
    OUT = {"SPY": {"cagr": round(100 * (sc.iloc[-1] ** (252 / len(sc)) - 1), 1), "dd": round(100 * (sc / sc.cummax() - 1).min(), 1)}, "clear_leader_info": CLINFO, "results": []}
    sma = lambda n: (spy > spy.rolling(n).mean()).shift(1, fill_value=False).values
    PKN = {n: np.where(sma(n), PARK["cl"], 0.0) for n in (100, 125, 150)}
    # ---- SEC cache: industry (SIC) and earnings release times
    SEC = json.load(open("data/sec_events_sic.json"))["tickers"]
    GRP = [((SEC.get(t) or {}).get("sic") or "")[:2] or None for t in tick]
    MODE = sys.argv[1]; G = []
    base_kw = [("ideal", dict(smart=True, mx=5)), ("realistic", dict(smart=True, mx=5, entry="open", cost=0.0015))]
    def add(label, **kw):
        for tag, b in base_kw:
            r = sim(PKN[100], **b, **kw); r.update(variant=label, scenario=tag); G.append(r); print(label, tag, r["cagr"], r["dd"], r.get("win_rate"), r["per"], flush=True)
    add("baseline (current best)")
    if MODE == "earnings":
        EARN = np.zeros((D, len(tick)), dtype=bool); di = {d: i for i, d in enumerate(dates.strftime("%Y-%m-%d"))}; ds = dates.strftime("%Y-%m-%d").values
        for j, t in enumerate(tick):
            for d, mi in (SEC.get(t) or {}).get("events", []):
                k = int(np.searchsorted(ds, d))
                if k < D and ds[k] == d and mi >= 570: k += 1
                if k < D: EARN[k:min(D, k + 5), j] = True   # reaction day falls inside the 5-day dip window
        OUT["earnings_info"] = {"tickers_with_events": sum(1 for t in tick if (SEC.get(t) or {}).get("events")), "note": "earnings dates exist from Aug 2004; before that the filter does nothing"}
        add("skip dips with earnings in the last 5 days", sig=S & ~EARN)
        add("ONLY dips with earnings (check)", sig=S & EARN)
    elif MODE == "volume":
        if VOL is None: raise RuntimeError("no volume column in prices.parquet")
        V = VOL[tick]; vr = (V.rolling(5, min_periods=3).mean() / V.rolling(50, min_periods=30).mean().shift(5)).values
        for k in (1.5, 2.0, 3.0): add(f"skip dips with volume > {k}x normal", sig=S & ~(vr > k))
        add("ONLY dips with volume > 2x normal (check)", sig=S & (vr > 2.0))
    elif MODE == "sector":
        for k in (1, 2, 3): add(f"max {k} stock(s) per industry", cap=k)
    elif MODE == "peer":
        r5 = Cf[tick].pct_change(5).where(M); grp = pd.Series(GRP, index=tick)
        peer = pd.DataFrame(np.nan, index=dates, columns=tick)
        for g, cols in grp.dropna().groupby(grp.dropna()).groups.items():
            x = r5[list(cols)]; sm = x.sum(axis=1, min_count=1); n = x.notna().sum(axis=1)
            for c in cols: peer[c] = ((sm - x[c].fillna(0)) / (n - x[c].notna())).where((n - x[c].notna()) >= 3)
        peer = peer.fillna(pd.DataFrame({c: spy.pct_change(5) for c in tick}))
        rp = Cf[tick].pct_change(5) - peer
        Sp = ((rp <= -0.10) & above & M).values
        add("dip vs industry peers (instead of SPY)", sig=Sp)
        add("dip vs BOTH SPY and industry peers", sig=S & Sp)
    elif MODE == "combo":
        V = VOL[tick]; vr = (V.rolling(5, min_periods=3).mean() / V.rolling(50, min_periods=30).mean().shift(5)).values
        r5 = Cf[tick].pct_change(5).where(M); grp = pd.Series(GRP, index=tick)
        peer = pd.DataFrame(np.nan, index=dates, columns=tick)
        for g, cols in grp.dropna().groupby(grp.dropna()).groups.items():
            x = r5[list(cols)]; sm = x.sum(axis=1, min_count=1); n = x.notna().sum(axis=1)
            for c in cols: peer[c] = ((sm - x[c].fillna(0)) / (n - x[c].notna())).where((n - x[c].notna()) >= 3)
        peer = peer.fillna(pd.DataFrame({c: spy.pct_change(5) for c in tick}))
        rp = (Cf[tick].pct_change(5) - peer).values
        EARN = np.zeros((D, len(tick)), dtype=bool); ds = dates.strftime("%Y-%m-%d").values
        for j, t in enumerate(tick):
            for d, mi in (SEC.get(t) or {}).get("events", []):
                k = int(np.searchsorted(ds, d))
                if k < D and ds[k] == d and mi >= 570: k += 1
                if k < D: EARN[k:min(D, k + 5), j] = True
        for k in (1.75, 2.0, 2.5):
            add(f"volume < {k}x", sig=S & ~(vr > k))
            add(f"volume < {k}x + dip vs peers too", sig=S & ~(vr > k) & (rp <= -0.10))
        add("volume < 2x + dip vs peers + skip earnings", sig=S & ~(vr > 2.0) & (rp <= -0.10) & ~EARN)
        rlv = rl.values; ab = (above & M).values
        for th in (0.08, 0.12):   # nearby dip sizes: does the gain hold?
            Sth = (rlv <= -th) & ab
            add(f"[dip {int(th*100)}%] baseline", sig=Sth)
            add(f"[dip {int(th*100)}%] volume < 2x", sig=Sth & ~(vr > 2.0))
            add(f"[dip {int(th*100)}%] volume < 2x + dip vs peers", sig=Sth & ~(vr > 2.0) & (rp <= -th))
    elif MODE == "tax":
        # US after-tax test for a Texas resident (no state income tax). Short-term gains (held <= 1 year) taxed at the
        # federal bracket; long-term at 15%. Losses offset gains within a year and carry forward (the $3k/yr offset
        # against salary is ignored). Everything still held at the end is sold and taxed. Wash-sale rules ignored.
        V = VOL[tick]; vr = (V.rolling(5, min_periods=3).mean() / V.rolling(50, min_periods=30).mean().shift(5)).values
        Sv = S & ~(vr > 2.0)
        posm = {r["m"]: r["pos"] for r in CLROWS["cl"]}; s100 = sma(100)
        lab = np.array([(posm.get(m, "SPY") if s100[i] else "CASH") for i, m in enumerate(mon)])
        park = PKN[100]; years = dates.year.values; LT = 0.15
        def sim_tax(sig, st_rate, cost=0.0005, entry="close", mx=5, slots=10, tax=True):
            eq = 1.0; curve = np.ones(D); pos = []; cur = None; seg0 = None; acc = 0.0
            st = lt = 0.0; cf_st = cf_lt = 0.0; paid = 0.0
            def year_end():
                nonlocal st, lt, cf_st, cf_lt, eq, paid
                a2 = st + cf_st; b2 = lt + cf_lt
                if a2 < 0 and b2 > 0: b3 = b2 + a2; a2, b2 = (0.0, b3) if b3 >= 0 else (b3, 0.0)
                if b2 < 0 and a2 > 0: a3 = a2 + b2; a2, b2 = (a3, 0.0) if a3 >= 0 else (0.0, a3)
                tx = st_rate * max(a2, 0.0) + LT * max(b2, 0.0); cf_st = min(a2, 0.0); cf_lt = min(b2, 0.0); st = lt = 0.0
                if tax: eq -= tx; paid += tx
            def realize(t):
                nonlocal st, lt, acc
                if seg0 is not None and t - seg0 > 252: lt += acc
                else: st += acc
                acc = 0.0
            for t in range(START, D):
                if lab[t] != cur:
                    if cur is not None and cur != "CASH": realize(t)
                    cur = lab[t]; seg0 = t if cur != "CASH" else None
                used = sum(p_[2] for p_ in pos); pv = max(0.0, eq - used); g = pv * park[t]; acc += g; day = g
                for p_ in pos:
                    gg = OC[t, p_[0]] if (entry == "open" and p_[1] == 0) else Rt[t, p_[0]]
                    day += p_[2] * gg; p_[2] *= 1 + gg
                eq += day; keep = []
                for p_ in pos:
                    p_[1] += 1
                    if p_[1] >= mx or over5[t, p_[0]]:
                        c = cost * p_[2]; eq -= c; st += p_[2] - p_[3] - c - cost * p_[3]
                    else: keep.append(p_)
                pos = keep; held = {p_[0] for p_ in pos}; used = sum(p_[2] for p_ in pos)
                new = [c for c in sorted(np.where(sig[t])[0], key=lambda c: -R[t, c]) if c not in held][: max(0, slots - len(pos))]
                if new:
                    w = min(eq / slots, max(0.0, eq - used) / len(new))
                    for c in new: pos.append([c, 0, w, w]); eq -= cost * w
                if t + 1 == D or years[t + 1] != years[t]:
                    if t + 1 == D:
                        for p_ in pos: st += p_[2] - p_[3]
                        if cur != "CASH": realize(t)
                    year_end()
                curve[t] = eq
            c = pd.Series(curve[START:], index=dates[START:]); pr = c.pct_change().fillna(0); yrs = len(pr) / 252
            per = {}
            for a2, b2 in [("1998", "2002"), ("2003", "2007"), ("2008", "2009"), ("2010", "2015"), ("2016", "2020"), ("2021", "2026")]:
                q = pr[(pr.index >= a2) & (pr.index <= b2 + "-12-31")]; per[a2 + "-" + b2] = round(100 * ((1 + q).prod() ** (252 / max(len(q), 1)) - 1), 1)
            return {"cagr": round(100 * (c.iloc[-1] ** (1 / yrs) - 1), 1), "dd": round(100 * (c / c.cummax() - 1).min(), 1), "per": per, "tax_paid_pct_of_start": round(100 * paid, 0), "final_x": round(float(c.iloc[-1]), 1)}
        sp = spy.iloc[START:] / spy.iloc[START]; yrs = len(sp) / 252; DY = 0.017
        g_ = sp.iloc[-1]; div_drag = (1 - LT * DY / (1 + 0.08)) ** yrs   # ~qualified dividends taxed yearly
        spy_after = 1 + (g_ * div_drag - 1) * (1 - LT)
        OUT["SPY_after_tax"] = {"cagr": round(100 * (spy_after ** (1 / yrs) - 1), 1), "final_x": round(float(spy_after), 1), "note": "dividends ~1.7%/yr taxed 15% yearly, gains taxed 15% once at the end"}
        OUT["SPY"]["final_x"] = round(float(g_), 1)
        for vname, sig in [("current (no volume filter)", S), ("with volume filter (skip > 2x)", Sv)]:
            for scen, kw in [("ideal", {}), ("realistic", dict(entry="open", cost=0.0015))]:
                r = sim_tax(sig, 0.0, tax=False, **kw); r.update(variant=vname, scenario=scen, tax="before tax / Roth IRA"); G.append(r); print(vname, scen, "pre", r["cagr"], r["final_x"], flush=True)
                for br in (0.22, 0.24, 0.32, 0.35):
                    r = sim_tax(sig, br, **kw); r.update(variant=vname, scenario=scen, tax=f"after tax, {int(br*100)}% bracket"); G.append(r); print(vname, scen, br, r["cagr"], r["dd"], r["final_x"], flush=True)
    elif MODE in ("both", "both2"):
        # ONE shared pot: earnings-drift trades + dip trades, idle money in Clear Leader (cash when SPY < 100-day avg).
        # Drift: stock beat SPY by >= X% on its earnings reaction day (SEC 8-K 2.02; filed before 9:30 -> same day, else next),
        #        buy next open, sell at the close after H trading days. Dip: current best + volume filter, smart exit.
        # Each trade gets 1/slots of the pot; drift buys happen at the open, dip buys at the close (so drift goes first).
        V = VOL[tick]; vr = (V.rolling(5, min_periods=3).mean() / V.rolling(50, min_periods=30).mean().shift(5)).values
        Sv = S & ~(vr > 2.0); Mv = M.values
        Ca = Cf[tick].values; ds = dates.strftime("%Y-%m-%d").values; spv = spy.values
        RX = np.full((D, len(tick)), np.nan)          # reaction (stock minus SPY) on reaction day k, stored at entry day k+1
        for j, t in enumerate(tick):
            for d, mi in (SEC.get(t) or {}).get("events", []):
                k = int(np.searchsorted(ds, d))
                if k < D and ds[k] == d and mi >= 570: k += 1
                if k < 1 or k + 1 >= D or not Mv[k, j]: continue
                c0, c1 = Ca[k, j], Ca[k - 1, j]
                if c0 > 0 and c1 > 0: RX[k + 1, j] = c0 / c1 - 1 - (spv[k] / spv[k - 1] - 1)
        T0 = int(np.searchsorted(dates.values, np.datetime64("2004-09-01")))
        posm = {r["m"]: r["pos"] for r in CLROWS["cl"]}; s100 = sma(100)
        lab = np.array([(posm.get(m, "SPY") if s100[i] else "CASH") for i, m in enumerate(mon)]); park = PKN[100]; years = dates.year.values
        def run(slots=10, use_dip=True, use_drift=True, th=0.05, hold=60, real=False, rate=0.0, split=None):
            cost = 0.0015 if real else 0.0005; eq = 1.0; curve = np.ones(D); pos = []; inv = []; ntr = {"dip": 0, "drift": 0}
            cur = None; seg0 = None; acc = 0.0; st_ = lt_ = cf_s = cf_l = 0.0
            def realize(t):
                nonlocal acc, st_, lt_
                if seg0 is not None and t - seg0 > 252: lt_ += acc
                else: st_ += acc
                acc = 0.0
            def year_end():
                nonlocal st_, lt_, cf_s, cf_l, eq
                a2, b2 = st_ + cf_s, lt_ + cf_l
                if a2 < 0 and b2 > 0: b3 = b2 + a2; a2, b2 = (0.0, b3) if b3 >= 0 else (b3, 0.0)
                if b2 < 0 and a2 > 0: a3 = a2 + b2; a2, b2 = (a3, 0.0) if a3 >= 0 else (0.0, a3)
                eq -= rate * max(a2, 0.0) + (0.15 if rate else 0.0) * max(b2, 0.0); cf_s, cf_l = min(a2, 0.0), min(b2, 0.0); st_ = lt_ = 0.0
            for t in range(T0, D):
                if lab[t] != cur:
                    if cur is not None and cur != "CASH": realize(t)
                    cur = lab[t]; seg0 = t if cur != "CASH" else None
                # 1) drift buys at the open
                if use_drift:
                    row = RX[t]; cand = np.where(row >= th)[0]
                    for j in sorted(cand, key=lambda j: -row[j]):
                        kinds = [p_ for p_ in pos if p_[4] == "drift"]
                        cap = slots if split is None else split[1]
                        if (len(pos) if split is None else len(kinds)) >= cap: break
                        if any(p_[0] == j for p_ in pos) or not (O[tick[j]].values[t] > 0): continue
                        used = sum(p_[2] for p_ in pos); w = min(eq / slots, max(0.0, eq - used))
                        if w <= 1e-9: break
                        pos.append([j, -1, w, w, "drift", t + hold - 1]); eq -= cost * w; ntr["drift"] += 1
                # 2) the day's returns
                used = sum(p_[2] for p_ in pos); pv = max(0.0, eq - used); g = pv * park[t]; acc += g; day = g
                for p_ in pos:
                    gg = OC[t, p_[0]] if (p_[1] == -1 or (p_[4] == "dip" and real and p_[1] == 0)) else Rt[t, p_[0]]
                    if p_[1] == -1: p_[1] = 0
                    day += p_[2] * gg; p_[2] *= 1 + gg
                eq += day; inv.append(used / max(eq, 1e-12))
                # 3) exits at the close
                keep = []
                for p_ in pos:
                    p_[1] += 1
                    out = (t >= p_[5]) if p_[4] == "drift" else (p_[1] >= 5 or over5[t, p_[0]])
                    if out: c = cost * p_[2]; eq -= c; st_ += p_[2] - p_[3] - c - cost * p_[3]
                    else: keep.append(p_)
                pos = keep
                # 4) dip buys at the close (or next open if realistic: same accounting as the dip tests)
                if use_dip:
                    held = {p_[0] for p_ in pos}; used = sum(p_[2] for p_ in pos)
                    room = (slots - len(pos)) if split is None else (split[0] - sum(1 for p_ in pos if p_[4] == "dip"))
                    new = [c for c in sorted(np.where(Sv[t])[0], key=lambda c: -R[t, c]) if c not in held][: max(0, room)]
                    for c in new:
                        w = min(eq / slots, max(0.0, eq - used))
                        if w <= 1e-9: break
                        pos.append([c, 0, w, w, "dip", 0]); eq -= cost * w; used += w; ntr["dip"] += 1
                if t + 1 == D or years[t + 1] != years[t]:
                    if t + 1 == D:
                        for p_ in pos: st_ += p_[2] - p_[3]
                        if cur != "CASH": realize(t)
                    if rate: year_end()
                curve[t] = eq
            c = pd.Series(curve[T0:], index=dates[T0:]); pr = c.pct_change().fillna(0); yrs = len(pr) / 252
            per = {}
            for a2, b2 in [("2004", "2007"), ("2008", "2009"), ("2010", "2015"), ("2016", "2020"), ("2021", "2026")]:
                q = pr[(pr.index >= a2) & (pr.index <= b2 + "-12-31")]; per[a2 + "-" + b2] = round(100 * ((1 + q).prod() ** (252 / max(len(q), 1)) - 1), 1)
            return {"cagr": round(100 * (c.iloc[-1] ** (1 / yrs) - 1), 1), "dd": round(100 * (c / c.cummax() - 1).min(), 1), "per": per,
                    "invested_pct": round(100 * float(np.mean(inv)), 1), "trades_per_year": {k: round(v / yrs, 1) for k, v in ntr.items()}, "final_x": round(float(c.iloc[-1]), 1)}
        sp = spy.iloc[T0:] / spy.iloc[T0]; OUT["SPY_2004"] = {"cagr": round(100 * (sp.iloc[-1] ** (252 / len(sp)) - 1), 1), "dd": round(100 * (sp / sp.cummax() - 1).min(), 1)}
        BOTH = []
        def addb(label, **kw):
            for real in (False, True):
                for rate in (0.0, 0.24):
                    r = run(real=real, rate=rate, **kw); r.update(variant=label, scenario="realistic" if real else "ideal", tax="after tax (24%)" if rate else "before tax")
                    BOTH.append(r); print(label, r["scenario"], r["tax"], r["cagr"], r["dd"], r["invested_pct"], r["trades_per_year"], flush=True)
        if MODE == "both":
            addb("dip only (10 x 10%)", use_drift=False)
            addb("drift only, 5%/60 days (10 x 10%)", use_dip=False)
            addb("SEPARATE: 5 dip slots + 5 drift slots (10% each)", split=(5, 5))
            for sl in (10, 15, 20): addb(f"SHARED pot, {sl} slots ({round(100/sl,1)}% each)", slots=sl)
            for th in (0.04, 0.05, 0.06):          # robustness: drift settings inside the shared pot (15 slots)
                for hd in (50, 60, 70):
                    for real in (False, True):
                        r = run(slots=15, th=th, hold=hd, real=real); r.update(variant=f"[grid] shared 15 slots, drift {int(th*100)}%/{hd}d", scenario="realistic" if real else "ideal", tax="before tax")
                        BOTH.append(r); print(r["variant"], r["scenario"], r["cagr"], r["dd"], flush=True)
        else:
            # robustness of the CAPPED mix: different caps x the 9 drift settings (realistic, before tax),
            # plus each cap at 5%/60d after tax, plus a bigger 6+6 (12 slots, 8.3% each) version
            for caps in ((3, 7), (4, 6), (5, 5), (6, 4), (7, 3)):
                for th in (0.04, 0.05, 0.06):
                    for hd in (50, 60, 70):
                        r = run(split=caps, th=th, hold=hd, real=True); r.update(variant=f"[grid] cap {caps[0]} dip + {caps[1]} drift, drift {int(th*100)}%/{hd}d", caps=list(caps), th=th, hold=hd, scenario="realistic", tax="before tax")
                        BOTH.append(r); print(r["variant"], r["cagr"], r["dd"], flush=True)
                for real in (False, True):
                    for rate in (0.0, 0.24):
                        r = run(split=caps, real=real, rate=rate); r.update(variant=f"cap {caps[0]} dip + {caps[1]} drift (5%/60d)", caps=list(caps), scenario="realistic" if real else "ideal", tax="after tax (24%)" if rate else "before tax")
                        BOTH.append(r); print(r["variant"], r["scenario"], r["tax"], r["cagr"], r["dd"], flush=True)
            for real in (False, True):
                r = run(slots=12, split=(6, 6), real=real); r.update(variant="cap 6 dip + 6 drift, 12 slots x 8.3%", scenario="realistic" if real else "ideal", tax="before tax"); BOTH.append(r); print(r["variant"], r["cagr"], r["dd"], flush=True)
        OUT["both"] = BOTH; OUT["mode"] = MODE
    elif MODE == "curve":
        # daily equity of the live strategy (volume filter, smart exit, Clear Leader parking w/ SPY 100d), for combining with other strategies
        V = VOL[tick]; vr = (V.rolling(5, min_periods=3).mean() / V.rolling(50, min_periods=30).mean().shift(5)).values
        cur = {}
        for tag, b in base_kw:
            r = sim(PKN[100], **b, sig=S & ~(vr > 2.0)); r.update(variant="volume < 2x (live strategy)", scenario=tag); G.append(r); cur[tag] = LASTC[0]
            print("curve", tag, r["cagr"], r["dd"], flush=True)
        pd.DataFrame({"ideal": cur["ideal"], "realistic": cur["realistic"]}).rename_axis("date").to_csv("data/dip_curve.csv", float_format="%.6f")
    elif MODE == "stop":
        for k in (0.08, 0.10, 0.15): add(f"stop-loss at -{int(k*100)}% from buy", stop=k)
    OUT["results"] = G; OUT["mode"] = MODE
    os.makedirs("data", exist_ok=True); json.dump(OUT, open(f"data/dip_filter_{MODE}.json", "w"), indent=1, default=float)
try:
    main()
except Exception:
    os.makedirs("data", exist_ok=True); json.dump({"error": traceback.format_exc()}, open(f"data/dip_filter_{sys.argv[1]}.json", "w")); print(traceback.format_exc()); sys.exit(1)
