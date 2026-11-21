"""Three tests from the Nov 20 2026 deep research (Dip bot v3.0, point-in-time S&P 500, 1999-2026). Research only, not financial advice.
A) SECTOR-RELATIVE DIPS: each stock is mapped to its SPDR sector ETF (from its SEC SIC code; SPY when the sector ETF has no data yet,
   e.g. XLRE before 2015, XLC before 2018). Versions: dip measured vs the sector instead of SPY; vs SPY AND vs the sector (stock fell more
   than its own sector too); skip when the whole sector ETF fell 5%+ in the 5 days.
B) STRESS TEST: how much of v3.0's return is just the market (beta to SPY) vs its own edge (alpha), by period; doubled costs;
   and 3-year drawdowns from 5,000 resampled paths (1-month blocks) -> a kill-switch level.
C) BLEND: SPY buy & hold + Dip bot v3.0 + a slow trend sleeve (Faber: SPY, EFA, IEF, VNQ, DBC, each 20% when above its 10-month average,
   else T-bills; monthly). Before tax and a rough after tax (dip + trend sleeves taxed 24% on each year's gain; SPY taxed 15% once at the end;
   a 'dip bot in a Roth' line taxes the dip sleeve at 0). Rebalanced monthly (approximation: fixed weights on monthly returns).
DRY=1: fake ETF data (code test)."""
import os, sys, json
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stack_and_rebound as S
OUT = "data/three_tests.json" if not S.DRY else "/tmp/three_tests_dry.json"
LIVE = dict(fill="close", park="cl", cs=0.0008, ce=0.0003); REAL = dict(fill="open", park="cl", cs=0.0015, ce=0.0005); V3 = dict(etf=True, bond=True)
dn, t0, D = S.dn, S.t0, S.D
def cagr(cv, a="1999-01-01", b="2100-01-01"):
    ix = np.flatnonzero((dn >= np.datetime64(a)) & (dn < np.datetime64(b)) & (np.arange(D) >= t0))
    c = cv[ix] / cv[max(ix[0] - 1, t0)]; return round((c[-1] ** (252 / len(ix)) - 1) * 100, 1)
def worst(cv):
    c = cv[t0:]; return round(float((c / np.maximum.accumulate(c) - 1).min()) * 100, 1)
def summ(cv, tr=None):
    o = {"1999-2026": cagr(cv), "1999-2012": cagr(cv, "1999-01-01", "2013-01-01"), "2013-2026": cagr(cv, "2013-01-01"), "2022": cagr(cv, "2022-01-01", "2023-01-01"), "worst": worst(cv)}
    if tr is not None: o["trades_per_month"] = round(len(tr) / ((D - t0) / 21), 1); o["avg_trade_pct"] = round(float(np.mean([x[2] for x in tr])) * 100, 2) if tr else None
    return o
RES = {"A_sector": {}, "B_stress": {}, "C_blend": {}}
# ---------------------------------------------------------------- A) sector-relative
SEC = json.load(open("data/sec_events_sic.json"))["tickers"]
def sector(sic):
    if not sic: return None
    s2, s3, s4 = int(sic[:2]), int(sic[:3]), int(sic[:4])
    if s3 == 283 or s3 == 384 or s2 == 80 or s4 == 8731: return "XLV"
    if s2 in (13, 29, 46): return "XLE"
    if s2 == 49: return "XLU"
    if s4 == 6798 or s2 == 65: return "XLRE"
    if 60 <= s2 <= 67: return "XLF"
    if s3 == 357 or s2 in (36, 38) or s2 == 73: return "XLK"
    if s2 in (48, 27, 78): return "XLC"
    if s2 in (20, 21) or s3 == 541: return "XLP"
    if s2 in (22, 23, 25, 31, 39, 70, 79) or 52 <= s2 <= 59: return "XLY"
    if s2 in (10, 12, 14, 24, 26, 28, 30, 32, 33): return "XLB"
    return "XLI"
SECT = [sector((SEC.get(t) or {}).get("sic")) for t in S.tick]
print("stocks with a sector:", sum(x is not None for x in SECT), "of", len(SECT), flush=True)
spy5 = np.r_[np.full(5, np.nan), S.SP[5:] / S.SP[:-5] - 1]
E5 = S.E_C / np.vstack([np.full((5, S.E_C.shape[1]), np.nan), S.E_C[:-5]]) - 1
SEC5 = np.repeat(spy5[:, None], len(S.tick), axis=1)             # sector ETF 5-day move per stock-day (SPY if none)
for j, e in enumerate(SECT):
    if e is not None and e in S.EI:
        x = E5[:, S.EI[e]]; SEC5[:, j] = np.where(np.isfinite(x), x, spy5)
