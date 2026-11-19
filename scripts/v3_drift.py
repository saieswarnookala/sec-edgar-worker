"""v3.0 + earnings-drift slots, and interest on cash (Nov 19 2026). Research only, not financial advice.
Engine = scripts/stack_and_rebound.py (point-in-time S&P 500, ETF dips, IEF bond parking, real Clear Leader parking).
Drift = S&P 500 stock that beat SPY by 5%+ on its earnings reaction day (SEC 8-K Item 2.02; filed before 9:30 -> that day, else the next),
bought at that day's close (live-like) or next open (realistic), held 60 trading days. Earnings dates exist from Aug 2004, so the
comparison period is 2004-2026. Versions: drift in 2 or 3 of the 10 slots (reserved), or 2-3 extra slots on top of v3.0's 10.
Cash interest: on cash days the idle money earns the 3-month T-bill yield (^IRX), like a money-market sweep.
Cost settings: LIVE-LIKE (close, 0.08%/side), IDEAL (close, 0.05%), REALISTIC (next open, 0.15%)."""
import os, sys, json
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stack_and_rebound as S
OUT = "data/v3_drift.json" if not S.DRY else "/tmp/v3_drift_dry.json"
LIVE = dict(fill="close", park="cl", cs=0.0008, ce=0.0003); IDEAL = dict(fill="close", park="cl"); REAL = dict(fill="open", park="cl", cs=0.0015, ce=0.0005)
V3 = dict(etf=True, bond=True); dn = S.dn
t04 = int(np.searchsorted(dn, np.datetime64("2004-09-01")))
def per(cv, a, b):
    ix = np.flatnonzero((dn >= np.datetime64(a)) & (dn < np.datetime64(b)) & (np.arange(S.D) >= t04))
    c = cv[ix] / cv[ix[0] - 1]; return round((c[-1] ** (252 / len(ix)) - 1) * 100, 1), round(float((c / np.maximum.accumulate(c) - 1).min()) * 100, 1)
def summ(cv, tr):
    a = per(cv, "2004-09-01", "2100-01-01"); e = per(cv, "2004-09-01", "2015-01-01"); l = per(cv, "2015-01-01", "2100-01-01")
    tr = [x for x in tr if x[0] >= t04]; nd = [x for x in tr if x[1] == "D"]
    return {"2004-2026": a[0], "worst": a[1], "2004-2014": e[0], "2015-2026": l[0],
            "2022": per(cv, "2022-01-01", "2023-01-01")[0], "trades_per_month": round(len(tr) / ((S.D - t04) / 21), 1),
            "drift_trades_per_month": round(len(nd) / ((S.D - t04) / 21), 1), "drift_avg_trade_pct": round(float(np.mean([x[2] for x in nd])) * 100, 2) if nd else None}
VARS = [("v3.0 now", {}), ("v3.0 + cash interest", dict(cash_interest=True)),
        ("v3.0, 2 of 10 slots drift", dict(drift=2)), ("v3.0, 3 of 10 slots drift", dict(drift=3)),
        ("v3.0 + 2 extra drift slots", dict(drift=2, drift_mode="extra")), ("v3.0 + 3 extra drift slots", dict(drift=3, drift_mode="extra")),
        ("v3.0 + 2 extra drift (4% beat)", dict(drift=2, drift_mode="extra", dth=0.04)), ("v3.0 + 2 extra drift (6% beat)", dict(drift=2, drift_mode="extra", dth=0.06)),
        ("v3.0 + 2 extra drift, 40-day hold", dict(drift=2, drift_mode="extra", dhold=40)),
        ("v3.0 + 2 extra drift + cash interest", dict(drift=2, drift_mode="extra", cash_interest=True))]
RES = {}
for cn, cost in (("live-like", LIVE), ("ideal", IDEAL), ("realistic", REAL)):
    for vn, kw in VARS:
        k = f"{cn} | {vn}"; RES[k] = summ(*S.sim(**V3, **cost, **kw)); g = RES[k]
        print(f"{k:52s} {g['2004-2026']}% worst {g['worst']} | 04-14 {g['2004-2014']} 15-26 {g['2015-2026']} | 2022 {g['2022']} | {g['trades_per_month']}/mo (drift {g['drift_trades_per_month']}, avg {g['drift_avg_trade_pct']}%)", flush=True)
assert summ(*S.sim(**V3, **LIVE, drift=0, drift_mode="extra")) == RES["live-like | v3.0 now"], "no drift must equal v3.0"
print("check ok: 0 drift slots = v3.0", flush=True)
json.dump({"note": __doc__, "built": str(pd.Timestamp.today().date()), "dry": S.DRY or None, "results": RES}, open(OUT, "w"), indent=1, default=float)
print("wrote", OUT, flush=True)
