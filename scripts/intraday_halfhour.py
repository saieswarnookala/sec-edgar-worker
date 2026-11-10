# Strategy B: first half-hour predicts last half-hour (Gao/Han/Li/Zhou). SPY and QQQ 1-min, 2016-now. Research only.
# Signal at 15:30 from the 9:30-10:00 return (and optionally the 15:00-15:30 return); hold 15:30 -> 16:00.
import sys, traceback
import numpy as np, pandas as pd
sys.path.insert(0, "scripts"); from intraday_common import bars, stats, spy_daily_stats, save

def run():
    res = {"results": []}
    for sym in ("SPY", "QQQ"):
        df = bars([sym], "1Min"); df["d"] = df.t.dt.normalize(); df["m"] = df.t.dt.hour * 60 + df.t.dt.minute - 570
        C = df.pivot_table(index="d", columns="m", values="c").reindex(columns=range(390)).ffill(axis=1)
        Op = df.groupby("d").o.first()
        r1 = C[29] / Op - 1; r12 = C[359] / C[329] - 1; rl = C[389] / C[359] - 1
        q = r1.abs().rolling(250).quantile(0.7).shift(1)
        rules = {
            "long last 30 min if first 30 min up": (r1 > 0).astype(float),
            "long/short by first 30 min": np.sign(r1),
            "long if first 30 min AND 15:00-15:30 both up": ((r1 > 0) & (r12 > 0)).astype(float),
            "long/short, only big first-30-min moves (top 30%)": np.sign(r1) * (r1.abs() > q),
            "long only, big up first 30 min (top 30%)": ((r1 > 0) & (r1.abs() > q)).astype(float),
            "always long last 30 min (baseline)": pd.Series(1.0, index=r1.index),
        }
        for name, sig in rules.items():
            for tag, cost in [("ideal 0.02%/side", 0.0002), ("realistic 0.05%/side", 0.0005)]:
                s = sig.fillna(0); daily = s * rl - 2 * cost * s.abs()
                st = stats(daily); st.update(symbol=sym, rule=name, costs=tag, trades=int((s != 0).sum()), win_rate=round(100 * float(((s * rl) > 0)[s != 0].mean()), 1))
                res["results"].append(st); print(sym, name, tag, st["cagr"], st["dd"], st["sharpe"], st["trades"], flush=True)
            # PDT: at most 3 trades per week (first 3 signals)
            s = sig.fillna(0).copy(); wk = pd.Series([d.isocalendar()[:2] for d in s.index], index=s.index); n = {}
            for d in s.index:
                if s[d] != 0:
                    k = wk[d]; n[k] = n.get(k, 0) + 1
                    if n[k] > 3: s[d] = 0
            daily = s * rl - 2 * 0.0005 * s.abs(); st = stats(daily); st.update(symbol=sym, rule=name + " [max 3/week]", costs="realistic 0.05%/side", trades=int((s != 0).sum()))
            res["results"].append(st)
    res["benchmark_SPY"] = spy_daily_stats()
    save("intraday_halfhour", res)

try: run()
except Exception: save("intraday_halfhour", {"error": traceback.format_exc()}); print(traceback.format_exc()); sys.exit(1)
