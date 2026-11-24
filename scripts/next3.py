"""Three follow-ups from the Nov 23 research report (Nov 24 2026; research only, not financial advice). v3.0 rules, point-in-time S&P 500 1999-2026.
A) Pre-earnings buys in idle slots (Frazzini-Lamont / Gao-Hu-Zhang: returns cluster before and around earnings). After dips and ETF dips, leftover
   slots buy S&P 500 stocks above their 200-day average with an earnings release coming (8-K Item 2.02 dates from SEC, 2004+; the date is treated as
   known in advance, which is mostly but not always true), strongest 6-month return first. Variants: buy 5 days before and sell the day before the
   release / hold through the reaction day; buy 1 day before and hold through; max 2 / 5 such slots.
B) FOMC even weeks (Cieslak-Morse-Vissing-Jorgensen 2019): the stock market's return since 1994 came in weeks 0, 2, 4, 6 of the Fed cycle (week 0 starts
   the day before a meeting). Stock parking (Clear Leader) only in even weeks; odd weeks earn T-bills (or IEF in v3.0 when SPY is weak, as today).
C) Walk-forward (fair final exam): each year from 2004 pick the dip size / hold / trend-average with the best return over ALL earlier years
   (and over the last 5 years), use it for that year only, chain the years. Compare with today's fixed settings (10% / 5 days / 200-day).
DRY=1: fake ETF data (code test)."""
import os, sys, json
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stack_and_rebound as S
OUT = "data/next3.json" if not S.DRY else "/tmp/next3_dry.json"
LIVE = dict(fill="close", park="cl", cs=0.0008, ce=0.0003); REAL = dict(fill="open", park="cl", cs=0.0015, ce=0.0005); V3 = dict(etf=True, bond=True, cash_interest=True)
dn = S.dn; D = len(dn); J = len(S.tick)
def row(name, c, tr):
    o = S.summ(c, tr); print(f"{name:70s} " + " | ".join(f"{k[:9]} {v.get('per_year_pct')}/{v['worst_drop_pct']}" for k, v in o.items() if isinstance(v, dict) and k in ("1999-2026", "1999-2012", "2013-2026", "2018-2026 (short data)")), flush=True); return o
RES = {"note": __doc__, "A_pre_earnings": {}, "B_fomc_even_weeks": {}, "C_walk_forward": {}}
# ---- A: earnings calendar (reaction day k = first session that can react to the release)
SEC = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "sec_events_sic.json")))["tickers"]
ds = np.array([str(d)[:10] for d in dn]); REACT = np.zeros((D, J), bool)
for j, tk in enumerate(S.tick):
    for d, mi in (SEC.get(tk) or {}).get("events", []):
        k = int(np.searchsorted(ds, d))
        if k < D and ds[k] == d and mi >= 570: k += 1
        if 0 < k < D: REACT[k, j] = True
print("earnings reaction days:", int(REACT.sum()), flush=True)
C = S.S_C; up200 = C > pd.DataFrame(C).rolling(200, min_periods=150).mean().values; MOM6 = C / np.vstack([np.full((126, J), np.nan), C[:-126]]) - 1
RANK = np.nan_to_num(-MOM6, nan=9.0); MEM = S.M[S.tick].values
def pre_sig(lead):          # True on day t if a reaction day is exactly `lead` sessions ahead
    P = np.zeros((D, J), bool); P[:-lead] = REACT[lead:]; return P & up200 & MEM
for fname, fkw in ((("live-like", LIVE),) if os.environ.get("QUICK") else (("live-like", LIVE), ("realistic", REAL))):
    off = 1 if fkw["fill"] == "open" else 0   # next-open fills buy a day later; hold counts from the fill
    base_c, base_t = S.sim(**fkw, **V3); RES["A_pre_earnings"][f"{fname} | v3.0 today (T-bill interest on cash)"] = row(f"{fname} | v3.0 today", base_c, base_t)
    for lbl, lead, hold, mx in (("buy 5 days before, sell the day before the release", 5, 4, 5), ("buy 5 days before, hold through the reaction day", 5, 5, 5),
                                ("buy 1 day before, hold through the reaction day", 1, 1, 5), ("buy 5 days before, hold through, max 2 slots", 5, 5, 2)):
        c, tr = S.sim(drift=mx, drift_mode="fill", dlast=True, pre=pre_sig(lead + off), pre_rank=RANK, dhold=hold + off, **fkw, **V3)
        RES["A_pre_earnings"][f"{fname} | {lbl}"] = row(f"{fname} | pre-earnings: {lbl}", c, tr)
