"""Two quick tests from the Nov 23 research report (research only, not financial advice). Point-in-time S&P 500, 1999-2026, v3.0 rules.
TEST 1 - which dips work: tag every v3.0 dip trade by (a) abnormal volume over the dip = 5-day volume / prior 50-day volume (the live bot already skips > 2x)
  and (b) normal liquidity = 60-day average dollar volume, ranked against the other S&P 500 stocks that day (shares outstanding are not in our data, so this
  stands in for 'turnover'; it is mostly company size). Keep a rule only if the low-vs-high tercile gap shows up in BOTH 1999-2012 and 2013-2026.
  Then full simulations that change the queue when there are more dips than slots: lowest abnormal volume first, or a 50/50 blend with dip size.
TEST 10 - idle money: the parking ETF (Clear Leader when SPY > 100-day) is scaled to a volatility target, rest in T-bills; targets 10/12/15/20%.
  Reference: today's rules with idle cash earning T-bills (fair comparison, since the scaled-down part earns T-bills).
DRY=1: fake ETF data (code test)."""
import os, sys, json
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stack_and_rebound as S
OUT = "data/park_turnover.json" if not S.DRY else "/tmp/park_turnover_dry.json"
LIVE = dict(fill="close", park="cl", cs=0.0008, ce=0.0003); REAL = dict(fill="open", park="cl", cs=0.0015, ce=0.0005); V3 = dict(etf=True, bond=True)
dn = S.dn
VR = S.vr[S.tick].values
DV = (S.RAW[S.tick] * S.VOLM[S.tick]).rolling(60, min_periods=40).mean().where(S.M[S.tick]).rank(axis=1, pct=True).values
def row(name, curve, trades):
    o = S.summ(curve, trades); print(f"{name:66s} " + " | ".join(f"{k} {v.get('per_year_pct', v.get('return_pct'))}%/{v['worst_drop_pct']}" for k, v in o.items() if isinstance(v, dict)), flush=True); return o
RES = {"note": __doc__, "test1_tags": {}, "test1_sims": {}, "test10_parking": {}}
for fname, fkw in (("live-like", LIVE), ("realistic", REAL)):
    log = []; curve, trades = S.sim(log=log, **fkw, **V3)
    RES["test1_sims"][f"{fname} | v3.0 today"] = row(f"{fname} | v3.0 today", curve, trades)
    off = 1 if fkw["fill"] == "open" else 0
    tr = [(x[1], x[2] - off, x[5]) for x in log if x[0] == "S"]                # (stock column, signal day, net return)
    j = np.array([a for a, _, _ in tr]); t = np.array([b for _, b, _ in tr]); r = np.array([c for _, _, c in tr])
    early = dn[t] < np.datetime64("2013-01-01")
    for tag, arr in (("abnormal volume over the dip (5d/50d)", VR[t, j]), ("normal dollar volume rank vs S&P 500", DV[t, j])):
        ok = np.isfinite(arr); q = np.nanquantile(arr[ok], [1 / 3, 2 / 3]); out = {"cutoffs": [round(float(x), 3) for x in q]}
        for lbl, m in (("low third", arr <= q[0]), ("middle third", (arr > q[0]) & (arr <= q[1])), ("high third", arr > q[1])):
            out[lbl] = {}
            for per, pm in (("1999-2012", early), ("2013-2026", ~early), ("all", np.ones(len(r), bool))):
                rr = r[m & ok & pm]
                out[lbl][per] = {"n": int(len(rr)), "avg_pct": round(float(rr.mean()) * 100, 2) if len(rr) else None, "win_pct": round(float((rr > 0).mean()) * 100, 1) if len(rr) else None,
                                 "t": round(float(rr.mean() / (rr.std() / np.sqrt(len(rr)))), 2) if len(rr) > 2 else None}
        RES["test1_tags"][f"{fname} | {tag}"] = out
        print(f"{fname} | {tag}: cutoffs {out['cutoffs']} | " + " | ".join(f"{lbl} {out[lbl]['1999-2012']['avg_pct']}/{out[lbl]['2013-2026']['avg_pct']}% (n {out[lbl]['all']['n']})" for lbl in ("low third", "middle third", "high third")), flush=True)
    # queue-order variants (only matter when there are more dips than slots)
    RK0 = S.S_RK.copy()
    vr_rank = pd.DataFrame(VR).rank(axis=1, pct=True).values; dip_rank = pd.DataFrame(RK0).rank(axis=1, pct=True).values
    for lbl, rk in (("queue: lowest abnormal volume first", np.nan_to_num(VR, nan=9)), ("queue: 50/50 dip size + low abnormal volume", np.nan_to_num(dip_rank + vr_rank, nan=9))):
        S.S_RK = rk; c2, t2 = S.sim(**fkw, **V3); S.S_RK = RK0
        RES["test1_sims"][f"{fname} | {lbl}"] = row(f"{fname} | {lbl}", c2, t2)
    # TEST 10
    c0, t0_ = S.sim(cash_interest=True, **fkw, **V3); RES["test10_parking"][f"{fname} | v3.0, idle cash earns T-bills (reference)"] = row(f"{fname} | v3.0 + T-bill interest (reference)", c0, t0_)
    for vt in (0.10, 0.12, 0.15, 0.20):
        c1, t1 = S.sim(cash_interest=True, park_vt=vt, **fkw, **V3)
        RES["test10_parking"][f"{fname} | parking vol target {int(vt * 100)}%"] = row(f"{fname} | parking vol target {int(vt * 100)}%", c1, t1)
json.dump(RES, open(OUT, "w"), indent=1, default=float); print("wrote", OUT)
