"""v3.0 tuning (Nov 19 2026): tuned dip settings judged out-of-sample, and a sector cap. Research only, not financial advice.
Engine = scripts/stack_and_rebound.py (point-in-time S&P 500, ETF dips, IEF bond parking, real Clear Leader daily parking).
Three cost settings: LIVE-LIKE (buy/sell at the close, 0.08%/side stocks - the Nov 18 minute replay showed the 3:45 bot trades at about
the close), IDEAL (close, 0.05%), REALISTIC (next open, 0.15%).
1) Walk-forward: a grid of dip size (8/9/10/12% worse than SPY), trend average (150/200 days) and max hold (3/5/7 days) on v3.0.
   Settings are PICKED on 1999-2012 only (live-like), then judged on 2013-2026, which the pick never saw. Today's 10%/200/5 shown too.
2) Sector cap: at most 2/3/4 of the 10 slots in one sector (SEC SIC codes grouped into 11 sectors; stocks without a SIC code are
   uncapped). Extra dips go to the next-best stock or an ETF dip.
DRY=1: fake ETF data (code test)."""
import os, sys, json, itertools
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stack_and_rebound as S
OUT = "data/v3_tuning.json" if not S.DRY else "/tmp/v3_tuning_dry.json"
LIVE = dict(fill="close", park="cl", cs=0.0008, ce=0.0003); IDEAL = dict(fill="close", park="cl"); REAL = dict(fill="open", park="cl", cs=0.0015, ce=0.0005)
V3 = dict(etf=True, bond=True)
dn = S.dn; t0 = S.t0
def per(cv, a, b):
    ix = np.flatnonzero((dn >= np.datetime64(a)) & (dn < np.datetime64(b)) & (np.arange(S.D) >= t0))
    c = cv[ix] / cv[max(ix[0] - 1, t0)]; return round((c[-1] ** (252 / len(ix)) - 1) * 100, 1), round(float((c / np.maximum.accumulate(c) - 1).min()) * 100, 1)
def summ(cv, tr):
    a = per(cv, "1999-01-01", "2100-01-01"); e = per(cv, "1999-01-01", "2013-01-01"); l = per(cv, "2013-01-01", "2100-01-01")
    return {"all": a[0], "worst": a[1], "1999-2012": e[0], "2013-2026": l[0], "2022": per(cv, "2022-01-01", "2023-01-01")[0],
            "trades_per_month": round(len(tr) / ((S.D - t0) / 21), 1), "avg_trade_pct": round(float(np.mean([x[2] for x in tr])) * 100, 2) if tr else None}
RES = {"grid": {}, "walk_forward": {}, "sector_cap": {}}
SIGS = {}
for dip, ma, mh in itertools.product((0.08, 0.09, 0.10, 0.12), (150, 200), (3, 5, 7)):
    key = f"dip {int(dip*100)}% | {ma}-day | hold {mh}"
    if (dip, ma) not in SIGS: SIGS[(dip, ma)] = S.make_sig(dip, ma)
    cv, tr = S.sim(**V3, **LIVE, sig=SIGS[(dip, ma)], mhs=mh)
    RES["grid"][key] = summ(cv, tr) | {"dip": dip, "ma": ma, "hold": mh}
    g = RES["grid"][key]; print(f"GRID {key:28s} live-like {g['all']}% worst {g['worst']} | 99-12 {g['1999-2012']} 13-26 {g['2013-2026']} 2022 {g['2022']} | {g['trades_per_month']}/mo", flush=True)
# walk-forward: best on 1999-2012, then look at 2013-2026
grid = RES["grid"]; base = "dip 10% | 200-day | hold 5"
ranked = sorted(grid, key=lambda k: -grid[k]["1999-2012"])
pick = ranked[0]
top5_late = [grid[k]["2013-2026"] for k in ranked[:5]]
RES["walk_forward"] = {"picked_on_1999_2012": pick, "picked_1999_2012": grid[pick]["1999-2012"], "picked_2013_2026": grid[pick]["2013-2026"],
                       "today_1999_2012": grid[base]["1999-2012"], "today_2013_2026": grid[base]["2013-2026"],
                       "top5_by_1999_2012_their_2013_2026": dict(zip(ranked[:5], top5_late)),
                       "rank_of_today_in_2013_2026": 1 + sorted(grid, key=lambda k: -grid[k]["2013-2026"]).index(base), "versions": len(grid),
                       "share_of_versions_beating_today_2013_2026_pct": round(100 * np.mean([grid[k]["2013-2026"] > grid[base]["2013-2026"] for k in grid]), 1)}
