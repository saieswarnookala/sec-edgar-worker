"""What to expect from the dip bot (Nov 18 2026). Research only, not financial advice.
Uses the daily equity curves of scripts/stack_and_rebound.py (point-in-time S&P 500, real Clear Leader parking, 1999-2026):
  today's Robinhood rules and Dip bot v3.0 (rules + ETF dips + bonds), realistic fills (next open, 0.15%/side) and ideal (close).
1) History: every 12-month window, losing years, longest time below a previous high, drawdown sizes.
2) Monte Carlo: 5,000 paths built from random 1-month blocks of the real daily returns (keeps bad streaks together),
   for 1 / 3 / 5 / 10 years: range of yearly returns, chance of losing money, chance of 20/30/40% drops.
3) Drawdown breaker: the drop seen in only 5% / 2% / 1% of 3-year paths -> where the live bot's halt line (MAX_DRAWDOWN, now 35%) should sit.
SPY buy & hold shown with the same method. DRY=1 uses the stack script's fake ETF data (code test)."""
import os, sys, json
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stack_and_rebound as S
OUT = "data/mc_expect.json" if not S.DRY else "/tmp/mc_expect_dry.json"
REAL = dict(fill="open", park="cl", cs=0.0015, ce=0.0005); IDEAL = dict(fill="close", park="cl")
CURVES = {"Robinhood rules, realistic": S.sim(**REAL)[0], "Dip bot v3.0, realistic": S.sim(etf=True, bond=True, **REAL)[0],
          "Robinhood rules, ideal": S.sim(**IDEAL)[0], "Dip bot v3.0, ideal": S.sim(etf=True, bond=True, **IDEAL)[0]}
spyc = np.ones(S.D); spyc[S.t0:] = S.SP[S.t0:] / S.SP[S.t0 - 1]; CURVES["SPY buy & hold"] = spyc
rng = np.random.default_rng(11); N, BLOCK = 5000, 21
def history(cv):
    c = pd.Series(cv[S.t0:], index=S.dates[S.t0:]); r = c.pct_change().dropna()
    roll = (c / c.shift(252) - 1).dropna()
    dd = c / c.cummax() - 1
    under, longest, start = 0, 0, None                    # longest stretch below a previous high (trading days)
    for v in dd.values:
        under = under + 1 if v < 0 else 0; longest = max(longest, under)
    yrs = c.resample("YE").last(); yr = yrs.pct_change(); yr.iloc[0] = yrs.iloc[0] / c.iloc[0] - 1
    epis, inn, low = [], False, 0                          # separate drawdown episodes deeper than 10%
    for v in dd.values:
        if v < -0.10 and not inn: inn, low = True, v
        elif inn: low = min(low, v)
        if inn and v == 0: epis.append(low); inn = False
    if inn: epis.append(low)
    return {"per_year_pct": round(((c.iloc[-1] / c.iloc[0]) ** (252 / len(r)) - 1) * 100, 1), "worst_drop_pct": round(float(dd.min()) * 100, 1),
            "12m_windows_pct": {f"p{q}": round(float(np.percentile(roll, q)) * 100, 1) for q in (5, 10, 25, 50, 75, 90)},
            "12m_windows_losing_pct": round(float((roll < 0).mean()) * 100, 1), "worst_12m_pct": round(float(roll.min()) * 100, 1), "best_12m_pct": round(float(roll.max()) * 100, 1),
            "calendar_years_losing": int((yr < 0).sum()), "calendar_years": int(len(yr)), "worst_calendar_year_pct": round(float(yr.min()) * 100, 1),
            "longest_below_high_months": round(longest / 21, 1), "drops_over_10pct": len(epis), "drops_over_20pct": int(sum(e < -0.20 for e in epis)),
            "years": {str(k.year): round(float(v) * 100, 1) for k, v in yr.items()}}
def monte(cv):
    r = (cv[S.t0 + 1:] / cv[S.t0:-1] - 1); n = len(r); out = {}
    for yrs in (1, 3, 5, 10):
        L = 252 * yrs; nb = -(-L // BLOCK); starts = rng.integers(0, n - BLOCK, (N, nb))
        paths = np.stack([np.concatenate([r[s:s + BLOCK] for s in row])[:L] for row in starts])
        eq = np.cumprod(1 + paths, axis=1); fin = eq[:, -1]; cagr = fin ** (1 / yrs) - 1
        mdd = (eq / np.maximum.accumulate(eq, axis=1) - 1).min(axis=1)
        out[f"{yrs}y"] = {"per_year_pct": {f"p{q}": round(float(np.percentile(cagr, q)) * 100, 1) for q in (5, 25, 50, 75, 95)},
                          "chance_losing_money_pct": round(float((fin < 1).mean()) * 100, 1),
                          "chance_beating_8pct_yr_pct": round(float((cagr > 0.08).mean()) * 100, 1),
                          "worst_drop_pct": {f"p{q}": round(float(np.percentile(mdd, q)) * 100, 1) for q in (50, 10, 5, 2, 1)},
                          "chance_drop_over_pct": {str(x): round(float((mdd < -x / 100).mean()) * 100, 1) for x in (15, 20, 30, 40)}}
    return out
RES = {}
for k, cv in CURVES.items():
    RES[k] = {"history": history(cv), "monte_carlo": monte(cv)}
    h, m = RES[k]["history"], RES[k]["monte_carlo"]
    print(f"{k:28s} {h['per_year_pct']}%/yr worst {h['worst_drop_pct']}% | 12m: p5 {h['12m_windows_pct']['p5']} p50 {h['12m_windows_pct']['p50']} losing {h['12m_windows_losing_pct']}% worst {h['worst_12m_pct']} | "
          f"losing yrs {h['calendar_years_losing']}/{h['calendar_years']} worst {h['worst_calendar_year_pct']} | longest below high {h['longest_below_high_months']} mo | "
          f"MC 1y lose {m['1y']['chance_losing_money_pct']}% 3y lose {m['3y']['chance_losing_money_pct']}% 3y dd p5 {m['3y']['worst_drop_pct']['p5']} p1 {m['3y']['worst_drop_pct']['p1']} | 10y p5/p50/p95 {m['10y']['per_year_pct']}", flush=True)
v3 = RES["Dip bot v3.0, realistic"]["monte_carlo"]["3y"]["worst_drop_pct"]; rh = RES["Robinhood rules, realistic"]["monte_carlo"]["3y"]["worst_drop_pct"]
BRK = {"note": "Halt line = deeper than the 3-year drop seen in 99% of simulated paths, so it only trips when something is really broken (not a normal slump).",
       "robinhood_rules_suggested_pct": int(np.ceil(-rh["p1"] / 5) * 5), "v3_suggested_pct": int(np.ceil(-v3["p1"] / 5) * 5), "current_live_pct": 35}
print("breaker:", json.dumps(BRK), flush=True)
json.dump({"note": __doc__, "built": str(pd.Timestamp.today().date()), "dry": S.DRY or None, "breaker": BRK, "results": RES}, open(OUT, "w"), indent=1, default=float)
print("wrote", OUT, flush=True)
