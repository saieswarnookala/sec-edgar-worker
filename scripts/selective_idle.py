# Selective short-term trades: only trade on strong setups, otherwise hold SPY. PIT S&P 500 (Johnbrick123/sp500-data), 1998-2026.
# Signal on day t close (excess move vs SPY + volume spike, optional market trend filter); enter close t (or open t+1); hold h days; 10 slots; costs 0.05%/side; idle -> SPY.
import os, json, urllib.request, traceback, sys
import pandas as pd, numpy as np
def main():
    REL = "https://github.com/Johnbrick123/sp500-data/releases/download/snapshot-2026-11/"
    for f in ["prices.parquet", "membership_intervals.parquet"]:
        if not os.path.exists("/tmp/" + f): urllib.request.urlretrieve(REL + f, "/tmp/" + f)
    px = pd.read_parquet("/tmp/prices.parquet", columns=["date", "ticker", "open", "close", "adj_close", "volume"])
    px["date"] = pd.to_datetime(px.date); px = px[px.date >= "1997-01-01"]
    mem = pd.read_parquet("/tmp/membership_intervals.parquet"); mem["start"] = pd.to_datetime(mem.start); mem["end"] = pd.to_datetime(mem.end)
    px = px[px.ticker.isin(set(mem.ticker) | {"SPY"})]
    px["aopen"] = px.open * px.adj_close / px.close; px["dv"] = px.volume * px.close
    dates = sorted(px[px.ticker == "SPY"].date.unique()); ALLT = sorted(px.ticker.unique())
    P = lambda v: px.pivot_table(index="date", columns="ticker", values=v, dropna=False).reindex(index=dates, columns=ALLT)
    C, O, DV = P("adj_close"), P("aopen"), P("dv"); del px
    valid = C.notna(); Cf = C.ffill()
    tick = [t for t in ALLT if t != "SPY"]
    M = pd.DataFrame(False, index=dates, columns=tick)
    for _, m in mem.iterrows():
        if m.ticker in M.columns:
            e = m.end if pd.notna(m.end) else pd.Timestamp("2100-01-01")
            M.loc[(M.index >= m.start) & (M.index < e), m.ticker] = True
    M &= valid[tick] & valid[tick].shift(-1, fill_value=False)
    spy = Cf["SPY"]; spyr = spy.pct_change().fillna(0)
    up = spy > spy.rolling(200).mean()
    r1 = Cf[tick].pct_change(); ex1 = r1.sub(spyr, axis=0)
    r5 = Cf[tick].pct_change(5).sub(spy.pct_change(5), axis=0)
    rv = DV[tick] / DV[tick].rolling(20).mean().shift(1)
    above = Cf[tick] > Cf[tick].rolling(200).mean()
    Rt = Cf[tick].pct_change().fillna(0).values; Ot = (Cf[tick] / O[tick] - 1).fillna(0).values
    D = len(dates); START = np.searchsorted(np.array(dates), np.datetime64("1998-01-01"))
    def sim(sig, hold, entry="close", slots=10, cost=0.0005, rank=None, idle="spy"):
        S = sig.values; RK = rank.values if rank is not None else None
        eq = 1.0; curve = np.ones(D); pos = []  # [col, days_held, weight]
        ntr = 0; wins = 0; tr_ret = []; invested = []
        for t in range(START, D):
            # returns for day t
            day = 0.0; used = sum(p[2] for p in pos)
            for p in pos:
                g = Ot[t, p[0]] if (p[1] == 0 and entry == "open") else Rt[t, p[0]]
                p[3] *= 1 + g; day += p[2] * g
            day += (1 - used) * (spyr.values[t] if idle == "spy" else 0.0)
            invested.append(used)
            eq *= 1 + day
            keep = []
            for p in pos:
                p[1] += 1
                if p[1] >= hold:
                    eq *= 1 - cost * p[2]; tr_ret.append(p[3] - 1 - 2 * cost); ntr += 1
                else: keep.append(p)
            pos = keep
            free = slots - len(pos)
            if free > 0:
                cand = np.where(S[t])[0]
                held = {p[0] for p in pos}; cand = [c for c in cand if c not in held]
                if RK is not None: cand = sorted(cand, key=lambda c: -RK[t, c])
                for c in cand[:free]:
                    eq *= 1 - cost / slots
                    if entry == "close": pos.append([c, 0, 1 / slots, 1.0]); pos[-1][1] = 0
                    else: pos.append([c, -0, 1 / slots, 1.0])
            if entry == "close":
                for p in pos:
                    if p[1] == 0: p[1] = 0
            curve[t] = eq
        c = pd.Series(curve[START:], index=dates[START:]); p = c.pct_change().fillna(0)
        yrs = len(p) / 252; cagr = c.iloc[-1] ** (1 / yrs) - 1; dd = (c / c.cummax() - 1).min()
        per = {}
        for a, b in [("1998", "2002"), ("2003", "2007"), ("2008", "2009"), ("2010", "2015"), ("2016", "2020"), ("2021", "2026")]:
            q = p[(p.index >= a) & (p.index <= b + "-12-31")]; per[a + "-" + b] = round(100 * ((1 + q).prod() ** (252 / max(len(q), 1)) - 1), 1)
        tr = np.array(tr_ret) if tr_ret else np.array([0.0])
        return {"cagr": round(100 * cagr, 1), "dd": round(100 * dd, 1), "per": per, "trades": ntr, "trades_per_month": round(ntr / (yrs * 12), 1),
                "avg_trade": round(100 * tr.mean(), 2), "avg_invested_pct": round(100 * float(np.mean(invested)), 1), "win_rate": round(100 * (tr > 0).mean(), 1)}
    # SPY baseline
    sc = spy.iloc[START:] / spy.iloc[START]; sp = sc.pct_change().fillna(0)
    OUT = {"SPY": {"cagr": round(100 * (sc.iloc[-1] ** (252 / len(sc)) - 1), 1), "dd": round(100 * (sc / sc.cummax() - 1).min(), 1)}}
    V = []
    U = up.values[:, None]
    for lb, thr, h, filt in [(5, 0.10, 3, "both"), (5, 0.08, 3, "both"), (7, 0.10, 2, "both"), (5, 0.10, 3, "stock only")]:
        rl = Cf[tick].pct_change(lb).sub(spy.pct_change(lb), axis=0)
        sig = (rl <= -thr) & above & M & (U if filt == "both" else True)
        for idle in ("spy", "cash"):
            s = sim(sig, h, "close", rank=-rl, idle=idle); s.update(name=f"{lb}d dip >={int(thr*100)}%, hold {h}, filters {filt}", idle=idle); V.append(s); print(s, flush=True)
    V.sort(key=lambda v: -v["cagr"]); OUT["variants"] = V
    os.makedirs("data", exist_ok=True); json.dump(OUT, open("data/selective_idle.json", "w"), indent=1, default=float)
try:
    main()
except Exception:
    os.makedirs("data", exist_ok=True); json.dump({"error": traceback.format_exc()}, open("data/selective_idle.json", "w")); print(traceback.format_exc()); sys.exit(1)