print("WALK-FORWARD", json.dumps(RES["walk_forward"]), flush=True)
# picked settings under all three cost settings
pdip, pma, pmh = grid[pick]["dip"], grid[pick]["ma"], grid[pick]["hold"]
for nm, cost in (("live-like", LIVE), ("ideal", IDEAL), ("realistic", REAL), ("2x live-like costs", dict(fill="close", park="cl", cs=0.0016, ce=0.0006))):
    for lab, sg, mh in (("today's settings", SIGS[(0.10, 200)], 5), (f"picked: {pick}", SIGS[(pdip, pma)], pmh), ("bot 6 settings (8%/150/7)", SIGS[(0.08, 150)], 7)):
        RES["walk_forward"][f"{nm} | {lab}"] = summ(*S.sim(**V3, **cost, sig=sg, mhs=mh))
        g = RES["walk_forward"][f"{nm} | {lab}"]; print(f"COST {nm:20s} {lab:40s} {g['all']}% worst {g['worst']} | 99-12 {g['1999-2012']} 13-26 {g['2013-2026']} | {g['trades_per_month']}/mo", flush=True)
# ---------------- sector cap
SEC = json.load(open("data/sec_events_sic.json"))["tickers"]
def sector(sic):
    if not sic: return None
    s2, s3, s4 = int(sic[:2]), int(sic[:3]), int(sic[:4])
    if s3 == 283 or s3 == 384 or s2 == 80 or s4 == 8731: return "health"
    if s2 in (13, 29, 46): return "energy"
    if s2 == 49: return "utilities"
    if s4 == 6798 or s2 == 65: return "real estate"
    if 60 <= s2 <= 67: return "financials"
    if s3 == 357 or s2 in (36, 38) or s2 == 73: return "tech"
    if s2 in (48, 27, 78): return "communication"
    if s2 in (20, 21) or s3 == 541: return "staples"
    if s2 in (22, 23, 25, 31, 39, 70, 79) or 52 <= s2 <= 59: return "discretionary"
    if s2 in (10, 12, 14, 24, 26, 28, 30, 32, 33): return "materials"
    return "industrials"
GRP = [sector((SEC.get(t) or {}).get("sic")) for t in S.tick]
print("stocks with a sector:", sum(g is not None for g in GRP), "of", len(GRP), flush=True)
for nm, cost in (("live-like", LIVE), ("realistic", REAL)):
    for cap in (None, 4, 3, 2):
        cv, tr = S.sim(**V3, **cost, grp=GRP, cap=cap)
        k = f"{nm} | {'no cap (v3.0 now)' if cap is None else f'max {cap} per sector'}"
        RES["sector_cap"][k] = summ(cv, tr)
        g = RES["sector_cap"][k]; print(f"CAP {k:36s} {g['all']}% worst {g['worst']} | 99-12 {g['1999-2012']} 13-26 {g['2013-2026']} 2022 {g['2022']} | {g['trades_per_month']}/mo avg {g['avg_trade_pct']}", flush=True)
# check: cap of 10 = no cap
assert summ(*S.sim(**V3, **LIVE, grp=GRP, cap=10)) == RES["sector_cap"]["live-like | no cap (v3.0 now)"], "cap 10 must equal no cap"
print("check ok: cap of 10 = no cap", flush=True)
json.dump({"note": __doc__, "built": str(pd.Timestamp.today().date()), "dry": S.DRY or None, **RES}, open(OUT, "w"), indent=1, default=float)
print("wrote", OUT, flush=True)
