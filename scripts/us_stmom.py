"""US short-term momentum sleeve (Nov 24 2026; research only, not financial advice). Point-in-time S&P 500, 1999-2026.
Idea (Medhat & Schmeling 2022): last month's winners keep winning among HEAVILY traded stocks (and reverse among lightly traded ones).
Rules: at each month-end close, rank S&P 500 members by last month's return among the most-traded third (60-day dollar volume, vs the other members),
hold the top 10 or 20 equally for a month. Monthly turnover is high, so this is a Roth-only idea (no tax drag). Costs 0.15%/side (realistic: next open)
or 0.08% (live-like); both trade at the month-end close (the overnight gap is ignored). References: same rules on ALL members (should be weaker), classic 12-1 month momentum top 20, SPY.
Then: blend with the dip bot v3.0 (realistic) 50/50 and 70/30 dip/momentum, rebalanced monthly, and the monthly correlation. DRY=1: fake ETF data."""
import os, sys, json
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stack_and_rebound as S
OUT = "data/us_stmom.json" if not S.DRY else "/tmp/us_stmom_dry.json"
dn = S.dn; D = len(dn); C = S.S_C; O = S.S_O; MEM = S.M[S.tick].values
RAW = S.RAW[S.tick].values; DV = pd.DataFrame(RAW * S.VOLM[S.tick].values).rolling(60, min_periods=40).mean().values
me = [t for t in range(S.t0, D - 1) if pd.Timestamp(dn[t]).month != pd.Timestamp(dn[t + 1]).month]
def lagret(t, a, b=0):      # return from t-a to t-b
    p0, p1 = C[t - a], C[t - b]; return np.where((p0 > 0) & (p1 > 0), p1 / p0 - 1, np.nan)
def run(kind="st", N=10, liquid=True, fill="close"):
    cost = 0.0008 if fill == "close" else 0.0015; eq = 1.0; curve = np.ones(D); w = {}; turn = 0.0
    for t in range(S.t0, D):
        if t > S.t0 and w:
            g = {j: ((C[t, j] / C[t - 1, j]) if (C[t - 1, j] > 0 and C[t, j] > 0) else 1.0) for j in w}   # missing price (delisted): held flat to the next month-end
            r = sum(wi * (g[j] - 1) for j, wi in w.items()); eq *= 1 + r; w = {j: wi * g[j] / (1 + r) for j, wi in w.items()}
        if t in set_me:
            ok = MEM[t] & (RAW[t] >= 5) & np.isfinite(C[t])
            if liquid:
                dv = np.where(ok, DV[t], np.nan); th = np.nanpercentile(dv, 66.7) if np.isfinite(dv).any() else np.inf; ok &= dv >= th
            sc = lagret(t, 21) if kind == "st" else lagret(t, 252, 21)
            cand = np.flatnonzero(ok & np.isfinite(sc)); pick = cand[np.argsort(-sc[cand])][:N]
            tgt = {int(j): 1.0 / N for j in pick}; tv = sum(abs(tgt.get(j, 0) - w.get(j, 0)) for j in set(tgt) | set(w))
            eq *= 1 - cost * tv; turn += tv; w = tgt
        curve[t] = eq
    return curve, turn / ((D - S.t0) / 252)
set_me = set(me)
def summ(c):
    o = {}
    for nm, a, b in (("1999-2026", "1999", "2100"), ("1999-2012", "1999", "2013"), ("2013-2026", "2013", "2100")):
        ii = np.flatnonzero((dn >= np.datetime64(a + "-01-01")) & (dn < np.datetime64(b + "-01-01")) & (np.arange(D) >= S.t0))
        cc = c[ii] / c[ii[0] - 1]; y = len(ii) / 252
        o[nm] = {"per_year_pct": round((cc[-1] ** (1 / y) - 1) * 100, 1), "worst_drop_pct": round(float((cc / np.maximum.accumulate(cc) - 1).min()) * 100, 1)}
    return o
def pr(n, o): print(f"{n:60s} " + " | ".join(f"{k} {v['per_year_pct']}/{v['worst_drop_pct']}" for k, v in o.items() if isinstance(v, dict)) + (f" | turnover {o['turnover_per_year']}x/yr" if "turnover_per_year" in o else ""), flush=True)
RES = {"note": __doc__, "sleeves": {}, "blends": {}}
spy = np.r_[np.ones(S.t0), S.SP[S.t0:] / S.SP[S.t0 - 1]] if len(S.SP) == D else None
if spy is not None: RES["sleeves"]["SPY"] = summ(spy); pr("SPY", RES["sleeves"]["SPY"])
curves = {}
for lbl, kw in (("short-term: last month's top 10, most-traded third", dict(kind="st", N=10, liquid=True)), ("short-term: top 20, most-traded third", dict(kind="st", N=20, liquid=True)),
                ("short-term: top 20, ALL members (should be weaker)", dict(kind="st", N=20, liquid=False)), ("classic 12-1 month momentum: top 20, all members", dict(kind="lt", N=20, liquid=False))):
    for fill in ("close", "open"):
        c, tv = run(fill=fill, **kw); o = summ(c); o["turnover_per_year"] = round(tv, 1); nm = f"{lbl} | {'live-like 0.08%' if fill == 'close' else 'realistic 0.15%'}"
        RES["sleeves"][nm] = o; curves[nm] = c; pr(nm, o)
dip, _ = S.sim(fill="open", park="cl", cs=0.0015, ce=0.0005, etf=True, bond=True, cash_interest=True); RES["sleeves"]["dip bot v3.0 realistic"] = summ(dip); pr("dip bot v3.0 realistic", RES["sleeves"]["dip bot v3.0 realistic"])
best = max([k for k in curves if "realistic" in k and "short-term" in k], key=lambda k: RES["sleeves"][k]["1999-2026"]["per_year_pct"]); RES["best_sleeve"] = best
mo = lambda c: pd.Series(c[S.t0:], index=pd.DatetimeIndex(dn[S.t0:])).resample("ME").last().pct_change().dropna()
RES["blends"]["monthly_correlation_dip_vs_best"] = round(float(mo(dip).corr(mo(curves[best]))), 2)
def blend(c1, c2, w1):
    r1 = np.r_[0, c1[1:] / c1[:-1] - 1]; r2 = np.r_[0, c2[1:] / c2[:-1] - 1]; a, b = w1, 1 - w1; out = np.ones(D)
    for t in range(S.t0, D):
        if t in set_me: tot = a + b; a, b = w1 * tot, (1 - w1) * tot
        a *= 1 + r1[t]; b *= 1 + r2[t]; out[t] = a + b
    return out
for w1 in (0.7, 0.5):
    nm = f"{int(w1*100)}% dip bot + {100-int(w1*100)}% {best}"; RES["blends"][nm] = summ(blend(dip, curves[best], w1)); pr(nm, RES["blends"][nm])
json.dump(RES, open(OUT, "w"), indent=1, default=float); print("wrote", OUT)
