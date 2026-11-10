# Strategy A: SPY intraday momentum ("Noise Area", Zarattini/Aziz/Barbon 2024) on Alpaca 1-min SPY, 2016-now. Research only.
# Each day: open O, prior close C1. sigma(m) = 14-day average of |close at minute m / open - 1|. Upper = max(O,C1)*(1+sigma), Lower = min(O,C1)*(1-sigma).
# Check every :00 and :30 from 10:00 to 15:30. Flat: price > Upper -> long, < Lower -> short. Long exits when price < max(Upper, VWAP) (short mirror). Flat at the close.
import sys, traceback, os
import numpy as np, pandas as pd
sys.path.insert(0, "scripts"); from intraday_common import bars, stats, spy_daily_stats, save

def run():
    sym = os.environ.get("SYM", "SPY")
    df = bars([sym], "1Min")
    df["d"] = df.t.dt.normalize(); df["m"] = df.t.dt.hour * 60 + df.t.dt.minute - 570
    days = sorted(df.d.unique()); print(sym, len(df), "bars", len(days), "days", flush=True)
    # minute grid per day (forward-fill gaps)
    C = df.pivot_table(index="d", columns="m", values="c").reindex(columns=range(390)).ffill(axis=1)
    Op = df.groupby("d").o.first(); tp = (df.h + df.l + df.c) / 3
    df["pv"] = tp * df.v
    PV = df.pivot_table(index="d", columns="m", values="pv", aggfunc="sum").reindex(columns=range(390)).fillna(0).cumsum(axis=1)
    V = df.pivot_table(index="d", columns="m", values="v", aggfunc="sum").reindex(columns=range(390)).fillna(0).cumsum(axis=1)
    VWAP = (PV / V.replace(0, np.nan)).ffill(axis=1)
    move = (C.div(Op, axis=0) - 1).abs()
    sigma = move.rolling(14).mean().shift(1)   # previous 14 days only
    close = C[389].fillna(C.ffill(axis=1).iloc[:, -1]); prevc = close.shift(1)
    dret = close.pct_change()
    vol14 = dret.rolling(14).std().shift(1)
    checks = [30 + 30 * k for k in range(12)]   # 10:00 .. 15:30
    res = {}
    def sim(long_only=False, cost=0.0002, sizing="1x", pdt=False):
        out = pd.Series(0.0, index=C.index); trades = []; week_count = {}
        for d in C.index:
            if pd.isna(sigma.loc[d, 60]) or pd.isna(prevc.loc[d]): continue
            O, C1 = Op.loc[d], prevc.loc[d]; up_b, lo_b = max(O, C1), min(O, C1)
            lev = 1.0 if sizing == "1x" else float(min(4.0, 0.02 / vol14.loc[d])) if vol14.loc[d] > 0 else 1.0
            wk = d.isocalendar()[:2]
            pos, entry, r = 0, None, 0.0
            for m in checks:
                p = C.loc[d, m]; s = sigma.loc[d, m]
                if pd.isna(p) or pd.isna(s): continue
                ub, lb, vw = up_b * (1 + s), lo_b * (1 - s), VWAP.loc[d, m]
                if pos == 1 and p < max(ub, vw): r += lev * (p / entry - 1) - lev * cost; pos = 0
                elif pos == -1 and p > min(lb, vw): r += lev * (entry / p - 1) - lev * cost; pos = 0
                if pos == 0:
                    if pdt and week_count.get(wk, 0) >= 3: continue
                    if p > ub: pos, entry = 1, p
                    elif p < lb and not long_only: pos, entry = -1, p
                    if pos: r -= lev * cost; trades.append(d); week_count[wk] = week_count.get(wk, 0) + 1
            if pos:
                p = C.loc[d, 389]
                r += lev * ((p / entry - 1) if pos == 1 else (entry / p - 1)) - lev * cost
            out.loc[d] = r
        st = stats(out); st["trades"] = len(trades); st["days_traded"] = len(set(trades)); return st
    for name, kw in [("long+short, 1x", {}), ("long only, 1x", dict(long_only=True)), ("long+short, vol target (<=4x)", dict(sizing="vol")),
                     ("long only, 3 trades/week (PDT)", dict(long_only=True, pdt=True))]:
        for tag, cost in [("no costs", 0.0), ("SPY spread ~0.002%/side", 0.00002), ("0.01%/side", 0.0001), ("0.02%/side", 0.0002)]:
            r = sim(cost=cost, **kw); r.update(variant=name, costs=tag); res.setdefault("results", []).append(r); print(name, tag, {k: r[k] for k in ("cagr", "dd", "sharpe", "trades")}, r.get("to_apr2024"), r.get("may2024_on"), flush=True)
    res["benchmark_" + sym] = spy_daily_stats() if sym == "SPY" else None
    res["note"] = "Alpaca 1-min SIP, regular hours, 2016-now. Paper sample ended Apr 2024: 'may2024_on' is out-of-sample for its rules."
    save("intraday_spy_momentum" + ("" if sym == "SPY" else "_" + sym.lower()), res)

try: run()
except Exception: save("intraday_spy_momentum", {"error": traceback.format_exc()}); print(traceback.format_exc()); sys.exit(1)
