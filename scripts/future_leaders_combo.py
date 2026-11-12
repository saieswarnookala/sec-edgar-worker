import sys, json, numpy as np, pandas as pd
sys.argv = ["x", "/tmp/fl/ignore.json"]
exec(open("scripts/future_leaders.py").read().split("res = {")[0])
dip = pd.read_csv("data/dip_curve.csv", index_col=0, parse_dates=True)["realistic"]
idx = dates[START:D]; dip = dip.reindex(idx).ffill()
spyc = pd.Series(spy[START:D] / spy[START], index=idx)
cfgs = {"oos_pick (8, 80%, 15% of high, mkt filter+exit)": dict(kind="run", N=8, mom_q=0.8, near_hi=0.85, trend=True, trend_exit=True, exit_rule="ma200"),
        "hindsight_best (10, 90%, 10%, mkt filter)": dict(kind="run", N=10, mom_q=0.9, near_hi=0.9, trend=True, exit_rule="ma200"),
        "plain (15, 90%, 10%, no filter)": dict(kind="run", N=15, mom_q=0.9, near_hi=0.9, exit_rule="ma200")}
def stats(c):
    c = c / c.iloc[0]; yrs = len(c) / 252; mid = c.index >= "2012-01-01"
    h1 = c[~mid]; h2 = c[mid]
    return dict(cagr=round((c.iloc[-1] ** (1 / yrs) - 1) * 100, 1), dd=round(float((c / c.cummax() - 1).min()) * 100, 1),
                h1=round(((h1.iloc[-1] / h1.iloc[0]) ** (252 / len(h1)) - 1) * 100, 1), h2=round(((h2.iloc[-1] / h2.iloc[0]) ** (252 / len(h2)) - 1) * 100, 1))
def blend(a, b, w):   # monthly rebalanced mix of two daily curves
    ra, rb = a.pct_change().fillna(0), b.pct_change().fillna(0); m = a.index.to_period("M")
    out = []; v = 1.0; wa = w
    for i in range(len(a)):
        if i == 0 or m[i] != m[i - 1]: va, vb = v * w, v * (1 - w)
        va *= 1 + ra.iloc[i]; vb *= 1 + rb.iloc[i]; v = va + vb; out.append(v)
    return pd.Series(out, index=a.index)
res = {"spy": stats(spyc), "dip": stats(dip)}
corr = {}
for name, c in cfgs.items():
    r, curve = run(**c, st=0, lt=0); rc = pd.Series(curve, index=idx)
    res[name] = stats(rc); corr[name] = round(float(dip.pct_change().corr(rc.pct_change())), 2)
    for w in (0.7, 0.5):
        res[f"{int(w*100)}% dip + {int((1-w)*100)}% {name.split(' ')[0]}"] = stats(blend(dip, rc, w))
res["corr_with_dip"] = corr
for k, v in res.items(): print(k, v)
json.dump(res, open("data/future_leaders_combo.json", "w"), indent=1)