# ---- B: FOMC weeks
F = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "calendar_effects.json")))["fomc_dates"]
A = sorted(set(int(np.searchsorted(ds, d)) for d in F if d in set(ds)))
EVEN = np.ones(D, bool); last = None; ai = 0
for t in range(D):
    while ai < len(A) and A[ai] - 1 <= t: last = A[ai] - 1; ai += 1      # cycle starts the day before the announcement
    if last is not None: EVEN[t] = ((t - last) // 5) % 2 == 0
print("FOMC meetings:", len(A), "even-week share", round(float(EVEN.mean()), 2), flush=True)
for fname, fkw in (("live-like", LIVE), ("realistic", REAL)):
    c, tr = S.sim(**fkw, **V3); RES["B_fomc_even_weeks"][f"{fname} | v3.0 today"] = row(f"{fname} | v3.0 today", c, tr)
    c, tr = S.sim(parkx=EVEN, **fkw, **V3); RES["B_fomc_even_weeks"][f"{fname} | stock parking only in FOMC even weeks"] = row(f"{fname} | parking only in FOMC even weeks", c, tr)
    c, tr = S.sim(parkx=~EVEN, **fkw, **V3); RES["B_fomc_even_weeks"][f"{fname} | placebo: parking only in odd weeks"] = row(f"{fname} | placebo: parking only in odd weeks", c, tr)
# ---- C: walk-forward on the daily engine (realistic fills)
GRID = [(dip, mh, ma) for dip in (0.08, 0.10, 0.12, 0.15) for mh in (3, 5, 7) for ma in (100, 200)] if not os.environ.get("QUICK") else [(0.10, 5, 200), (0.12, 3, 100)]
yr_ret = {}
for dip, mh, ma in GRID:
    c, _ = S.sim(sig=S.make_sig(dip, ma), mhs=mh, **REAL, **V3)
    s = pd.Series(c, index=pd.DatetimeIndex(dn)).iloc[S.t0 - 1:]; ye = s.resample("YE").last(); prev = np.r_[s.iloc[0], ye.values[:-1]]
    yr_ret[(dip, mh, ma)] = {k.year: v / p - 1 for k, v, p in zip(ye.index, ye.values, prev)}
    print("grid", dip, mh, ma, round((np.prod([1 + x for x in yr_ret[(dip, mh, ma)].values()]) ** (1 / len(yr_ret[(dip, mh, ma)])) - 1) * 100, 1), flush=True)
years = sorted(next(iter(yr_ret.values())).keys()); fixed = (0.10, 5, 200)
def chain(pick):
    out, picks = [], {}
    for y in years:
        if y < 2004: continue
        k = pick(y); picks[y] = f"{int(k[0]*100)}% / {k[1]}d / {k[2]}-day"; out.append(yr_ret[k][y])
    return out, picks
score = lambda k, ys: np.prod([1 + yr_ret[k][x] for x in ys])
wf_all, p_all = chain(lambda y: max(GRID, key=lambda k: score(k, [x for x in years if x < y])))
wf_5y, p_5y = chain(lambda y: max(GRID, key=lambda k: score(k, [x for x in years if y - 5 <= x < y])))
fx, _ = chain(lambda y: fixed)
best_hind = max(GRID, key=lambda k: score(k, [x for x in years if x >= 2004])); bh, _ = chain(lambda y: best_hind)
cg = lambda r: round((np.prod([1 + x for x in r]) ** (1 / len(r)) - 1) * 100, 1)
RES["C_walk_forward"] = {"period": "2004-2026, realistic fills, v3.0", "fixed_today_10pct_5d_200": cg(fx), "walk_forward_all_past_years": cg(wf_all), "walk_forward_last_5_years": cg(wf_5y),
                         "best_in_hindsight": {"setting": f"{int(best_hind[0]*100)}% / {best_hind[1]}d / {best_hind[2]}-day", "per_year": cg(bh)},
                         "picks_all_past": p_all, "picks_last_5y": p_5y, "grid_per_year_2004_2026": {f"{int(k[0]*100)}% / {k[1]}d / {k[2]}-day": cg([yr_ret[k][y] for y in years if y >= 2004]) for k in GRID}}
print("walk-forward", {k: v for k, v in RES["C_walk_forward"].items() if not isinstance(v, dict)}, RES["C_walk_forward"]["best_in_hindsight"], flush=True)
json.dump(RES, open(OUT, "w"), indent=1, default=float); print("wrote", OUT)
