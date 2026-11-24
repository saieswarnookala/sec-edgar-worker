"""Luck check (Nov 24 2026; research only, not financial advice). After ~70 tested ideas, is the US dip bot's backtest still better than the luckiest
of many tries would look by chance? Deflated Sharpe ratio (Bailey & Lopez de Prado 2014): the probability the true Sharpe is above zero AFTER
allowing for the number of trials (N), how much the trials' Sharpes vary, and the returns' skew / fat tails. Keep a strategy if DSR > 0.95.
Trial-Sharpe spread: measured from a grid of dip-bot variants run here (add-ons x hold lengths x dip sizes x fills).
N: 70 (every catalogue entry) and 15 (families of near-duplicate tweaks). Also t-stat of the Sharpe (Harvey-Liu-Zhu want t > 3).
India: walk-forward check on the 120-variant momentum grid in data/india_momentum.json (does picking the best on 2008-2018 still win in 2019-2026?)."""
import os, sys, json, math
from statistics import NormalDist
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stack_and_rebound as S
OUT = "data/luck_check.json" if not S.DRY else "/tmp/luck_check_dry.json"
Z = NormalDist(); g = 0.5772156649
LIVE = dict(fill="close", park="cl", cs=0.0008, ce=0.0003); REAL = dict(fill="open", park="cl", cs=0.0015, ce=0.0005)
def daily(curve):
    c = curve[S.t0:]; r = c[1:] / c[:-1] - 1; return r[np.isfinite(r)]
def stats(r):
    m, s = r.mean(), r.std(ddof=1); sr = m / s; z = (r - m) / s
    return dict(sr=sr, skew=float((z ** 3).mean()), kurt=float((z ** 4).mean()), T=len(r))
def dsr(st, var_sr, N):
    sr0 = math.sqrt(var_sr) * ((1 - g) * Z.inv_cdf(1 - 1 / N) + g * Z.inv_cdf(1 - 1 / (N * math.e)))
    den = math.sqrt(max(1e-12, 1 - st["skew"] * st["sr"] + (st["kurt"] - 1) / 4 * st["sr"] ** 2))
    return Z.cdf((st["sr"] - sr0) * math.sqrt(st["T"] - 1) / den), sr0
RES = {"note": __doc__, "grid": {}, "candidates": {}, "india_walk_forward": {}}
grid = []
for fname, fkw in (("live-like", LIVE), ("realistic", REAL)):
    for lbl, kw in (S.COMBOS[:2] if os.environ.get("QUICK") else S.COMBOS):
        for mh in ((5,) if os.environ.get("QUICK") else (3, 5, 7)):
            c, _ = S.sim(mhs=mh, **fkw, **kw); st = stats(daily(c)); grid.append(st["sr"])
            RES["grid"][f"{fname} | {lbl} | hold {mh}"] = round(st["sr"] * math.sqrt(252), 3)
    for dip in ((0.12,) if os.environ.get("QUICK") else (0.08, 0.12, 0.15)):
        c, _ = S.sim(sig=S.make_sig(dip, 200), **fkw); st = stats(daily(c)); grid.append(st["sr"]); RES["grid"][f"{fname} | v1 dip {int(dip * 100)}%"] = round(st["sr"] * math.sqrt(252), 3)
    print(fname, "grid done", len(grid), flush=True)
var_sr = float(np.var(grid, ddof=1)); RES["trial_sharpe_spread_annual"] = round(math.sqrt(var_sr) * math.sqrt(252), 3)
for name, kw in (("previous live (v1) | realistic", REAL), ("v3.0 (live) | realistic", dict(REAL, etf=True, bond=True)),
                 ("v3.0 (live) | live-like", dict(LIVE, etf=True, bond=True)), ("v3.0 | realistic | 2013-2026 only", dict(REAL, etf=True, bond=True))):
    c, _ = S.sim(**kw)
    if "2013" in name: i13 = int(np.argmax(S.dn >= np.datetime64("2013-01-01"))); cc = c[i13 - 1:]; r = cc[1:] / cc[:-1] - 1; r = r[np.isfinite(r)]
    else: r = daily(c)
    st = stats(r); sr_a = st["sr"] * math.sqrt(252); tstat = st["sr"] * math.sqrt(st["T"])
    o = {"sharpe_annual": round(sr_a, 3), "years": round(st["T"] / 252, 1), "t_stat": round(tstat, 2), "skew": round(st["skew"], 2), "kurtosis": round(st["kurt"], 1)}
    for N in (15, 70):
        p, sr0 = dsr(st, var_sr, N); o[f"DSR_N{N}"] = round(p, 3); o[f"luck_bar_sharpe_N{N}"] = round(sr0 * math.sqrt(252), 3)
    o["verdict"] = ("passes both (DSR > 0.95 at N=70, t > 3)" if o["DSR_N70"] > 0.95 and tstat > 3 else "DSR passes at N=70, but t below 3" if o["DSR_N70"] > 0.95
                    else "DSR passes at N=15 only" if o["DSR_N15"] > 0.95 else "does not clear the luck bar")
    RES["candidates"][name] = o; print(name, o, flush=True)
# India: 120 momentum variants, picked on 2008-2018 vs 2019-2026
try:
    mom = json.load(open("data/india_momentum.json"))["momentum"]
    tr = np.array([m["train_2008_2018"]["cagr"] for m in mom]); te = np.array([m["test_2019_2026"]["cagr"] for m in mom])
    rk = lambda a: np.argsort(np.argsort(a)) / (len(a) - 1)
    top = np.argsort(-tr)[:10]
    RES["india_walk_forward"] = {"variants": len(mom), "rank_correlation_train_vs_test": round(float(np.corrcoef(rk(tr), rk(te))[0, 1]), 2),
        "best_in_train_test_cagr": float(te[np.argmax(tr)]), "best_in_train_test_percentile": round(float(rk(te)[np.argmax(tr)]) * 100, 0),
        "top10_in_train_median_test_cagr": float(np.median(te[top])), "all_variants_median_test_cagr": float(np.median(te)),
        "share_of_top10_below_test_median": round(float(np.mean(te[top] < np.median(te))) * 100, 0)}
    print("India walk-forward", RES["india_walk_forward"], flush=True)
except Exception as e: RES["india_walk_forward"] = {"error": str(e)}
json.dump(RES, open(OUT, "w"), indent=1, default=float); print("wrote", OUT)
