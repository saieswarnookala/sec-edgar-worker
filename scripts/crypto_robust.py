"""Bitcoin 10-month trend rule: robustness (Nov 20 2026). Research only, not financial advice.
Same data/costs as scripts/crypto_trend.py (Yahoo BTC-USD from Sep 2014, ETF route 0.10%/trade + 0.25%/yr, idle money in T-bills).
Checks: (1) average length 6-14 months; (2) check day in the month (1st/8th/15th/22nd/last); (3) trading 0/1/3/7/14 days late;
(4) start year 2015/2017/2019/2021; (5) daily versions 100-300 days; (6) PLACEBO: 2,000 random in/out monthly schedules with the same
share of months invested -> where the real rule ranks. DRY=1: fake prices."""
import os, sys, json
import numpy as np, pandas as pd
sys.argv = [sys.argv[0]]
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "crypto_trend.py")).read()
src = src[:src.index("RES = {}")]                                  # reuse data loading + run()/stats() only
g = {"__name__": "ct"}; exec(src, g)
BTC, cash_r, stats, DRY = g["BTC"], g["cash_r"], g["stats"], g["DRY"]
OUT = "data/crypto_robust.json" if not DRY else "/tmp/crypto_robust_dry.json"
COST, FEE = 0.001, 0.0025
r_all = BTC.pct_change().fillna(0); cr = cash_r.reindex(BTC.index).fillna(0)
def backtest(sig_on_check, delay=0):
    """sig_on_check: Series of 0/1 on check days -> held from (check day + 1 + delay)"""
    s = pd.Series(np.nan, index=BTC.index); s.loc[sig_on_check.index] = sig_on_check.values
    hold = s.ffill().fillna(0).shift(1 + delay).fillna(0)
    sw = hold.diff().abs().fillna(hold.iloc[0])
    cv = (1 + hold * (r_all - FEE / 365) + (1 - hold) * cr - sw * COST).cumprod()
    return cv, int(sw.sum()), float(hold.mean())
def checks(day):
    """check dates: the given day of each month (or the month's last day), using the close that day"""
    if day == "last": return BTC.resample("ME").last().index.intersection(BTC.index)
    return BTC.index[BTC.index.day == day]
def rule(n, day="last"):
    cd = checks(day); px = BTC.loc[cd]; return (px > px.rolling(n).mean()).astype(float)
def row(cv, n):
    a = stats(cv); b = stats(cv, "2015-01-01", "2020-01-01"); c = stats(cv, "2020-01-01"); d = stats(cv, "2022-01-01", "2023-01-01")
    yrs = (BTC.index[-1] - BTC.index[0]).days / 365.25
    return {"per_year": a["per_year_pct"], "worst": a["worst_drop_pct"], "2015-19": b["per_year_pct"], "2020-26": c["per_year_pct"], "2022": d["total_pct"], "trades_per_year": round(n / yrs, 1)}
RES = {"hold": row((1 + r_all - FEE / 365).cumprod(), 0)}
print("HOLD", RES["hold"], flush=True)
def show(k): print(f"{k:42s} {RES[k]}", flush=True)
for n in range(6, 15):
    k = f"length {n} months"; RES[k] = row(*backtest(rule(n))[:2]); show(k)
for d in (1, 8, 15, 22, "last"):
    k = f"check day {d}"; RES[k] = row(*backtest(rule(10, d))[:2]); show(k)
for dl in (0, 1, 3, 7, 14):
    k = f"trade {dl} days late"; RES[k] = row(*backtest(rule(10), dl)[:2]); show(k)
for n in (100, 150, 200, 250, 300):
    sig = (BTC > BTC.rolling(n).mean()).astype(float); k = f"daily {n}-day average"; RES[k] = row(*backtest(sig)[:2]); show(k)
cv10, n10, inv10 = backtest(rule(10))
for y in (2015, 2017, 2019, 2021, 2023):
    a = f"{y}-01-01"; h = (1 + r_all - FEE / 365).cumprod(); k = f"start {y}"
    RES[k] = {"rule_per_year": stats(cv10, a)["per_year_pct"], "rule_worst": stats(cv10, a)["worst_drop_pct"], "hold_per_year": stats(h, a)["per_year_pct"], "hold_worst": stats(h, a)["worst_drop_pct"]}; show(k)
# placebo: random monthly schedules with the same share of months in Bitcoin
rng = np.random.default_rng(5); cd = checks("last"); on = rule(10).dropna(); share = float(on.iloc[10:].mean()); real = stats(cv10)["per_year_pct"]; realw = stats(cv10)["worst_drop_pct"]
pl, plw = [], []
for _ in range(2000):
    sig = pd.Series((rng.random(len(cd)) < share).astype(float), index=cd); sig.iloc[:10] = 0
    cv, _, _ = backtest(sig); st = stats(cv); pl.append(st["per_year_pct"]); plw.append(st["worst_drop_pct"])
pl, plw = np.array(pl), np.array(plw)
RES["placebo"] = {"months_invested_share": round(share, 2), "real_rule_per_year": real, "placebo_median_per_year": round(float(np.median(pl)), 1), "placebo_p95_per_year": round(float(np.percentile(pl, 95)), 1),
                  "share_of_placebos_beating_rule_pct": round(float((pl >= real).mean()) * 100, 1), "real_worst": realw, "placebo_median_worst": round(float(np.median(plw)), 1),
                  "share_of_placebos_with_smaller_worst_drop_pct": round(float((plw >= realw).mean()) * 100, 1)}
print("PLACEBO", RES["placebo"], flush=True)
json.dump({"note": __doc__, "built": str(pd.Timestamp.today().date()), "dry": DRY or None, "results": RES}, open(OUT, "w"), indent=1, default=float)
print("wrote", OUT, flush=True)