own5 = S.S_C / np.vstack([np.full((5, S.S_C.shape[1]), np.nan), S.S_C[:-5]]) - 1
vs_sec = np.nan_to_num(own5 - SEC5, nan=1); sec_drop = np.nan_to_num(SEC5, nan=0)
BASE = S.SIG                                                       # = vs SPY <= -10% (+ trend, volume, price rules)
rest = S.make_sig(dip=-9.0)                                        # every rule except the dip size (dip <= +900% is always true)
VAR = {"v3.0 as is (vs SPY)": BASE, "vs SECTOR instead of SPY (10%)": rest & (vs_sec <= -0.10),
       "vs SPY 10% AND vs sector 7%": BASE & (vs_sec <= -0.07), "vs SPY 10% AND vs sector 10%": BASE & (vs_sec <= -0.10),
       "skip if the sector ETF fell 5%+ in the 5 days": BASE & ~(sec_drop <= -0.05)}
for cname, cost in (("live-like", LIVE), ("realistic", REAL)):
    for vn, sg in VAR.items():
        k = f"{cname} | {vn}"; RES["A_sector"][k] = summ(*S.sim(**V3, **cost, sig=sg))
        g = RES["A_sector"][k]; print(f"SECTOR {k:62s} {g['1999-2026']}% | 99-12 {g['1999-2012']} 13-26 {g['2013-2026']} | 2022 {g['2022']} | worst {g['worst']} | {g['trades_per_month']}/mo avg {g['avg_trade_pct']}%", flush=True)
# ---------------------------------------------------------------- B) stress test
cv_live, tr_live = S.sim(**V3, **LIVE); cv_real, _ = S.sim(**V3, **REAL)
cv_2x, _ = S.sim(**V3, fill="close", park="cl", cs=0.0016, ce=0.0006)
spyc = np.ones(D); spyc[t0:] = S.SP[t0:] / S.SP[t0 - 1]
def ab(cv, a, b):
    ix = np.flatnonzero((dn >= np.datetime64(a)) & (dn < np.datetime64(b)) & (np.arange(D) > t0))
    r = cv[ix] / cv[ix - 1] - 1; m = S.SP[ix] / S.SP[ix - 1] - 1
    beta = float(np.cov(r, m)[0, 1] / np.var(m, ddof=1)); alpha = float((r - beta * m).mean() * 252)
    resid = r - beta * m; t = float(resid.mean() / (resid.std(ddof=1) / np.sqrt(len(r))))
    return {"beta": round(beta, 2), "alpha_pct_per_year": round(alpha * 100, 1), "alpha_t_stat": round(t, 1), "bot_pct_per_year": cagr(cv, a, b), "spy_pct_per_year": cagr(spyc, a, b)}
for nm, cv in (("live-like", cv_live), ("realistic", cv_real), ("live-like, 2x costs", cv_2x)):
    for a, b in (("1999-01-01", "2100-01-01"), ("1999-01-01", "2008-01-01"), ("2008-01-01", "2013-01-01"), ("2013-01-01", "2020-01-01"), ("2020-01-01", "2100-01-01")):
        k = f"{nm} | {a[:4]}-{'2026' if b[:4] == '2100' else str(int(b[:4]) - 1)}"; RES["B_stress"][k] = ab(cv, a, b)
        g = RES["B_stress"][k]; print(f"STRESS {k:36s} bot {g['bot_pct_per_year']}% SPY {g['spy_pct_per_year']}% | beta {g['beta']} | own edge {g['alpha_pct_per_year']}%/yr (t {g['alpha_t_stat']})", flush=True)
