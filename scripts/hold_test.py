"""How long to hold a dip (Nov 23 2026). Research only, not financial advice.
Question (Sai): if a dip stock has not bounced after 5 days, would waiting longer (until it climbs back above its 5-day average) earn more per year?
Today: sell when the close is above the 5-day average (from day 1), or after 5 trading days whatever the price (ETF dips: 10 days).
Tested: stock max hold 3 / 5 / 7 / 10 / 15 days and 40 days (= until it bounces; a cap so a delisted or flat stock cannot sit forever), for the previous live rules (v1) and v3.0,
live-like (buy at the 3:45 close) and realistic (next open, higher costs). Point-in-time S&P 500, 1999-2026.
Also per trade: win rate, average, average loser, and how the forced (max-hold) exits do. DRY=1: fake data (code test)."""
import os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stack_and_rebound as S
OUT = "data/hold_test.json" if not S.DRY else "/tmp/hold_test_dry.json"
LIVE = dict(fill="close", park="cl", cs=0.0008, ce=0.0003); REAL = dict(fill="open", park="cl", cs=0.0015, ce=0.0005)
BOTS = [("previous live (v1)", {}), ("v3.0 (live now)", dict(etf=True, bond=True))]
HOLDS = [3, 5, 7, 10, 15, 40]
def tstats(log, mh, off=0):   # off = 1 for next-open fills (the sim counts the buy day as day 1)
    r = np.array([x[5] for x in log if x[0] == "S"]); age = np.array([x[3] - x[2] + off for x in log if x[0] == "S"])
    if not len(r): return {}
    forced = age >= mh 
    f = lambda a: {"n": int(len(a)), "win_pct": round(float(np.mean(a > 0)) * 100, 1), "avg_pct": round(float(a.mean()) * 100, 2),
                   "avg_loser_pct": round(float(a[a < 0].mean()) * 100, 2) if (a < 0).any() else None, "worst_pct": round(float(a.min()) * 100, 1)} if len(a) else None
    return {"all": f(r), "bounced": f(r[~forced]), "forced_exit": f(r[forced]), "forced_share_pct": round(float(forced.mean()) * 100, 1),
            "avg_days_held": round(float(age.mean()), 1), "lost_10pct_plus_pct": round(float(np.mean(r < -0.10)) * 100, 1)}
RES = {}
for fname, fkw in (("live-like", LIVE), ("realistic", REAL)):
    for bot, bkw in BOTS:
        for mh in HOLDS:
            log = []; curve, trades = S.sim(mhs=mh, log=log, **fkw, **bkw)
            name = f"{bot} | {fname} | max hold {'40 (= until it bounces)' if mh == 40 else str(mh) + ' days'}"
            RES[name] = S.summ(curve, trades) | {"trades": tstats(log, mh, 1 if fkw["fill"] == "open" else 0)}
            a = RES[name]; full = next(iter(v for k, v in a.items() if isinstance(v, dict) and "per_year_pct" in v), {})
            t = a["trades"].get("all") or {}
            print(f"{name:58s} {full.get('per_year_pct')}%/yr worst {full.get('worst_drop_pct')}% | win {t.get('win_pct')}% avg {t.get('avg_pct')}% "
                  f"| forced {a['trades'].get('forced_share_pct')}% -> {(a['trades'].get('forced_exit') or {}).get('avg_pct')}% | days {a['trades'].get('avg_days_held')}", flush=True)
json.dump({"note": __doc__, "results": RES}, open(OUT, "w"), indent=1, default=float)
print("wrote", OUT)
