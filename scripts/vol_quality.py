"""Busy vs quiet dips, full simulations (Nov 24 2026; research only, not financial advice). v3.0 rules, point-in-time S&P 500 1999-2026.
Trade tags showed dips on quiet volume (5-day / prior 50-day volume < 1.05) averaged +0.85%/trade vs ~+0.1% for busy ones (1.4-2x), in both halves.
Here: skip busy dips (cut 1.4x / 1.6x; today 2x) or buy them at half size (> 1.4x / > 1.2x), or tilt (1.5x size quiet, 0.5x busy).
Freed slots / money go to ETF dips and parking as usual. The 5-minute replay (v3.2) runs the same rules in intraday_exits.py VOLTEST=1. DRY=1: fake ETF data."""
import os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stack_and_rebound as S
OUT = "data/vol_quality.json" if not S.DRY else "/tmp/vol_quality_dry.json"
LIVE = dict(fill="close", park="cl", cs=0.0008, ce=0.0003); REAL = dict(fill="open", park="cl", cs=0.0015, ce=0.0005); V3 = dict(etf=True, bond=True)
VR = np.nan_to_num(S.vr[S.tick].values, nan=9.0)
def sig(cut): return S.SIG & (VR <= cut)
def half(th): return np.where(VR > th, 0.5, 1.0)
VARS = [("today (skip > 2x)", {}), ("skip > 1.6x", dict(sig=sig(1.6))), ("skip > 1.4x", dict(sig=sig(1.4))), ("skip > 1.2x", dict(sig=sig(1.2))),
        ("half size > 1.4x", dict(wmul=half(1.4))), ("half size > 1.2x", dict(wmul=half(1.2))), ("tilt: 1.5x size < 1.05x, half size > 1.4x", dict(wmul=np.where(VR < 1.05, 1.5, np.where(VR > 1.4, 0.5, 1.0))))]
RES = {"note": __doc__, "results": {}}
for fname, fkw in (("live-like", LIVE), ("realistic", REAL)):
    for lbl, kw in VARS:
        c, tr = S.sim(**fkw, **V3, **kw); o = S.summ(c, tr); RES["results"][f"{fname} | {lbl}"] = o
        print(f"{fname} | {lbl:44s} " + " | ".join(f"{k[:9]} {v.get('per_year_pct')}/{v['worst_drop_pct']}" for k, v in o.items() if isinstance(v, dict) and k in ("1999-2026", "1999-2012", "2013-2026", "2018-2026 (short data)")), flush=True)
json.dump(RES, open(OUT, "w"), indent=1, default=float); print("wrote", OUT)