rng = np.random.default_rng(7)
def mc_dd(cv, years=3, N=5000, B=21):
    r = cv[t0 + 1:] / cv[t0:-1] - 1; L = 252 * years; nb = -(-L // B); st = rng.integers(0, len(r) - B, (N, nb))
    p = np.stack([np.concatenate([r[s:s + B] for s in row])[:L] for row in st]); eq = np.cumprod(1 + p, axis=1)
    dd = (eq / np.maximum.accumulate(eq, axis=1) - 1).min(axis=1)
    return {f"p{q}": round(float(np.percentile(dd, 100 - q)) * 100, 1) for q in (50, 90, 95, 99)}
for nm, cv in (("live-like", cv_live), ("realistic", cv_real)):
    RES["B_stress"][f"3-year worst drop, resampled | {nm}"] = mc_dd(cv)
    print(f"STRESS 3-year worst drop ({nm}): {RES['B_stress'][f'3-year worst drop, resampled | {nm}']} | history {worst(cv)}%", flush=True)
k99 = -RES["B_stress"]["3-year worst drop, resampled | realistic"]["p99"]
RES["B_stress"]["kill_switch_suggestion_pct"] = int(np.ceil(k99 / 5) * 5)
print("kill switch (deeper than 99% of resampled 3-year paths, realistic fills):", RES["B_stress"]["kill_switch_suggestion_pct"], "%", flush=True)
# ---------------------------------------------------------------- C) blend
if hasattr(S, "DAILY") and not S.DRY: DLY = {k: np.nan_to_num(S.DAILY[k]) for k in ("SPY", "EFA", "IEF", "VNQ", "DBC")}
else: DLY = {"SPY": S.spyr, "EFA": np.nan_to_num(S.Er[:, S.EI["EFA"]]), "IEF": S.BOND_R, "VNQ": S.spyr * 0.8, "DBC": np.nan_to_num(S.Er[:, S.EI["EEM"]])}
mo = pd.PeriodIndex(pd.DatetimeIndex(dn), freq="M"); trend = np.zeros(D)
lvl = {k: np.cumprod(1 + v) for k, v in DLY.items()}
mend = {k: pd.Series(v, index=mo).groupby(level=0).last() for k, v in lvl.items()}
for t in range(t0, D):
    m = mo[t]; r = 0.0
    for k in DLY:
        s = mend[k]; prev = s[s.index < m]
        on = len(prev) >= 10 and prev.iloc[-1] > prev.iloc[-10:].mean()
        r += 0.2 * (DLY[k][t] if on else S.TBILL_R[t])
    trend[t] = r
tc = np.ones(D); tc[t0:] = np.cumprod(1 + trend[t0:])
def mret(cv): s = pd.Series(cv[t0 - 1:], index=pd.DatetimeIndex(dn[t0 - 1:])); return s.resample("ME").last().pct_change().dropna()
M_ = {"spy": mret(spyc), "dip": mret(cv_live), "trend": mret(tc)}; M_["dip_real"] = mret(cv_real)
def blend(w, dipkey="dip", roth=False):
    r = sum(w[k] * M_[k if k != "dip" else dipkey] for k in w); cv = (1 + r).cumprod()
    yrs = len(r) / 12; pre = cv.iloc[-1] ** (1 / yrs) - 1; dd = float((cv / cv.cummax() - 1).min())
    # rough after tax: each sleeve on its own; dip/trend taxed 24% on yearly gains (losses carried), SPY 15% once at the end
    at = 1.0
    for k, wk in w.items():
        if wk == 0: continue
        mr = M_[k if k != "dip" else dipkey]; yr = (1 + mr).groupby(mr.index.year).prod() - 1
        if k == "spy": g = float((1 + yr).prod()); sleeve = 1 + (g - 1) * 0.85
        else:
            rate = 0.0 if (roth and k == "dip") else 0.24; sleeve, carry = 1.0, 0.0
            for x in yr.values:
                gain = sleeve * x; net = gain + carry
                tax = rate * net if net > 0 else 0.0; carry = 0.0 if net > 0 else net
                sleeve = sleeve + gain - tax
        at += wk * (sleeve - 1)
    return {"before_tax": round(pre * 100, 1), "after_tax_rough": round((at ** (1 / yrs) - 1) * 100, 1), "worst_monthly_drop": round(dd * 100, 1),
            "worst_12m": round(float(((1 + r).rolling(12).apply(np.prod, raw=True) - 1).min()) * 100, 1)}
MIX = {"100% SPY": {"spy": 1}, "100% dip bot v3.0": {"dip": 1}, "100% trend sleeve": {"trend": 1},
       "50 SPY / 25 dip / 25 trend": {"spy": .5, "dip": .25, "trend": .25}, "34 / 33 / 33": {"spy": .34, "dip": .33, "trend": .33},
       "25 SPY / 50 dip / 25 trend": {"spy": .25, "dip": .5, "trend": .25}, "70 dip / 30 SPY": {"dip": .7, "spy": .3}, "50 dip / 50 trend": {"dip": .5, "trend": .5}}
for cn, dk in (("live-like", "dip"), ("realistic", "dip_real")):
    for nm, w in MIX.items():
        for roth in (False, True):
            if roth and "dip" not in w: continue
            k = f"{cn} | {nm}{' | dip sleeve in a Roth' if roth else ''}"; RES["C_blend"][k] = blend(w, dk, roth)
            g = RES["C_blend"][k]; print(f"BLEND {k:58s} before {g['before_tax']}% after~{g['after_tax_rough']}% | worst {g['worst_monthly_drop']}% worst 12m {g['worst_12m']}%", flush=True)
c = pd.concat(M_, axis=1).corr().round(2); RES["C_blend"]["monthly_correlation"] = c.to_dict(); print("CORR", c.to_dict(), flush=True)
json.dump({"note": __doc__, "built": str(pd.Timestamp.today().date()), "dry": S.DRY or None, **RES}, open(OUT, "w"), indent=1, default=float)
print("wrote", OUT, flush=True)
