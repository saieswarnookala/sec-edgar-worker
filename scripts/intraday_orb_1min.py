# Strategy C, done properly: Opening Range Breakout re-simulated on 1-MINUTE bars (5-min bars could not tell whether the
# tight stop or the entry came first). Uses the candidate list from intraday_orb.py (same filters: S&P 500, price > $5,
# avg volume >= 1M, ATR > $0.50, opening relative volume >= 1). Only the top-20 per day (all, and long-only) are re-simulated.
import sys, os, glob, time, traceback
import numpy as np, pandas as pd
sys.path.insert(0, "scripts"); from intraday_common import bars, stats, save

def candidates():
    T = pd.read_csv("data/intraday_orb_trades.csv.gz", parse_dates=["d"])
    a = T.sort_values(["d", "rv"], ascending=[True, False]).groupby("d").head(20)
    b = T[T.long == 1].sort_values(["d", "rv"], ascending=[True, False]).groupby("d").head(20)
    return pd.concat([a, b]).drop_duplicates(["d", "sym"])[["d", "sym", "rv"]]

def atr_table(syms):
    out = {}
    for i in range(0, len(syms), 50):
        df = bars(syms[i:i + 50], "1Day", regular=False)
        for s, g in df.groupby("sym"):
            g = g.set_index(g.t.dt.normalize()); pc = g.c.shift(1)
            tr = pd.concat([g.h - g.l, (g.h - pc).abs(), (g.l - pc).abs()], axis=1).max(axis=1)
            out[s] = tr.rolling(14).mean().shift(1)
    return out

def simulate(b, atr):
    """b: one symbol's 1-min bars for one day (9:30-15:59). Returns (long, ret, risk) or None."""
    mm = b.t.dt.hour.values * 60 + b.t.dt.minute.values
    orb = b[mm < 575]; rest = b[mm >= 575]
    if len(orb) < 3 or rest.empty or not atr > 0: return None
    o, h, l, c = orb.o.iloc[0], orb.h.max(), orb.l.min(), orb.c.iloc[-1]
    if c == o: return None
    long = c > o; lvl = h if long else l; risk = 0.1 * atr
    entry = stop = ex = None
    for bo, bh, bl, bc in zip(rest.o.values, rest.h.values, rest.l.values, rest.c.values):
        if entry is None:
            if long and bh >= lvl: entry = max(lvl, bo); stop = entry - risk
            elif not long and bl <= lvl: entry = min(lvl, bo); stop = entry + risk
            else: continue
            if (long and bl <= stop) or (not long and bh >= stop): ex = stop; break   # same-minute stop: count as loss
            continue
        if long:
            if bo <= stop: ex = bo; break
            if bl <= stop: ex = stop; break
        else:
            if bo >= stop: ex = bo; break
            if bh >= stop: ex = stop; break
    if entry is None: return None
    if ex is None: ex = rest.c.values[-1]
    return int(long), (ex / entry - 1) if long else (entry / ex - 1), risk / entry

def collect(k, n):
    U = candidates(); days = sorted(U.d.unique())[k::n]; U = U[U.d.isin(days)]
    atr = atr_table(sorted(U.sym.unique())); rows = []; t0 = time.time()
    for j, d in enumerate(days):
        x = U[U.d == d]; d = pd.Timestamp(d)
        st = d.replace(hour=9, minute=30).tz_localize("America/New_York").tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
        en = d.replace(hour=16).tz_localize("America/New_York").tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
        df = bars(list(x.sym), "1Min", start=st, end=en)
        for s, b in df.groupby("sym"):
            a = atr.get(s); a = a.get(d, np.nan) if a is not None else np.nan
            r = simulate(b, a)
            if r: rows.append((d, s, float(x[x.sym == s].rv.iloc[0]), *r))
        if j % 50 == 0: print(j, "/", len(days), "days", len(rows), "trades", round((time.time() - t0) / 60, 1), "min", flush=True)
    os.makedirs("parts", exist_ok=True)
    pd.DataFrame(rows, columns=["d", "sym", "rv", "long", "ret", "risk"]).to_csv(f"parts/orb1_part_{k}.csv.gz", index=False)

def run():
    T = pd.concat([pd.read_csv(f, parse_dates=["d"]) for f in glob.glob("parts/**/orb1_part_*.csv.gz", recursive=True)])
    T.to_csv("data/intraday_orb_1min_trades.csv.gz", index=False); print(len(T), "trades", flush=True)
    days = pd.DatetimeIndex(sorted(bars(["SPY"], "1Day", regular=False).t.dt.normalize().unique()))
    res = {"results": [], "trades_simulated": len(T)}
    def port(topn=20, long_only=False, cost=0.001, sizing="equal", pdt=False):
        x = T[T.long == 1] if long_only else T
        x = x.sort_values(["d", "rv"], ascending=[True, False]).groupby("d").head(1 if pdt else topn)
        if pdt:
            wk = x.d.map(lambda d: d.isocalendar()[:2]); x = x[x.groupby(wk).cumcount() < 3]
        if sizing == "equal": w = pd.Series(1.0 if pdt else 1.0 / topn, index=x.index)
        else:
            w = (0.01 / x.risk).clip(upper=4.0); tot = w.groupby(x.d).transform("sum"); w = w * np.minimum(1, 4.0 / tot)
        daily = (w * (x.ret - 2 * cost)).groupby(x.d).sum().reindex(days).fillna(0)
        st = stats(daily); st.update(trades=len(x), win_rate=round(100 * float((x.ret > 2 * cost).mean()), 1), avg_trade_pct=round(100 * float((x.ret - 2 * cost).mean()), 3), avg_gross_pct=round(100 * float(x.ret.mean()), 3))
        return st
    variants = [("top 20, long+short, equal 5% each", {}), ("top 20, long only, equal 5% each", dict(long_only=True)),
                ("top 20, long+short, paper sizing (1% risk, <=4x)", dict(sizing="risk")), ("top 5, long+short, equal 20% each", dict(topn=5)),
                ("1 stock/day, max 3/week, long only, 100% (PDT)", dict(pdt=True, long_only=True)), ("1 stock/day, max 3/week, long+short, 100% (PDT)", dict(pdt=True))]
    for name, kw in variants:
        for tag, cost in [("no costs", 0.0), ("0.02%/side", 0.0002), ("0.05%/side", 0.0005), ("0.10%/side", 0.001)]:
            st = port(cost=cost, **kw); st.update(variant=name, costs=tag); res["results"].append(st)
            print(name, tag, st.get("cagr"), st.get("dd"), st.get("trades"), st.get("win_rate"), st.get("avg_gross_pct"), flush=True)
    save("intraday_orb_1min", res)

try:
    if sys.argv[1:2] == ["collect"]: collect(int(sys.argv[2]), int(sys.argv[3]))
    else: run()
except Exception:
    if sys.argv[1:2] == ["collect"]: raise
    save("intraday_orb_1min", {"error": traceback.format_exc()}); print(traceback.format_exc()); sys.exit(1)
