# Test 4 improvements ONE AT A TIME on the final "dip + smart parking" strategy. PIT S&P 500, 1998-2026. Research only.
import os, json, urllib.request, traceback, sys
import pandas as pd, numpy as np
def main():
    REL = "https://github.com/Johnbrick123/sp500-data/releases/download/snapshot-2026-11/"
    for f in ["prices.parquet", "membership_intervals.parquet"]:
        if not os.path.exists("/tmp/" + f): urllib.request.urlretrieve(REL + f, "/tmp/" + f)
    px = pd.read_parquet("/tmp/prices.parquet", columns=["date", "ticker", "open", "close", "adj_close"])
    px["date"] = pd.to_datetime(px.date); px = px[px.date >= "1997-01-01"]
    mem = pd.read_parquet("/tmp/membership_intervals.parquet"); mem["start"] = pd.to_datetime(mem.start); mem["end"] = pd.to_datetime(mem.end)
    px = px[px.ticker.isin(set(mem.ticker) | {"SPY"})]; px["aopen"] = px.open * px.adj_close / px.close
    dates = sorted(px[px.ticker == "SPY"].date.unique()); ALLT = sorted(px.ticker.unique())
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
    park = (spy > spy.rolling(210).mean()).shift(1, fill_value=False).values
    above = Cf[tick] > Cf[tick].rolling(200).mean()
    Rt = Cf[tick].pct_change().fillna(0).values
    OC = (Cf[tick] / O[tick] - 1).fillna(0).values          # open -> close (next-morning entry first day)
    over5 = (Cf[tick] > Cf[tick].rolling(5).mean()).values  # bounced above 5-day average
    vol = spy.pct_change().rolling(20).std()
    fear = (vol > vol.rolling(252).quantile(0.8)).values   # SPY volatility in top 20% of past year (VIX stand-in)
    D = len(dates); START = int(np.searchsorted(np.array(dates), np.datetime64("1998-01-01")))
    def dip(lb, thr):
        rl = Cf[tick].pct_change(lb).sub(spy.pct_change(lb), axis=0)
        return ((rl <= -thr) & above & M).values, (-rl).values
    def sim(S, R, hold=3, cost=0.0005, entry="close", smart_exit=False, max_hold=None, boost=False, slots=10):
        eq = 1.0; curve = np.ones(D); pos = []; tr = []; inv = []
        for t in range(START, D):
            used = sum(p[2] for p in pos); day = 0.0
            for p in pos:
                g = OC[t, p[0]] if (entry == "open" and p[1] == 0) else Rt[t, p[0]]
                p[3] *= 1 + g; day += p[2] * g
            day += max(0.0, 1 - used) * (spyr[t] if park[t] else 0.0); inv.append(used); eq *= 1 + day
            keep = []
            for p in pos:
                g = OC[t, p[0]] if (entry == "open" and p[1] == 0) else Rt[t, p[0]]
                p[1] += 1; p[2] *= (1 + g) / (1 + day)
                limit = max_hold if smart_exit else hold
                if p[1] >= limit or (smart_exit and over5[t, p[0]]):
                    eq *= 1 - cost * p[2]; tr.append((p[3] - 1 - 2 * cost, p[1]))
                else: keep.append(p)
            pos = keep; used = sum(p[2] for p in pos)
            held = {p[0] for p in pos}
            new = [c for c in sorted(np.where(S[t])[0], key=lambda c: -R[t, c]) if c not in held][: max(0, slots - len(pos))]
            if new:
                cap = 0.20 if (boost and fear[t]) else 0.10
                w = min(cap, max(0.0, 1 - used) / len(new))
                for c in new:
                    pos.append([c, 0, w, 1.0]); eq *= 1 - cost * w
            curve[t] = eq
        return curve, tr, inv
    def stats(curve, tr=None, inv=None):
        c = pd.Series(curve[START:], index=dates[START:]); p = c.pct_change().fillna(0); yrs = len(p) / 252
        per = {}
        for a, b in [("1998", "2002"), ("2003", "2007"), ("2008", "2009"), ("2010", "2015"), ("2016", "2020"), ("2021", "2026")]:
            q = p[(p.index >= a) & (p.index <= b + "-12-31")]; per[a + "-" + b] = round(100 * ((1 + q).prod() ** (252 / max(len(q), 1)) - 1), 1)
        o = {"cagr": round(100 * (c.iloc[-1] ** (1 / yrs) - 1), 1), "dd": round(100 * (c / c.cummax() - 1).min(), 1), "per": per}
        if tr:
            r = np.array([x[0] for x in tr]); h = np.array([x[1] for x in tr])
            o.update(trades_per_month=round(len(r) / (yrs * 12), 1), win_rate=round(100 * (r > 0).mean(), 1), avg_trade=round(100 * r.mean(), 2), avg_days_held=round(float(h.mean()), 1))
        if inv: o["invested_pct"] = round(100 * float(np.mean(inv)), 1)
        return o
    sc = spy.iloc[START:] / spy.iloc[START]
    OUT = {"SPY": {"cagr": round(100 * (sc.iloc[-1] ** (252 / len(sc)) - 1), 1), "dd": round(100 * (sc / sc.cummax() - 1).min(), 1)}}
    S, R = dip(5, 0.10); V = {}
    def run(key, label, **kw):
        cv, tr, inv = sim(S, R, **kw); s = stats(cv, tr, inv); s["label"] = label; V[key] = s; print(key, s, flush=True)
    run("0_baseline", "Final strategy as is (buy at close, 0.05%/side, sell after 3 days)")
    # 1. Realistic entry
    run("1a_costs", "1. Realistic: higher costs 0.15%/side (slippage)", cost=0.0015)
    run("1b_open", "1. Realistic: buy next morning's open", entry="open")
    run("1c_open_costs", "1. Realistic: next morning open + 0.15%/side", entry="open", cost=0.0015)
    # 2. Smarter exit
    run("2a_exit5", "2. Smart exit: sell when back above 5-day average (max 5 days)", smart_exit=True, max_hold=5)
    run("2b_exit10", "2. Smart exit: sell when back above 5-day average (max 10 days)", smart_exit=True, max_hold=10)
    # 3. Blend of nearby versions (equal money, no rebalancing)
    curves = []
    for lb, thr, h in [(5, 0.08, 2), (5, 0.08, 3), (5, 0.10, 2), (5, 0.10, 3)]:
        s2, r2 = dip(lb, thr); cv, _, _ = sim(s2, r2, hold=h); curves.append(cv / cv[START])
    s = stats(np.mean(curves, axis=0)); s["label"] = "3. Blend: 8%/10% dip x 2/3-day hold, equal money"; V["3_blend"] = s; print("3_blend", s, flush=True)
    # 4. Fear filter: double size when market volatility is high
    run("4_fear", "4. Fear boost: up to 20% per trade when SPY volatility is in top 20% of past year", boost=True)
    OUT["variants"] = V
    OUT["note"] = "Each improvement tested alone on the final strategy (5-day dip >=10% vs SPY, stock above 200d, hold 3, waiting money in SPY only above ~10-month average). VIX not in dataset; SPY 20-day volatility used instead."
    os.makedirs("data", exist_ok=True); json.dump(OUT, open("data/dip_improvements.json", "w"), indent=1, default=float)
try:
    main()
except Exception:
    os.makedirs("data", exist_ok=True); json.dump({"error": traceback.format_exc()}, open("data/dip_improvements.json", "w")); print(traceback.format_exc()); sys.exit(1)
