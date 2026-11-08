# Four ways to keep money working: sizing, stacking, smarter parking, looser triggers. PIT S&P 500, 1998-2026. Research only.
import os, json, urllib.request, traceback, sys
import pandas as pd, numpy as np
def main():
    REL = "https://github.com/Johnbrick123/sp500-data/releases/download/snapshot-2026-11/"
    for f in ["prices.parquet", "membership_intervals.parquet"]:
        if not os.path.exists("/tmp/" + f): urllib.request.urlretrieve(REL + f, "/tmp/" + f)
    px = pd.read_parquet("/tmp/prices.parquet", columns=["date", "ticker", "close", "adj_close", "volume"])
    px["date"] = pd.to_datetime(px.date); px = px[px.date >= "1997-01-01"]
    mem = pd.read_parquet("/tmp/membership_intervals.parquet"); mem["start"] = pd.to_datetime(mem.start); mem["end"] = pd.to_datetime(mem.end)
    px = px[px.ticker.isin(set(mem.ticker) | {"SPY"})]; px["dv"] = px.volume * px.close
    dates = sorted(px[px.ticker == "SPY"].date.unique()); ALLT = sorted(px.ticker.unique())
    P = lambda v: px.pivot_table(index="date", columns="ticker", values=v, dropna=False).reindex(index=dates, columns=ALLT)
    C, DV = P("adj_close"), P("dv"); del px
    valid = C.notna(); Cf = C.ffill(); tick = [t for t in ALLT if t != "SPY"]
    M = pd.DataFrame(False, index=dates, columns=tick)
    for _, m in mem.iterrows():
        if m.ticker in M.columns:
            e = m.end if pd.notna(m.end) else pd.Timestamp("2100-01-01")
            M.loc[(M.index >= m.start) & (M.index < e), m.ticker] = True
    M &= valid[tick] & valid[tick].shift(-1, fill_value=False)
    spy = Cf["SPY"]; spyr = spy.pct_change().fillna(0).values
    up = (spy > spy.rolling(200).mean()); U = up.values[:, None]
    trend_park = (spy > spy.rolling(210).mean()).shift(1, fill_value=False).values  # ~10-month avg, decided yesterday
    above = Cf[tick] > Cf[tick].rolling(200).mean()
    r1 = Cf[tick].pct_change().sub(spy.pct_change(), axis=0); rv = DV[tick] / DV[tick].rolling(20).mean().shift(1)
    Rt = Cf[tick].pct_change().fillna(0).values
    D = len(dates); START = int(np.searchsorted(np.array(dates), np.datetime64("1998-01-01")))
    def dip(lb, thr, mkt=True):
        rl = Cf[tick].pct_change(lb).sub(spy.pct_change(lb), axis=0)
        s = (rl <= -thr) & above & M
        if mkt: s &= U
        return s.values, (-rl).values
    brk = ((r1 >= 0.05) & (rv >= 3) & U & M).values; brk_rank = r1.values
    def sim(sigs, idle="spy", cap=0.10, slots=10, cost=0.0005):
        """sigs: list of (signal, rank, hold). Weight per new position = min(cap, free/new). idle: spy | cash | trend."""
        eq = 1.0; curve = np.ones(D); pos = []; tr = []; inv = []
        for t in range(START, D):
            used = sum(p[2] for p in pos); day = 0.0
            for p in pos:
                g = Rt[t, p[0]]; p[3] *= 1 + g; day += p[2] * g
            park = spyr[t] if (idle == "spy" or (idle == "trend" and trend_park[t])) else 0.0
            day += max(0.0, 1 - used) * park; inv.append(used); eq *= 1 + day
            keep = []
            for p in pos:
                p[1] += 1; p[2] *= (1 + Rt[t, p[0]]) / (1 + day)  # drift weight with prices
                if p[1] >= p[4]: eq *= 1 - cost * p[2]; tr.append(p[3] - 1 - 2 * cost)
                else: keep.append(p)
            pos = keep; used = sum(p[2] for p in pos)
            held = {p[0] for p in pos}; new = []
            for S, R, h in sigs:
                for c in sorted(np.where(S[t])[0], key=lambda c: -R[t, c]):
                    if c not in held and c not in [n[0] for n in new]: new.append((c, h))
            new = new[: max(0, slots - len(pos))]
            if new:
                w = min(cap, max(0.0, 1 - used) / len(new))
                for c, h in new:
                    if w <= 0: break
                    pos.append([c, 0, w, 1.0, h]); eq *= 1 - cost * w
            curve[t] = eq
        c = pd.Series(curve[START:], index=dates[START:]); p = c.pct_change().fillna(0); yrs = len(p) / 252
        per = {}
        for a, b in [("1998", "2002"), ("2003", "2007"), ("2008", "2009"), ("2010", "2015"), ("2016", "2020"), ("2021", "2026")]:
            q = p[(p.index >= a) & (p.index <= b + "-12-31")]; per[a + "-" + b] = round(100 * ((1 + q).prod() ** (252 / max(len(q), 1)) - 1), 1)
        tr = np.array(tr) if tr else np.array([0.0])
        return {"cagr": round(100 * (c.iloc[-1] ** (1 / yrs) - 1), 1), "dd": round(100 * (c / c.cummax() - 1).min(), 1), "per": per,
                "invested_pct": round(100 * float(np.mean(inv)), 1), "trades_per_month": round(len(tr) / (yrs * 12), 1), "avg_trade": round(100 * tr.mean(), 2), "win_rate": round(100 * (tr > 0).mean(), 1)}
    sc = spy.iloc[START:] / spy.iloc[START]
    OUT = {"SPY": {"cagr": round(100 * (sc.iloc[-1] ** (252 / len(sc)) - 1), 1), "dd": round(100 * (sc / sc.cummax() - 1).min(), 1)}}
    d10 = dip(5, 0.10); d8 = dip(5, 0.08); d10s = dip(5, 0.10, mkt=False)
    base = [(d10[0], d10[1], 3)]
    V = []
    def add(group, name, sigs, **kw):
        for idle in ("cash", "spy", "trend"):
            s = sim(sigs, idle=idle, **kw); s.update(group=group, name=name, idle=idle); V.append(s); print(group, name, idle, s["cagr"], s["dd"], s["invested_pct"], flush=True)
    add("0 baseline", "dip 10%, 10 slots of 10%", base)
    for cap in (0.20, 0.33, 0.50):
        add("1 bigger bets", f"dip 10%, up to {int(cap*100)}% per trade", base, cap=cap)
    add("2 stack", "dip 10% (3d) + breakout (20d)", base + [(brk, brk_rank, 20)])
    add("2 stack", "dip 10% + breakout, up to 33% per trade", base + [(brk, brk_rank, 20)], cap=0.33)
    add("4 looser", "dip 8%", [(d8[0], d8[1], 3)])
    add("4 looser", "dip 10%, no market filter", [(d10s[0], d10s[1], 3)])
    add("combo", "dip 8% no market filter + breakout, up to 33%", [(dip(5, 0.08, False)[0], dip(5, 0.08, False)[1], 3), (brk, brk_rank, 20)], cap=0.33)
    OUT["variants"] = V
    OUT["note"] = "idle: cash = 0%; spy = SPY; trend = SPY when SPY above ~10-month average, else cash (stand-in for Clear Leader crash filter; no daily Clear Leader series available). Earnings drift not stacked: SEC events only from 2004."
    os.makedirs("data", exist_ok=True); json.dump(OUT, open("data/money_working.json", "w"), indent=1, default=float)
try:
    main()
except Exception:
    os.makedirs("data", exist_ok=True); json.dump({"error": traceback.format_exc()}, open("data/money_working.json", "w")); print(traceback.format_exc()); sys.exit(1)
